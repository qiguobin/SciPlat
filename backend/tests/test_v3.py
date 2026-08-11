"""V3 功能测试：引用格式/章节/报告/时间线/备份/精读/时长/重复合并/双链/待办重复。"""
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _ref(title="AlphaFold2", doi="", authors=None, tags=""):
    r = client.post("/api/references", json={
        "title": title, "doi": doi, "authors": authors or ["A. Author", "B. Author"],
        "year": 2021, "venue": "Nature", "tags": tags,
    })
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- 引用格式 ----------------
def test_citation_formats():
    r = _ref(doi="10.1038/nature")
    for fmt, marker in [("gbt7714", "[J]"), ("apa", "https://doi.org/"), ("ieee", '"')]:
        resp = client.post("/api/references/citations/format", json={"ids": [r["id"]], "format": fmt})
        assert resp.status_code == 200, resp.text
        assert marker in resp.json()["citations"][0]
    resp = client.post("/api/references/citations/format", json={"ids": [r["id"]], "format": "unknown"})
    assert resp.status_code == 400

    # >3 作者 GB/T 加"等"
    r2 = _ref(title="Many Authors", authors=["A", "B", "C", "D"])
    resp = client.post("/api/references/citations/format", json={"ids": [r2["id"]], "format": "gbt7714"})
    assert "等" in resp.json()["citations"][0]


# ---------------- 论文章节 ----------------
def test_paper_sections_and_written_words():
    p = client.post("/api/papers", json={"title": "章节论文"}).json()
    s = client.post(f"/api/papers/{p['id']}/sections", json={
        "title": "引言", "order_no": 1, "target_words": 1000, "status": "撰写中",
    })
    assert s.status_code == 200, s.text
    sid = s.json()["id"]

    client.post("/api/writing-logs", json={"date": "2026-08-10", "paper_id": p["id"], "section_id": sid, "word_count": 300})
    client.post("/api/writing-logs", json={"date": "2026-08-11", "paper_id": p["id"], "section_id": sid, "word_count": 500})

    detail = client.get(f"/api/papers/{p['id']}").json()
    assert detail["sections"][0]["written_words"] == 800
    assert detail["sections"][0]["title"] == "引言"

    assert client.delete(f"/api/papers/sections/{sid}").status_code == 200


# ---------------- 学期报告 / 组会材料 / 时间线 ----------------
def test_term_report_and_meeting_material():
    r = client.get("/api/schedule/term-report", params={"year": 2026, "semester": 2})
    assert r.status_code == 200
    assert "学期" in r.json()["label"]
    assert "科研总结报告" in r.json()["markdown"]

    r = client.get("/api/schedule/meeting-material")
    assert r.status_code == 200
    assert "组会材料" in r.json()["markdown"]


def test_timeline():
    p = client.post("/api/projects", json={"title": "时间线项目"}).json()
    client.post(f"/api/projects/{p['id']}/milestones", json={"title": "里程碑A", "due_date": "2026-09-01"})
    client.post("/api/todos", json={"date": "2026-09-15", "title": "待办A"})
    client.post("/api/papers", json={"title": "截稿论文", "submission_deadline": "2026-10-01"})
    # 给第一个阶段设开始日期，使其进入时间线
    phid = client.get(f"/api/projects/{p['id']}").json()["phases"][0]["id"]
    client.put(f"/api/projects/phases/{phid}", json={"start_date": "2026-08-20", "status": "进行中"})

    r = client.get("/api/schedule/timeline", params={"start": "2026-08-01", "end": "2026-12-31"})
    body = r.json()
    types = {e["type"] for e in body["events"]}
    assert "milestone" in types and "todo" in types and "deadline" in types and "phase" in types
    dates = [e["date"] for e in body["events"]]
    assert dates == sorted(dates)

    # 类型筛选
    r = client.get("/api/schedule/timeline", params={"kinds": "milestone,todo"})
    assert all(e["type"] in ("milestone", "todo") for e in r.json()["events"])


