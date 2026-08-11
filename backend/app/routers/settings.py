"""键值设置：写作周目标等。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _get_value(db: Session, key: str) -> str:
    s = db.query(models.Setting).filter_by(key=key).first()
    return s.value if s else ""


def _set_value(db: Session, key: str, value: str) -> None:
    s = db.query(models.Setting).filter_by(key=key).first()
    if s:
        s.value = value
    else:
        db.add(models.Setting(key=key, value=value))
    db.commit()


@router.get("/writing-goal")
def writing_goal(db: Session = Depends(get_db)):
    value = _get_value(db, "writing_goal")
    return {"goal": int(value) if value.isdigit() else 0}


@router.put("/writing-goal")
def set_writing_goal(body: dict, db: Session = Depends(get_db)):
    goal = max(0, int(body.get("goal", 0)))
    _set_value(db, "writing_goal", str(goal))
    return {"goal": goal}
