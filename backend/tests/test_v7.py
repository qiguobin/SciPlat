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
