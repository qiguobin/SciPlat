"""全库备份与恢复：zip 导出（db + files + meta），恢复前自动备份当前库。"""
import hashlib
import io
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import config
from ..database import engine, get_db

router = APIRouter(prefix="/api/backup", tags=["backup"])

META_VERSION = "0.3.0"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _do_restore(data: bytes, password: str = "", sha256: str = "") -> dict:
    """恢复核心流程（本地上传 / WebDAV 云端恢复共用）。"""
    if not data:
        raise HTTPException(400, "空文件")
    if sha256 and _sha256_hex(data).lower() != sha256.lower():
        raise HTTPException(400, "SHA256 校验失败：备份文件已损坏或被篡改")
    if password:
        from ..services import crypto
        from cryptography.fernet import InvalidToken

        try:
            data = crypto.decrypt_bytes(data, password)
        except InvalidToken:
            raise HTTPException(400, "密码错误或备份文件已损坏") from None

    tmp = config.DATA_DIR / "_restore_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(tmp)
        db_file = tmp / "sci.db"
        if not db_file.exists():
            raise HTTPException(400, "备份包中缺少 sci.db，无法恢复")
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_file))
            conn.execute("SELECT count(*) FROM sqlite_master")
            conn.close()
        except Exception as e:
            raise HTTPException(400, f"备份数据库损坏：{e}") from e
        _checkpoint_db()
        pre = config.DATA_DIR / f"pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        pre.mkdir(exist_ok=True)
        if config.DB_PATH.exists():
            shutil.copy2(config.DB_PATH, pre / "sci.db")
        if config.FILES_DIR.exists():
            shutil.copytree(config.FILES_DIR, pre / "files")
        shutil.rmtree(config.FILES_DIR, ignore_errors=True)
        if (tmp / "files").exists():
            shutil.copytree(tmp / "files", config.FILES_DIR)
        shutil.copy2(db_file, config.DB_PATH)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {
        "ok": True,
        "message": "恢复成功。请重启应用（关闭窗口后重新运行 start.bat）以加载新数据。",
        "pre_restore": pre.name,
    }


@router.post("/restore")
async def restore_backup(file: UploadFile, password: str = Form(""), sha256: str = Form("")):
    """从备份 zip 恢复：SHA256 校验（可选）→ 密码解密（.enc，可选）→ 解压校验 → 恢复。"""
    data = await file.read()
    return _do_restore(data, password, sha256)


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
    raw = buf.getvalue()
    (auto_dir / fname).write_bytes(raw)
    # SHA256 校验文件伴随生成
    (auto_dir / f"{fname}.sha256").write_text(_sha256_hex(raw), encoding="utf-8")
    # 清理旧备份（含校验文件）
    backups = sorted(auto_dir.glob("*.zip"))
    for old in backups[:-AUTO_BACKUP_KEEP]:
        old.unlink()
        (auto_dir / f"{old.name}.sha256").unlink(missing_ok=True)
    return {"created": fname, "kept": len(backups[-AUTO_BACKUP_KEEP:])}


@router.post("/encrypt")
def encrypt_backup(body: dict):
    """密码加密指定备份（auto-backups 内）：生成 {name}.enc，保留原文件。"""
    name = str(body.get("name") or "").strip()
    password = str(body.get("password") or "")
    if not name or not password:
        raise HTTPException(400, "请提供备份文件名与密码")
    src = config.DATA_DIR / AUTO_BACKUP_DIR_NAME / name
    if not src.exists() or not src.is_file():
        raise HTTPException(404, "备份文件不存在")
    from ..services import crypto

    enc = crypto.encrypt_bytes(src.read_bytes(), password)
    enc_path = src.with_suffix(src.suffix + ".enc")
    enc_path.write_bytes(enc)
    (config.DATA_DIR / AUTO_BACKUP_DIR_NAME / f"{enc_path.name}.sha256").write_text(
        _sha256_hex(enc), encoding="utf-8")
    return {"ok": True, "enc_name": enc_path.name, "message": "加密完成（原文件已保留，可自行删除）"}


