"""笔记：reference（阅读笔记）/ project（实验记录）+ 双链 [[标题]] 解析。"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/notes", tags=["notes"])

LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")  # 双链语法


def _resolve_target(db: Session, title: str) -> dict | None:
    """把 [[标题]] 解析为可跳转对象。"""
    t = title.strip()
    ref = db.query(models.Reference).filter(models.Reference.title == t).first()
    if ref:
        return {"type": "reference", "id": ref.id, "link": "/references"}
    proj = db.query(models.Project).filter(models.Project.title == t).first()
    if proj:
        return {"type": "project", "id": proj.id, "link": f"/projects/{proj.id}"}
    note = db.query(models.Note).filter(models.Note.content.like(f"%{t}%")).first()
    if note:
        return {"type": "note", "id": note.id, "link": None}
    # 模糊匹配候选
    candidates = []
    for r in db.query(models.Reference).filter(models.Reference.title.like(f"%{t}%")).limit(3).all():
        candidates.append({"type": "reference", "id": r.id, "title": r.title})
    return {"candidates": candidates} if candidates else None


@router.get("/backlinks")
def backlinks(target: str, db: Session = Depends(get_db)):
    """反向链接：哪些笔记引用了 [[target]]。"""
    kw = f"%[[{target}]]%"
    notes = db.query(models.Note).filter(models.Note.content.like(kw)).all()
    return [{
        "id": n.id,
        "target_type": n.target_type,
        "target_id": n.target_id,
        "content": n.content[:200],
        "updated_at": n.updated_at.isoformat(),
    } for n in notes]


@router.get("/graph")
def graph(db: Session = Depends(get_db)):
    """双链知识网络：笔记节点 + 笔记→对象 的引用边。"""
    refs = {r.id: r.title for r in db.query(models.Reference).all()}
    projects = {p.id: p.title for p in db.query(models.Project).all()}
    notes = db.query(models.Note).all()

    nodes: dict[str, dict] = {}
    links: list[dict] = []

    def _add_node(key: str, label: str, kind: str) -> None:
        if key not in nodes:
            nodes[key] = {"key": key, "label": label, "kind": kind}

    for n in notes:
        _add_node(f"note:{n.id}", f"📝 {n.content[:24]}", "note")
        for m in LINK_RE.finditer(n.content):
            title = m.group(1).strip()
            if title in refs.values():
                rid = next(k for k, v in refs.items() if v == title)
                _add_node(f"ref:{rid}", f"📄 {title[:24]}", "reference")
                links.append({"source": f"note:{n.id}", "target": f"ref:{rid}"})
            elif title in projects.values():
                pid = next(k for k, v in projects.items() if v == title)
                _add_node(f"proj:{pid}", f"📁 {title[:24]}", "project")
                links.append({"source": f"note:{n.id}", "target": f"proj:{pid}"})
            else:
                _add_node(f"topic:{title}", f"🏷 {title[:24]}", "topic")
                links.append({"source": f"note:{n.id}", "target": f"topic:{title}"})

    return {"nodes": list(nodes.values()), "links": links}


@router.get("")
def list_notes(target_type: str, target_id: int, db: Session = Depends(get_db)):
    notes = (
        db.query(models.Note)
        .filter(models.Note.target_type == target_type, models.Note.target_id == target_id)
        .order_by(models.Note.created_at.desc())
        .all()
    )
    return [schemas.NoteOut.model_validate(n) for n in notes]


@router.post("")
def create_note(body: schemas.NoteCreate, db: Session = Depends(get_db)):
    n = models.Note(**body.model_dump())
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.put("/{nid}")
def update_note(nid: int, body: schemas.NoteUpdate, db: Session = Depends(get_db)):
    n = db.get(models.Note, nid)
    if not n:
        raise HTTPException(404, "笔记不存在")
    n.content = body.content
    n.updated_at = datetime.now()
    db.commit()
    db.refresh(n)
    return n


@router.delete("/{nid}")
def delete_note(nid: int, db: Session = Depends(get_db)):
    n = db.get(models.Note, nid)
    if not n:
        raise HTTPException(404, "笔记不存在")
    db.delete(n)
    db.commit()
    return {"ok": True}
