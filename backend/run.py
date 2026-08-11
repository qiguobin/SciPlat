"""启动入口：python run.py（自动打开浏览器，设置 SCI_NO_BROWSER=1 可禁用）。"""
import os
import threading
import time
import webbrowser

import uvicorn

from app import config


def _open_browser() -> None:
    if os.environ.get("SCI_NO_BROWSER"):
        return
    time.sleep(1.5)
    webbrowser.open(f"http://{config.HOST}:{config.PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)
