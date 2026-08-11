"""待办事项：日历待办、状态流转、科研动态事件链。"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/todos", tags=["todos"])

VALID_STATUS = ("待办", "进行中", "已完成")
VALID_REPEAT = ("none", "daily", "weekly")


def _get(db: Session, tid: int) -> models.Todo:
    t = db.get(models.Todo, tid)
    if not t:
        raise HTTPException(404, "待办不存在")
    return t


def _out(t: models.Todo) -> schemas.TodoOut:
    return schemas.TodoOut(
        id=t.id,
        date=t.date,
        title=t.title,
        description=t.description,
        status=t.status,
        priority=t.priority,
        project_id=t.project_id,
        project_title=t.project.title if t.project else None,
        repeat=t.repeat,
        created_at=t.created_at,
        completed_at=t.completed_at,
    )


def _spawn_next(t: models.Todo) -> None:
    """完成重复待办时生成下一周期实例。"""
    if t.repeat == "daily":
        nxt = t.date + timedelta(days=1)
    elif t.repeat == "weekly":
        nxt = t.date + timedelta(days=7)
    else:
        return
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        exists = db.query(models.Todo).filter(
            models.Todo.date == nxt, models.Todo.title == t.title
        ).first()
        if not exists:
            db.add(models.Todo(
                date=nxt, title=t.title, description=t.description,
                status="待办", priority=t.priority, project_id=t.project_id, repeat=t.repeat,
            ))
            db.commit()
    finally:
        db.close()


@router.get("")
def list_todos(
    date_: Optional[date] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    status: Optional[str] = None,
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Todo)
    if date_:
        query = query.filter(models.Todo.date == date_)
    if start:
        query = query.filter(models.Todo.date >= start)
    if end:
        query = query.filter(models.Todo.date < end)
    if status:
        query = query.filter(models.Todo.status == status)
    if project_id:
        query = query.filter(models.Todo.project_id == project_id)
    todos = query.order_by(models.Todo.date.desc(), models.Todo.created_at.desc()).all()
    return [_out(t) for t in todos]


@router.get("/stats")
def todo_stats(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    """待办完成率统计（可按项目）。"""
    query = db.query(models.Todo)
    if project_id:
        query = query.filter(models.Todo.project_id == project_id)
    todos = query.all()
    done = sum(1 for t in todos if t.status == "已完成")
    total = len(todos)
    return {"total": total, "done": done, "pending": total - done, "rate": round(done / total * 100) if total else 0}


@router.get("/activity", response_model=list[schemas.TodoOut])
def activity(days: int = 14, db: Session = Depends(get_db)):
    """科研动态事件链：近 N 天新增/完成/更新的待办，按时间倒序。"""
    since = datetime.now().date() - timedelta(days=days)
    todos = (
        db.query(models.Todo)
        .filter(models.Todo.date >= since)
        .order_by(models.Todo.completed_at.desc(), models.Todo.created_at.desc())
        .all()
    )
    return [_out(t) for t in todos]


@router.post("", response_model=schemas.TodoOut)
def create_todo(body: schemas.TodoCreate, db: Session = Depends(get_db)):
    if body.status not in VALID_STATUS:
        raise HTTPException(400, f"非法状态：{body.status}")
    if body.repeat not in VALID_REPEAT:
        raise HTTPException(400, f"非法重复规则：{body.repeat}")
    t = models.Todo(
        **body.model_dump(),
        completed_at=datetime.now() if body.status == "已完成" else None,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _out(t)


@router.put("/{tid}", response_model=schemas.TodoOut)
def update_todo(tid: int, body: schemas.TodoUpdate, db: Session = Depends(get_db)):
    t = _get(db, tid)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in VALID_STATUS:
        raise HTTPException(400, f"非法状态：{data['status']}")
    if "repeat" in data and data["repeat"] not in VALID_REPEAT:
        raise HTTPException(400, f"非法重复规则：{data['repeat']}")
    if "status" in data:
        t.completed_at = datetime.now() if data["status"] == "已完成" else None
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return _out(t)


@router.patch("/{tid}/status", response_model=schemas.TodoOut)
def change_status(tid: int, body: schemas.TodoStatusChange, db: Session = Depends(get_db)):
    t = _get(db, tid)
    if body.status not in VALID_STATUS:
        raise HTTPException(400, f"非法状态：{body.status}")
    t.status = body.status
    t.completed_at = datetime.now() if body.status == "已完成" else None
    db.commit()
    if body.status == "已完成":
        _spawn_next(t)  # 重复待办：生成下一周期实例
    db.refresh(t)
    return _out(t)


@router.delete("/{tid}")
def delete_todo(tid: int, db: Session = Depends(get_db)):
    t = _get(db, tid)
    db.delete(t)
    db.commit()
    return {"ok": True}
