"""冒烟测试：核心 API 全流程（数据目录由 conftest.py 统一设置）。"""
from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()  # TestClient 未进入 with 上下文时 lifespan 不触发，需显式建表
client = TestClient(app)


def _project(title="测试课题"):
    r = client.post("/api/projects", json={"title": title, "ptype": "学位课题", "status": "进行中"})
    assert r.status_code == 200, r.text
    return r.json()


def test_stats_and_ai_capabilities():
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert "projects" in body and "deadlines" in body and "recent" in body

    r = client.get("/api/ai/capabilities")
    assert r.status_code == 200
    assert r.json()["platform"] == "sci-plat"


def test_project_crud_milestone_timeline():
    p = _project()
    pid = p["id"]

    # 里程碑
    r = client.post(f"/api/projects/{pid}/milestones", json={"title": "开题报告", "due_date": "2026-12-01"})
    assert r.status_code == 200, r.text
    mid = r.json()["id"]

    # 时间线
    r = client.post(f"/api/projects/{pid}/timeline", json={"title": "中期检查", "point_date": "2027-06-01"})
    assert r.status_code == 200

    # 详情
    r = client.get(f"/api/projects/{pid}")
    body = r.json()
    assert len(body["milestones"]) == 1
    assert len(body["timeline_points"]) == 1

    # 更新项目
    r = client.put(f"/api/projects/{pid}", json={"status": "暂停"})
    assert r.json()["status"] == "暂停"

    # 导出 zip
    r = client.get(f"/api/projects/{pid}/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    # 清理
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_paper_status_flow_and_versions():
    p = _project()
    r = client.post("/api/papers", json={
        "title": "Deep Learning Survey", "project_id": p["id"],
        "paper_type": "期刊", "target_journal": "Nature", "keywords": "DL, survey",
        "submission_deadline": "2099-01-01",
    })
    assert r.status_code == 200, r.text
    paper_id = r.json()["id"]

    # 版本上传
    r = client.post(
        f"/api/papers/{paper_id}/versions",
        files={"file": ("draft_v1.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"changelog": "初稿"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version_no"] == 1

    # 非法状态转移被拒绝
    r = client.post(f"/api/papers/{paper_id}/status", json={"to": "Accepted"})
    assert r.status_code == 400

    # 合法流程：Draft -> Submitted -> Under Review -> Revision -> Resubmitted -> Accepted -> Published
    for target in ("Submitted", "Under Review", "Revision", "Resubmitted", "Under Review", "Accepted", "Published"):
        r = client.post(f"/api/papers/{paper_id}/status", json={"to": target})
        assert r.status_code == 200, f"{target}: {r.text}"
    assert r.json()["status"] == "Published"
    assert r.json()["next_statuses"] == []

    # 审稿记录
    r = client.post(
        f"/api/papers/{paper_id}/review-rounds",
        data={"decision": "Major Revision", "summary": "补充实验", "review_date": "2026-08-01"},
    )
    assert r.status_code == 200, r.text

    # 详情
    r = client.get(f"/api/papers/{paper_id}")
    body = r.json()
    assert len(body["versions"]) == 1
    assert len(body["review_rounds"]) == 1

    # 列表过滤
    r = client.get("/api/papers", params={"status": "Published"})
    assert any(x["id"] == paper_id for x in r.json())

    assert client.delete(f"/api/papers/{paper_id}").status_code == 200


def test_material_upload_preview_download():
    p = _project()
    r = client.post(
        "/api/materials",
        files=[("files", ("实验数据.csv", b"a,b,c\n1,2,3\n", "text/csv"))],
        data={"project_id": str(p["id"]), "category": "数据", "tags": "RNA-seq"},
    )
    assert r.status_code == 200, r.text
    mid = r.json()[0]["id"]

    # 预览（文本）
    r = client.get(f"/api/materials/{mid}/preview")
    assert r.status_code == 200
    assert "1,2,3" in r.text

    # 下载
    r = client.get(f"/api/materials/{mid}/download")
    assert r.status_code == 200

    # 元数据更新
    r = client.put(f"/api/materials/{mid}", json={"name": "实验数据v2"})
    assert r.json()["name"] == "实验数据v2"

    assert client.delete(f"/api/materials/{mid}").status_code == 200


def test_reference_bibtex_import_and_export():
    bib = """@article{kingma2015adam,
  title = {Adam: A Method for Stochastic Optimization},
  author = {Kingma, Diederik P. and Ba, Jimmy},
  journal = {ICLR},
  year = {2015},
  doi = {10.48550/arXiv.1412.6980}
}
"""
    r = client.post("/api/references/import-bib", files={"file": ("refs.bib", bib.encode(), "text/plain")})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1

    r = client.get("/api/references")
    refs = r.json()
    assert len(refs) == 1
    assert refs[0]["authors"] == ["Diederik P. Kingma", "Jimmy Ba"]

    # 导出
    r = client.get("/api/references/export-bib")
    assert "kingma2015adam" in r.text

    # 笔记
    r = client.post("/api/notes", json={"target_type": "reference", "target_id": refs[0]["id"], "content": "# 笔记"})
    assert r.status_code == 200
    r = client.get("/api/notes", params={"target_type": "reference", "target_id": refs[0]["id"]})
    assert len(r.json()) == 1

    # DOI 元数据（离线时允许失败）
    r = client.post("/api/references/doi-metadata", json={"doi": "10.1038/nature14539"})
    assert r.status_code in (200, 404)

    assert client.delete(f"/api/references/{refs[0]['id']}").status_code == 200


def test_search():
    _project("图神经网络项目")
    r = client.get("/api/search", params={"q": "图神经网络"})
    assert r.status_code == 200
    assert len(r.json()["projects"]) == 1
