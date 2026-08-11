"""V5 功能测试：实验步骤/模板/评论、集合/关联/保存视图、资源、画布、模板、批量、提及、燃尽图。"""
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _project_with_phase():
    p = client.post("/api/projects", json={"title": "V5项目"}).json()
    phid = client.get(f"/api/projects/{p['id']}").json()["phases"][0]["id"]
    return p, phid


def _experiment(phid):
    r = client.post(f"/api/projects/phases/{phid}/experiments", json={"title": "V5实验", "date": "2026-08-10"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- 实验步骤 ----------------
def test_experiment_steps():
    _, phid = _project_with_phase()
    exp = _experiment(phid)

    s1 = client.post(f"/api/experiments/{exp['id']}/steps", json={"title": "准备样本", "order_no": 0, "duration_min": 30})
    assert s1.status_code == 200, s1.text
    s2 = client.post(f"/api/experiments/{exp['id']}/steps", json={"title": "跑实验", "order_no": 1})
    assert s2.status_code == 200

    # 完成一个步骤
    r = client.put(f"/api/experiments/steps/{s1.json()['id']}", json={"status": "已完成"})
    assert r.json()["status"] == "已完成"

    # 进度
    r = client.get(f"/api/experiments/{exp['id']}/progress")
    assert r.json() == {"total": 2, "done": 1, "percent": 50}

    steps = client.get(f"/api/experiments/{exp['id']}/steps").json()
    assert len(steps) == 2
    assert client.delete(f"/api/experiments/steps/{s2.json()['id']}").status_code == 200


# ---------------- 实验模板库 ----------------
def test_experiment_templates():
    t = client.post("/api/experiment-templates", json={
        "title": "消融实验模板", "category": "实验",
        "body": {"purpose": "验证模块贡献", "method": "逐模块移除",
                 "steps": [{"title": "训练 baseline", "duration_min": 120}, {"title": "移除模块 A"}]},
    })
    assert t.status_code == 200, t.text
    tid = t.json()["id"]

    _, phid = _project_with_phase()
    r = client.post(f"/api/experiment-templates/{tid}/apply", json={"phase_id": phid, "title": "消融 1", "date": "2026-08-11"})
    assert r.status_code == 200
    eid = r.json()["id"]
    steps = client.get(f"/api/experiments/{eid}/steps").json()
    assert len(steps) == 2
    assert steps[0]["duration_min"] == 120

    assert client.delete(f"/api/experiment-templates/{tid}").status_code == 200


# ---------------- 实验评论 ----------------
def test_experiment_comments():
    _, phid = _project_with_phase()
    exp = _experiment(phid)
    c = client.post(f"/api/experiments/{exp['id']}/comments", json={"content": "注意对照组设置"})
    assert c.status_code == 200, c.text
    cid = c.json()["id"]
    comments = client.get(f"/api/experiments/{exp['id']}/comments").json()
    assert len(comments) == 1
    assert client.delete(f"/api/experiments/comments/{cid}").status_code == 200


# ---------------- 文献集合 ----------------
def test_collections():
    r = client.post("/api/collections", json={"name": "经典必读"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    # 重复拒绝
    assert client.post("/api/collections", json={"name": "经典必读"}).status_code == 400

    ref = client.post("/api/references", json={"title": "集合文献"}).json()
    r = client.post(f"/api/references/{ref['id']}/collections", json={"collection_id": cid, "linked": True})
    assert r.status_code == 200
    cols = client.get("/api/collections").json()
    assert cols[0]["count"] == 1
    # 移除
    client.post(f"/api/references/{ref['id']}/collections", json={"collection_id": cid, "linked": False})
    assert client.get("/api/collections").json()[0]["count"] == 0

    assert client.delete(f"/api/collections/{cid}").status_code == 200


# ---------------- 手动关联文献 ----------------
def test_related_references():
    a = client.post("/api/references", json={"title": "A文献"}).json()
    b = client.post("/api/references", json={"title": "B文献"}).json()
    r = client.post(f"/api/references/{a['id']}/related", json={"reference_id": b["id"]})
    assert r.status_code == 200
    # 自关联拒绝
    assert client.post(f"/api/references/{a['id']}/related", json={"reference_id": a["id"]}).status_code == 400
    assert client.delete(f"/api/references/{a['id']}/related/{b['id']}").status_code == 200


# ---------------- 保存的搜索视图 ----------------
def test_saved_views():
    r = client.post("/api/saved-views", json={"name": "Q1未读", "filters": {"quartile": "Q1", "read_status": "未读"}})
    assert r.status_code == 200, r.text
    views = client.get("/api/saved-views").json()
    assert len(views) == 1 and views[0]["filters"]["quartile"] == "Q1"
    assert client.delete(f"/api/saved-views/{views[0]['id']}").status_code == 200


# ---------------- 资源库存 ----------------
def test_resources():
    r = client.post("/api/resources", json={"name": "Trizol", "rtype": "试剂", "quantity": 10, "unit": "瓶", "low_threshold": 3})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    # 消耗
    r = client.post(f"/api/resources/{rid}/adjust", json={"delta": -8})
    assert r.json()["quantity"] == 2
    assert r.json()["status"] == "低库存"  # 低于阈值

    # 耗尽
    r = client.post(f"/api/resources/{rid}/adjust", json={"delta": -5})
    assert r.json()["quantity"] == 0
    assert r.json()["status"] == "已耗尽"

    # 补充
    r = client.post(f"/api/resources/{rid}/adjust", json={"delta": 10})
    assert r.json()["quantity"] == 10

    resources = client.get("/api/resources").json()
    assert len(resources) == 1
    assert client.delete(f"/api/resources/{rid}").status_code == 200


# ---------------- 科研画布 ----------------
def test_canvas():
    n1 = client.post("/api/canvas/nodes", json={"ntype": "project", "title": "画布项目", "ref_id": 1, "x": 10, "y": 20}).json()
    n2 = client.post("/api/canvas/nodes", json={"ntype": "text", "title": "想法", "x": 200, "y": 20}).json()

    e = client.post("/api/canvas/edges", json={"from_node": n1["id"], "to_node": n2["id"]})
    assert e.status_code == 200, e.text
    eid = e.json()["id"]

    canvas = client.get("/api/canvas").json()
    assert len(canvas["nodes"]) == 2 and len(canvas["edges"]) == 1

    # 移动节点
    r = client.put(f"/api/canvas/nodes/{n1['id']}", json={"x": 50, "y": 60})
    assert r.json()["x"] == 50

    # 删除节点级联删边
    assert client.delete(f"/api/canvas/nodes/{n1['id']}").status_code == 200
    canvas = client.get("/api/canvas").json()
    assert len(canvas["edges"]) == 0
    assert client.delete(f"/api/canvas/nodes/{n2['id']}").status_code == 200


# ---------------- 统一模板 ----------------
def test_templates():
    t = client.post("/api/templates", json={"ttype": "待办", "name": "每周组会", "content": {"title": "组会准备", "priority": "高"}})
    assert t.status_code == 200, t.text
    tid = t.json()["id"]
    templates = client.get("/api/templates").json()
    assert any(x["id"] == tid for x in templates)
    assert client.delete(f"/api/templates/{tid}").status_code == 200


# ---------------- 材料批量 ----------------
def test_material_batch():
    p = client.post("/api/projects", json={"title": "批量项目"}).json()
    r = client.post("/api/materials", files=[("files", ("a.csv", b"1", "text/csv")), ("files", ("b.csv", b"2", "text/csv"))],
                    data={"project_id": str(p["id"]), "category": "数据"})
    assert r.status_code == 200, r.text
    ids = [m["id"] for m in r.json()]
    assert len(ids) == 2

    r = client.post("/api/materials/batch", json={"ids": ids, "action": "category", "category": "图表"})
    assert r.json()["updated"] == 2
    r = client.post("/api/materials/batch", json={"ids": ids, "action": "tags", "tags": "批量"})
    assert r.json()["updated"] == 2
    mats = client.get("/api/materials").json()
    assert all(m["category"] == "图表" and "批量" in m["tags"] for m in mats)

    r = client.post("/api/materials/batch", json={"ids": ids, "action": "delete"})
    assert r.json()["deleted"] == 2
    assert client.get("/api/materials").json() == []


# ---------------- 未链接提及 ----------------
def test_note_mentions():
    ref = client.post("/api/references", json={"title": "提及目标文献"}).json()
    note = client.post("/api/notes", json={"target_type": "reference", "target_id": ref["id"], "content": "这篇论文引用了 提及目标文献 的方法，参见 [[已有链接]]"}).json()
    r = client.get("/api/notes/mentions", params={"note_id": note["id"]})
    assert r.status_code == 200
    titles = [m["title"] for m in r.json()["mentions"]]
    assert "提及目标文献" in titles
    assert "已有链接" not in titles  # 已链接的不算


# ---------------- 燃尽图 ----------------
def test_burndown():
    from datetime import date, timedelta
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    client.post("/api/todos", json={"date": monday.isoformat(), "title": "燃尽待办A"})
    client.post("/api/todos", json={"date": monday.isoformat(), "title": "燃尽待办B"})
    r = client.get("/api/schedule/burndown")
    assert r.status_code == 200
    body = r.json()
    assert len(body["days"]) == 7
    assert body["days"][0]["remaining"] == 2
    assert body["days"][0]["done"] == 0
