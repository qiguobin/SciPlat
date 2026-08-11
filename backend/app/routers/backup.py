"""全库备份与恢复：zip 导出（db + files + meta），恢复前自动备份当前库。"""
import io
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import config
from ..database import engine

router = APIRouter(prefix="/api/backup", tags=["backup"])

META_VERSION = "0.3.0"


def _checkpoint_db() -> None:
    """WAL checkpoint 确保数据落盘，然后拷贝 db 文件。"""
    with engine.connect() as conn:
        conn.execute(__import__("sqlalchemy").text("PRAGMA wal_checkpoint(TRUNCATE)"))


@router.get("/download")
def download_backup():
    """导出全库备份 zip：sci.db + files/ + meta.json。"""
    _checkpoint_db()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if config.DB_PATH.exists():
            zf.write(config.DB_PATH, "sci.db")
        files_dir = config.FILES_DIR
        if files_dir.exists():
            for f in files_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f"files/{f.relative_to(files_dir)}")
        zf.writestr("meta.json", json.dumps({
            "app": "sciplat",
            "version": META_VERSION,
            "exported_at": datetime.now().isoformat(),
            "files_count": sum(1 for _ in files_dir.rglob("*")) if files_dir.exists() else 0,
        }, ensure_ascii=False, indent=2))
    buf.seek(0)
    fname = f"sciplat-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    from urllib.parse import quote
    disposition = f"attachment; filename*=UTF-8''{quote(fname)}"
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": disposition})


@router.post("/restore")
async def restore_backup(file: UploadFile):
    """从备份 zip 恢复。流程：临时目录解压 → 校验 db → 当前库存 pre-restore → 替换 → 提示重启。"""
    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")

    tmp = config.DATA_DIR / "_restore_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(tmp)
        db_file = tmp / "sci.db"
        if not db_file.exists():
            raise HTTPException(400, "备份包中缺少 sci.db，无法恢复")
        # 校验 sqlite 可打开
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_file))
            conn.execute("SELECT count(*) FROM sqlite_master")
            conn.close()
        except Exception as e:
            raise HTTPException(400, f"备份数据库损坏：{e}") from e
        # 当前库先备份
        _checkpoint_db()
        pre = config.DATA_DIR / f"pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        pre.mkdir(exist_ok=True)
        if config.DB_PATH.exists():
            shutil.copy2(config.DB_PATH, pre / "sci.db")
        if config.FILES_DIR.exists():
            shutil.copytree(config.FILES_DIR, pre / "files")
        # 替换
        shutil.rmtree(config.FILES_DIR, ignore_errors=True)
        if (tmp / "files").exists():
            shutil.copytree(tmp / "files", config.FILES_DIR)
        shutil.copy2(db_file, config.DB_PATH)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {
        "ok": True,
        "message": "恢复成功。请重启应用（关闭窗口后重新运行 start.bat）以加载新数据。",
        "pre_restore": pre.name if 'pre' in locals() else None,
    }


@router.get("/pre-restore-list")
def pre_restore_list():
    """列出恢复前自动备份的目录。"""
    items = []
    for d in config.DATA_DIR.glob("pre-restore-*"):
        if d.is_dir():
            items.append({"name": d.name, "path": str(d)})
    return {"items": items}


AUTO_BACKUP_DIR_NAME = "auto-backups"
AUTO_BACKUP_INTERVAL_DAYS = 7
AUTO_BACKUP_KEEP = 5


def _auto_backup(force: bool = False) -> dict:
    """自动备份到 data/auto-backups/，保留最近 N 份。启动时检查，超期才执行。"""
    auto_dir = config.DATA_DIR / AUTO_BACKUP_DIR_NAME
    auto_dir.mkdir(parents=True, exist_ok=True)
    if not force:
        if not config.DB_PATH.exists():
            return {"skipped": "数据库不存在"}
        import os
        from datetime import datetime as dt
        mtime = dt.fromtimestamp(config.DB_PATH.stat().st_mtime)
        backups = sorted(auto_dir.glob("*.zip"))
        if backups and (dt.now() - mtime).days < AUTO_BACKUP_INTERVAL_DAYS:
            return {"skipped": "近期已备份"}
    # 生成备份
    _checkpoint_db()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if config.DB_PATH.exists():
            zf.write(config.DB_PATH, "sci.db")
        if config.FILES_DIR.exists():
            for f in config.FILES_DIR.rglob("*"):
                if f.is_file():
                    zf.write(f, f"files/{f.relative_to(config.FILES_DIR)}")
        zf.writestr("meta.json", json.dumps({
            "app": "sciplat", "version": META_VERSION,
            "exported_at": datetime.now().isoformat(), "type": "auto",
        }, ensure_ascii=False))
    fname = f"auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    (auto_dir / fname).write_bytes(buf.getvalue())
    # 清理旧备份
    backups = sorted(auto_dir.glob("*.zip"))
    for old in backups[:-AUTO_BACKUP_KEEP]:
        old.unlink()
    return {"created": fname, "kept": len(backups[-AUTO_BACKUP_KEEP:])}


@router.get("/auto-list")
def auto_backup_list():
    """列出自动备份文件。"""
    auto_dir = config.DATA_DIR / AUTO_BACKUP_DIR_NAME
    items = []
    if auto_dir.exists():
        for f in sorted(auto_dir.glob("*.zip"), reverse=True):
            items.append({"name": f.name, "size": f.stat().st_size,
                          "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
    return {"interval_days": AUTO_BACKUP_INTERVAL_DAYS, "keep": AUTO_BACKUP_KEEP, "items": items}
