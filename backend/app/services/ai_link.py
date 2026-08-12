"""AI 自动关联：本地 TF-IDF 相似度召回候选 + LLM 深度语义评分。

流程：
1. 本地 TF-IDF（纯 Python，标题×2 + 摘要 + 关键词 + 全文片段）两两余弦相似度，
   按阈值召回候选对（上限 MAX_PAIRS），秒级完成、无需联网——只做「召回」，不做最终判断；
2. 候选对分批交给 LLM 深度评分：每篇文献注入标题/作者/期刊/年份 + 摘要/全文片段，
   由 LLM 基于论文内容判断关联强度（权重 + 理由 + 标签）；
3. 未配置 LLM / LLM 评分失败时降级为本地特征权重，但**必须通过 warnings 明确告知用户**，
   不再静默伪装成「AI 关联」。

结果持久化到 reference_ai_links 表，重新生成时整体覆盖。
"""
import json
import math
import re
from collections import Counter
from typing import Optional

from . import llm as llm_service
from .. import models
from ..database import SessionLocal

SIM_THRESHOLD = 0.12      # 候选对余弦相似度下限
MAX_PAIRS = 80            # 候选对总数上限
BATCH_SIZE = 20           # 每批交给 LLM 的文献对数（浅模式）
BATCH_SIZE_DEEP = 10      # 深度模式批次（内容更长，控 token）
LOCAL_CAP = 70            # 本地降级权重上限
DEEP_FULL_TEXT_CHARS = 1200  # 深度模式注入每篇的全文片段长度
RECALL_FULL_TEXT_CHARS = 2000  # 候选召回纳入词频的全文片段长度
EXTRACT_PDF_LIMIT = 30    # 评分前自动提取全文的篇数上限

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[a-z0-9]{2,}")


def _tokens(text: str) -> list[str]:
    """轻量分词：英文/数字单词 + 中文 2-gram（无第三方依赖）。"""
    t = (text or "").lower()
    tokens = _LATIN.findall(t)
    cjk = "".join(_CJK.findall(t))
    if len(cjk) >= 2:
        tokens += [cjk[i:i + 2] for i in range(len(cjk) - 1)]
    return tokens


def _build_docs(refs: list) -> list[tuple[int, Counter]]:
    """每条文献 → (id, 词频 Counter)，标题权重 ×2，含摘要/关键词/全文片段。"""
    docs: list[tuple[int, Counter]] = []
    for r in refs:
        title = r.title or ""
        summary = ""
        keywords = ""
        fulltext = ""
        if r.text:
            summary = r.text.summary or ""
            keywords = r.text.keywords or ""
            if r.text.text:
                fulltext = re.sub(r"\s+", " ", r.text.text)[:RECALL_FULL_TEXT_CHARS]
        counter = Counter(_tokens(f"{title} {title} {summary} {keywords} {fulltext}"))
        docs.append((r.id, counter))
    return docs


def _cosine(a: Counter, b: Counter, idf: dict[str, float]) -> float:
    """TF-IDF 加权余弦相似度（稀疏点积）。"""
    if not a or not b:
        return 0.0
    dot = 0.0
    na = nb = 0.0
    for token, count in a.items():
        w = count * idf.get(token, 1.0)
        na += w * w
        if token in b:
            dot += w * b[token] * idf.get(token, 1.0)
    for token, count in b.items():
        w = count * idf.get(token, 1.0)
        nb += w * w
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _structural_features(a, b) -> tuple[float, list[str]]:
    """结构化特征分（标签/作者/期刊/年份），与 network.similarity 同口径。

    文本余弦低的同主题文献（如共享标签）也能进入候选，保证任何文献库都能产生关联。
    """
    score = 0.0
    factors: list[str] = []
    a_tags = {t.strip().lower() for t in (a.tags or "").split(",") if t.strip()}
    b_tags = {t.strip().lower() for t in (b.tags or "").split(",") if t.strip()}
    shared_tags = a_tags & b_tags
    if shared_tags:
        score += 3.0 * len(shared_tags)
        factors.append("tags")
    a_authors = {x.strip().lower() for x in (a.authors or []) if x.strip()}
    b_authors = {x.strip().lower() for x in (b.authors or []) if x.strip()}
    if a_authors & b_authors:
        score += 2.0
        factors.append("authors")
    if a.venue and b.venue and a.venue.strip().lower() == b.venue.strip().lower():
        score += 1.0
        factors.append("venue")
    if a.year and b.year and abs(a.year - b.year) <= 1:
        score += 0.5
        factors.append("year")
    return score, factors


