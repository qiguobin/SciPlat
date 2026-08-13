"""V10 测试：桌面更新（下载目录/安装器启动/失败不退出）+ LLM API 服务状态探测与可用性统计。"""
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _configure_llm(base_url: str = "https://api.example.com/v1", model: str = "test-model"):
    r = client.put("/api/settings/llm", json={
        "provider": "openai", "base_url": base_url, "model": model, "api_key": "sk-test",
    })
    assert r.status_code == 200, r.text


# ==================== 桌面更新辅助 ====================

def test_downloads_dir_real_or_fallback():
    """下载目录解析：真实系统返回非空路径（或异常时回退 Downloads）。"""
    from app.services import desktop_update

    d = desktop_update.downloads_dir()
    assert isinstance(d, Path) and str(d)
    assert d.is_absolute()


def test_downloads_dir_fallback_on_shell_error():
    """SHGetKnownFolderPath 抛异常 → 回退 %USERPROFILE%\\Downloads。"""
    from app.services import desktop_update

    with patch("ctypes.windll.shell32.SHGetKnownFolderPath", side_effect=OSError("no shell")):
        d = desktop_update.downloads_dir()
    assert d == Path.home() / "Downloads"


def test_launch_installer_args():
    """安装器以独立进程静默启动，参数完整（无 PowerShell 中间层）。"""
    from app.services import desktop_update

    log = Path("C:/Users/t/Downloads/sciplat-install.log")
    with patch("app.services.desktop_update.subprocess.Popen") as popen:
        desktop_update.launch_installer(r"C:\Users\t\Downloads\SciPlatSetup-0.7.0.exe", log)
    args, kw = popen.call_args
    cmd = args[0]
    assert cmd[0].endswith("SciPlatSetup-0.7.0.exe")
    assert "/SILENT" in cmd and "/SUPPRESSMSGBOXES" in cmd and "/NORESTART" in cmd
    assert any(a.startswith("/LOG=") for a in cmd)
    assert kw["creationflags"] & 0x00000008  # DETACHED_PROCESS


def test_start_install_failure_returns_error(tmp_path):
    """安装器启动失败：返回错误 dict（应用不退出），日志写入下载目录。"""
    from app.services import desktop_update

    exe = tmp_path / "SciPlatSetup-x.exe"
    exe.write_bytes(b"MZ")
    with patch("app.services.desktop_update.launch_installer", side_effect=OSError("access denied")):
        result = desktop_update.start_install(str(exe))
    assert result["ok"] is False
    assert "失败" in result["error"]
    assert (tmp_path / "sciplat-install.log").exists()


def test_start_install_success(tmp_path):
    """安装器启动成功：返回 ok。"""
    from app.services import desktop_update

    exe = tmp_path / "SciPlatSetup-x.exe"
    exe.write_bytes(b"MZ")
    with patch("app.services.desktop_update.subprocess.Popen"):
        result = desktop_update.start_install(str(exe))
    assert result["ok"] is True


# ==================== API 服务状态探测 ====================

def test_probe_success_and_failure():
    """探测成功（端点+延迟）与失败（ok=False）。"""
    _configure_llm()
    from app.services import llm as llm_service

    class _Ok:
        status_code = 200

    with patch("app.services.llm.httpx.get", return_value=_Ok()) as g:
        r = llm_service.probe_api_status(SessionLocal())
    assert r["ok"] is True
    assert r["endpoint"] == "https://api.example.com/v1/models"
    assert "latency_ms" in r
    g.assert_called_once()

    with patch("app.services.llm.httpx.get", side_effect=OSError("conn refused")):
        r2 = llm_service.probe_api_status(SessionLocal())
    assert r2["ok"] is False
    assert "error" in r2


def test_probe_base_url_variants():
    """裸域名 base_url：先试 /models，失败再试 /v1/models（兼容两种存储格式）。"""
    _configure_llm(base_url="https://api.example.com")
    from app.services import llm as llm_service

    class _Err:
        status_code = 404

    class _Ok:
        status_code = 200

    with patch("app.services.llm.httpx.get", side_effect=[_Err(), _Ok()]) as g:
        r = llm_service.probe_api_status(SessionLocal())
    assert r["ok"] is True
    urls = [c.args[0] for c in g.call_args_list]
    assert urls == ["https://api.example.com/models", "https://api.example.com/v1/models"]


def test_probe_ollama_tags():
    """Ollama 分支探测 /api/tags。"""
    _configure_llm()
    from app.services import llm as llm_service

    with SessionLocal() as db:
        db.query(models.Setting).filter_by(key="llm_provider").update({"value": "ollama"})
        db.commit()

    class _Ok:
        status_code = 200

        def raise_for_status(self):
            pass

    with patch("app.services.llm.httpx.get", return_value=_Ok()) as g:
        r = llm_service.probe_api_status(SessionLocal())
    assert r["ok"] is True
    assert r["endpoint"] == "http://127.0.0.1:11434/api/tags"


def test_health_stats_record_and_availability():
    """统计记录与可用性百分比计算（最近 30 次滑动窗口）。"""
    _configure_llm()
    from app.services import llm as llm_service

    with SessionLocal() as db:
        for ok in ([True] * 7 + [False] * 3):
            llm_service._record_health(db, ok, 120, "https://x/models")
    with SessionLocal() as db:
        status = llm_service.get_llm_status(db)
    assert status["total_checks"] == 10
    assert status["ok_checks"] == 7
    assert status["availability_pct"] == 70
    assert status["online"] is False  # 最近一次探测失败
    assert len(status["history"]) == 10


def test_health_history_capped_30():
    """history 最多保留 30 次；百分比按最近 30 次计算。"""
    _configure_llm()
    from app.services import llm as llm_service

    with SessionLocal() as db:
        for i in range(40):
            llm_service._record_health(db, i % 2 == 0, 100, "https://x/models")
    with SessionLocal() as db:
        status = llm_service.get_llm_status(db)
    assert len(status["history"]) == 30
    assert status["total_checks"] == 40
    assert status["availability_pct"] == 50


def test_llm_status_endpoints():
    """GET /llm/status 读缓存；POST /llm/status/refresh 实时探测并记录。"""
    _configure_llm()

    class _Ok:
        status_code = 200

    with patch("app.services.llm.httpx.get", return_value=_Ok()):
        r = client.post("/api/llm/status/refresh")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True and body["ok"] is True

    r2 = client.get("/api/llm/status")
    assert r2.status_code == 200
    s = r2.json()
    assert s["online"] is True
    assert s["total_checks"] >= 1
    assert s["availability_pct"] is not None


def test_llm_status_not_configured():
    """未配置 LLM → configured=False（不触发任何外部请求）。"""
    r = client.get("/api/llm/status")
    assert r.status_code == 200
    assert r.json()["configured"] is False


def test_health_includes_llm_status():
    """/health 返回 llm_status 缓存摘要（零外部请求）。"""
    _configure_llm()
    from app.services import llm as llm_service

    with SessionLocal() as db:
        llm_service._record_health(db, True, 100, "https://x/models")
    r = client.get("/api/health")
    assert r.status_code == 200
    hs = r.json()["llm_status"]
    assert hs["online"] is True
    assert hs["availability_pct"] == 100
