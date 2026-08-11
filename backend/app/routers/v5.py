"""V5 功能聚合路由：实验步骤/模板/评论、文献集合/关联/保存视图、资源库存、画布、统一模板、批量操作、提及、燃尽图。"""
import re
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api", tags=["v5"])


# ================ 实验步骤（eLabFTW Steps） ================
@router.get("/experiments/{eid}/steps", response_model=list[schemas.StepOut])
def list_steps(eid: int, db: Session = Depends(get_db)):
    exp = db.get(models.PhaseExperiment, eid)
    if not exp:
        raise HTTPException(404, "实验不存在")
    return db.query(models.ExperimentStep).filter_by(experiment_id=eid).order_by(models.ExperimentStep.order_no).all()


@router.post("/experiments/{eid}/steps", response_model=schemas.StepOut)
def create_step(eid: int, body: schemas.StepCreate, db: Session = Depends(get_db)):
    exp = db.get(models.PhaseExperiment, eid)
    if not exp:
        raise HTTPException(404, "实验不存在")
    s = models.ExperimentStep(experiment_id=eid, **body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.put("/experiments/steps/{sid}", response_model=schemas.StepOut)
def update_step(sid: int, body: schemas.StepUpdate, db: Session = Depends(get_db)):
    s = db.get(models.ExperimentStep, sid)
    if not s:
        raise HTTPException(404, "步骤不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/experiments/steps/{sid}")
def delete_step(sid: int, db: Session = Depends(get_db)):
    s = db.get(models.ExperimentStep, sid)
    if not s:
        raise HTTPException(404, "步骤不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/experiments/{eid}/progress")
def experiment_progress(eid: int, db: Session = Depends(get_db)):
    exp = db.get(models.PhaseExperiment, eid)
    if not exp:
        raise HTTPException(404, "实验不存在")
    steps = db.query(models.ExperimentStep).filter_by(experiment_id=eid).all()
    done = sum(1 for s in steps if s.status == "已完成")
    return {"total": len(steps), "done": done, "percent": round(done / len(steps) * 100) if steps else 0}


# ================ 实验模板库 ================
@router.get("/experiment-templates", response_model=list[schemas.ExperimentTemplateOut])
def list_templates(db: Session = Depends(get_db)):
    return db.query(models.ExperimentTemplate).order_by(models.ExperimentTemplate.category, models.ExperimentTemplate.title).all()


@router.post("/experiment-templates", response_model=schemas.ExperimentTemplateOut)
def create_template(body: schemas.ExperimentTemplateCreate, db: Session = Depends(get_db)):
    t = models.ExperimentTemplate(**body.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/experiment-templates/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db)):
    t = db.get(models.ExperimentTemplate, tid)
    if not t:
        raise HTTPException(404, "模板不存在")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("/experiment-templates/{tid}/apply")
def apply_template(tid: int, body: dict, db: Session = Depends(get_db)):
    """按模板创建实验（含步骤）：body={phase_id, title, date}。"""
    t = db.get(models.ExperimentTemplate, tid)
    if not t:
        raise HTTPException(404, "模板不存在")
    phase_id = int(body.get("phase_id", 0))
    if not db.get(models.ProjectPhase, phase_id):
        raise HTTPException(400, "phase_id 无效")
    b = t.body or {}
    exp = models.PhaseExperiment(
        phase_id=phase_id,
        title=body.get("title") or t.title,
        date=date.fromisoformat(body["date"]) if body.get("date") else date.today(),
        purpose=b.get("purpose", ""),
        method=b.get("method", ""),
        hypothesis=b.get("hypothesis", ""),
        variables=b.get("variables", ""),
        controls=b.get("controls", ""),
    )
    db.add(exp)
    db.flush()
    for i, st in enumerate(b.get("steps", [])):
        db.add(models.ExperimentStep(
            experiment_id=exp.id, title=st.get("title", ""),
            order_no=i, duration_min=st.get("duration_min"),
        ))
    db.commit()
    db.refresh(exp)
    return {"id": exp.id, "title": exp.title}


# ================ 实验评论 ================
@router.get("/experiments/{eid}/comments", response_model=list[schemas.CommentOut])
def list_comments(eid: int, db: Session = Depends(get_db)):
    if not db.get(models.PhaseExperiment, eid):
        raise HTTPException(404, "实验不存在")
    return db.query(models.ExperimentComment).filter_by(experiment_id=eid).order_by(models.ExperimentComment.created_at.desc()).all()


