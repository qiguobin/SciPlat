"""科研材料管理：上传/下载/预览/元数据编辑。"""
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import storage

router = APIRouter(prefix="/api/materials", tags=["materials"])

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
TEXT_EXTS = {
    ".txt", ".md", ".py", ".c", ".cpp", ".h", ".java", ".js", ".ts", ".json",
    ".tex", ".csv", ".yml", ".yaml", ".xml", ".html", ".css", ".sh", ".bat", ".r", ".sql", ".log",
}


def _get(db: Session, mid: int) -> models.Material:
    m = db.get(models.Material, mid)
    if not m:
        raise HTTPException(404, "材料不存在")
    return m


def _out(m: models.Material) -> schemas.MaterialOut:
    return schemas.MaterialOut(
        id=m.id,
        project_id=m.project_id,
        project_title=m.project.title if m.project else None,
        category=m.category,
        name=m.name,
        description=m.description,
        tags=m.tags,
        file_name=m.file_name,
        size=m.size,
        mime=m.mime,
        created_at=m.created_at,
    )


def _delete_file(rel: str) -> None:
    try:
        storage.storage.delete(rel)
    except (ValueError, OSError):
        pass


@router.get("")
def list_materials(
    project_id: Optional[int] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Material)
    if project_id:
        query = query.filter(models.Material.project_id == project_id)
    if category:
        query = query.filter(models.Material.category == category)
    if q:
        kw = f"%{q}%"
        query = query.filter(
            models.Material.name.like(kw)
            | models.Material.tags.like(kw)
            | models.Material.description.like(kw)
        )
    materials = query.order_by(models.Material.created_at.desc()).all()
    return [_out(m) for m in materials]


@router.post("")
async def upload_materials(
    files: List[UploadFile],
    project_id: Optional[int] = Form(None),
    category: str = Form("其他"),
    tags: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    """批量上传：每个文件生成一条材料记录；同项目同名文件视为覆盖更新（旧文件入版本库）。"""
    created = []
    for f in files:
        data = await f.read()
        if not f.filename:
            continue
        safe_name = Path(f.filename).name
        # 同名覆盖：保留历史版本
        existing = (
            db.query(models.Material)
            .filter(models.Material.project_id == project_id, models.Material.file_name == safe_name)
            .first()
        )
        rel, _ = storage.storage.save(data, f.filename)
        if existing:
            vno = (db.query(models.MaterialVersion).filter_by(material_id=existing.id).count() or 0) + 1
            db.add(models.MaterialVersion(
                material_id=existing.id, version_no=vno,
                file_name=existing.file_name, stored_path=existing.stored_path, size=existing.size,
            ))
            existing.file_name = safe_name
            existing.stored_path = rel
            existing.size = len(data)
            existing.mime = f.content_type or ""
            existing.name = Path(f.filename).stem
            existing.category = category
            existing.tags = tags
            if description:
                existing.description = description
            db.commit()
            db.refresh(existing)
            created.append(_out(existing))
            continue
        m = models.Material(
            project_id=project_id,
            category=category,
            name=Path(f.filename).stem,
            description=description,
            tags=tags,
            file_name=safe_name,
            stored_path=rel,
            size=len(data),
            mime=f.content_type or "",
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        created.append(_out(m))
    return created


@router.get("/{mid}/download")
def download_material(mid: int, db: Session = Depends(get_db)):
    m = _get(db, mid)
    path = storage.storage.abs_path(m.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    disposition = f"attachment; filename*=UTF-8''{quote(m.file_name)}"
    return FileResponse(path, media_type="application/octet-stream", headers={"Content-Disposition": disposition})


@router.get("/{mid}/preview")
def preview_material(mid: int, db: Session = Depends(get_db)):
    """在线预览：PDF/图片直接内嵌，文本类返回内容，其余类型提示下载。"""
    m = _get(db, mid)
    path = storage.storage.abs_path(m.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    ext = Path(m.file_name).suffix.lower()
    if ext == ".pdf" or ext in IMAGE_EXTS:
        media_type = m.mime or ("application/pdf" if ext == ".pdf" else "image/*")
        return FileResponse(path, media_type=media_type)
    if ext in TEXT_EXTS:
        content = path.read_bytes()[: 512 * 1024].decode("utf-8", errors="replace")
        return PlainTextResponse(content)
    raise HTTPException(415, "该类型不支持在线预览，请下载查看")


@router.put("/{mid}")
def update_material(mid: int, body: schemas.MaterialUpdate, db: Session = Depends(get_db)):
    m = _get(db, mid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return _out(m)


@router.delete("/{mid}")
def delete_material(mid: int, db: Session = Depends(get_db)):
    m = _get(db, mid)
    _delete_file(m.stored_path)
    for v in db.query(models.MaterialVersion).filter_by(material_id=mid).all():
        _delete_file(v.stored_path)
    db.delete(m)
    db.commit()
    return {"ok": True}


# ---------- 历史版本 ----------
@router.get("/{mid}/versions", response_model=list[schemas.MaterialVersionOut])
def list_versions(mid: int, db: Session = Depends(get_db)):
    _get(db, mid)
    versions = db.query(models.MaterialVersion).filter_by(material_id=mid).order_by(models.MaterialVersion.version_no.desc()).all()
    return versions


@router.post("/{mid}/versions/{vid}/restore", response_model=schemas.MaterialOut)
def restore_version(mid: int, vid: int, db: Session = Depends(get_db)):
    """回滚到历史版本：当前文件入版本库，版本文件提升为主记录。"""
    m = _get(db, mid)
    v = db.get(models.MaterialVersion, vid)
    if not v or v.material_id != mid:
        raise HTTPException(404, "版本不存在")
    # 当前文件存入新版本
    if m.stored_path:
        vno = (db.query(models.MaterialVersion).filter_by(material_id=mid).count() or 0) + 1
        db.add(models.MaterialVersion(
            material_id=mid, version_no=vno, file_name=m.file_name,
            stored_path=m.stored_path, size=m.size,
        ))
    # 版本文件提升
    m.file_name = v.file_name
    m.stored_path = v.stored_path
    m.size = v.size
    db.delete(v)
    db.commit()
    db.refresh(m)
    return _out(m)


@router.delete("/versions/{vid}")
def delete_version(vid: int, db: Session = Depends(get_db)):
    v = db.get(models.MaterialVersion, vid)
    if not v:
        raise HTTPException(404, "版本不存在")
    _delete_file(v.stored_path)
    db.delete(v)
    db.commit()
    return {"ok": True}


@router.get("/versions/{vid}/download")
def download_version(vid: int, db: Session = Depends(get_db)):
    v = db.get(models.MaterialVersion, vid)
    if not v:
        raise HTTPException(404, "版本不存在")
    from fastapi.responses import FileResponse
    path = storage.storage.abs_path(v.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    disposition = f"attachment; filename*=UTF-8''{quote(v.file_name)}"
    return FileResponse(path, media_type="application/octet-stream", headers={"Content-Disposition": disposition})
