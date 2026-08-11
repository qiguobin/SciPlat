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
    try:
        webview.create_window(
            "SciPlat 博士生科研管理平台",
            f"http://{SERVER}:{port}/",
            width=1440,
            height=900,
            min_size=(1024, 640),
            icon=icon,
            background_color="#0B1120",
        )
    except TypeError:
        # 旧版 pywebview 无 icon 参数时降级
        webview.create_window(
            "SciPlat 博士生科研管理平台",
            f"http://{SERVER}:{port}/",
            width=1440,
            height=900,
            min_size=(1024, 640),
            background_color="#0B1120",
        )
    webview.start()
    # 窗口关闭 → 主进程退出（daemon 服务线程随之结束）
