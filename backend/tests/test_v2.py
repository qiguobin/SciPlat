"""V2 功能测试：学生档案/待办/日程/阶段化/灵感/导师沟通/写作/成果/文献增强。"""
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402

client = TestClient(app)


def _project():
    r = client.post("/api/projects", json={"title": "测试项目"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- 学生档案 ----------------
def test_profile_crud():
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["name"] == ""

    r = client.put("/api/profile", json={
        "name": "张三", "student_id": "20240001", "school": "示例大学",
        "major": "计算机科学", "advisor": "李教授", "research_direction": "深度学习",
        "enrollment_year": 2024, "expected_graduation": 2028,
    })
    assert r.status_code == 200
    assert r.json()["name"] == "张三"
    assert r.json()["expected_graduation"] == 2028

    # 头像上传
    r = client.post("/api/profile/photo", files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\nfake", "image/png")})
    assert r.status_code == 200
    assert r.json()["photo_path"]
    r = client.get("/api/profile/photo")
    assert r.status_code == 200


# ---------------- 待办 ----------------
def test_todos_flow_and_activity():
    r = client.post("/api/todos", json={"date": "2026-08-10", "title": "完成实验方案", "priority": "高"})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    assert r.json()["completed_at"] is None

    # 状态流转：完成 → completed_at 有值
    r = client.patch(f"/api/todos/{tid}/status", json={"status": "已完成"})
    assert r.status_code == 200
    assert r.json()["completed_at"] is not None

    # 列表按日期查
    r = client.get("/api/todos", params={"date": "2026-08-10"})
    assert len(r.json()) == 1

    # 动态链
    r = client.get("/api/todos/activity")
    assert r.status_code == 200
    assert any(t["id"] == tid for t in r.json())

    # 非法状态
    r = client.patch(f"/api/todos/{tid}/status", json={"status": "不存在的状态"})
    assert r.status_code == 400

    assert client.delete(f"/api/todos/{tid}").status_code == 200


# ---------------- 项目阶段化 ----------------
def test_project_default_phases_and_links():
    p = _project()
    detail = client.get(f"/api/projects/{p['id']}").json()
    assert len(detail["phases"]) == 5  # 预置五阶段
    names = [ph["name"] for ph in detail["phases"]]
    assert names == ["开题设计", "初期想法验证", "实验阶段", "分析阶段", "总结与论文"]
    phid = detail["phases"][0]["id"]

    # 阶段状态流转
    r = client.put(f"/api/projects/phases/{phid}", json={"status": "进行中"})
    assert r.json()["status"] == "进行中"

    # 结构化实验记录
    r = client.post(f"/api/projects/phases/{phid}/experiments", json={
        "title": "预训练模型对比", "date": "2026-08-10",
        "purpose": "验证 baseline", "method": "训练 3 个模型",
        "result": "A 优于 B", "conclusion": "采用 A", "reflection": "数据量不足",
        "material_ids": "1,2",
    })
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    assert r.json()["reflection"] == "数据量不足"

    # 文献证据关联
    ref = client.post("/api/references", json={"title": "Transformer", "tags": "方法"}).json()
    r = client.post(f"/api/projects/phases/{phid}/references", json={"reference_id": ref["id"]})
    assert r.status_code == 200

    # 任务关联
    todo = client.post("/api/todos", json={"date": "2026-08-11", "title": "跑实验"}).json()
    r = client.post(f"/api/projects/phases/{phid}/tasks", json={"todo_id": todo["id"]})
    assert r.status_code == 200

    # 详情包含关联
    detail = client.get(f"/api/projects/{p['id']}").json()
    phase = detail["phases"][0]
    assert phase["reference_ids"] == [ref["id"]]
    assert phase["todo_ids"] == [todo["id"]]
    assert len(phase["experiments"]) == 1

    # 解除关联
    assert client.delete(f"/api/projects/phases/{phid}/references/{ref['id']}").status_code == 200
    assert client.delete(f"/api/projects/phases/{phid}/tasks/{todo['id']}").status_code == 200
    assert client.delete(f"/api/projects/phases/experiments/{eid}").status_code == 200
    assert client.delete(f"/api/projects/phases/{phid}").status_code == 200


# ---------------- 日程：周报 / 热力图 / 阶段总览 ----------------
def test_schedule_summary_report_heatmap():
    _project()
    client.post("/api/todos", json={"date": "2026-08-10", "title": "周报待办"})

    r = client.get("/api/schedule/summary", params={"period": "week"})
    assert r.status_code == 200
    assert r.json()["stats"]["todos_pending"] >= 1

    r = client.get("/api/schedule/report", params={"period": "month"})
    body = r.json()
    assert "科研进展汇报" in body["markdown"]
    assert body["label"]

    r = client.get("/api/schedule/heatmap")
    assert r.status_code == 200
    assert r.json()["year"] == 2026

    r = client.get("/api/schedule/phases")
    assert r.status_code == 200
    assert r.json()[0]["total"] == 5


# ---------------- 灵感 ----------------
def test_ideas_and_convert():
    idea = client.post("/api/ideas", json={"content": "试试对比学习", "tags": "idea"})
    assert idea.status_code == 200
    iid = idea.json()["id"]

    # 转为待办
    r = client.post(f"/api/ideas/{iid}/convert", json={"target": "todo", "date": "2026-08-15", "priority": "低"})
    assert r.status_code == 200
    assert r.json()["created"]["type"] == "todo"
    assert client.get("/api/ideas").json()[0]["status"] == "已转化"

    # 转为实验记录（需要 phase_id）
    p = _project()
    phase_id = client.get(f"/api/projects/{p['id']}").json()["phases"][0]["id"]
    idea2 = client.post("/api/ideas", json={"content": "换个学习率"})
    iid2 = idea2.json()["id"]
    r = client.post(f"/api/ideas/{iid2}/convert", json={"target": "experiment"})
    assert r.status_code == 400  # 缺 phase_id
    r = client.post(f"/api/ideas/{iid2}/convert", json={"target": "experiment", "phase_id": phase_id})
    assert r.status_code == 200
    assert r.json()["created"]["type"] == "experiment"


# ---------------- 导师沟通 ----------------
def test_meetings_and_action_convert():
    m = client.post("/api/advisor-meetings", json={
        "date": "2026-08-08", "topic": "中期讨论",
        "summary": "讨论了方法部分", "action_items": ["补充 baseline 对比", "调研相关综述"],
    })
    assert m.status_code == 200, m.text
    mid = m.json()["id"]
    assert len(m.json()["action_items"]) == 2

    r = client.post(f"/api/advisor-meetings/{mid}/actions/0/convert")
    assert r.status_code == 200
    assert r.json()["todo_id"]

    # 意见标记 ✓
    assert client.get("/api/advisor-meetings").json()[0]["action_items"][0].startswith("✓")

    assert client.delete(f"/api/advisor-meetings/{mid}").status_code == 200


# ---------------- 写作打卡 ----------------
def test_writing_logs():
    r = client.post("/api/writing-logs", json={"date": "2026-08-10", "word_count": 1200, "note": "方法部分"})
    assert r.status_code == 200, r.text
    wid = r.json()["id"]

    r = client.get("/api/writing-logs", params={"start": "2026-08-01", "end": "2026-09-01"})
    assert len(r.json()) == 1

    r = client.put(f"/api/writing-logs/{wid}", json={"word_count": 1500})
    assert r.json()["word_count"] == 1500
    assert client.delete(f"/api/writing-logs/{wid}").status_code == 200


# ---------------- 成果管理 ----------------
def test_achievements_and_paper_sync():
    # 独立成果
    r = client.post("/api/achievements", json={
        "atype": "专利", "title": "一种模型压缩方法", "status": "申请中",
        "identifier": "CN2026XXXX", "date": "2026-06-01",
    })
    assert r.status_code == 200, r.text
    aid = r.json()["id"]

    # 论文同步：状态为 Accepted/Published 自动出现
    client.post("/api/papers", json={"title": "同步论文", "status": "Published", "target_journal": "Nature"})
    client.post("/api/papers", json={"title": "未接收论文", "status": "Draft"})

    r = client.get("/api/achievements")
    body = r.json()
    synced = [a for a in body if a.get("synced")]
    assert len(synced) == 1
    assert synced[0]["title"] == "同步论文"

    r = client.get("/api/achievements/stats")
    assert r.json()["by_type"]["论文"] == 1
    assert r.json()["by_type"]["专利"] == 1

    # 类型校验
    r = client.post("/api/achievements", json={"atype": "不存在", "title": "x"})
    assert r.status_code == 400

    assert client.delete(f"/api/achievements/{aid}").status_code == 200


# ---------------- 文献增强 ----------------
def test_reference_v2_fields_and_fulltext_degrade():
    r = client.post("/api/references", json={
        "title": "增强文献", "category": "综述", "quartile": "Q1", "journal_if": "10.2",
    })
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert r.json()["category"] == "综述"

    # 全文检索：无 DOI/标题离线 → 404 或 502（降级）
    r = client.post(f"/api/references/{rid}/fetch-fulltext")
    assert r.status_code in (404, 502)

    # 在线阅读：无附件 → 404
    assert client.get(f"/api/references/{rid}/read").status_code == 404

    # 文本提取：无附件 → 400
    assert client.post(f"/api/references/{rid}/extract-text").status_code == 400
    assert client.get(f"/api/references/{rid}/text").status_code == 404

    # 上传 PDF 后可读
    r = client.post(f"/api/references/{rid}/attachment", files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 200
    assert r.json()["fulltext_source"] == ""  # 手动上传不标记 auto
    r = client.get(f"/api/references/{rid}/read")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")


# ---------------- 迁移验证 ----------------
def test_migration_columns_exist():
    db = SessionLocal()
    try:
        cols = {c.name for c in models.Reference.__table__.columns}
        assert {"category", "quartile", "journal_if", "fulltext_source"} <= cols
        exp_cols = {c.name for c in models.PhaseExperiment.__table__.columns}
        assert {"purpose", "method", "result", "conclusion", "reflection", "material_ids"} <= exp_cols
    finally:
        db.close()
