"""文献关联图谱测试：相似度、引用链接、过滤、降级（数据目录由 conftest.py 统一设置）。"""
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402

init_db()
client = TestClient(app)


def _ref(title, tags="", authors=None, venue="", year=None, doi=""):
    r = client.post("/api/references", json={
        "title": title, "tags": tags, "authors": authors or [],
        "venue": venue, "year": year, "doi": doi,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _citations_map():
    db = SessionLocal()
    try:
        return {c.ref_id: c.cited_doi for c in db.query(models.ReferenceCitation).all()}
    finally:
        db.close()


def test_similarity_shared_tags_and_authors():
    _ref("Attention Is All You Need", tags="transformer, deep learning", authors=["A. Vaswani"], venue="NeurIPS", year=2017)
    _ref("BERT: Pre-training", tags="transformer, NLP", authors=["A. Vaswani", "J. Devlin"], venue="NeurIPS", year=2018)
    _ref("Random Unrelated Paper", tags="biology", authors=["B. Nobody"], venue="Nature", year=2020)

    r = client.get("/api/references/network")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 3

    # 前两篇：共享标签 transformer + 共享作者 Vaswani + 同刊 NeurIPS + 年份相邻
    link = next(l for l in body["links"] if l["weight"] > 0)
    assert set(link["factors"]) >= {"tags", "authors", "venue", "year"}
    assert link["citation"] is False
    # 不相关文献不产生边
    assert len(body["links"]) == 1

    # 权重计算：score = 3 + 2 + 1 + 0.5 = 6.5 → round(6.5*12) = 78 → cap 70
    assert link["weight"] == 70


def test_network_filters():
    _ref("Paper A", tags="graph, theory")
    _ref("Paper B", tags="graph")
    _ref("Paper C", tags="nlp")

    r = client.get("/api/references/network", params={"tag": "graph"})
    body = r.json()
    assert len(body["nodes"]) == 2
    assert all("graph" in n["tags"] for n in body["nodes"])

    r = client.get("/api/references/network", params={"min_weight": 50})
    body = r.json()
    assert all(l["weight"] >= 50 for l in body["links"])


def test_citation_links_and_stats():
    ref_a = _ref("A", tags="x", doi="10.1000/a")
    ref_b = _ref("B", tags="y", doi="10.1000/b")
    # 直接插入引用记录：A 引用了 B
    db = SessionLocal()
    try:
        db.add(models.ReferenceCitation(ref_id=ref_a["id"], cited_doi="https://doi.org/10.1000/b"))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/references/network")
    body = r.json()
    cit_link = next(l for l in body["links"] if l["citation"])
    assert cit_link["weight"] == 30
    assert cit_link["factors"] == ["citation"]

    # stats
    r = client.get("/api/references/network/stats")
    stats = r.json()
    assert stats["node_count"] == 2
    assert stats["citation_link_count"] == 1
    assert stats["citation_records"] == 1
    assert stats["citations_fetched"] == 1

    # 删除引用记录
    db = SessionLocal()
    try:
        cid = db.query(models.ReferenceCitation).first().id
    finally:
        db.close()
    r = client.delete(f"/api/references/citations/{cid}")
    assert r.status_code == 200


def test_fetch_citations_requires_doi():
    ref = _ref("No DOI Paper")
    r = client.post(f"/api/references/{ref['id']}/fetch-citations")
    assert r.status_code == 400


def test_fetch_all_citations_offline_degrade():
    """联网失败时返回错误计数，不崩溃（离线降级）。"""
    _ref("Online Paper", doi="10.1000/offline-test")
    r = client.post("/api/references/fetch-all-citations")
    assert r.status_code == 200
    body = r.json()
    assert body["refs"] >= 1
    assert body["fetched"] == 0  # 离线或网络异常时全部失败
    assert body["errors"] >= 1