# ---------------- 备份与恢复 ----------------
def test_backup_roundtrip():
    _ref(title="备份文献")
    r = client.get("/api/backup/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    zip_data = r.content
    assert zip_data.startswith(b"PK")

    r = client.post("/api/backup/restore", files={"file": ("backup.zip", zip_data, "application/zip")})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    # 恢复后数据仍在（同库）
    assert client.get("/api/references").json()


# ---------------- 精读 / 进度 / 阅读时长 ----------------
def test_deep_reading_progress_and_sessions():
    r = _ref(title="精读文献")
    rid = r["id"]

    resp = client.put(f"/api/references/{rid}/deep-reading", json={
        "question": "如何预测结构？", "method": "Transformer", "conclusion": "有效", "insight": "可用于我的方法",
    })
    assert resp.status_code == 200
    assert resp.json()["question"] == "如何预测结构？"

    resp = client.get(f"/api/references/{rid}/deep-reading")
    assert resp.json()["insight"] == "可用于我的方法"

    resp = client.patch(f"/api/references/{rid}/progress", json={"progress": 50})
    assert resp.json()["read_status"] == "在读"
    resp = client.patch(f"/api/references/{rid}/progress", json={"progress": 100})
    assert resp.json()["read_status"] == "已读"

    client.post(f"/api/references/{rid}/reading-session", json={"seconds": 120})
    client.post(f"/api/references/{rid}/reading-session", json={"seconds": 3})  # 太短忽略
    stats = client.get("/api/references/reading-stats").json()
    assert stats["minutes"][str(rid)] == 2


# ---------------- 重复检测与合并 ----------------
def test_duplicates_and_merge():
    a = _ref(title="Duplicate Paper", doi="10.1000/dup")
    b = _ref(title="Duplicate Paper", doi="10.1000/dup2")
    note = client.post("/api/notes", json={"target_type": "reference", "target_id": a["id"], "content": "重要笔记"})

    resp = client.get("/api/references/duplicates")
    groups = resp.json()
    assert any(a["id"] in g["ids"] and b["id"] in g["ids"] for g in groups)

    resp = client.post(f"/api/references/{b['id']}/merge", json={"target_id": a["id"]})
    assert resp.status_code == 200, resp.text

    # 笔记重定向到目标
    notes = client.get("/api/notes", params={"target_type": "reference", "target_id": a["id"]}).json()
    assert any(n["content"] == "重要笔记" for n in notes)
    # 被合并项软标记
    merged = client.get(f"/api/references/{b['id']}").json()
    assert merged["title"].startswith("[已合并]")


# ---------------- 双链笔记 ----------------
def test_backlinks_and_graph():
    r = _ref(title="双链目标")
    client.post("/api/notes", json={"target_type": "reference", "target_id": r["id"], "content": "参见 [[双链目标]] 的方法"})
    client.post("/api/notes", json={"target_type": "reference", "target_id": r["id"], "content": "普通笔记"})

    resp = client.get("/api/notes/backlinks", params={"target": "双链目标"})
    assert len(resp.json()) == 1

    resp = client.get("/api/notes/graph")
    body = resp.json()
    assert any(n["kind"] == "reference" for n in body["nodes"])
    assert len(body["links"]) >= 1


# ---------------- 待办重复与完成率 ----------------
def test_todo_repeat_and_stats():
    p = client.post("/api/projects", json={"title": "统计项目"}).json()
    t = client.post("/api/todos", json={
        "date": "2026-08-10", "title": "每周组会准备", "repeat": "weekly", "project_id": p["id"],
    }).json()
    client.patch(f"/api/todos/{t['id']}/status", json={"status": "已完成"})

    # 自动生成下周实例
    resp = client.get("/api/todos", params={"date": "2026-08-17"})
    assert any(x["title"] == "每周组会准备" for x in resp.json())

    stats = client.get("/api/todos/stats", params={"project_id": p["id"]}).json()
    assert stats["total"] >= 2
    assert stats["done"] >= 1
    assert stats["rate"] > 0

    # 非法重复规则
    resp = client.post("/api/todos", json={"date": "2026-08-10", "title": "x", "repeat": "yearly"})
    assert resp.status_code == 400
