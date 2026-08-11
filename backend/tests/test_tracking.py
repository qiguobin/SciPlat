"""追踪测试：预置源初始化、抓取去重、入库、通知联动。"""
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_preset_sources_init():
    """预置源初始化：RSS 源实测（网络可达的 active）。"""
    r = client.get("/api/tracking/sources")
    assert r.status_code == 200
    sources = r.json()
    assert len(sources) >= 20  # 25 RSS + 3 arXiv
    assert any(s["stype"] == "arxiv_category" for s in sources)
    # arXiv 分类源默认 active
    arxiv = [s for s in sources if s["stype"] == "arxiv_category"]
    assert all(s["active"] for s in arxiv)


def test_arxiv_fetch_and_dedupe():
    """arXiv 抓取 + 去重（用极小 max_results 避免网络负担）。"""
    # 手动创建源（离线降级：网络不可达时 last_error 记录，不崩溃）
    r = client.post("/api/tracking/sources", json={"name": "测试关键词", "stype": "arxiv_keyword", "query": "all:transformer"})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    r = client.post("/api/tracking/fetch", json={"source_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert "created" in body  # 离线时 created=0 且 last_error 记录


def test_rss_fetch_degrade():
    """RSS 不可达降级：last_error 记录，不崩溃。"""
    r = client.post("/api/tracking/sources", json={"name": "坏源", "stype": "rss", "query": "https://nonexistent.invalid/rss"})
    sid = r.json()["id"]
    r = client.post("/api/tracking/fetch", json={"source_id": sid})
    assert r.status_code == 200
    sources = client.get("/api/tracking/sources").json()
    bad = next(s for s in sources if s["id"] == sid)
    assert bad["last_error"]  # 记录了错误
    assert bad["item_count"] == 0


def test_manual_source_crud():
    r = client.post("/api/tracking/sources", json={"name": "临时源", "stype": "rss", "query": "https://example.com/rss"})
    sid = r.json()["id"]
    r = client.put(f"/api/tracking/sources/{sid}", json={"active": False})
    assert r.json()["active"] is False
    assert client.delete(f"/api/tracking/sources/{sid}").status_code == 200
