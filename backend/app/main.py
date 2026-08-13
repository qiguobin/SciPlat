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
    workspace,
    writing,
)

_UPTIME_START = time.time()
_WORKSPACE_LOCK = threading.Lock()


def switch_workspace(path: str) -> str:
    """切换工作区（数据目录）：重建引擎/存储 → 建表/迁移/FTS → key 加密迁移 → 自动备份节流。

    调用方（routers/workspace.py）延迟 import 本函数以避免循环依赖。
    """
    with _WORKSPACE_LOCK:
        from .database import rebind as rebind_db
        from .services import storage as storage_service

        config.set_data_dir(path)
        rebind_db()                      # 重建 engine/SessionLocal + init_db + rebuild_fts
        _migrate_api_key_encryption()    # 新库明文 key 加密迁移（幂等）
        try:
            backup._auto_backup()        # 新库自动备份（距上次 >7 天）
        except Exception:
            pass
        storage_service.rebind()         # 文件存储指向新 FILES_DIR
    return str(config.DATA_DIR)


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
    """后台线程：每 6 小时抓取活跃订阅源（新条目自动写系统通知）。

    引擎代际（_engine_gen）变化说明切换了工作区：跳过当轮，下一轮自动用新库。
    """
    import time as _time

    from . import database as _db

    last_gen = None
    while True:
        _time.sleep(tracking.FETCH_INTERVAL_HOURS * 3600)
        try:
            if _db._engine_gen == last_gen:
                db = _db.SessionLocal()
                try:
                    tracking.auto_fetch_all(db)
                finally:
                    db.close()
            else:
                last_gen = _db._engine_gen  # 引擎已切换：本轮跳过，下轮用新库
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


def _llm_health_loop() -> None:
    """后台线程：启动时探测一次 LLM API，之后每 30 分钟一次（写历史统计，失败静默）。"""
    import time as _time

    from .database import SessionLocal

    first = True
    while True:
        if first:
            first = False
        else:
            _time.sleep(30 * 60)
        try:
            db = SessionLocal()
            try:
                from .services import llm as llm_service

                llm_service.probe_and_record(db)
            finally:
                db.close()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # FTS 全文索引全量重建（幂等，保证存量文献入库）
    try:
        from .database import rebuild_fts

        rebuild_fts()
    except Exception:
        pass
    _migrate_api_key_encryption()
    # 启动时自动备份（距上次 >7 天）
    try:
        backup._auto_backup()
    except Exception:
        pass
    # 启动科研追踪后台线程
    threading.Thread(target=_tracker_loop, daemon=True).start()
    # 启动 LLM API 健康探测线程（立即探测一次 + 每 30 分钟）
    threading.Thread(target=_llm_health_loop, daemon=True).start()
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
    workspace.router,
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
