"""AI 路由：LLM 配置、通用对话、文献解读/十问、综述、投稿建议、组会。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..services import llm as llm_service

router = APIRouter(prefix="/api", tags=["ai"])

MAX_CONTEXT = 60000  # 注入 LLM 的文本上限


def _require_llm(db: Session) -> None:
    if not llm_service.is_configured(db):
        raise HTTPException(400, "未配置 LLM。请在顶栏 ⚙️ 设置中配置 OpenAI 兼容 API 或 Ollama。")


def _safe_chat(db: Session, system: str, messages: list[dict], task: str = "", model: str = "") -> str:
    try:
        return llm_service.chat(db, system, messages, task=task, model=model)
    except llm_service.LLMNotConfigured as e:
        raise HTTPException(400, str(e)) from e
    except llm_service.LLMError as e:
        raise HTTPException(502, str(e)) from e


# ================ LLM 配置 ================
def _setting(db: Session, key: str) -> str:
    s = db.query(models.Setting).filter_by(key=key).first()
    return s.value if s else ""


@router.get("/settings/llm")
def get_llm_settings(db: Session = Depends(get_db)):
    api_key_raw = _setting(db, "llm_api_key")
    api_key = api_key_raw
    if _setting(db, "llm_api_key_encrypted") == "1" and api_key_raw:
        from ..services import crypto

        api_key = crypto.decrypt_text(api_key_raw)
    model = _setting(db, "llm_model")
    # 当前模型的元数据（上下文窗口 / 单价）
    from ..services import llm as llm_service

    llm_service.ensure_model_meta(db)
    meta = db.query(models.LlmModelMeta).filter_by(model=model).first()
    return {
        "provider": _setting(db, "llm_provider") or "openai",
        "base_url": _setting(db, "llm_base_url"),
        "api_key_set": bool(api_key),
        "api_key": api_key,  # 本地单机，解密返回明文便于编辑
        "model": model,
        "ollama_url": _setting(db, "llm_ollama_url") or "http://127.0.0.1:11434",
        "context_window": meta.context_window if meta else 0,
        "input_price_per_m": meta.input_price_per_m if meta else 0,
        "output_price_per_m": meta.output_price_per_m if meta else 0,
        "cache_price_per_m": meta.cache_price_per_m if meta else 0,
        "model_route": llm_service.get_model_route(db),
    }


@router.put("/settings/llm")
def update_llm_settings(body: dict, db: Session = Depends(get_db)):
    """保存 LLM 配置。同时接受前端短键（provider/base_url/...）与 llm_ 前缀键。"""
    # 前端表单键 → 存储键 映射（storage 键带 llm_ 前缀）
    key_map = {
        "llm_provider": "llm_provider", "provider": "llm_provider",
        "llm_base_url": "llm_base_url", "base_url": "llm_base_url",
        "llm_api_key": "llm_api_key", "api_key": "llm_api_key",
        "llm_model": "llm_model", "model": "llm_model",
        "llm_ollama_url": "llm_ollama_url", "ollama_url": "llm_ollama_url",
    }
    saved = []
    for front_key, storage_key in key_map.items():
        if front_key in body:
            value = str(body[front_key] or "")
            # API Key 加密入库（Fernet）
            if storage_key == "llm_api_key" and value:
                from ..services import crypto

                value = crypto.encrypt_text(value)
                flag = db.query(models.Setting).filter_by(key="llm_api_key_encrypted").first()
                if flag:
                    flag.value = "1"
                else:
                    db.add(models.Setting(key="llm_api_key_encrypted", value="1"))
            s = db.query(models.Setting).filter_by(key=storage_key).first()
            if s:
                s.value = value
            else:
                db.add(models.Setting(key=storage_key, value=value))
            saved.append(storage_key)
    # 模型元数据（上下文窗口 / 单价）存 llm_model_meta 表；空值/未填不覆盖
    if any(k in body for k in ("context_window", "input_price_per_m", "output_price_per_m", "cache_price_per_m")):
        from ..services import llm as llm_service

        model_name = str(body.get("model") or _setting(db, "llm_model")).strip()
        if model_name:
            llm_service.ensure_model_meta(db)
            meta = db.query(models.LlmModelMeta).filter_by(model=model_name).first()
            if meta is None:
                meta = models.LlmModelMeta(model=model_name)
                db.add(meta)
            for key, attr in (
                ("context_window", "context_window"),
                ("input_price_per_m", "input_price_per_m"),
                ("output_price_per_m", "output_price_per_m"),
                ("cache_price_per_m", "cache_price_per_m"),
            ):
                if key in body and body[key] not in (None, ""):
                    try:
                        setattr(meta, attr, float(body[key]) if "price" in key else int(body[key]))
                    except (ValueError, TypeError):
                        pass
            saved.append("model_meta")
    # 任务→模型 路由表
    if "model_route" in body and isinstance(body["model_route"], dict):
        from ..services import llm as llm_service

        llm_service.save_model_route(db, body["model_route"])
        saved.append("model_route")
    db.commit()
    return {"ok": True, "saved": saved}


# ================ LLM 用量 / 余额 / 模型元数据 ================
BALANCE_CACHE_MINUTES = 10


def _read_balance(db: Session, force: bool = False) -> dict:
    """余额读取：手动填写值优先；DeepSeek 自动获取并缓存 10 分钟。"""
    import json
    from datetime import datetime, timedelta

    from ..services import llm as llm_service

    now = datetime.now()
    manual = _setting(db, "llm_balance_manual")
    cache_raw = _setting(db, "llm_balance_cache")
    at_raw = _setting(db, "llm_balance_at")

    fresh = False
    if at_raw:
        try:
            fresh = (now - datetime.fromisoformat(at_raw)) < timedelta(minutes=BALANCE_CACHE_MINUTES)
        except ValueError:
            fresh = False

    if force or not fresh:
        result = llm_service.fetch_balance(db)
        s = db.query(models.Setting).filter_by(key="llm_balance_cache").first()
        if s:
            s.value = json.dumps(result, ensure_ascii=False)
        else:
            db.add(models.Setting(key="llm_balance_cache", value=json.dumps(result, ensure_ascii=False)))
        s2 = db.query(models.Setting).filter_by(key="llm_balance_at").first()
        if s2:
            s2.value = now.isoformat()
        else:
            db.add(models.Setting(key="llm_balance_at", value=now.isoformat()))
        db.commit()
    else:
        try:
            result = json.loads(cache_raw or "{}")
        except json.JSONDecodeError:
            result = {"is_available": False, "total_balance": 0.0, "currency": "CNY", "note": "余额缓存损坏"}

    if manual:
        try:
            result = {**result, "is_available": True, "total_balance": float(manual), "manual": True}
        except ValueError:
            pass
    result["fetched_at"] = _setting(db, "llm_balance_at")
    return result


@router.get("/llm/usage")
def llm_usage(db: Session = Depends(get_db)):
    """用量统计：今日/本月/累计 + 分模型明细。"""
    from ..services import llm as llm_service

    return llm_service.get_usage_summary(db)


@router.get("/llm/balance")
def llm_balance(db: Session = Depends(get_db)):
    return _read_balance(db)


@router.post("/llm/balance/refresh")
def llm_balance_refresh(db: Session = Depends(get_db)):
    return _read_balance(db, force=True)


@router.put("/llm/balance")
def llm_balance_set(body: dict, db: Session = Depends(get_db)):
    """手动填写余额（空字符串清除手动值，恢复自动查询）。"""
    manual = str(body.get("manual", "")).strip()
    s = db.query(models.Setting).filter_by(key="llm_balance_manual").first()
    if s:
        s.value = manual
    else:
        db.add(models.Setting(key="llm_balance_manual", value=manual))
    db.commit()
    return _read_balance(db, force=True)


@router.get("/llm/models")
def llm_models(db: Session = Depends(get_db)):
    """模型元数据列表（上下文窗口/单价，可编辑）。"""
    from ..services import llm as llm_service

    llm_service.ensure_model_meta(db)
    rows = db.query(models.LlmModelMeta).order_by(models.LlmModelMeta.model).all()
    return [{
        "model": r.model, "context_window": r.context_window,
        "input_price_per_m": r.input_price_per_m, "output_price_per_m": r.output_price_per_m,
        "cache_price_per_m": r.cache_price_per_m, "currency": r.currency,
    } for r in rows]


@router.post("/llm/chat")
def llm_chat(body: dict, db: Session = Depends(get_db)):
    """通用对话：{system?, messages: [{role, content}]}"""
    _require_llm(db)
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(400, "缺少消息")
    return {"reply": _safe_chat(db, body.get("system", ""), messages, task="chat")}


@router.post("/llm/test")
def llm_test(db: Session = Depends(get_db)):
    result = llm_service.test_connection(db)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result


@router.get("/llm/status")
def llm_status(db: Session = Depends(get_db)):
    """API 服务状态（读缓存，零外部请求）：在线状态 / 可用性百分比 / 最近探测统计。"""
    from ..services import llm as llm_service

    return llm_service.get_llm_status(db)


@router.post("/llm/status/refresh")
def llm_status_refresh(db: Session = Depends(get_db)):
    """立即探测一次 API 并记录历史统计。"""
    from ..services import llm as llm_service

    return llm_service.probe_and_record(db)


# ================ 文献 AI 解读 + 十问 ================
@router.post("/references/{rid}/ai-summary")
def ai_summary(rid: int, db: Session = Depends(get_db)):
    _require_llm(db)
    ref = db.get(models.Reference, rid)
    if not ref:
        raise HTTPException(404, "文献不存在")
    text = ""
    rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
    if rt:
        text = rt.text[:MAX_CONTEXT]
    if not text:
        # Reference 无 abstract 字段：摘要存在 ReferenceText.summary，无则退回标题
        text = ((rt.summary if rt else "") or ref.title)[:MAX_CONTEXT]

    system = "你是资深科研助手。基于给定论文内容，用中文输出结构化解读（Markdown）：## 核心贡献 / ## 方法 / ## 主要结果与结论 / ## 局限与不足 / ## 对我的启发。"
    result = _safe_chat(db, system, [{"role": "user", "content": f"论文标题：{ref.title}\n\n论文内容：\n{text}"}], task="summary")
    return {"summary": result}


@router.post("/references/{rid}/ai-ten-questions")
def ai_ten_questions(rid: int, db: Session = Depends(get_db)):
    _require_llm(db)
    ref = db.get(models.Reference, rid)
    if not ref:
        raise HTTPException(404, "文献不存在")
    rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
    text = (rt.text if rt and rt.text else ((rt.summary if rt else "") or ref.title))[:MAX_CONTEXT]

    system = "你是科研导师。基于论文内容，生成「论文十问」：10 个精读问题（为何做/做了什么/怎么做/结果如何/有何局限/与我的研究有何关联等），每问留出待答空间。用 Markdown 编号输出。"
    result = _safe_chat(db, system, [{"role": "user", "content": f"论文标题：{ref.title}\n\n论文内容：\n{text}"}], task="summary")
    return {"questions": result}


# ================ AI 对话式文献精读（持久化问答） ================
CHAT_HISTORY_WINDOW = 10      # 注入 LLM 的最近对话条数
CHAT_MSG_CAP = 2000           # 单条历史消息截断


def _reference_context(db: Session, rid: int) -> str:
    """文献上下文：标题 + 摘要 + 全文截断（供对话注入）。"""
    ref = db.get(models.Reference, rid)
    rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
    text = rt.text if rt and rt.text else ((rt.summary if rt else "") or ref.title)
    return f"论文标题：{ref.title}\n\n论文内容：\n{text[:MAX_CONTEXT]}"


@router.get("/references/{rid}/chat")
def list_chat(rid: int, db: Session = Depends(get_db)):
    """读取该文献的对话历史（按时间正序），重开阅读器时恢复。"""
    if not db.get(models.Reference, rid):
        raise HTTPException(404, "文献不存在")
    rows = db.query(models.ChatMessage).filter_by(reference_id=rid).order_by(models.ChatMessage.created_at).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in rows]


@router.post("/references/{rid}/chat")
def chat_reference(rid: int, body: dict, db: Session = Depends(get_db)):
    """对话式精读：注入全文上下文 + 最近 N 条历史，问答持久化。"""
    _require_llm(db)
    ref = db.get(models.Reference, rid)
    if not ref:
        raise HTTPException(404, "文献不存在")
    question = str(body.get("question", "")).strip()
    if not question:
        raise HTTPException(400, "请输入问题")
    context = _reference_context(db, rid)
    history = db.query(models.ChatMessage).filter_by(reference_id=rid) \
        .order_by(models.ChatMessage.created_at.desc()).limit(CHAT_HISTORY_WINDOW).all()
    messages = [{"role": m.role, "content": m.content[:CHAT_MSG_CAP]} for m in reversed(history)]
    messages.append({"role": "user", "content": question})
    system = (
        "你是科研文献精读助手。基于给定论文内容回答用户问题；若论文内容不足以回答，"
        "请明确说明并给出合理的推断方向。回答使用中文，必要时保留英文术语。"
        f"\n\n{context}"
    )
    reply = _safe_chat(db, system, messages, task="chat", model=str(body.get("model") or ""))
    db.add(models.ChatMessage(reference_id=rid, role="user", content=question[:8000]))
    db.add(models.ChatMessage(reference_id=rid, role="assistant", content=reply))
    db.commit()
    return {"reply": reply}


@router.delete("/references/{rid}/chat")
def clear_chat(rid: int, db: Session = Depends(get_db)):
    """清空该文献的对话历史。"""
    if not db.get(models.Reference, rid):
        raise HTTPException(404, "文献不存在")
    db.query(models.ChatMessage).filter_by(reference_id=rid).delete()
    db.commit()
    return {"ok": True}


# ================ AI 文献综述 + PDF 导出 ================
@router.post("/references/ai-review")
def ai_review(body: dict, db: Session = Depends(get_db)):
    _require_llm(db)
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "请选择文献")
    refs = []
    chunks = []
    for rid in ids[:15]:
        r = db.get(models.Reference, rid)
        if not r:
            continue
        refs.append(r)
        rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
        abstract = rt.summary if rt and rt.summary else "（无摘要）"
        chunks.append(f"[{len(refs)}] 标题：{r.title}\n作者：{'、'.join(r.authors[:3])}\n年份：{r.year}\n摘要：{abstract[:800]}")
    if not refs:
        raise HTTPException(400, "未找到有效文献")
    context = "\n\n".join(chunks)[:MAX_CONTEXT]

    system = "你是文献综述专家。基于给定文献列表，生成结构化中文综述（Markdown）：## 引言（研究背景与主题范围）/ ## 主题分组（按方法或主题分 2-4 组，每组对比文献观点与差异）/ ## 关键发现与共识 / ## 争议与开放问题 / ## 结论与展望 / ## 参考文献（用 [n] 对应文献列表）。"
    result = _safe_chat(db, system, [{"role": "user", "content": context}], task="summary")
    # 附上文献列表供引用核对
    ref_list = "\n".join(f"[{i + 1}] {r.title}（{r.year}）{('，' + r.venue) if r.venue else ''}" for i, r in enumerate(refs))
    return {"markdown": result + f"\n\n---\n\n## 文献列表\n{ref_list}"}


@router.post("/references/ai-review/export")
def ai_review_export(body: dict, db: Session = Depends(get_db)):
    """导出综述为 .md 文件。"""
    _require_llm(db)
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "请选择文献")
    refs = []
    chunks = []
    for rid in ids[:15]:
        r = db.get(models.Reference, rid)
        if not r:
            continue
        refs.append(r)
        rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
        abstract = rt.summary if rt and rt.summary else "（无摘要）"
        chunks.append(f"[{len(refs)}] 标题：{r.title}\n作者：{'、'.join(r.authors[:3])}\n年份：{r.year}\n摘要：{abstract[:800]}")
    context = "\n\n".join(chunks)[:MAX_CONTEXT]
    system = "你是文献综述专家。基于文献列表生成结构化中文综述（Markdown），含引言/主题分组/关键发现/争议/结论/参考文献。"
    result = _safe_chat(db, system, [{"role": "user", "content": context}], task="summary")
    ref_list = "\n".join(f"[{i + 1}] {r.title}（{r.year}）{('，' + r.venue) if r.venue else ''}" for i, r in enumerate(refs))
    content = f"# AI 文献综述\n\n{result}\n\n---\n\n## 文献列表\n{ref_list}\n"
    from urllib.parse import quote
    disposition = "attachment; filename*=UTF-8''" + quote("AI文献综述.md")
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": disposition})


# ================ 论文 AI 投稿建议 ================
@router.post("/papers/{pid}/ai-submit-review")
def ai_submit_review(pid: int, db: Session = Depends(get_db)):
    _require_llm(db)
    paper = db.get(models.Paper, pid)
    if not paper:
        raise HTTPException(404, "论文不存在")
    sections = db.query(models.PaperSection).filter_by(paper_id=pid).order_by(models.PaperSection.order_no).all()
    sec_text = "\n".join(f"- {s.title}（{s.status}）" + (f"：{s.content[:200]}" if s.content else "") for s in sections)
    context = (
        f"论文标题：{paper.title}\n类型：{paper.paper_type}　目标期刊：{paper.target_journal or '未定'}\n"
        f"关键词：{paper.keywords}\n摘要：{paper.abstract or '（未填写）'}\n\n章节进度：\n{sec_text or '（未设置章节）'}"
    )
    system = "你是期刊审稿专家（对标 Nature 审稿标准）。对给定论文进行投稿前审查，输出（Markdown）：## 摘要质量评估 / ## 结构完整度 / ## 方法严谨性提示 / ## 语言与表达建议 / ## 期刊匹配度与推荐 / ## 投稿前 Checklist（逐项 ✅/❌）。"
    result = _safe_chat(db, system, [{"role": "user", "content": context}], task="review")
    return {"review": result}


# ================ AI 写作润色助手 ================
POLISH_ACTIONS = {
    "polish": "学术润色：保持原意，改进表达、语法与学术规范性",
    "translate_zh": "翻译为中文（学术风格）",
    "translate_en": "翻译为英文（学术风格，术语地道）",
    "expand": "扩写：保持原意并补充细节与论证，篇幅约 1.5-2 倍",
    "condense": "缩写：提炼核心要点，篇幅约为原文一半",
    "deai": "去 AI 味：改写为更自然的人类学术写作风格，降低模板化痕迹",
}


@router.post("/ai/polish")
def ai_polish(body: dict, db: Session = Depends(get_db)):
    """AI 写作润色：学术润色 / 中英互译 / 扩写 / 缩写 / 降 AI 味。"""
    _require_llm(db)
    text = str(body.get("text", "")).strip()
    action = str(body.get("action", "polish"))
    if not text:
        raise HTTPException(400, "请输入需要处理的文本")
    if action not in POLISH_ACTIONS:
        raise HTTPException(400, f"不支持的动作：{action}")
    system = (
        f"你是学术写作助手。任务：{POLISH_ACTIONS[action]}。"
        "只输出处理后的结果文本，不要任何解释、前缀或引号。"
    )
    result = _safe_chat(db, system, [{"role": "user", "content": text[:20000]}], task="polish")
    return {"result": result, "action": action}


# ================ 组会记录（关联项目/文献 + AI 纪要/问答） ================
MEETING_TYPES = ["组会", "进展汇报", "文献汇报", "开题", "中期", "预答辩"]
MEETING_STATUSES = ["已安排", "已召开", "已归档"]


def _meeting_out(db: Session, m: models.GroupMeeting) -> dict:
    """组会序列化：含关联项目标题与文献信息。"""
    ref_rows = db.query(models.MeetingReference).filter_by(meeting_id=m.id).all()
    ref_ids = [r.reference_id for r in ref_rows]
    titles: dict[int, str] = {}
    if ref_ids:
        titles = {r.id: r.title for r in db.query(models.Reference).filter(models.Reference.id.in_(ref_ids)).all()}
    proj_title = ""
    if m.project_id:
        p = db.get(models.Project, m.project_id)
        proj_title = p.title if p else ""
    return {
        "id": m.id, "date": m.date.isoformat(), "topic": m.topic, "summary": m.summary,
        "qa_notes": m.qa_notes, "ppt_file_name": m.ppt_file_name,
        "project_id": m.project_id, "project_title": proj_title,
        "meeting_type": m.meeting_type, "status": m.status,
        "attendees": m.attendees, "duration_min": m.duration_min, "agenda": m.agenda,
        "reference_ids": ref_ids,
        "reference_titles": [titles.get(i, "") for i in ref_ids],
    }


def _apply_meeting_fields(m: models.GroupMeeting, body: dict) -> None:
    if body.get("date"):
        m.date = date.fromisoformat(str(body["date"]))
    if "topic" in body:
        m.topic = str(body["topic"])[:200]
    if "summary" in body:
        m.summary = str(body["summary"])
    if "qa_notes" in body:
        m.qa_notes = str(body["qa_notes"])
    if "project_id" in body:
        m.project_id = int(body["project_id"]) if body["project_id"] else None
    if "meeting_type" in body:
        m.meeting_type = str(body["meeting_type"])[:20]
    if "status" in body:
        m.status = str(body["status"])[:20]
    if "attendees" in body:
        m.attendees = str(body["attendees"])[:500]
    if "duration_min" in body:
        m.duration_min = int(body["duration_min"]) if body["duration_min"] else None
    if "agenda" in body:
        m.agenda = str(body["agenda"])


def _set_meeting_refs(db: Session, mid: int, ref_ids: list) -> None:
    db.query(models.MeetingReference).filter_by(meeting_id=mid).delete()
    for rid in (ref_ids or [])[:50]:
        if db.get(models.Reference, rid):
            db.add(models.MeetingReference(meeting_id=mid, reference_id=int(rid)))


def _meeting_ref_context(db: Session, m: models.GroupMeeting) -> str:
    """关联文献上下文（标题 + 摘要），供 AI 纪要/问答注入。"""
    refs = [db.get(models.Reference, r.reference_id)
            for r in db.query(models.MeetingReference).filter_by(meeting_id=m.id).all()]
    refs = [r for r in refs if r]
    if not refs:
        return ""
    chunks = []
    for i, r in enumerate(refs[:10], 1):
        rt = db.query(models.ReferenceText).filter_by(reference_id=r.id).first()
        abstract = rt.summary if rt and rt.summary else "（无摘要）"
        chunks.append(f"[{i}] 标题：{r.title}（{r.year or '未知年份'}，{r.venue or '未知期刊'}）\n摘要：{abstract[:500]}")
    return "\n\n".join(chunks)


@router.get("/group-meetings")
def list_meetings(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    """组会列表：可选按项目过滤。"""
    query = db.query(models.GroupMeeting)
    if project_id:
        query = query.filter(models.GroupMeeting.project_id == project_id)
    meetings = query.order_by(models.GroupMeeting.date.desc()).all()
    return [_meeting_out(db, m) for m in meetings]


@router.post("/group-meetings")
def create_meeting(body: dict, db: Session = Depends(get_db)):
    m = models.GroupMeeting(
        date=date.fromisoformat(str(body.get("date", date.today().isoformat()))),
        topic=str(body.get("topic", ""))[:200],
        summary=str(body.get("summary", "")),
        meeting_type=str(body.get("meeting_type", "组会"))[:20],
        status=str(body.get("status", "已安排"))[:20],
    )
    _apply_meeting_fields(m, body)
    db.add(m)
    db.commit()
    db.refresh(m)
    _set_meeting_refs(db, m.id, body.get("reference_ids") or [])
    db.commit()
    return _meeting_out(db, m)


@router.put("/group-meetings/{mid}")
def update_meeting(mid: int, body: dict, db: Session = Depends(get_db)):
    m = db.get(models.GroupMeeting, mid)
    if not m:
        raise HTTPException(404, "组会记录不存在")
    _apply_meeting_fields(m, body)
    if "reference_ids" in body:
        _set_meeting_refs(db, mid, body.get("reference_ids") or [])
    db.commit()
    return _meeting_out(db, m)


@router.get("/group-meetings/{mid}/references")
def get_meeting_refs(mid: int, db: Session = Depends(get_db)):
    m = db.get(models.GroupMeeting, mid)
    if not m:
        raise HTTPException(404, "组会记录不存在")
    return [r.reference_id for r in db.query(models.MeetingReference).filter_by(meeting_id=mid).all()]


@router.put("/group-meetings/{mid}/references")
def set_meeting_refs(mid: int, body: dict, db: Session = Depends(get_db)):
    """整组替换关联文献。"""
    m = db.get(models.GroupMeeting, mid)
    if not m:
        raise HTTPException(404, "组会记录不存在")
    _set_meeting_refs(db, mid, body.get("reference_ids") or [])
    db.commit()
    return {"ok": True}


@router.delete("/group-meetings/{mid}")
def delete_meeting(mid: int, db: Session = Depends(get_db)):
    m = db.get(models.GroupMeeting, mid)
    if not m:
        raise HTTPException(404, "组会记录不存在")
    if m.ppt_stored_path:
        from .materials import _delete_file
        _delete_file(m.ppt_stored_path)
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.post("/group-meetings/{mid}/ppt")
def upload_ppt(mid: int, file: UploadFile, db: Session = Depends(get_db)):
    m = db.get(models.GroupMeeting, mid)
    if not m:
        raise HTTPException(404, "组会记录不存在")
    from .materials import _delete_file
    from ..services import storage
    if m.ppt_stored_path:
        _delete_file(m.ppt_stored_path)
    data = file.read()
    rel, safe = storage.storage.save(data, file.filename or "slides.pptx")
    m.ppt_file_name = safe
    m.ppt_stored_path = rel
    db.commit()
    return {"ok": True, "ppt_file_name": safe}


@router.get("/group-meetings/{mid}/ppt")
def download_ppt(mid: int, db: Session = Depends(get_db)):
    m = db.get(models.GroupMeeting, mid)
    if not m or not m.ppt_stored_path:
        raise HTTPException(404, "暂无 PPT")
    from ..services import storage
    path = storage.storage.abs_path(m.ppt_stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    from urllib.parse import quote
    disposition = f"attachment; filename*=UTF-8''{quote(m.ppt_file_name or 'slides.pptx')}"
    return FileResponse(path, media_type="application/octet-stream", headers={"Content-Disposition": disposition})


@router.post("/group-meetings/{mid}/ai-notes")
def ai_meeting_notes(mid: int, db: Session = Depends(get_db)):
    """AI 问答式笔记：基于组会要点 + 关联文献生成问题与答案框架。"""
    _require_llm(db)
    m = db.get(models.GroupMeeting, mid)
    if not m:
        raise HTTPException(404, "组会记录不存在")
    if not m.summary:
        raise HTTPException(400, "请先填写组会要点")
    context = f"组会主题：{m.topic}\n会议类型：{m.meeting_type}\n\n要点记录：\n{m.summary[:MAX_CONTEXT]}"
    ref_ctx = _meeting_ref_context(db, m)
    if ref_ctx:
        context += f"\n\n本次组会关联文献：\n{ref_ctx}"
    system = (
        "你是科研组会记录助手。基于组会要点与关联文献，生成「问答式笔记」（Markdown）："
        "## 会议问答（5-8 个关键问题及简要答案；有关联文献时，问题应结合文献内容，"
        "如「这篇文献对当前项目有何启发」「文献方法与我们的工作有何异同」）/ "
        "## 待办事项提炼 / ## 下次组会建议。"
    )
    result = _safe_chat(db, system, [{"role": "user", "content": context}], task="summary")
    m.qa_notes = result
    db.commit()
    return {"qa_notes": result}


@router.post("/group-meetings/{mid}/ai-summary")
def ai_meeting_summary(mid: int, db: Session = Depends(get_db)):
    """AI 生成结构化会议纪要（结论/决议/待办），写入 summary 可编辑保存。"""
    _require_llm(db)
    m = db.get(models.GroupMeeting, mid)
    if not m:
        raise HTTPException(404, "组会记录不存在")
    base = (
        f"组会主题：{m.topic}\n会议类型：{m.meeting_type}\n议程：{m.agenda or '（未填写）'}\n"
        f"参会人：{m.attendees or '（未填写）'}\n时长：{str(m.duration_min) + ' 分钟' if m.duration_min else '（未记录）'}"
    )
    context = base
    if m.summary:
        context += f"\n\n要点记录：\n{m.summary[:MAX_CONTEXT]}"
    ref_ctx = _meeting_ref_context(db, m)
    if ref_ctx:
        context += f"\n\n本次组会关联文献：\n{ref_ctx}"
    system = (
        "你是科研组会纪要助手。基于给定信息生成结构化会议纪要（Markdown）："
        "## 会议概况（时间/类型/参会人/议程）/ ## 讨论要点（逐条归纳）"
        "/ ## 结论与决议 / ## 待办事项（谁负责、何时完成）/ ## 风险与遗留问题。"
    )
    result = _safe_chat(db, system, [{"role": "user", "content": context}], task="summary")
    m.summary = result
    db.commit()
    return {"summary": result}
