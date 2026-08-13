"""桌面端更新辅助（独立模块便于单测）：Windows 默认下载文件夹 + 静默安装器启动。

- downloads_dir()：SHGetKnownFolderPath(FOLDERID_Downloads)，失败回退 %USERPROFILE%\\Downloads
- launch_installer()：直接 Popen 启动 Inno Setup 安装器（不经 PowerShell，避免转义/AV 拦截）
- start_install()：包装启动逻辑，失败写日志并返回错误 dict（应用不退出）
"""
from pathlib import Path

import subprocess  # 模块级导入：测试可 patch（launch_installer 使用）


def downloads_dir() -> Path:
    """Windows 默认下载文件夹；SHGetKnownFolderPath 失败时回退 %USERPROFILE%\\Downloads。"""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Downloads = {374DE290-123F-4565-9164-39C4925E467B}
        folder_id = GUID(
            0x374DE290, 0x123F, 0x4565,
            (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
        )
        shell32 = ctypes.windll.shell32
        buf = ctypes.c_wchar_p()
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(buf))
        if hr == 0 and buf.value:
            return Path(buf.value)
    except Exception:  # noqa: BLE001
        pass
    return Path.home() / "Downloads"


def launch_installer(path: str, log) -> None:
    """以独立进程静默启动 Inno Setup 安装器。启动失败抛异常，由调用方处理。

    list 参数不经 shell（无引号转义问题）；DETACHED_PROCESS 使子进程不随父进程退出。
    """
    subprocess.Popen(
        [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/LOG={log}"],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


def start_install(path: str) -> dict:
    """启动安装器；失败时写日志并返回 {"ok": False, "error"}（应用不退出）。

    成功返回 {"ok": True}，由调用方延迟退出（释放 PyInstaller onefile 文件锁）。
    """
    import time

    try:
        log_dir = Path(path).parent if Path(path).parent.is_dir() else downloads_dir()
        log = log_dir / "sciplat-install.log"
    except Exception:  # noqa: BLE001
        log = downloads_dir() / "sciplat-install.log"
    try:
        launch_installer(path, log)
    except Exception as e:  # noqa: BLE001
        try:
            log.write_text(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 启动安装器失败：{e}", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": f"启动安装器失败：{e}"}
    return {"ok": True}
