"""系统通知：操作记录上报、列表、已读。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

KEEP_LIMIT = 200  # 最多保留条数


@router.get("")
def list_notifications(limit: int = 30, db: Session = Depends(get_db)):
    """通知列表：未读优先，按时间倒序。"""
    items = db.query(models.Notification).order_by(
        models.Notification.read_at.is_(None).desc(),
        models.Notification.created_at.desc(),
    ).limit(limit).all()
    unread = db.query(models.Notification).filter(models.Notification.read_at.is_(None)).count()
    return {
        "unread": unread,
        "items": [{
            "id": n.id, "message": n.message, "category": n.category,
            "target_type": n.target_type, "target_id": n.target_id,
            "read": n.read_at is not None,
            "created_at": n.created_at.isoformat(),
        } for n in items],
    }


@router.post("")
def create_notification(body: dict, db: Session = Depends(get_db)):
    """前端写操作成功后自动上报（fire-and-forget）。"""
    message = str(body.get("message", ""))[:300]
    if not message:
        raise HTTPException(400, "缺少消息内容")
    n = models.Notification(
        message=message,
        category=str(body.get("category", "info"))[:20],
        target_type=str(body.get("target_type", ""))[:30],
        target_id=int(body["target_id"]) if body.get("target_id") else None,
    )
    db.add(n)
    db.commit()
    # 清理超出保留上限的旧通知
    total = db.query(models.Notification).count()
    if total > KEEP_LIMIT:
        overflow = db.query(models.Notification).order_by(models.Notification.created_at).limit(total - KEEP_LIMIT).all()
        for o in overflow:
            db.delete(o)
        db.commit()
    return {"ok": True, "id": n.id}


@router.post("/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db)):
    n = db.get(models.Notification, nid)
    if not n:
        raise HTTPException(404, "通知不存在")
    n.read_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db)):
    now = datetime.now()
    for n in db.query(models.Notification).filter(models.Notification.read_at.is_(None)).all():
        n.read_at = now
    db.commit()
    return {"ok": True}
