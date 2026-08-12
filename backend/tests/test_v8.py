"""V8 测试：PubMed / OpenAlex（中文）多来源匹配、DOI 回退链、勾选列布局相关后端改动。"""
from unittest.mock import patch

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)

# ---- mock 数据 ----
PUBMED_HIT = {
    "title": "Graph neural networks for molecular property prediction",
    "authors": ["Alice Zhang", "Bob Li"],
    "year": 2024,
    "venue": "Nature Machine Intelligence",
    "doi": "10.1038/s42256-024-00001-1",
    "pmid": "39123456",
    "language": "eng",
}
OPENALEX_HIT = {
    "title": "基于图神经网络的分子性质预测",
    "authors": ["张三", "李四"],
    "year": 2023,
    "venue": "科学通报",
    "doi": "10.1360/TB2023-00001",
    "language": "zh",
}
CROSSREF_HIT = {
    "title": "Graph neural networks for molecular property prediction",
    "authors": ["Alice Zhang"],
    "year": 2024,
    "venue": "Nature Machine Intelligence",
    "doi": "10.1038/s42256-024-00001-1",
}


def _ref(title: str, doi: str = ""):
    r = client.post("/api/references", json={"title": title, "doi": doi})
    assert r.status_code == 200, r.text
    return r.json()


def test_match_candidates_sources_and_dedup():
    """多来源候选合并：按 DOI 去重、source 标记正确。"""
    with patch("app.services.pubmed.search_pubmed", return_value=[PUBMED_HIT]), \
         patch("app.services.metadata.fetch_openalex", return_value=[OPENALEX_HIT]), \
         patch("app.services.metadata.fetch_crossref_search", return_value=[CROSSREF_HIT]):
        r = client.post("/api/references/match-candidates", json={"q": "graph neural networks molecular", "source": "auto"})
    assert r.status_code == 200, r.text
    cands = r.json()["candidates"]
    # PubMed 与 CrossRef 同 DOI → 只保留一个
    assert len(cands) == 2
    sources = {c["source"] for c in cands}
    assert sources == {"pubmed", "openalex"}
    zh = next(c for c in cands if c["source"] == "openalex")
    assert zh["language"] == "zh"
    assert zh["doi"] == "10.1360/TB2023-00001"


def test_match_candidates_source_filter():
    """指定来源时只查该来源。"""
    with patch("app.services.pubmed.search_pubmed", return_value=[PUBMED_HIT]) as pm, \
         patch("app.services.metadata.fetch_openalex", return_value=[]) as oa:
        r = client.post("/api/references/match-candidates", json={"q": "graph neural networks", "source": "pubmed"})
    assert r.status_code == 200, r.text
    assert len(r.json()["candidates"]) == 1
    assert r.json()["candidates"][0]["source"] == "pubmed"
    pm.assert_called_once()
    oa.assert_not_called()


def test_match_candidates_empty_404():
    """无命中 → 404 提示。"""
    with patch("app.services.pubmed.search_pubmed", return_value=[]), \
         patch("app.services.metadata.fetch_openalex", return_value=[]), \
         patch("app.services.metadata.fetch_crossref_search", return_value=[]):
        r = client.post("/api/references/match-candidates", json={"q": "nonexistent unique title xyzzy"})
    assert r.status_code == 404


def test_ai_metadata_english_title_uses_pubmed_openalex():
    """无 DOI 英文标题：PubMed 命中 → 补全字段含 doi；OpenAlex/CrossRef 兜底不覆盖已有值。"""
    ref = _ref("Graph neural networks for molecular property prediction")

    with patch("app.services.pubmed.search_pubmed_single", return_value=PUBMED_HIT), \
         patch("app.services.metadata.fetch_openalex", return_value=[OPENALEX_HIT]), \
         patch("app.services.metadata.fetch_crossref_search", return_value=[]), \
         patch("app.services.metadata.infer_metadata_llm", return_value={}):  # 未配置 LLM 也走 API
        r = client.post(f"/api/references/{ref['id']}/ai-metadata")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "pubmed"
    assert "doi" in body["filled"]
    assert "venue" in body["filled"]

    r = client.get(f"/api/references/{ref['id']}")
    row = r.json()
    assert row["doi"] == PUBMED_HIT["doi"]
    assert row["venue"] == "Nature Machine Intelligence"
    assert row["authors"] == PUBMED_HIT["authors"]


