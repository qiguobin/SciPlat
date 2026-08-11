"""学生信息：单例行档案 + 头像上传。"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import storage

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _get_or_create(db: Session) -> models.StudentProfile:
    p = db.query(models.StudentProfile).first()
    if not p:
        p = models.StudentProfile()
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


@router.get("", response_model=schemas.ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    return _get_or_create(db)


@router.put("", response_model=schemas.ProfileOut)
def update_profile(body: schemas.ProfileUpdate, db: Session = Depends(get_db)):
    p = _get_or_create(db)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.post("/photo", response_model=schemas.ProfileOut)
async def upload_photo(file: UploadFile, db: Session = Depends(get_db)):
    p = _get_or_create(db)
    if p.photo_path:
        try:
            storage.storage.delete(p.photo_path)
        except (ValueError, OSError):
            pass
    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")
    rel, safe = storage.storage.save(data, file.filename or "avatar.png")
    p.photo_path = rel
    db.commit()
    db.refresh(p)
    return p


@router.get("/photo")
def get_photo(db: Session = Depends(get_db)):
    p = _get_or_create(db)
    if not p.photo_path:
        raise HTTPException(404, "未设置头像")
    from fastapi.responses import FileResponse
    path = storage.storage.abs_path(p.photo_path)
    if not path.exists():
        raise HTTPException(404, "头像文件缺失")
    return FileResponse(path)
