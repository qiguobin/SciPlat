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
from pathlib import Path

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


def _downloads_dir() -> Path:
    """Windows 默认下载文件夹（见 services/desktop_update，供 download 复用）。"""
    from app.services import desktop_update

    return desktop_update.downloads_dir()


class UpdateApi:
    """pywebview js_api：前端一键升级能力（下载安装包到下载文件夹 → SHA256 校验 → 静默安装）。"""

    def download(self, url: str, sha256: str) -> dict:
        """流式下载安装包到 Windows 默认下载文件夹并校验 SHA256（进度经 window 回调前端）。

        文件名取自 URL 资产名（如 SciPlatSetup-0.7.0.exe）；下载完成后保留文件，用户可见可留底。
        """
        import hashlib

        import httpx

        try:
            d = _downloads_dir()
            d.mkdir(parents=True, exist_ok=True)
            name = Path(url).name or f"SciPlatSetup-{int(time.time())}.exe"
            target = d / name
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
        """启动静默安装器并立即退出当前应用；启动失败时返回错误（应用不退出，前端可提示）。

        Inno Setup [Setup] CloseApplications=yes 会自行关闭占用 SciPlat.exe 的进程；
        再延迟 5 秒退出兜底释放 PyInstaller onefile 文件锁。安装日志写入下载目录。
        """
        from app.services import desktop_update

        result = desktop_update.start_install(path)
        if not result["ok"]:
            return result
        # 等待 onefile 文件锁释放后退出；Inno Setup 安装完成后自动拉起新版本（[Run] nowait）
        time.sleep(5)
        os._exit(0)
        return {"ok": True}  # 不可达（os._exit），仅类型兜底

    def _progress(self, pct: int) -> None:
        global _WINDOW
        try:
            if _WINDOW is not None:
                _WINDOW.evaluate_js(f"window.__updateProgress && window.__updateProgress({pct})")
        except Exception:  # noqa: BLE001
            pass


class WorkspaceApi:
    """pywebview js_api：工作区相关桌面能力（系统目录选择器）。"""

    def pick_directory(self) -> list[str] | None:
        """弹出系统文件夹选择对话框，返回选中路径列表（取消返回 None）。"""
        global _WINDOW
        try:
            if _WINDOW is None:
                return None
            result = _WINDOW.create_file_dialog(webview.FOLDER_DIALOG)
            if isinstance(result, str):
                return [result]
            return list(result or [])
        except Exception:  # noqa: BLE001
            return None


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
    workspace_api = WorkspaceApi()
    # js_api 使用 dict：前端通过 pywebview.api.update.* / pywebview.api.workspace.* 调用
    _js_api = {"update": update_api, "workspace": workspace_api}
    try:
        _win = webview.create_window(
            "SciPlat 博士生科研管理平台",
            f"http://{SERVER}:{port}/",
            width=1440,
            height=900,
            min_size=(1024, 640),
            icon=icon,
            background_color="#0B1120",
            js_api=_js_api,
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
            js_api=_js_api,
        )
    # 窗口引用存入模块级变量（实例属性会造成循环引用卡死）
    _WINDOW = _win
    webview.start()
    # 窗口关闭 → 主进程退出（daemon 服务线程随之结束）
