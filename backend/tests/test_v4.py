"""V4 功能测试：复盘/风险/模板复制/阶段建议/期刊库/投稿历程/意见转待办/周目标/队列/引用关联/RIS/批注/材料版本/成果附件/CV/CSV。"""
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _project():
    r = client.post("/api/projects", json={"title": "V4项目"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- 项目：复盘 / 风险 / 模板复制 / 阶段建议 ----------------
def test_project_review():
    p = _project()
    r = client.put(f"/api/projects/{p['id']}/review", json={
        "goal_achievement": "达成 80%", "difficulties": "数据不足", "lessons": "先验证可行性",
    })
    assert r.status_code == 200, r.text
    assert r.json()["goal_achievement"] == "达成 80%"
    r = client.get(f"/api/projects/{p['id']}/review")
    assert r.json()["lessons"] == "先验证可行性"


def test_project_risks():
    p = _project()
    r = client.post(f"/api/projects/{p['id']}/risks", json={"title": "GPU 不足", "severity": "高"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    r = client.put(f"/api/projects/risks/{rid}", json={"status": "处理中"})
    assert r.json()["status"] == "处理中"
    r = client.put(f"/api/projects/risks/{rid}", json={"status": "已解决", "resolution": "申请到资源"})
    assert r.json()["resolved_at"] is not None

    r = client.get(f"/api/projects/{p['id']}/risks")
    assert len(r.json()) == 1
    assert client.delete(f"/api/projects/risks/{rid}").status_code == 200


def test_copy_template():
    p = _project()
    detail = client.get(f"/api/projects/{p['id']}").json()
    assert len(detail["phases"]) == 5
    r = client.post(f"/api/projects/{p['id']}/copy-template")
    assert r.status_code == 200
    np_ = r.json()
    assert np_["title"].endswith("（副本）")
    nd = client.get(f"/api/projects/{np_['id']}").json()
    assert len(nd["phases"]) == 5
    assert all(not ph["is_default"] for ph in nd["phases"])


def test_phase_suggestions():
    p = _project()
    detail = client.get(f"/api/projects/{p['id']}").json()
    ph = detail["phases"][0]
    # 设为进行中 + 3 条实验 + 4/5 任务完成
    client.put(f"/api/projects/phases/{ph['id']}", json={"status": "进行中"})
    for i in range(3):
        client.post(f"/api/projects/phases/{ph['id']}/experiments", json={
            "title": f"实验{i}", "date": "2026-08-10",
        })
    tids = []
    for i in range(5):
        t = client.post("/api/todos", json={"date": "2026-08-10", "title": f"任务{i}"}).json()
        client.post(f"/api/projects/phases/{ph['id']}/tasks", json={"todo_id": t["id"]})
        tids.append(t["id"])
    for tid in tids[:4]:
        client.patch(f"/api/todos/{tid}/status", json={"status": "已完成"})

    r = client.get(f"/api/projects/{p['id']}/phase-suggestions")
    body = r.json()
    assert len(body["suggestions"]) == 1
    s = body["suggestions"][0]
    assert s["phase_name"] == "开题设计"
    assert s["experiments"] == 3
    assert s["task_rate"] == 80
    assert s["next_phase_name"] == "初期想法验证"


# ---------------- 论文：期刊库 / 投稿历程 / 意见转待办 / 周目标 ----------------
def test_journals_presets_and_crud():
    r = client.get("/api/papers/journals")
    assert r.status_code == 200
    assert len(r.json()) >= 15  # 预设初始化
    names = {j["name"] for j in r.json()}
    assert "NeurIPS" in names

    r = client.post("/api/papers/journals", json={"name": "自定义期刊", "quartile": "Q2"})
    assert r.status_code == 200
    jid = r.json()["id"]
    r = client.put(f"/api/papers/journals/{jid}", json={"impact_factor": "5.0"})
    assert r.json()["impact_factor"] == "5.0"
    assert client.delete(f"/api/papers/journals/{jid}").status_code == 200


def test_status_history_and_convert():
    p = client.post("/api/papers", json={"title": "历程论文"}).json()
    for to in ("Submitted", "Under Review"):
        client.post(f"/api/papers/{p['id']}/status", json={"to": to})
    r = client.get(f"/api/papers/{p['id']}/status-history")
    logs = r.json()
    assert len(logs) == 2
    assert logs[0]["from_status"] == "Draft" and logs[0]["to_status"] == "Submitted"

    # 审稿意见转待办
    rr = client.post(f"/api/papers/{p['id']}/review-rounds", data={"decision": "Major Revision", "summary": "补充实验对比"})
    rid = rr.json()["id"]
    r = client.post(f"/api/papers/review-rounds/{rid}/convert", json={"text": "补充实验对比"})
    assert r.status_code == 200
    assert r.json()["todo_id"]
    todos = client.get("/api/todos").json()
    assert any(t["title"] == "补充实验对比" for t in todos)


def test_writing_goal_and_streak():
    r = client.put("/api/settings/writing-goal", json={"goal": 5000})
    assert r.json()["goal"] == 5000
    assert client.get("/api/settings/writing-goal").json()["goal"] == 5000

    from datetime import date, timedelta
    today = date.today()
    for i in range(3):
        client.post("/api/writing-logs", json={"date": (today - timedelta(days=i)).isoformat(), "word_count": 100})
    r = client.get("/api/writing-logs/streak")
    assert r.json()["streak"] == 3


# ---------------- 文献：队列 / 引用关联 / RIS / 批注 ----------------
def test_reading_queue():
    r = client.post("/api/references", json={"title": "队列文献"})
    rid = r.json()["id"]
    r = client.patch(f"/api/references/{rid}/queue", json={"priority": 2, "date": "2026-08-15"})
    assert r.json()["queue_priority"] == 2
    q = client.get("/api/references/queue").json()
    assert any(x["id"] == rid for x in q)
    # 出队
    r = client.patch(f"/api/references/{rid}/queue", json={"priority": 0})
    assert r.json()["queue_priority"] == 0
    q = client.get("/api/references/queue").json()
    assert not any(x["id"] == rid for x in q)


def test_paper_reference_link():
    p = client.post("/api/papers", json={"title": "引用论文"}).json()
    r = client.post("/api/references", json={"title": "被引文献"})
    rid = r.json()["id"]
    r = client.post(f"/api/papers/{p['id']}/references", json={"reference_id": rid})
    assert r.status_code == 200
    refs = client.get(f"/api/papers/{p['id']}/references").json()
    assert len(refs) == 1 and refs[0]["title"] == "被引文献"
    assert client.delete(f"/api/papers/{p['id']}/references/{rid}").status_code == 200


def test_ris_import():
    ris = """TY  - JOUR
AU  - Kingma, Diederik P.
AU  - Ba, Jimmy
TI  - Adam: A Method for Stochastic Optimization
JO  - ICLR
PY  - 2015
DO  - 10.48550/arXiv.1412.6980
ER  - 
"""
    r = client.post("/api/references/import-ris", files={"file": ("refs.ris", ris.encode(), "text/plain")})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1
    refs = client.get("/api/references").json()
    assert refs[0]["authors"] == ["Kingma, Diederik P.", "Ba, Jimmy"]
    assert refs[0]["venue"] == "ICLR"
    # DOI 去重
    r = client.post("/api/references/import-ris", files={"file": ("refs.ris", ris.encode(), "text/plain")})
    assert r.json()["skipped"] == 1


def test_annotations_crud():
    r = client.post("/api/references", json={"title": "批注文献"})
    rid = r.json()["id"]
    r = client.post(f"/api/references/{rid}/annotations", json={"page": 1, "color": "#FDE047", "rect": "0.1,0.2,0.3,0.05"})
    assert r.status_code == 200, r.text
    aid = r.json()["id"]
    r = client.put(f"/api/references/annotations/{aid}", json={"note": "关键结论"})
    assert r.json()["note"] == "关键结论"
    anns = client.get(f"/api/references/{rid}/annotations").json()
    assert len(anns) == 1
    assert client.delete(f"/api/references/annotations/{aid}").status_code == 200


# ---------------- 系统：材料版本 / 成果附件 CV / CSV ----------------
def test_material_versions():
    p = _project()
    r = client.post("/api/materials", files=[("files", ("data.csv", b"v1,data", "text/csv"))],
                    data={"project_id": str(p["id"]), "category": "数据"})
    assert r.status_code == 200, r.text
    mid = r.json()[0]["id"]

    # 同名覆盖 → 版本
    r = client.post("/api/materials", files=[("files", ("data.csv", b"v2,data", "text/csv"))],
                    data={"project_id": str(p["id"]), "category": "数据"})
    assert len(r.json()) == 1
    versions = client.get(f"/api/materials/{mid}/versions").json()
    assert len(versions) == 1
    assert versions[0]["version_no"] == 1

    # 回滚
    r = client.post(f"/api/materials/{mid}/versions/{versions[0]['id']}/restore")
    assert r.status_code == 200
    m = client.get(f"/api/materials/{mid}") if False else r.json()
    assert m["file_name"] == "data.csv"
    assert client.delete(f"/api/materials/{mid}").status_code == 200


def test_achievement_attachment_and_cv():
    a = client.post("/api/achievements", json={"atype": "专利", "title": "CV专利", "status": "已授权"}).json()
    r = client.post(f"/api/achievements/{a['id']}/attachment", files={"file": ("cert.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 200
    assert r.json()["file_name"] == "cert.pdf"
    r = client.get(f"/api/achievements/{a['id']}/download")
    assert r.status_code == 200

    r = client.get("/api/achievements/cv-export")
    assert r.status_code == 200
    assert "CV专利" in r.text
    assert "科研成果列表" in r.text


def test_csv_export():
    client.post("/api/todos", json={"date": "2026-08-10", "title": "CSV待办"})
    r = client.get("/api/export/csv", params={"kind": "todos"})
    assert r.status_code == 200
    assert "CSV待办" in r.text
    assert r.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    assert client.get("/api/export/csv", params={"kind": "不存在的"}).status_code == 400


def test_auto_backup_list():
    r = client.get("/api/backup/auto-list")
    assert r.status_code == 200
    assert "interval_days" in r.json()