@router.post("/experiments/{eid}/comments", response_model=schemas.CommentOut)
def create_comment(eid: int, body: schemas.CommentCreate, db: Session = Depends(get_db)):
    if not db.get(models.PhaseExperiment, eid):
        raise HTTPException(404, "实验不存在")
    c = models.ExperimentComment(experiment_id=eid, content=body.content)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/experiments/comments/{cid}")
def delete_comment(cid: int, db: Session = Depends(get_db)):
    c = db.get(models.ExperimentComment, cid)
    if not c:
        raise HTTPException(404, "评论不存在")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ================ 文献集合（Zotero Collections） ================
@router.get("/collections")
def list_collections(db: Session = Depends(get_db)):
    cols = db.query(models.Collection).all()
    return [{"id": c.id, "name": c.name, "count": len(c.links)} for c in cols]


@router.post("/collections", response_model=schemas.CollectionOut)
def create_collection(body: schemas.CollectionCreate, db: Session = Depends(get_db)):
    if db.query(models.Collection).filter_by(name=body.name).first():
        raise HTTPException(400, "集合已存在")
    c = models.Collection(name=body.name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/collections/{cid}")
def delete_collection(cid: int, db: Session = Depends(get_db)):
    c = db.get(models.Collection, cid)
    if not c:
        raise HTTPException(404, "集合不存在")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/references/{rid}/collections")
def reference_collections(rid: int, db: Session = Depends(get_db)):
    if not db.get(models.Reference, rid):
        raise HTTPException(404, "文献不存在")
    links = db.query(models.ReferenceCollectionLink).filter_by(reference_id=rid).all()
    return [{"collection_id": l.collection_id, "name": l.collection.name} for l in links]


@router.post("/references/{rid}/collections")
def link_collection(rid: int, body: dict, db: Session = Depends(get_db)):
    """{collection_id, linked: bool} 加入/移出集合。"""
    if not db.get(models.Reference, rid):
        raise HTTPException(404, "文献不存在")
    cid = int(body.get("collection_id", 0))
    linked = bool(body.get("linked", True))
    link = db.query(models.ReferenceCollectionLink).filter_by(collection_id=cid, reference_id=rid).first()
    if linked and not link:
        db.add(models.ReferenceCollectionLink(collection_id=cid, reference_id=rid))
        db.commit()
    elif not linked and link:
        db.delete(link)
        db.commit()
    return {"ok": True}


# ================ 手动关联文献（Zotero Related） ================
@router.post("/references/{rid}/related")
def add_related(rid: int, body: schemas.RelatedLink, db: Session = Depends(get_db)):
    if rid == body.reference_id:
        raise HTTPException(400, "不能关联自身")
    if not db.get(models.Reference, body.reference_id):
        raise HTTPException(404, "文献不存在")
    exists = db.query(models.RelatedReference).filter(
        ((models.RelatedReference.ref_a == rid) & (models.RelatedReference.ref_b == body.reference_id))
        | ((models.RelatedReference.ref_a == body.reference_id) & (models.RelatedReference.ref_b == rid))
    ).first()
    if not exists:
        db.add(models.RelatedReference(ref_a=rid, ref_b=body.reference_id))
        db.commit()
    return {"ok": True}


@router.delete("/references/{rid}/related/{rid2}")
def remove_related(rid: int, rid2: int, db: Session = Depends(get_db)):
    link = db.query(models.RelatedReference).filter(
        ((models.RelatedReference.ref_a == rid) & (models.RelatedReference.ref_b == rid2))
        | ((models.RelatedReference.ref_a == rid2) & (models.RelatedReference.ref_b == rid))
    ).first()
    if not link:
        raise HTTPException(404, "关联不存在")
    db.delete(link)
    db.commit()
    return {"ok": True}


# ================ 保存的搜索视图 ================
@router.get("/saved-views")
def list_saved_views(db: Session = Depends(get_db)):
    return [{"id": v.id, "name": v.name, "filters": v.filters} for v in db.query(models.SavedView).order_by(models.SavedView.name).all()]


@router.post("/saved-views")
def create_saved_view(body: schemas.SavedViewCreate, db: Session = Depends(get_db)):
    v = models.SavedView(name=body.name, filters=body.filters)
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"id": v.id, "name": v.name, "filters": v.filters}