@router.get("/auto-list")
def auto_backup_list():
    """列出自动备份文件（含 SHA256）。"""
    auto_dir = config.DATA_DIR / AUTO_BACKUP_DIR_NAME
    items = []
    if auto_dir.exists():
        for f in sorted(auto_dir.glob("*.zip*"), reverse=True):
            if f.suffix == ".sha256":
                continue
            sha = ""
            sf = auto_dir / f"{f.name}.sha256"
            if sf.exists():
                sha = sf.read_text(encoding="utf-8").strip()
            items.append({
                "name": f.name, "size": f.stat().st_size,
                "encrypted": f.suffix == ".enc",
                "sha256": sha,
                "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return {"interval_days": AUTO_BACKUP_INTERVAL_DAYS, "keep": AUTO_BACKUP_KEEP, "items": items}


# ================ WebDAV 云备份 ================
WEBDAV_KEYS = ("webdav_url", "webdav_user", "webdav_pass", "webdav_enabled")


def _webdav_cfg(db=None) -> dict:
    """读取 WebDAV 配置（密码解密）。"""
    from .. import models
    from ..database import SessionLocal
    from ..services import crypto

    own = db is None
    session = db or SessionLocal()
    try:
        def v(key: str) -> str:
            s = session.query(models.Setting).filter_by(key=key).first()
            return s.value if s else ""

        pwd_raw = v("webdav_pass")
        pwd = pwd_raw
        if pwd_raw:
            pwd = crypto.decrypt_text(pwd_raw)
        return {
            "url": v("webdav_url"),
            "user": v("webdav_user"),
            "pass": pwd,
            "enabled": v("webdav_enabled") == "1",
        }
    finally:
        if own:
            session.close()


def _save_webdav_cfg(body: dict, db) -> dict:
    from .. import models
    from ..services import crypto

    saved = {}
    for key, storage_key in (("url", "webdav_url"), ("user", "webdav_user"), ("pass", "webdav_pass"), ("enabled", "webdav_enabled")):
        if key not in body:
            continue
        value = str(body[key] or "")
        if key == "pass" and value:
            value = crypto.encrypt_text(value)
        if key == "enabled":
            value = "1" if body[key] else "0"
        s = db.query(models.Setting).filter_by(key=storage_key).first()
        if s:
            s.value = value
        else:
            db.add(models.Setting(key=storage_key, value=value))
        saved[storage_key] = value
    db.commit()
    return saved


@router.get("/webdav/settings")
def webdav_settings(db=Depends(get_db)):
    """读取 WebDAV 配置（密码解密返回，本地单机）。"""
    return _webdav_cfg()


@router.put("/webdav/settings")
def webdav_settings_save(body: dict, db=Depends(get_db)):
    _save_webdav_cfg(body, db)
    cfg = _webdav_cfg(db)
    return {"ok": True, **{k: cfg[k] for k in ("url", "user", "enabled")}}


@router.post("/webdav/test")
def webdav_test(body: dict, db=Depends(get_db)):
    from ..services import webdav

    url = str(body.get("url") or "").strip()
    user = str(body.get("user") or "").strip()
    password = str(body.get("pass") or "")
    if not url or not user:
        raise HTTPException(400, "请填写 WebDAV 地址与账号")
    ok, note = webdav.test_connection(url, user, password)
    if not ok:
        raise HTTPException(400, note)
    return {"ok": True, "note": note}


@router.post("/webdav/upload")
def webdav_upload(body: dict, db=Depends(get_db)):
    """上传备份到 WebDAV：优先上传最新自动备份，无则现场生成。"""
    from ..services import webdav

    cfg = _webdav_cfg(db)
    if not cfg["url"] or not cfg["user"]:
        raise HTTPException(400, "请先配置 WebDAV")
    if not cfg["enabled"]:
        raise HTTPException(400, "WebDAV 未启用（请在设置中开启）")
    name = str(body.get("name") or "").strip()
    if name:
        src = config.DATA_DIR / AUTO_BACKUP_DIR_NAME / name
        if not src.exists():
            raise HTTPException(404, "备份文件不存在")
        data = src.read_bytes()
    else:
        auto = _auto_backup(force=True)
        fname = auto.get("created")
        if not fname:
            raise HTTPException(400, "备份生成失败")
        src = config.DATA_DIR / AUTO_BACKUP_DIR_NAME / fname
        data = src.read_bytes()
        name = fname
    try:
        webdav.upload(cfg["url"], cfg["user"], cfg["pass"], name, data)
    except ValueError as e:
        raise HTTPException(502, str(e)) from e
    return {"ok": True, "name": name}


@router.get("/webdav/list")
def webdav_list(db=Depends(get_db)):
    from ..services import webdav

    cfg = _webdav_cfg(db)
    if not cfg["url"] or not cfg["user"]:
        raise HTTPException(400, "请先配置 WebDAV")
    try:
        return {"items": webdav.list_files(cfg["url"], cfg["user"], cfg["pass"])}
    except ValueError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/webdav/restore")
def webdav_restore(body: dict, db=Depends(get_db)):
    """从 WebDAV 云端备份恢复（支持加密包 + 密码）。"""
    from ..services import webdav

    cfg = _webdav_cfg(db)
    name = str(body.get("name") or "").strip()
    password = str(body.get("password") or "")
    if not cfg["url"] or not cfg["user"]:
        raise HTTPException(400, "请先配置 WebDAV")
    if not name:
        raise HTTPException(400, "请选择云端备份文件")
    try:
        data = webdav.download(cfg["url"], cfg["user"], cfg["pass"], name)
    except ValueError as e:
        raise HTTPException(502, str(e)) from e
    return _do_restore(data, password=password)