def _candidate_pairs(refs: list) -> list[dict]:
    """候选对生成：TF-IDF 文本余弦（≥阈值）∪ 结构化特征候选（共享标签/作者等）。

    文本相似度低的同主题文献也能进入候选，避免「0 候选无法关联」。
    """
    docs = _build_docs(refs)
    n = len(docs)
    if n < 2:
        return []
    df: Counter = Counter()
    for _, counter in docs:
        df.update(counter.keys())
    idf = {token: math.log(n / (1 + freq)) + 1 for token, freq in df.items()}

    pairs: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine(docs[i][1], docs[j][1], idf)
            if sim >= SIM_THRESHOLD:
                pairs.append({
                    "a": docs[i][0], "b": docs[j][0],
                    "sim": round(sim, 3), "struct_score": 0.0, "struct_factors": [],
                })

    # 结构化兜底：文本相似度不足但共享标签/作者/期刊/年份（特征分 ≥ 1.5）
    seen = {(p["a"], p["b"]) for p in pairs}
    for i in range(n):
        for j in range(i + 1, n):
            a_id, b_id = docs[i][0], docs[j][0]
            if (a_id, b_id) in seen:
                continue
            s, factors = _structural_features(refs[i], refs[j])
            if s >= 1.5:
                pairs.append({
                    "a": a_id, "b": b_id,
                    "sim": 0.0, "struct_score": s, "struct_factors": factors,
                })
                seen.add((a_id, b_id))
    pairs.sort(key=lambda p: p["sim"], reverse=True)
    return pairs[:MAX_PAIRS]


def _ref_map(refs: list) -> dict[int, object]:
    return {r.id: r for r in refs}


def _chunk_context(pair: dict, refs_by_id: dict[int, object], title_only: bool = False, deep: bool = True) -> str:
    a, b = refs_by_id.get(pair["a"]), refs_by_id.get(pair["b"])
    if not a or not b:
        return ""
    if title_only:
        return f"{pair['a']}: {a.title}\n{pair['b']}: {b.title}"

    def _desc(r) -> str:
        abstract = (r.text.summary if r.text and r.text.summary else "").strip()
        if deep and r.text and r.text.text:
            full = re.sub(r"\s+", " ", r.text.text).strip()
            if full:
                return (f"[{r.id}] 标题：{r.title}\n作者：{'、'.join((r.authors or [])[:3])}\n"
                        f"年份：{r.year or '未知'}\n期刊：{r.venue or '未知'}\n"
                        f"摘要：{abstract[:400]}\n全文片段：{full[:DEEP_FULL_TEXT_CHARS]}")
        if abstract:
            return (f"[{r.id}] 标题：{r.title}\n作者：{'、'.join((r.authors or [])[:3])}\n"
                    f"年份：{r.year or '未知'}\n期刊：{r.venue or '未知'}\n摘要：{abstract[:400]}")
        return (f"[{r.id}] 标题：{r.title}\n作者：{'、'.join((r.authors or [])[:3])}\n"
                f"年份：{r.year or '未知'}\n期刊：{r.venue or '未知'}\n摘要/全文：（无）")

    return f"### 文献 {pair['a']}\n{_desc(a)}\n\n### 文献 {pair['b']}\n{_desc(b)}"


