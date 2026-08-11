# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包 SciPlat 桌面端为单文件 SciPlat.exe（内嵌前端 dist + 窗口图标）。

注意：PyInstaller 会把 spec 复制到临时目录执行，SPECPATH 不可用于定位源码，
因此仓库根目录从 cwd 解析（构建脚本会在仓库根目录执行），或设置 SCI_REPO_ROOT 覆盖。
用法：在仓库根目录执行
    python -m PyInstaller desktop/backend.spec --noconfirm --distpath backend/dist --workpath backend/build/pyinstaller --clean
"""
import os
from pathlib import Path

repo = Path(os.environ.get("SCI_REPO_ROOT", "")).resolve() if os.environ.get("SCI_REPO_ROOT") else Path.cwd().resolve()
if not (repo / "frontend" / "dist").is_dir():
    raise SystemExit(f"无法定位仓库根目录（当前 cwd={repo}），请从仓库根目录执行或设置 SCI_REPO_ROOT")

backend_dir = repo / "backend"
frontend_dist = repo / "frontend" / "dist"
icon_ico = repo / "desktop" / "build" / "icon.ico"

a = Analysis(
    [str(backend_dir / "_bundle_main.py")],
    pathex=[str(backend_dir)],
    datas=[
        (str(frontend_dist), "frontend/dist"),
        (str(icon_ico), "."),  # 窗口图标（_MEIPASS/icon.ico）
    ],
    hiddenimports=[
        # uvicorn 动态加载的子模块
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "uvicorn.middleware",
        "uvicorn.middleware.proxy_headers",
        "uvicorn.middleware.message_logger",
        # pywebview（WebView2 / edgechromium 后端，基于 pythonnet）
        "webview",
        "webview.platforms",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "webview.util",
        "webview.menu",
        "clr",
        "pythonnet",
        # ORM / 依赖
        "sqlalchemy.dialects.sqlite",
        "multipart",
        "anyio",
        "httpcore",
        "certifi",
        "proxy_tools",
    ],
    excludes=["uvloop", "httptools", "websockets", "watchfiles", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SciPlat",
    console=False,  # 无控制台窗口（桌面端后台运行）
    icon=[str(icon_ico)] if icon_ico.exists() else [],
    upx=False,
)
