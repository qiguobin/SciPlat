"""写作字数打卡。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/writing-logs", tags=["writing"])


def _get(db: Session, wid: int) -> models.WritingLog:
    w = db.get(models.WritingLog, wid)
    if not w:
        raise HTTPException(404, "打卡记录不存在")
    return w


@router.get("")
def list_logs(
    start: Optional[date] = None,
    end: Optional[date] = None,
    paper_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.WritingLog)
    if start:
        query = query.filter(models.WritingLog.date >= start)
    if end:
        query = query.filter(models.WritingLog.date < end)
    if paper_id:
        query = query.filter(models.WritingLog.paper_id == paper_id)
    logs = query.order_by(models.WritingLog.date.desc()).all()
    return [schemas.WritingLogOut.model_validate(w) for w in logs]


@router.get("/streak")
def streak(db: Session = Depends(get_db)):
    """连续打卡天数：从今天（或昨天）往前数连续有打卡记录的天数。"""
    from datetime import timedelta

    dates = {w.date for w in db.query(models.WritingLog).all()}
    streak_days = 0
    d = date.today()
    if d not in dates:  # 今天没打卡，从昨天开始算
        d -= timedelta(days=1)
    while d in dates:
        streak_days += 1
        d -= timedelta(days=1)
    return {"streak": streak_days}


@router.post("", response_model=schemas.WritingLogOut)
def create_log(body: schemas.WritingLogCreate, db: Session = Depends(get_db)):
    w = models.WritingLog(**body.model_dump())
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@router.put("/{wid}", response_model=schemas.WritingLogOut)
def update_log(wid: int, body: schemas.WritingLogUpdate, db: Session = Depends(get_db)):
    w = _get(db, wid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    return w


@router.delete("/{wid}")
def delete_log(wid: int, db: Session = Depends(get_db)):
    w = _get(db, wid)
    db.delete(w)
    db.commit()
    return {"ok": True}