def _parse_json_array(text: str) -> Optional[list[dict]]:
    """容错解析 LLM 返回的 JSON 数组（容忍 markdown 代码块与前后缀文本）。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    start, end = t.find("["), t.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(t[start:end + 1])
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


def _llm_score_batch(db, batch: list[dict], refs_by_id: dict[int, object], deep: bool = True) -> Optional[list[dict]]:
    """一批候选对交给 LLM 深度评分（基于摘要+全文内容）。

    调用失败 / 返回无法解析时返回 None，由调用方降级为本地近似**并记录 warning**。
    """
    lines = "\n\n".join(_chunk_context(p, refs_by_id, deep=deep) for p in batch)
    pairs = ", ".join(f'{{"a": {p["a"]}, "b": {p["b"]}}}' for p in batch)
    system = (
        "你是文献计量学专家。请基于每篇文献的标题、作者、期刊和**摘要/全文内容**，"
        "深入分析两篇论文在方法、数据、结论、理论上的真实关联（同一主题/方法/数据/结论互补/引用依赖等），"
        "而不是仅凭标签或领域关键词做表面对比。"
        "只输出一个 JSON 数组（不要任何其他文字），每个元素格式："
        '{"a": 文献ID, "b": 文献ID, "weight": 0到100的整数, "reason": "一句话中文理由（20字内，基于内容分析）", "tags": ["标签"]}。'
        "标签只能从以下选择：方法相似、结论互补、同领域、同技术路线、理论支撑、引用依赖。"
    )
    user = (
        f"请评估下面 {len(batch)} 对文献的关联强度，权重 0-100（0=无关，100=高度相关）。\n\n"
        f"{lines}\n\n输出 JSON 数组，元素按文献 ID 对应对应上面给出的 a/b 顺序。"
    )
    try:
        # 深度评分：单批 90s 超时，超时/网络失败降级并在上层记录 warning
        raw = llm_service.chat(db, system, [{"role": "user", "content": user}], max_tokens=4000, timeout=90, task="link")
    except Exception:
        return None
    data = _parse_json_array(raw)
    if data is None:
        return None
    results = []
    for item in data:
        if not isinstance(item, dict) or "a" not in item or "b" not in item:
            continue
        weight = int(item.get("weight") or 0)
        weight = max(0, min(100, weight))
        tags = [str(x) for x in (item.get("tags") or [])][:4]
        results.append({
            "a": int(item["a"]), "b": int(item["b"]),
            "weight": weight,
            "reason": str(item.get("reason") or "")[:200],
            "tags": tags,
            "method": "llm",
        })
    return results


def _extract_missing_texts(db, refs: list, max_papers: int = EXTRACT_PDF_LIMIT) -> int:
    """深度评分前：对有 PDF 附件但未提取文本的文献自动提取全文（供 LLM 内容分析）。

    返回实际提取篇数；单篇失败静默跳过，不中断主流程。
    """
    from . import pdfextract, storage as storage_service

    done = 0
    for r in refs:
        if done >= max_papers:
            break
        if not r.stored_path:
            continue
        if r.text and r.text.text:
            continue
        path = storage_service.storage.abs_path(r.stored_path)
        if not path.exists():
            continue
        try:
            text = pdfextract.extract_pdf_text(path)
            if not text:
                continue
            info = pdfextract.make_summary(text)
            rt = db.query(models.ReferenceText).filter_by(reference_id=r.id).first()
            if rt is None:
                rt = models.ReferenceText(reference_id=r.id)
                db.add(rt)
            rt.text = text
            if not rt.summary:
                rt.summary = info.get("summary", "")
            if not rt.keywords:
                rt.keywords = info.get("keywords", "")
            done += 1
        except Exception:
            continue
    if done:
        db.commit()
    return done


def run_auto_link(db, deep: bool = True) -> dict:
    """执行完整 AI 自动关联流程，整体覆盖旧结果。返回统计信息与 warnings（降级提示）。"""
    refs = db.query(models.Reference).all()
    if len(refs) < 2:
        return {"created": 0, "method": "local", "llm_calls": 0, "pairs": 0, "skipped": 0, "warnings": []}

    # 深度评分前自动提取缺全文的文献（保证 LLM 有论文内容可分析，而不只是标签/摘要）
    if deep:
        _extract_missing_texts(db, refs)

    pairs = _candidate_pairs(refs)
    refs_by_id = _ref_map(refs)
    llm_configured = llm_service.is_configured(db)
    warnings: list[str] = []

    scored: list[dict] = []
    llm_calls = 0
    failed_batches = 0
    batch_size = BATCH_SIZE_DEEP if deep else BATCH_SIZE
    if llm_configured:
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i + batch_size]
            llm_calls += 1
            results = _llm_score_batch(db, batch, refs_by_id, deep=deep)
            if results is not None:
                by_key = {(r["a"], r["b"]): r for r in results}
                for p in batch:
                    hit = by_key.get((p["a"], p["b"])) or by_key.get((p["b"], p["a"]))
                    scored.append(hit if hit else _local_score(p))
            else:
                failed_batches += 1
                scored += [_local_score(p) for p in batch]
        if failed_batches:
            warnings.append(f"LLM 评分失败 {failed_batches} 批（网络/API Key 问题），这批关联已降级为本地特征近似，请检查配置后重试")
    else:
        scored = [_local_score(p) for p in pairs]
        warnings.append("未配置 LLM：本次关联基于本地特征近似（标签/文本相似度）。配置 LLM API 后重新运行，可获得基于论文摘要/全文内容的深度语义关联")

    # 整体覆盖旧结果（过滤 LLM 判定为 0 的「无关」对，避免噪音）
    db.query(models.ReferenceAiLink).delete()
    kept = 0
    for s in scored:
        if s["weight"] <= 0:
            continue
        kept += 1
        a, b = sorted((s["a"], s["b"]))
        db.add(models.ReferenceAiLink(
            ref_a=a, ref_b=b, weight=s["weight"], reason=s["reason"],
            tags=s.get("tags") or [], method=s["method"],
        ))
    db.commit()

    return {
        "created": kept,
        "method": "llm" if (llm_configured and llm_calls > failed_batches) else "local",
        "llm_calls": llm_calls,
        "pairs": len(pairs),
        "struct_pairs": sum(1 for p in pairs if p.get("struct_factors")),
        "skipped": len(scored) - kept,
        "warnings": warnings,
    }


def _local_score(pair: dict) -> dict:
    """LLM 不可用时的本地降级评分（文本相似 / 结构化特征双口径）。

    reason 带「本地近似」前缀，与 LLM 深度评分结果明确区分。
    """
    text_weight = pair.get("sim", 0.0) * 80
    struct_weight = pair.get("struct_score", 0.0) * 12
    weight = min(LOCAL_CAP, round(max(text_weight, struct_weight)))
    if pair.get("struct_factors"):
        factor_names = {
            "tags": "共享标签", "authors": "共享作者", "venue": "同期刊/会议", "year": "年份相近",
        }
        reason = "本地近似：" + "、".join(factor_names.get(f, f) for f in pair["struct_factors"])
        tags = ["特征关联"]
    else:
        reason = f"本地近似：标题/摘要文本相似度 {pair['sim']:.2f}"
        tags = ["文本相似"]
    return {
        "a": pair["a"], "b": pair["b"],
        "weight": max(1, weight),
        "reason": reason,
        "tags": tags,
        "method": "local",
    }