def test_ai_metadata_chinese_title_skips_pubmed():
    """无 DOI 中文标题：跳过 PubMed（不调用），OpenAlex 中文命中补全。"""
    ref = _ref("基于图神经网络的分子性质预测")

    with patch("app.services.pubmed.search_pubmed_single", return_value=PUBMED_HIT) as pm, \
         patch("app.services.metadata.fetch_openalex", return_value=[OPENALEX_HIT]), \
         patch("app.services.metadata.fetch_crossref_search", return_value=[]), \
         patch("app.services.metadata.infer_metadata_llm", return_value={}):
        r = client.post(f"/api/references/{ref['id']}/ai-metadata")
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "openalex"
    pm.assert_not_called()  # 中文标题不查 PubMed

    row = client.get(f"/api/references/{ref['id']}").json()
    assert row["doi"] == OPENALEX_HIT["doi"]
    assert row["venue"] == "科学通报"


def test_ai_metadata_low_similarity_filtered():
    """候选标题相似度 <0.6 → 不合并，避免错配。"""
    ref = _ref("Deep learning for protein structure")
    unrelated = {"title": "A totally different paper about cooking chemistry", "authors": ["X"],
                 "year": 2020, "venue": "Some Journal", "doi": "10.9999/nope.1", "language": "en"}
    with patch("app.services.pubmed.search_pubmed_single", return_value=unrelated), \
         patch("app.services.metadata.fetch_openalex", return_value=[]), \
         patch("app.services.metadata.fetch_crossref_search", return_value=[]), \
         patch("app.services.metadata.infer_metadata_llm", return_value={}):
        r = client.post(f"/api/references/{ref['id']}/ai-metadata")
    # 未补全任何字段 → 400（与现有约定一致）
    assert r.status_code == 400
    row = client.get(f"/api/references/{ref['id']}").json()
    assert row["doi"] == ""


def test_doi_metadata_crossref_fallback_pubmed():
    """CrossRef 未命中 → 自动回退 PubMed（按 DOI），响应带 source=pubmed。"""
    with patch("app.services.doi.fetch_doi_metadata", return_value=None), \
         patch("app.services.pubmed.search_pubmed_single", return_value=PUBMED_HIT):
        r = client.post("/api/references/doi-metadata", json={"doi": "10.1038/s42256-024-00001-1"})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "pubmed"
    assert r.json()["title"] == PUBMED_HIT["title"]


def test_doi_metadata_crossref_primary():
    """CrossRef 命中时不回退 PubMed。"""
    crossref = {k: v for k, v in PUBMED_HIT.items() if k not in ("pmid", "language")}
    with patch("app.services.doi.fetch_doi_metadata", return_value=crossref) as doi, \
         patch("app.services.pubmed.search_pubmed_single", return_value=PUBMED_HIT) as pm:
        r = client.post("/api/references/doi-metadata", json={"doi": "10.1038/s42256-024-00001-1"})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "crossref"
    doi.assert_called_once()
    pm.assert_not_called()


def test_ai_match_batch_survives_api_failure():
    """批量补全：外部 API 全部异常时静默跳过，不中断、不报错。"""
    refs = [_ref(f"Batch failure paper {i}") for i in range(2)]
    with patch("app.services.pubmed.search_pubmed_single", side_effect=Exception("network down")), \
         patch("app.services.metadata.fetch_openalex", side_effect=Exception("timeout")), \
         patch("app.services.metadata.fetch_crossref_search", side_effect=Exception("refused")), \
         patch("app.services.metadata.infer_metadata_llm", return_value={}):
        r = client.post("/api/references/ai-match", json={"limit": 20, "only_incomplete": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["processed"] >= 2
    assert body["filled_total"] == 0


def test_merge_metadata_doi_validation():
    """merge_metadata：无效 DOI 不落库，有效 DOI 才写入。"""
    with SessionLocal() as db:
        ref = models.Reference(title="Test DOI validation")
        db.add(ref)
        db.commit()
        rid = ref.id

        # 无效格式
        from app.services import metadata
        filled, _ = metadata.merge_metadata(ref, None, {"doi": "not-a-doi 10.x bad", "title": "Test DOI validation"})
        assert "doi" not in filled
        # 有效格式
        filled, _ = metadata.merge_metadata(ref, None, {"doi": "10.1000/valid-doi-123"})
        assert "doi" in filled
        db.commit()
        db.refresh(ref)
        assert ref.doi == "10.1000/valid-doi-123"
        db.delete(ref)
        db.commit()
