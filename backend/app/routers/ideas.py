"""灵感收集箱：快速捕获 → 一键转为待办或实验记录。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/ideas", tags=["ideas"])

VALID_STATUS = ("待处理", "已转化", "搁置")


def _get(db: Session, iid: int) -> models.Idea:
    i = db.get(models.Idea, iid)
    if not i:
        raise HTTPException(404, "灵感不存在")
    return i


@router.get("")
def list_ideas(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Idea)
    if status:
        query = query.filter(models.Idea.status == status)
    ideas = query.order_by(models.Idea.created_at.desc()).all()
    return [schemas.IdeaOut.model_validate(i) for i in ideas]


@router.post("", response_model=schemas.IdeaOut)
def create_idea(body: schemas.IdeaCreate, db: Session = Depends(get_db)):
    i = models.Idea(**body.model_dump())
    db.add(i)
    db.commit()
    db.refresh(i)
    return i


@router.put("/{iid}", response_model=schemas.IdeaOut)
def update_idea(iid: int, body: schemas.IdeaUpdate, db: Session = Depends(get_db)):
    i = _get(db, iid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(i, k, v)
    db.commit()
    db.refresh(i)
    return i


@router.delete("/{iid}")
def delete_idea(iid: int, db: Session = Depends(get_db)):
    i = _get(db, iid)
    db.delete(i)
    db.commit()
    return {"ok": True}


@router.post("/{iid}/convert")
def convert_idea(iid: int, body: schemas.IdeaConvertBody, db: Session = Depends(get_db)):
    """一键转化：转为待办（todo）或实验记录（experiment）。"""
    i = _get(db, iid)
    created: dict = {}
    if body.target == "todo":
        todo = models.Todo(
            date=body.date or date.today(),
            title=i.content[:200],
            description=i.content,
            priority=body.priority,
            project_id=body.project_id,
        )
        db.add(todo)
        db.commit()
        db.refresh(todo)
        created = {"type": "todo", "id": todo.id}
    elif body.target == "experiment":
        if not body.phase_id:
            raise HTTPException(400, "转为实验记录需要指定项目阶段 phase_id")
        phase = db.get(models.ProjectPhase, body.phase_id)
        if not phase:
            raise HTTPException(404, "项目阶段不存在")
        exp = models.PhaseExperiment(
            phase_id=body.phase_id,
            title=i.content[:200],
            date=body.date or date.today(),
            method=i.content,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        created = {"type": "experiment", "id": exp.id}
    else:
        raise HTTPException(400, "target 仅支持 todo / experiment")

    i.status = "已转化"
    db.commit()
    return {"ok": True, "created": created}
