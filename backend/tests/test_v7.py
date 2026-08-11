"""V7 测试：文献等级标签（JCR/中科院/新锐）、AI 自动关联、组会增强。"""
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _ref(title: str, doi: str = ""):
    r = client.post("/api/references", json={"title": title, "doi": doi, "year": 2024})
    assert r.status_code == 200, r.text
    return r.json()


def _add_text(ref_id: int, summary: str):
    with SessionLocal() as db:
        db.add(models.ReferenceText(reference_id=ref_id, text="", summary=summary, keywords=""))
        db.commit()


def test_reference_level_fields():
    """JCR/中科院/新锐分区可创建、修改、列表返回；reading_progress 在 Out 中。"""
    r = client.post("/api/references", json={
        "title": "Graph Neural Networks in Chemistry",
        "doi": "10.1000/xyz",
        "venue": "Nature Machine Intelligence",
        "jcr_quartile": "Q1",
        "cas_quartile": "1区",
        "xinrui_quartile": "1区",
        "journal_if": "23.8",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jcr_quartile"] == "Q1"
    assert body["cas_quartile"] == "1区"
    assert body["xinrui_quartile"] == "1区"
    assert body["reading_progress"] == 0
    rid = body["id"]

    r = client.put(f"/api/references/{rid}", json={"cas_quartile": "2区", "reading_progress": 40})
    assert r.status_code == 200, r.text
    assert r.json()["cas_quartile"] == "2区"

    r = client.get("/api/references")
    row = [x for x in r.json() if x["id"] == rid][0]
    assert row["jcr_quartile"] == "Q1"
    assert row["cas_quartile"] == "2区"
    assert "reading_progress" in row


def test_ai_auto_link_local_fallback():
    """AI 自动关联：未配置 LLM 时本地 TF-IDF 降级，生成可管理的 AI 边。"""
    a = _ref("Graph Neural Networks for Molecular Property Prediction")
    b = _ref("Molecular property prediction with graph neural networks")
    c = _ref("Quantum chemistry calculations for small molecules")
    _add_text(a["id"], "We propose a graph neural network framework for molecular property prediction, "
                       "comparing GNN architectures on quantum chemistry datasets.")
    _add_text(b["id"], "A benchmark study of graph neural network methods for molecular property prediction, "
                       "evaluating message passing and attention variants.")
    _add_text(c["id"], "We compute quantum chemistry properties of small molecules using DFT "
                       "and compare with experimental measurements.")

    r = client.post("/api/references/ai-auto-link")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "local"  # 测试环境未配置 LLM → 本地降级
    assert body["created"] >= 1

    r = client.get("/api/references/ai-links")
    links = r.json()
    assert len(links) >= 1
    assert links[0]["weight"] > 0
    assert links[0]["title_a"] and links[0]["title_b"]

    r = client.get("/api/references/network")
    net = r.json()
    ai_edges = [l for l in net["links"] if l.get("ai")]
    assert len(ai_edges) >= 1
    assert ai_edges[0]["reason"]

    # 单条删除 + 全清
    lid = links[0]["id"]
    assert client.delete(f"/api/references/ai-links/{lid}").status_code == 200
    assert client.delete("/api/references/ai-links").status_code == 200
    assert client.get("/api/references/ai-links").json() == []


def test_ai_auto_link_struct_candidates():
    """结构化兜底：仅共享标签、文本完全无关的文献也能生成关联。"""
    from unittest.mock import patch

    a = client.post("/api/references", json={"title": "量子计算绝热演化协议", "tags": "共同主题"}).json()
    b = client.post("/api/references", json={"title": "深海热液喷口微生物群落", "tags": "共同主题"}).json()
    # 无文本提取 → 文本余弦为 0，只能靠共享标签特征兜底
    with patch("app.services.llm.is_configured", return_value=False):
        r = client.post("/api/references/ai-auto-link")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    assert body["struct_pairs"] == 1

    links = client.get("/api/references/ai-links").json()
    assert len(links) == 1
    assert links[0]["reason"] == "共享标签"
    assert links[0]["weight"] > 0


def test_ai_auto_link_llm_failure_fallback():
    """LLM 批量评分抛异常时整批降级为本地权重，仍生成关联。"""
    from unittest.mock import patch

    a = client.post("/api/references", json={"title": "Fallback Alpha Study", "tags": "共同主题"}).json()
    b = client.post("/api/references", json={"title": "Fallback Beta Study", "tags": "共同主题"}).json()
    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.llm.chat", side_effect=Exception("LLM 网络错误")):
        r = client.post("/api/references/ai-auto-link")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] >= 1
    assert body["method"] == "llm"  # 入口判定基于配置，但降级链路保底
    links = client.get("/api/references/ai-links").json()
    assert len(links) >= 1
    assert links[0]["method"] == "local"  # 实际由本地特征评分兜底


def test_group_meeting_project_and_references():
    """组会：关联项目 + 文献、元信息字段、项目过滤、AI 接口降级提示。"""
    p = client.post("/api/projects", json={"title": "组会项目", "ptype": "学位课题", "status": "进行中"}).json()
    a = _ref("Group Meeting Reference One")
    b = _ref("Group Meeting Reference Two")

    r = client.post("/api/group-meetings", json={
        "date": "2026-08-10",
        "topic": "周组会",
        "meeting_type": "进展汇报",
        "status": "已召开",
        "project_id": p["id"],
        "attendees": "张三, 李四",
        "duration_min": 90,
        "agenda": "1. 论文进展\n2. 文献讨论",
        "summary": "讨论图神经网络方法",
        "reference_ids": [a["id"], b["id"]],
    })
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["project_id"] == p["id"]
    assert m["project_title"] == "组会项目"
    assert m["meeting_type"] == "进展汇报"
    assert m["status"] == "已召开"
    assert m["attendees"] == "张三, 李四"
    assert m["duration_min"] == 90
    assert m["reference_ids"] == [a["id"], b["id"]]
    assert len(m["reference_titles"]) == 2
    mid = m["id"]

    # 按项目过滤
    assert len(client.get("/api/group-meetings", params={"project_id": p["id"]}).json()) == 1
    assert len(client.get("/api/group-meetings").json()) == 1

    # 更新字段 + 整组替换关联文献
    r = client.put(f"/api/group-meetings/{mid}", json={"status": "已归档", "reference_ids": [b["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已归档"
    assert r.json()["reference_ids"] == [b["id"]]
    assert client.get(f"/api/group-meetings/{mid}/references").json() == [b["id"]]

    # 未配置 LLM → 400 引导配置
    assert client.post(f"/api/group-meetings/{mid}/ai-summary").status_code == 400
    assert client.post(f"/api/group-meetings/{mid}/ai-notes").status_code == 400

    # 删除后列表为空
    assert client.delete(f"/api/group-meetings/{mid}").status_code == 200
    assert client.get("/api/group-meetings").json() == []


def test_ai_metadata_merge_only_missing():
    """AI 自动匹配：LLM 推断只填空缺字段，已有值不覆盖；摘要/关键词写入 ReferenceText。"""
    from unittest.mock import patch

    r = client.post("/api/references", json={"title": "Merge Test Paper", "venue": "已有期刊"})
    assert r.status_code == 200
    rid = r.json()["id"]

    fake = {"venue": "LLM 推断期刊（不应覆盖）", "year": 2025, "keywords": "测试关键词", "cas_quartile": "2区"}
    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.metadata.infer_metadata_llm", return_value=fake), \
         patch("app.services.metadata.fetch_crossref", return_value={}):
        r = client.post(f"/api/references/{rid}/ai-metadata")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "venue" not in body["filled"]  # 已有值不覆盖
    assert "year" in body["filled"] and "cas_quartile" in body["filled"]
    assert body["source"] == "llm"

    ref = client.get(f"/api/references/{rid}").json()
    assert ref["venue"] == "已有期刊"
    assert ref["year"] == 2025
    assert ref["cas_quartile"] == "2区"
    with SessionLocal() as db:
        rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
        assert rt is not None and rt.keywords == "测试关键词"

    # 全部字段已补全 → 再跑无新字段 → 400
    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.metadata.infer_metadata_llm", return_value=fake), \
         patch("app.services.metadata.fetch_crossref", return_value={}):
        r = client.post(f"/api/references/{rid}/ai-metadata")
    assert r.status_code == 400


def test_ai_metadata_crossref_source():
    """有 DOI 时 CrossRef 补全基础字段，source=crossref。"""
    from unittest.mock import patch

    r = client.post("/api/references", json={"title": "Crossref Paper", "doi": "10.1234/test"})
    assert r.status_code == 200
    rid = r.json()["id"]

    cr = {"title": "", "authors": ["Alice"], "year": 2023, "venue": "Nature", "abstract": "crossref abstract"}
    with patch("app.services.metadata.fetch_crossref", return_value=cr), \
         patch("app.services.metadata.infer_metadata_llm", return_value={}):
        r = client.post(f"/api/references/{rid}/ai-metadata")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "crossref"
    assert "authors" in body["filled"] and "venue" in body["filled"] and "summary" in body["filled"]

    ref = client.get(f"/api/references/{rid}").json()
    assert ref["authors"] == ["Alice"]
    assert ref["venue"] == "Nature"


def test_ai_match_batch_incomplete_only():
    """批量补全：默认只处理信息不完整的文献，完整文献跳过。"""
    from unittest.mock import patch

    a = client.post("/api/references", json={"title": "Batch Incomplete One", "venue": "Journal A"}).json()
    b = client.post("/api/references", json={"title": "Batch Incomplete Two"}).json()
    c = client.post("/api/references", json={
        "title": "Complete One", "venue": "J B", "year": 2024, "doi": "10.1/x", "jcr_quartile": "Q1",
    }).json()

    fake = {"year": 2024, "venue": "Filled Venue"}
    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.metadata.infer_metadata_llm", return_value=fake), \
         patch("app.services.metadata.fetch_crossref", return_value={}):
        r = client.post("/api/references/ai-match", json={"limit": 10, "only_incomplete": True})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {res["id"] for res in body["results"]}
    assert a["id"] in ids and b["id"] in ids
    assert c["id"] not in ids  # 完整文献不处理
    assert body["filled_total"] >= 2


# ================ D 系列：对话精读 / AI 周报 / 润色 / 投稿看板 ================

def test_chat_persistent_history():
    """对话式精读：问答持久化、历史恢复、清空。"""
    from unittest.mock import patch

    r = client.post("/api/references", json={"title": "Chat Test Paper"})
    rid = r.json()["id"]
    _add_text(rid, "我们提出一种新的图神经网络方法。")

    # 未配置 LLM → 400
    r = client.post(f"/api/references/{rid}/chat", json={"question": "核心创新是什么？"})
    assert r.status_code == 400

    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.llm.chat", return_value="核心创新是图神经网络方法。"):
        r = client.post(f"/api/references/{rid}/chat", json={"question": "核心创新是什么？"})
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "核心创新是图神经网络方法。"

    # 历史已持久化：1 问 1 答
    r = client.get(f"/api/references/{rid}/chat")
    msgs = r.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"

    # 第二次提问带历史
    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.llm.chat", return_value="追问回答。"):
        r = client.post(f"/api/references/{rid}/chat", json={"question": "还有局限吗？"})
    assert r.status_code == 200
    assert len(client.get(f"/api/references/{rid}/chat").json()) == 4

    # 清空
    assert client.delete(f"/api/references/{rid}/chat").status_code == 200
    assert client.get(f"/api/references/{rid}/chat").json() == []


def test_report_ai_fallback():
    """AI 周报：未配置 LLM 时自动降级为模板，不报错。"""
    r = client.get("/api/schedule/report", params={"period": "week", "ai": True})
    assert r.status_code == 200
    body = r.json()
    assert body["ai"] is False
    assert "#" in body["markdown"]


def test_report_ai_with_llm():
    """AI 周报：配置 LLM 时返回 AI 生成内容。"""
    from unittest.mock import patch

    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.llm.chat", return_value="# AI 周报\n\n## 本周概况\n一切顺利。"):
        r = client.get("/api/schedule/report", params={"period": "week", "ai": True})
    assert r.status_code == 200
    body = r.json()
    assert body["ai"] is True
    assert body["markdown"].startswith("# AI 周报")


def test_ai_polish_actions():
    """AI 润色：未配置 LLM → 400；配置后返回结果。"""
    from unittest.mock import patch

    r = client.post("/api/ai/polish", json={"text": "我们需要验证这个方法的有效性。", "action": "polish"})
    assert r.status_code == 400

    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.llm.chat", return_value="我们需要验证该方法的有效性。"):
        r = client.post("/api/ai/polish", json={"text": "我们需要验证这个方法的有效性。", "action": "polish"})
    assert r.status_code == 200, r.text
    assert r.json()["result"]

    # 非法动作
    with patch("app.services.llm.is_configured", return_value=True):
        r = client.post("/api/ai/polish", json={"text": "x", "action": "unknown"})
    assert r.status_code == 400


def test_submission_board_and_review_deadline():
    """投稿看板：状态分组、审稿预期日推算、超时标记；stats 审稿超时提醒。"""
    from datetime import datetime, timedelta

    # 期刊 + 小论文 + 状态流转（Draft→Submitted→Under Review）
    client.post("/api/papers/journals", json={
        "name": "Test Review Journal", "quartile": "Q1", "impact_factor": "10.5",
        "review_weeks": 2, "notes": "测试",
    })
    p = client.post("/api/papers", json={
        "title": "Board Paper", "paper_type": "期刊", "paper_scale": "小论文",
        "target_journal": "Test Review Journal", "status": "Draft",
    }).json()
    pid = p["id"]
    assert client.post(f"/api/papers/{pid}/status", json={"to": "Submitted"}).status_code == 200
    assert client.post(f"/api/papers/{pid}/status", json={"to": "Under Review"}).status_code == 200
    # 把提交时间改成 30 天前，审稿开始 29 天前 → 预期结果日（+2 周）已过 → 超时
    from app.database import SessionLocal
    with SessionLocal() as db:
        logs = db.query(models.PaperStatusLog).filter_by(paper_id=pid).order_by(models.PaperStatusLog.id).all()
        logs[0].created_at = datetime.now() - timedelta(days=30)
        logs[1].created_at = datetime.now() - timedelta(days=29)
        db.commit()

    r = client.get("/api/papers/submission-board")
    assert r.status_code == 200
    board = r.json()
    assert board["overdue_count"] >= 1
    underway = next(g for g in board["groups"] if g["key"] == "underway")
    card = next(c for c in underway["cards"] if c["id"] == pid)
    assert card["target_journal"] == "Test Review Journal"
    assert card["journal_quartile"] == "Q1"
    assert card["expected_review_date"] is not None
    assert card["overdue"] is True
    assert card["days_left"] < 0

    # stats.deadlines 含 review 超时条目
    r = client.get("/api/stats")
    review_deadlines = [d for d in r.json()["deadlines"] if d["type"] == "review"]
    assert len(review_deadlines) >= 1
    assert review_deadlines[0]["days_left"] < 0


# ================ S 系列：健康检查 / 系统事件（状态栏） ================

def test_health_and_system_events():
    """健康检查字段齐全；错误事件写入/读取/计数/清空。"""
    from app import main as main_module

    # health
    r = client.get("/api/health")
    assert r.status_code == 200
    h = r.json()
    assert h["status"] == "ok"
    assert h["version"] == "0.4.0"
    assert h["db_path"].endswith("sci.db")
    assert "data_dir" in h and "db_size" in h
    assert "llm_configured" in h and "python" in h and "uptime_seconds" in h

    # 写入一条错误事件（直接调用中间件记录函数）
    main_module._log_system_event("error", "GET /api/test-500", "ValueError: boom")
    r = client.get("/api/system-events")
    assert r.status_code == 200
    events = r.json()
    assert len(events) >= 1
    assert events[0]["level"] == "error"
    assert "boom" in events[0]["message"]

    # health 错误计数联动
    h = client.get("/api/health").json()
    assert h["error_count"] >= 1

    # 清空
    assert client.post("/api/system-events/clear").status_code == 200
    assert client.get("/api/system-events").json() == []
    assert client.get("/api/health").json()["error_count"] == 0


# ================ U 系列：自动更新 ================

def test_compare_versions():
    from app.services import updater

    assert updater.compare_versions("0.4.0", "0.5.0") == 1
    assert updater.compare_versions("0.4.0", "0.4.0") == 0
    assert updater.compare_versions("0.5.0", "0.4.0") == -1
    assert updater.compare_versions("0.4.0", "0.4.1") == 1
    assert updater.compare_versions("0.9.9", "0.10.0") == 1
    assert updater.compare_versions("abc", "0.1.0") == 1  # 非法分段按 0 处理


def test_update_check_endpoint():
    from unittest.mock import patch

    from app.services import updater

    # 有新版（强制）
    with patch.object(updater, "fetch_latest", return_value=(
        {"version": "9.9.9", "url": "https://x/Setup.exe", "sha256": "abc", "notes": "新功能", "mandatory": True},
        "",
    )):
        r = client.get("/api/update/check")
    assert r.status_code == 200
    d = r.json()
    assert d["has_update"] is True
    assert d["latest_version"] == "9.9.9"
    assert d["mandatory"] is True
    assert d["notes"] == "新功能"
    assert d["download_url"] == "https://x/Setup.exe"

    # 相同版本 → 无更新
    with patch.object(updater, "fetch_latest", return_value=({"version": "0.4.0", "url": ""}, "")):
        assert client.get("/api/update/check").json()["has_update"] is False

    # 网络失败 → error 透出
    with patch.object(updater, "fetch_latest", return_value=(None, "更新源不可达：timeout")):
        d = client.get("/api/update/check").json()
        assert d["has_update"] is False
        assert "更新源不可达" in d["error"]


def test_update_settings_source():
    # 默认源
    assert "github.com" in client.get("/api/settings/update").json()["source_url"]
    # 保存自定义源
    r = client.put("/api/settings/update", json={"source_url": "http://127.0.0.1:9999/latest.json"})
    assert r.status_code == 200
    assert r.json()["source_url"] == "http://127.0.0.1:9999/latest.json"
    assert client.get("/api/settings/update").json()["source_url"] == "http://127.0.0.1:9999/latest.json"
    # 恢复默认
    client.put("/api/settings/update", json={"source_url": ""})
    assert "github.com" in client.get("/api/settings/update").json()["source_url"]


# ================ L 系列：LLM 用量 / 余额 / 上下文监控 ================

def _setup_llm_cfg():
    with SessionLocal() as db:
        db.add(models.Setting(key="llm_base_url", value="https://api.deepseek.com/v1"))
        db.add(models.Setting(key="llm_api_key", value="sk-test"))
        db.add(models.Setting(key="llm_model", value="deepseek-chat"))
        db.commit()


def test_llm_usage_record_and_summary():
    """chat 调用后 usage 落库（含缓存命中与费用折算）；聚合统计正确。"""
    from unittest.mock import patch

    from app.services import llm as llm_service

    _setup_llm_cfg()
    fake_resp = type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {
        "choices": [{"message": {"content": " 回复 "}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                  "prompt_cache_hit_tokens": 40},
    }})()

    with patch("app.services.llm.httpx.post", return_value=fake_resp):
        with SessionLocal() as db:
            reply = llm_service.chat(db, "sys", [{"role": "user", "content": "hi"}])
            assert reply == "回复"
            rows = db.query(models.LlmUsageLog).all()
            assert len(rows) == 1
            row = rows[0]
            assert row.model == "deepseek-chat"
            assert row.prompt_tokens == 100 and row.completion_tokens == 50
            assert row.cache_hit_tokens == 40
            # 费用：miss 60/1M×2 + hit 40/1M×0.5 + out 50/1M×8 = 0.00054
            assert abs(row.cost - 0.00054) < 1e-6
            summary = llm_service.get_usage_summary(db)
            assert summary["today"]["total_tokens"] == 150
            assert summary["today"]["calls"] == 1
            assert summary["by_model"][0]["model"] == "deepseek-chat"
            # health 扩展字段
            from app.main import app as fastapi_app
            from fastapi.testclient import TestClient

            h = TestClient(fastapi_app).get("/api/health").json()
            assert h["llm_context_window"] == 128000
            assert h["llm_usage_today"]["total_tokens"] == 150
            assert h["ai_tasks_running"] == 0


def test_llm_usage_ollama_branch():
    """Ollama 分支：prompt_eval_count/eval_count 落库。"""
    from unittest.mock import patch

    from app.services import llm as llm_service

    with SessionLocal() as db:
        db.add(models.Setting(key="llm_provider", value="ollama"))
        db.add(models.Setting(key="llm_model", value="qwen2.5"))
        db.commit()
    fake_resp = type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {
        "message": {"content": "本地回复"},
        "prompt_eval_count": 30,
        "eval_count": 12,
    }})()

    with patch("app.services.llm.httpx.post", return_value=fake_resp):
        with SessionLocal() as db:
            assert llm_service.chat(db, "", [{"role": "user", "content": "hi"}]) == "本地回复"
            row = db.query(models.LlmUsageLog).first()
            assert row.provider == "ollama" and row.prompt_tokens == 30 and row.completion_tokens == 12
            assert row.cost == 0.0  # 本地免费


def test_llm_balance_flow():
    """余额：DeepSeek 自动获取 + 10 分钟缓存 + 手动值优先。"""
    from unittest.mock import patch

    from app.routers.ai import _read_balance
    from app.services import llm as llm_service

    _setup_llm_cfg()
    fake = type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {
        "balance_infos": [{"total_balance": "12.34", "currency": "CNY"}],
    }})()

    with patch("app.services.llm.httpx.get", return_value=fake):
        with SessionLocal() as db:
            r = llm_service.fetch_balance(db)
            assert r["is_available"] and r["total_balance"] == 12.34
            # 首次 _read_balance：写入缓存
            r1 = _read_balance(db)
            assert r1["total_balance"] == 12.34
            # 缓存命中：不应再请求外部
            with patch("app.services.llm.httpx.get", side_effect=AssertionError("不应再请求")):
                r2 = _read_balance(db)
                assert r2["total_balance"] == 12.34

    # 手动余额优先
    with SessionLocal() as db:
        s = db.query(models.Setting).filter_by(key="llm_balance_manual").first()
        if s:
            s.value = "99.9"
        else:
            db.add(models.Setting(key="llm_balance_manual", value="99.9"))
        db.commit()
        r3 = _read_balance(db)
        assert r3["total_balance"] == 99.9 and r3.get("manual")

    # Ollama / 其他服务商说明
    with SessionLocal() as db:
        s = db.query(models.Setting).filter_by(key="llm_provider").first()
        if s:
            s.value = "ollama"
        else:
            db.add(models.Setting(key="llm_provider", value="ollama"))
        db.commit()
        r4 = llm_service.fetch_balance(db)
        assert r4["is_available"] is False and "本地" in r4["note"]


def test_ai_task_counter():
    """批任务计数器：进入 +1 退出 -1。"""
    from app.services import llm as llm_service

    assert llm_service.active_tasks() == 0
    with llm_service.ai_task():
        assert llm_service.active_tasks() == 1
        with llm_service.ai_task():
            assert llm_service.active_tasks() == 2
        assert llm_service.active_tasks() == 1
    assert llm_service.active_tasks() == 0


def test_llm_models_meta_endpoint():
    """模型元数据：预设种子 + 列表接口。"""
    r = client.get("/api/llm/models")
    assert r.status_code == 200
    names = {m["model"] for m in r.json()}
    assert "deepseek-chat" in names
    meta = next(m for m in r.json() if m["model"] == "deepseek-chat")
    assert meta["context_window"] == 128000 and meta["input_price_per_m"] == 2.0
    # 通过 settings 接口编辑元数据
    r = client.put("/api/settings/llm", json={"model": "deepseek-chat", "context_window": 65536, "input_price_per_m": 1.5})
    assert r.status_code == 200
    meta = next(m for m in client.get("/api/llm/models").json() if m["model"] == "deepseek-chat")
    assert meta["context_window"] == 65536 and meta["input_price_per_m"] == 1.5
