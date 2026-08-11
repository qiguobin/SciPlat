"""全局配置：路径与端口。数据目录可用环境变量 SCI_DATA_DIR 覆盖。"""
import os
import sys
from pathlib import Path

APP_VERSION = "0.6.0"
APP_NAME = "SciPlat"

if getattr(sys, "frozen", False):
    # PyInstaller 打包：资源在 _MEIPASS 临时目录（onefile）或 exe 同级
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent  # sci_plat/
    _BUNDLE_ROOT = BASE_DIR

DATA_DIR = Path(os.environ.get("SCI_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "sci.db"
FILES_DIR = DATA_DIR / "files"

# 前端构建产物：源码树 / _MEIPASS / exe 同级 三处兜底
FRONTEND_DIST = Path(os.environ.get("SCI_FRONTEND_DIST", "")) if os.environ.get("SCI_FRONTEND_DIST") else None
if FRONTEND_DIST is None:
    for candidate in (
        _BUNDLE_ROOT / "frontend" / "dist",
        _BUNDLE_ROOT / "dist",
        BASE_DIR / "frontend" / "dist",
    ):
        if candidate.is_dir():
            FRONTEND_DIST = candidate
            break
    else:
        FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

HOST = "127.0.0.1"
PORT = int(os.environ.get("SCI_PORT", "8000"))