@router.delete("/saved-views/{vid}")
def delete_saved_view(vid: int, db: Session = Depends(get_db)):
    v = db.get(models.SavedView, vid)
    if not v:
        raise HTTPException(404, "视图不存在")
    db.delete(v)
    db.commit()
    return {"ok": True}


# ================ 资源库存（eLabFTW 资源库） ================
@router.get("/resources", response_model=list[schemas.ResourceOut])
def list_resources(db: Session = Depends(get_db)):
    resources = db.query(models.LabResource).order_by(models.LabResource.rtype, models.LabResource.name).all()
    # 自动状态：低库存 / 过期
    today = date.today()
    for r in resources:
        if r.expiry_date and r.expiry_date < today:
            r.status = "过期"
        elif r.low_threshold is not None and r.quantity <= r.low_threshold and r.status != "已耗尽":
            r.status = "低库存"
    return resources


@router.post("/resources", response_model=schemas.ResourceOut)
def create_resource(body: schemas.ResourceCreate, db: Session = Depends(get_db)):
    r = models.LabResource(**body.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.put("/resources/{rid}", response_model=schemas.ResourceOut)
def update_resource(rid: int, body: schemas.ResourceUpdate, db: Session = Depends(get_db)):
    r = db.get(models.LabResource, rid)
    if not r:
        raise HTTPException(404, "资源不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r


@router.post("/resources/{rid}/adjust")
def adjust_resource(rid: int, body: dict, db: Session = Depends(get_db)):
    """数量增减：{delta: -1 或 +5}（消耗/补充）。"""
    r = db.get(models.LabResource, rid)
    if not r:
        raise HTTPException(404, "资源不存在")
    delta = float(body.get("delta", 0))
    r.quantity = max(0, r.quantity + delta)
    if r.quantity == 0:
        r.status = "已耗尽"
    elif r.low_threshold is not None and r.quantity <= r.low_threshold:
        r.status = "低库存"
    else:
        r.status = "正常"
    db.commit()
    db.refresh(r)
    return schemas.ResourceOut.model_validate(r)


@router.delete("/resources/{rid}")
def delete_resource(rid: int, db: Session = Depends(get_db)):
    r = db.get(models.LabResource, rid)
    if not r:
        raise HTTPException(404, "资源不存在")
    db.delete(r)
    db.commit()
    return {"ok": True}


# ================ 科研画布（Obsidian Canvas） ================
@router.get("/canvas")
def get_canvas(db: Session = Depends(get_db)):
    nodes = db.query(models.CanvasNode).order_by(models.CanvasNode.id).all()
    edges = db.query(models.CanvasEdge).all()
    return {
        "nodes": [schemas.CanvasNodeOut.model_validate(n) for n in nodes],
        "edges": [schemas.CanvasEdgeOut.model_validate(e) for e in edges],
    }


@router.post("/canvas/nodes", response_model=schemas.CanvasNodeOut)
def create_canvas_node(body: schemas.CanvasNodeCreate, db: Session = Depends(get_db)):
    n = models.CanvasNode(**body.model_dump())
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.put("/canvas/nodes/{nid}", response_model=schemas.CanvasNodeOut)
def update_canvas_node(nid: int, body: schemas.CanvasNodeUpdate, db: Session = Depends(get_db)):
    n = db.get(models.CanvasNode, nid)
    if not n:
        raise HTTPException(404, "节点不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(n, k, v)
    db.commit()
    db.refresh(n)
    return n


@router.delete("/canvas/nodes/{nid}")
def delete_canvas_node(nid: int, db: Session = Depends(get_db)):
    n = db.get(models.CanvasNode, nid)
    if not n:
        raise HTTPException(404, "节点不存在")
    db.query(models.CanvasEdge).filter(
        (models.CanvasEdge.from_node == nid) | (models.CanvasEdge.to_node == nid)
    ).delete(synchronize_session=False)
    db.delete(n)
    db.commit()
    return {"ok": True}


@router.post("/canvas/edges", response_model=schemas.CanvasEdgeOut)
def create_canvas_edge(body: schemas.CanvasEdgeCreate, db: Session = Depends(get_db)):
    if body.from_node == body.to_node:
        raise HTTPException(400, "不能连接自身")
    e = models.CanvasEdge(from_node=body.from_node, to_node=body.to_node)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.delete("/canvas/edges/{eid}")
def delete_canvas_edge(eid: int, db: Session = Depends(get_db)):
    e = db.get(models.CanvasEdge, eid)
    if not e:
        raise HTTPException(404, "连线不存在")
    db.delete(e)
    db.commit()
    return {"ok": True}


# ================ 统一模板系统 ================
@router.get("/templates", response_model=list[schemas.TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    return db.query(models.Template).order_by(models.Template.ttype, models.Template.name).all()


@router.post("/templates", response_model=schemas.TemplateOut)
def create_template_global(body: schemas.TemplateCreate, db: Session = Depends(get_db)):
    t = models.Template(**body.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/templates/{tid}")
def delete_template_global(tid: int, db: Session = Depends(get_db)):
    t = db.get(models.Template, tid)
    if not t:
        raise HTTPException(404, "模板不存在")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ================ 材料批量操作 ================
@router.post("/materials/batch")
def batch_materials(body: dict, db: Session = Depends(get_db)):
    ids = [int(x) for x in body.get("ids", [])]
    action = body.get("action", "")
    if not ids:
        raise HTTPException(400, "未选择材料")
    materials = db.query(models.Material).filter(models.Material.id.in_(ids)).all()
    if action == "delete":
        for m in materials:
            if m.stored_path:
                try:
                    from ..services import storage
                    storage.storage.delete(m.stored_path)
                except (ValueError, OSError):
                    pass
            db.delete(m)
        db.commit()
        return {"ok": True, "deleted": len(materials)}
    if action == "category":
        category = body.get("category", "")
        if not category:
            raise HTTPException(400, "缺少分类")
        for m in materials:
            m.category = category
        db.commit()
        return {"ok": True, "updated": len(materials)}
    if action == "tags":
        tags = body.get("tags", "")
        for m in materials:
            existing = {t.strip() for t in (m.tags or "").split(",") if t.strip()}
            existing |= {t.strip() for t in tags.split(",") if t.strip()}
            m.tags = ", ".join(sorted(existing))
        db.commit()
        return {"ok": True, "updated": len(materials)}
    raise HTTPException(400, f"不支持的操作：{action}")


# ================ 未链接提及 ================
@router.get("/notes/mentions")
def note_mentions(note_id: int, db: Session = Depends(get_db)):
    """检测笔记文本中出现的文献/项目标题（未用 [[]] 包裹）→ 未链接提及。"""
    note = db.get(models.Note, note_id)
    if not note:
        raise HTTPException(404, "笔记不存在")
    linked = set(re.findall(r"\[\[([^\[\]]+)\]\]", note.content))
    text = re.sub(r"\[\[[^\[\]]+\]\]", "", note.content)
    mentions = []
    for r in db.query(models.Reference).all():
        if r.title in text and r.title not in linked:
            mentions.append({"type": "reference", "id": r.id, "title": r.title, "link": "/references"})
    for p in db.query(models.Project).all():
        if p.title in text and p.title not in linked:
            mentions.append({"type": "project", "id": p.id, "title": p.title, "link": f"/projects/{p.id}"})
    return {"mentions": mentions[:20]}


# ================ 燃尽图 ================
@router.get("/schedule/burndown")
def burndown(db: Session = Depends(get_db)):
    """本周燃尽图：本周内每日的剩余未完成待办数。"""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    days = []
    remaining = 0
    for i in range(7):
        d = monday + timedelta(days=i)
        day_todos = db.query(models.Todo).filter(models.Todo.date == d).all()
        # 今天之后未完成也算剩余
        remaining = sum(1 for t in day_todos if t.status != "已完成") if d > today else remaining
        total_created = db.query(models.Todo).filter(models.Todo.date <= d, models.Todo.date >= monday).count()
        done_so_far = db.query(models.Todo).filter(
            models.Todo.date >= monday, models.Todo.date <= d, models.Todo.status == "已完成"
        ).count()
        days.append({
            "date": d.isoformat(),
            "label": f"周{i + 1}",
            "remaining": max(0, total_created - done_so_far),
            "done": done_so_far,
        })
    return {"week_start": monday.isoformat(), "days": days}
