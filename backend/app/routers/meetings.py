"""导师沟通记录：会议纪要 + action_items（可转为待办）。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/advisor-meetings", tags=["meetings"])


def _get(db: Session, mid: int) -> models.AdvisorMeeting:
    m = db.get(models.AdvisorMeeting, mid)
    if not m:
        raise HTTPException(404, "沟通记录不存在")
    return m


@router.get("")
def list_meetings(db: Session = Depends(get_db)):
    meetings = db.query(models.AdvisorMeeting).order_by(models.AdvisorMeeting.date.desc()).all()
    return [schemas.MeetingOut.model_validate(m) for m in meetings]


@router.post("", response_model=schemas.MeetingOut)
def create_meeting(body: schemas.MeetingCreate, db: Session = Depends(get_db)):
    m = models.AdvisorMeeting(**body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.put("/{mid}", response_model=schemas.MeetingOut)
def update_meeting(mid: int, body: schemas.MeetingUpdate, db: Session = Depends(get_db)):
    m = _get(db, mid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{mid}")
def delete_meeting(mid: int, db: Session = Depends(get_db)):
    m = _get(db, mid)
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.post("/{mid}/actions/{idx}/convert")
def convert_action(mid: int, idx: int, db: Session = Depends(get_db)):
    """将导师意见（action_items[idx]）转为待办。"""
    m = _get(db, mid)
    if idx < 0 or idx >= len(m.action_items or []):
        raise HTTPException(404, "意见条目不存在")
    item = m.action_items[idx]
    todo = models.Todo(date=date.today(), title=item[:200], description=item)
    db.add(todo)
    db.commit()
    db.refresh(todo)
    # 标记该条意见已转化（前缀 ✓）—— JSON 列需整体重新赋值才触发变更检测
    items = list(m.action_items or [])
    items[idx] = f"✓ {item}" if not item.startswith("✓") else item
    m.action_items = items
    db.commit()
    return {"ok": True, "todo_id": todo.id}
