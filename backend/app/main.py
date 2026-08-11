"""FastAPI 入口：API 路由 + 前端静态托管（SPA fallback）+ 系统事件中间件。"""
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import config
from .database import init_db
from .routers import (
    achievements,
    ai as ai_router,
    backup,
    export as export_router,
    ideas,
    materials,
    meetings,
    notes,
    notifications,
    papers,
    profile,
    projects,
    references,
    schedule,
    settings,
    stats,
    todos,
    tracking,
    update as update_router,
    v5,
    writing,
)

_UPTIME_START = time.time()


def _log_system_event(level: str, source: str, message: str) -> None:
    """写入系统事件表（状态栏错误监控）；失败静默。"""
    try:
        from . import models
        from .database import SessionLocal

        db = SessionLocal()
        try:
            db.add(models.SystemEvent(level=level, source=source[:200], message=message[:2000]))
            # 保留最近 200 条
            ids = [e.id for e in db.query(models.SystemEvent).order_by(models.SystemEvent.created_at.desc()).offset(200).all()]
            if ids:
                db.query(models.SystemEvent).filter(models.SystemEvent.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


async def _record_exceptions(request: Request, call_next):
    """未处理异常（5xx）自动写入系统事件，供状态栏错误计数。"""
    try:
        return await call_next(request)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 记录后继续抛出
        _log_system_event("error", f"{request.method} {request.url.path}", f"{type(exc).__name__}: {exc}")
        raise


def _tracker_loop() -> None:
    """后台线程：每 6 小时抓取活跃订阅源（新条目自动写系统通知）。"""
    import time as _time

    from .database import SessionLocal

    while True:
        _time.sleep(tracking.FETCH_INTERVAL_HOURS * 3600)
        try:
            db = SessionLocal()
            try:
                tracking.auto_fetch_all(db)
            finally:
                db.close()
        except Exception:
            pass


def _migrate_api_key_encryption() -> None:
    """启动迁移（幂等）：明文 llm_api_key → Fernet 加密 + 标记。密钥文件随数据目录走。"""
    try:
        from . import models
        from .database import SessionLocal
        from .services import crypto

        db = SessionLocal()
        try:
            s = db.query(models.Setting).filter_by(key="llm_api_key").first()
            flag = db.query(models.Setting).filter_by(key="llm_api_key_encrypted").first()
            if s and s.value and not (flag and flag.value == "1"):
                s.value = crypto.encrypt_text(s.value)
                if flag:
                    flag.value = "1"
                else:
                    db.add(models.Setting(key="llm_api_key_encrypted", value="1"))
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _migrate_api_key_encryption()
    # 启动时自动备份（距上次 >7 天）
    try:
        backup._auto_backup()
    except Exception:
        pass
    # 启动科研追踪后台线程
    threading.Thread(target=_tracker_loop, daemon=True).start()
    yield


app = FastAPI(title="SciPlat 科研管理平台", version=config.APP_VERSION, lifespan=lifespan)

app.middleware("http")(_record_exceptions)

for router in (
    projects.router,
    papers.router,
    materials.router,
    references.router,
    notes.router,
    stats.router,
    profile.router,
    todos.router,
    schedule.router,
    ideas.router,
    meetings.router,
    writing.router,
    achievements.router,
    backup.router,
    settings.router,
    export_router.router,
    v5.router,
    notifications.router,
    tracking.router,
    ai_router.router,
    update_router.router,
):
    app.include_router(router)


# ---- 前端静态托管：构建产物存在时启用，SPA 路由回退 index.html ----
DIST = config.FRONTEND_DIST


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(404, "接口不存在")
    if DIST.is_dir():
        target = DIST / path
        if target.is_file():
            return FileResponse(target)
        index = DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
    return {"msg": "SciPlat API 已启动。前端未构建：请运行 npm run build（或开发模式 npm run dev）。"}
