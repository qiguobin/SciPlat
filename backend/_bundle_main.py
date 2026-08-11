"""桌面端入口（pywebview）：内嵌 uvicorn 服务 + 原生 WebView2 窗口。

打包：PyInstaller 单文件 SciPlat.exe（内嵌 frontend/dist）。
注意：必须静态 import app.main（而非字符串导入），否则 PyInstaller 无法收集模块树。
"""
import os
import socket
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOCK_PORT = 8765   # 单实例锁端口（占用即已有实例在运行）
BASE_PORT = 8766   # 服务端口起始（被占则 +1）


def _lock_instance() -> bool:
    """单实例锁：绑定锁端口，失败说明已有实例。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return True
    except OSError:
        return False


def _pick_port(start: int = BASE_PORT, tries: int = 50):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return None


if not _lock_instance():
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, "SciPlat 已在运行中，请勿重复启动。", "SciPlat", 0x40)
    sys.exit(0)

port = _pick_port()
if port is None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, "无可用端口，启动失败。", "SciPlat", 0x40)
    sys.exit(1)

os.environ["SCI_PORT"] = str(port)
os.environ.setdefault("SCI_NO_BROWSER", "1")

import webview  # noqa: E402
import uvicorn  # noqa: E402

from app import config  # noqa: E402
import app.main  # noqa: E402,F401  静态导入：确保全量模块被收集

SERVER = "127.0.0.1"


def _run_server() -> None:
    uvicorn.run(app.main.app, host=SERVER, port=config.PORT, reload=False, log_level="warning")


def _wait_ready(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://{SERVER}:{port}/api/health"
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.4)
    return False


# 模块级窗口引用：进度回调使用（不能挂到 js_api 实例属性上——
# Window 内部持有 js_api 引用，实例属性会导致循环引用 → pywebview 递归溢出卡死）
_WINDOW = None


class UpdateApi:
    """pywebview js_api：前端一键升级能力（下载安装包 → SHA256 校验 → 静默安装）。"""

    def download(self, url: str, sha256: str) -> dict:
        """流式下载安装包到临时目录并校验 SHA256（进度经 window 回调前端）。"""
        import hashlib
        import tempfile
        from pathlib import Path

        import httpx

        try:
            d = Path(tempfile.gettempdir()) / "sciplat-update"
            d.mkdir(parents=True, exist_ok=True)
            target = d / f"SciPlatSetup-{int(time.time())}.exe"
            h = hashlib.sha256()
            with httpx.stream("GET", url, timeout=300, follow_redirects=True) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length") or 0)
                done = 0
                with open(target, "wb") as f:
                    for chunk in resp.iter_bytes(1 << 20):
                        f.write(chunk)
                        h.update(chunk)
                        done += len(chunk)
                        if total:
                            self._progress(min(100, round(done * 100 / total)))
            if sha256 and h.hexdigest().lower() != sha256.lower():
                target.unlink(missing_ok=True)
                return {"ok": False, "error": "SHA256 校验失败：文件可能被篡改或下载不完整，请重试"}
            self._progress(100)
            return {"ok": True, "path": str(target)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"下载失败：{e}"}

    def install(self, path: str) -> dict:
        """启动静默安装器并立即退出当前应用。

        用 PowerShell 隐藏窗口延迟 5 秒：等待当前进程与 WebView2 子进程完全退出、
        释放 SciPlat.exe 文件占用（PyInstaller onefile 运行时锁定 exe），
        再启动安装器覆盖升级（同 AppId，保留 data/）。安装日志写入临时目录便于排查。
        """
        import subprocess
        import tempfile
        from pathlib import Path

        log = Path(tempfile.gettempdir()) / "sciplat-update" / "install.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        # 单引号包裹路径（临时目录路径不含单引号）
        ps = (
            f"Start-Sleep -Seconds 5; "
            f"Start-Process -FilePath '{path}' "
            f"-ArgumentList '/SILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/LOG={log}'"
        )
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
        except Exception:  # noqa: BLE001
            pass
        # 立即退出：释放 PyInstaller onefile 对 exe 的占用，让安装器可以覆盖文件
        os._exit(0)
        return {"ok": True}

    def _progress(self, pct: int) -> None:
        global _WINDOW
        try:
            if _WINDOW is not None:
                _WINDOW.evaluate_js(f"window.__updateProgress && window.__updateProgress({pct})")
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    threading.Thread(target=_run_server, daemon=True).start()
    if not _wait_ready():
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, "后端服务启动失败（30 秒内未就绪）。", "SciPlat", 0x40)
        sys.exit(1)

    icon = None
    ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(ico):
        icon = ico
    update_api = UpdateApi()
    try:
        _win = webview.create_window(
            "SciPlat 博士生科研管理平台",
            f"http://{SERVER}:{port}/",
            width=1440,
            height=900,
            min_size=(1024, 640),
            icon=icon,
            background_color="#0B1120",
            js_api=update_api,
        )
    except TypeError:
        # 旧版 pywebview 无 icon/js_api 参数时降级
        _win = webview.create_window(
            "SciPlat 博士生科研管理平台",
            f"http://{SERVER}:{port}/",
            width=1440,
            height=900,
            min_size=(1024, 640),
            background_color="#0B1120",
            js_api=update_api,
        )
    # 窗口引用存入模块级变量（实例属性会造成循环引用卡死）
    _WINDOW = _win
    webview.start()
    # 窗口关闭 → 主进程退出（daemon 服务线程随之结束）
