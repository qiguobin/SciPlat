"""V9 测试：AI 关联深度解析（全文内容评分 / 不静默降级）+ 多工作区存储（独立数据目录）。"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient  # noqa: E402

from app import config, models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402

# 工作区注册表隔离：不污染用户 ~/.sciplat
os.environ["SCI_WORKSPACES_FILE"] = os.path.join(tempfile.mkdtemp(prefix="sciplat-ws-test-"), "workspaces.json")

init_db()
client = TestClient(app)

_ORIG_DATA_DIR = str(config.DATA_DIR)


def _ref(title: str, text: str = "", summary: str = ""):
    r = client.post("/api/references", json={"title": title})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    if text or summary:
        with SessionLocal() as db:
            db.add(models.ReferenceText(reference_id=rid, text=text, summary=summary, keywords=""))
            db.commit()
    return rid


def _new_ws_dir(name: str) -> str:
    return tempfile.mkdtemp(prefix=f"sciplat-ws-{name}-")


# ==================== AI 关联深度解析 ====================

def test_ai_link_deep_prompt_contains_fulltext():
    """LLM 评分 prompt 必须包含全文片段（深度内容解析），且使用深度评分参数。"""
    rid1 = _ref("Graph neural networks for molecular property prediction",
                text="We propose graph neural network architectures for molecular property prediction with attention.",
                summary="GNN for molecules")
    rid2 = _ref("Molecular property prediction using graph attention networks",
                text="Graph attention networks achieve state of the art on molecular property benchmarks.",
                summary="GAT for molecules")
    captured: dict = {}

    def fake_chat(db, system, messages, **kw):
        captured.update(kw)
        captured["user"] = messages[-1]["content"]
        return json.dumps([{"a": rid1, "b": rid2, "weight": 88, "reason": "同为图神经网络分子性质预测", "tags": ["方法相似"]}])

    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.llm.chat", side_effect=fake_chat):
        r = client.post("/api/references/ai-auto-link")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "llm"
    assert body["warnings"] == []
    assert body["created"] >= 1
    # 深度参数
    assert captured.get("max_tokens") == 4000
    assert captured.get("timeout") == 90
    assert captured.get("task") == "link"
    # prompt 包含全文片段（不是只对比标签/摘要）
    assert "全文片段" in captured["user"]
    assert "GNN for molecules" in captured["user"]


def test_ai_link_no_llm_warns_local():
    """未配置 LLM：明确 warning，不静默伪装成 AI 关联。"""
    _ref("Attention is all you need for transformers")
    # 共享标签触发结构化候选（标题词汇不完全重叠也能形成候选对）
    client.post("/api/references", json={"title": "Transformer architectures for language modeling", "tags": "transformer"})
    with SessionLocal() as db:
        first = db.query(models.Reference).order_by(models.Reference.id).first()
        first.tags = "transformer"
        db.commit()
    with patch("app.services.llm.is_configured", return_value=False):
        r = client.post("/api/references/ai-auto-link")
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "local"
    assert any("未配置 LLM" in w for w in body["warnings"])
    links = client.get("/api/references/ai-links").json()
    assert links and all(l["method"] == "local" for l in links)


def test_ai_link_llm_failure_warns_degraded():
    """配置了 LLM 但调用失败：method=local 且 warning 告知降级，不静默。"""
    _ref("Graph neural networks for chemistry")
    _ref("Graph neural networks for molecular property prediction")
    with patch("app.services.llm.is_configured", return_value=True), \
         patch("app.services.llm.chat", side_effect=Exception("connection refused")):
        r = client.post("/api/references/ai-auto-link")
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "local"
    assert any("评分失败" in w for w in body["warnings"])
    links = client.get("/api/references/ai-links").json()
    assert links and all(l["method"] == "local" for l in links)


def test_ai_link_extracts_pdf_text_before_scoring():
    """深度评分前自动提取 PDF 全文（有附件无文本的文献）。"""
    from app.services import ai_link, storage as storage_service

    rel, _name = storage_service.storage.save(b"%PDF-1.4 fake content", "paper.pdf")
    rid = _ref("Extract me for linking")
    with SessionLocal() as db:
        ref = db.get(models.Reference, rid)
        ref.stored_path = rel
        db.commit()

    with patch("app.services.pdfextract.extract_pdf_text",
               return_value="Graph neural networks for molecules full text content beyond summary"), \
         patch("app.services.pdfextract.make_summary",
               return_value={"summary": "GNN summary", "keywords": "gnn, molecules"}):
        with SessionLocal() as db:
            done = ai_link._extract_missing_texts(db, db.query(models.Reference).all())
    assert done == 1
    with SessionLocal() as db:
        rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
        assert rt is not None
        assert "full text content" in rt.text
        assert rt.summary == "GNN summary"


# ==================== 工作区 ====================

def test_workspace_current_default_registered():
    """首次使用自动注册当前数据目录为默认工作区。"""
    r = client.get("/api/workspace")
    assert r.status_code == 200
    body = r.json()
    assert body["current"] == str(config.DATA_DIR)
    cur = [w for w in body["workspaces"] if w["current"]]
    assert cur and cur[0]["path"] == str(config.DATA_DIR)


def test_workspace_create_switch_isolation():
    """创建即切换；A/B 工作区数据完全隔离；切回后数据仍在。"""
    b = _new_ws_dir("b")
    r = client.post("/api/workspace", json={"name": "B 课题", "path": b})
    assert r.status_code == 200, r.text
    try:
        assert str(config.DATA_DIR) == str(Path(b).resolve())
        r = client.post("/api/references", json={"title": "B workspace paper"})
        assert r.status_code == 200
        # 切回 A：B 的文献不可见
        r = client.post("/api/workspace/switch", json={"path": _ORIG_DATA_DIR})
        assert r.status_code == 200, r.text
        titles = [x["title"] for x in client.get("/api/references").json()]
        assert "B workspace paper" not in titles
        # 再切回 B：文献仍在
        r = client.post("/api/workspace/switch", json={"path": b})
        assert r.status_code == 200
        titles = [x["title"] for x in client.get("/api/references").json()]
        assert "B workspace paper" in titles
    finally:
        client.post("/api/workspace/switch", json={"path": _ORIG_DATA_DIR})


def test_workspace_switch_fts_available():
    """切换后新库 FTS 索引可用。"""
    b = _new_ws_dir("fts")
    r = client.post("/api/workspace", json={"name": "fts", "path": b})
    assert r.status_code == 200, r.text
    try:
        client.post("/api/references", json={"title": "FTS workspace test paper"})
        r = client.post("/api/references/fts-search", json={"q": "workspace"})
        assert r.status_code == 200, r.text
    finally:
        client.post("/api/workspace/switch", json={"path": _ORIG_DATA_DIR})


def test_workspace_storage_isolated():
    """切换后文件存储指向新工作区目录。"""
    b = _new_ws_dir("stor")
    client.post("/api/workspace", json={"name": "stor", "path": b})
    try:
        from app.services import storage as storage_service
        rel, _name = storage_service.storage.save(b"%PDF", "x.pdf")
        p = storage_service.storage.abs_path(rel)
        assert Path(b).resolve() in p.resolve().parents
    finally:
        client.post("/api/workspace/switch", json={"path": _ORIG_DATA_DIR})


def _ws_delete(path: str):
    """TestClient.delete 不接受 json 参数，用通用 request 发送 DELETE + body。"""
    return client.request("DELETE", "/api/workspace", json={"path": path})


def test_workspace_remove_keeps_files():
    """注销工作区不删除任何数据文件；当前工作区不可注销。"""
    b = _new_ws_dir("rm")
    client.post("/api/workspace", json={"name": "rm", "path": b})
    try:
        marker = Path(b) / "keep.txt"
        marker.write_text("data", encoding="utf-8")
        # 当前工作区不可注销
        r = _ws_delete(b)
        assert r.status_code == 400
        # 切回后注销
        client.post("/api/workspace/switch", json={"path": _ORIG_DATA_DIR})
        r = _ws_delete(b)
        assert r.status_code == 200, r.text
        assert marker.exists()  # 文件保留
        paths = [w["path"] for w in client.get("/api/workspace").json()["workspaces"]]
        assert str(Path(b).resolve()) not in paths
    finally:
        client.post("/api/workspace/switch", json={"path": _ORIG_DATA_DIR})


def test_workspace_switch_rejects_missing_dir():
    """切换不存在的目录 → 400。"""
    r = client.post("/api/workspace/switch", json={"path": str(Path(_ORIG_DATA_DIR) / "not-exist-xyz")})
    assert r.status_code == 400
    # 未受影响
    r = client.get("/api/workspace")
    assert r.json()["current"] == str(config.DATA_DIR)
