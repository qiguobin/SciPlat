"""项目管理：CRUD、里程碑、关键时间线、结构化导出（zip）、阶段化进展。"""
import io
import re
import zipfile
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..services import storage

router = APIRouter(prefix="/api/projects", tags=["projects"])

# 材料分类 -> 导出目录（与 ZCode 学术技能链文件组织约定对齐）
CATEGORY_DIR = {
    "数据": "data",
    "代码": "code",
    "图表": "figures",
    "实验记录": "docs",
    "文档": "docs",
    "其他": "other",
}

# 预置五阶段模板（创建项目时自动生成，可改名/增删）
DEFAULT_PHASES = ["开题设计", "初期想法验证", "实验阶段", "分析阶段", "总结与论文"]

_LOAD = (
    selectinload(models.Project.milestones),
    selectinload(models.Project.timeline_points),
    selectinload(models.Project.papers),
    selectinload(models.Project.materials),
    selectinload(models.Project.phases).selectinload(models.ProjectPhase.experiments),
    selectinload(models.Project.phases).selectinload(models.ProjectPhase.references),
    selectinload(models.Project.phases).selectinload(models.ProjectPhase.tasks),
)


def _get(db: Session, pid: int, detail: bool = False) -> models.Project:
    q = db.query(models.Project)
    if detail:
        q = q.options(*_LOAD)
    p = q.filter(models.Project.id == pid).first()
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


def _out(p: models.Project) -> schemas.ProjectOut:
    return schemas.ProjectOut(
        id=p.id,
        title=p.title,
        ptype=p.ptype,
        status=p.status,
        description=p.description,
        start_date=p.start_date,
        end_date=p.end_date,
        created_at=p.created_at,
        updated_at=p.updated_at,
        paper_count=len(p.papers),
        material_count=len(p.materials),
        milestone_count=len(p.milestones),
    )


def _delete_file(rel: str | None) -> None:
    if rel:
        try:
            storage.storage.delete(rel)
        except (ValueError, OSError):
            pass


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).options(*_LOAD).order_by(models.Project.updated_at.desc()).all()
    return [_out(p) for p in projects]


@router.post("")
def create_project(body: schemas.ProjectCreate, db: Session = Depends(get_db)):
    p = models.Project(**body.model_dump())
    db.add(p)
    db.flush()  # 拿到 id 再生成预置阶段
    for i, name in enumerate(DEFAULT_PHASES):
        db.add(models.ProjectPhase(project_id=p.id, name=name, sort_order=i, is_default=True))
    db.commit()
    db.refresh(p)
    return _out(p)


@router.get("/{pid}", response_model=schemas.ProjectDetailOut)
def get_project(pid: int, db: Session = Depends(get_db)):
    p = _get(db, pid, detail=True)
    phases = [
        schemas.PhaseDetailOut(
            **schemas.PhaseOut.model_validate(ph).model_dump(),
            experiments=[schemas.ExperimentOut.model_validate(e) for e in ph.experiments],
            reference_ids=[r.reference_id for r in ph.references],
            todo_ids=[t.todo_id for t in ph.tasks],
        )
        for ph in p.phases
    ]
    out = schemas.ProjectDetailOut(
        **_out(p).model_dump(),
        milestones=[schemas.MilestoneOut.model_validate(m) for m in p.milestones],
        timeline_points=[schemas.TimelineOut.model_validate(t) for t in p.timeline_points],
        papers=[schemas.PaperOut.model_validate(pa) for pa in p.papers],
        materials=[schemas.MaterialOut.model_validate(m) for m in p.materials],
        phases=phases,
    )
    return out


@router.put("/{pid}")
def update_project(pid: int, body: schemas.ProjectUpdate, db: Session = Depends(get_db)):
    p = _get(db, pid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.updated_at = datetime.now()
    db.commit()
    db.refresh(p)
    return _out(p)


@router.delete("/{pid}")
def delete_project(pid: int, db: Session = Depends(get_db)):
    p = _get(db, pid, detail=True)
    for m in p.materials:
        _delete_file(m.stored_path)
    for paper in p.papers:
        for v in paper.versions:
            _delete_file(v.stored_path)
        for r in paper.review_rounds:
            _delete_file(r.stored_path)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/{pid}/export")
def export_project(pid: int, db: Session = Depends(get_db)):
    """导出为结构化 zip：README.md 索引 + docs/data/code/figures/other 分类目录。"""
    p = _get(db, pid, detail=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", p.title)[:60] or "project"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        lines = [
            f"# {p.title}",
            "",
            f"- 类型：{p.ptype}｜状态：{p.status}",
            f"- 时间：{p.start_date or '—'} ~ {p.end_date or '—'}",
            f"- 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]
        if p.milestones:
            lines += ["## 里程碑", ""]
            lines += [f"- [{m.status}] {m.title}（{m.due_date}）{('：' + m.note) if m.note else ''}" for m in p.milestones]
            lines.append("")
        if p.papers:
            lines += ["## 关联论文", ""]
            lines += [f"- {pa.title}（{pa.status}）" for pa in p.papers]
            lines.append("")
        lines += ["## 材料清单", ""]
        for m in p.materials:
            lines.append(f"- [{m.category}] {m.name} → {m.file_name}（{m.size} bytes）")
        zf.writestr(f"{safe}/README.md", "\n".join(lines))

        for m in p.materials:
            sub = CATEGORY_DIR.get(m.category, "other")
            try:
                zf.write(storage.storage.abs_path(m.stored_path), f"{safe}/{sub}/{m.file_name}")
            except (FileNotFoundError, ValueError):
                zf.writestr(f"{safe}/{sub}/{m.file_name}", "[文件缺失]")

    buf.seek(0)
    fname = f"{safe}.zip"
    disposition = f"attachment; filename=\"export.zip\"; filename*=UTF-8''{quote(fname)}"
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": disposition})


# ---------- 里程碑 ----------
@router.post("/{pid}/milestones", response_model=schemas.MilestoneOut)
def create_milestone(pid: int, body: schemas.MilestoneCreate, db: Session = Depends(get_db)):
    _get(db, pid)
    m = models.Milestone(project_id=pid, **body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.put("/milestones/{mid}", response_model=schemas.MilestoneOut)
def update_milestone(mid: int, body: schemas.MilestoneUpdate, db: Session = Depends(get_db)):
    m = db.get(models.Milestone, mid)
    if not m:
        raise HTTPException(404, "里程碑不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/milestones/{mid}")
def delete_milestone(mid: int, db: Session = Depends(get_db)):
    m = db.get(models.Milestone, mid)
    if not m:
        raise HTTPException(404, "里程碑不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ---------- 关键时间线 ----------
@router.post("/{pid}/timeline", response_model=schemas.TimelineOut)
def create_timeline(pid: int, body: schemas.TimelineCreate, db: Session = Depends(get_db)):
    _get(db, pid)
    t = models.TimelinePoint(project_id=pid, **body.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.put("/timeline/{tid}", response_model=schemas.TimelineOut)
def update_timeline(tid: int, body: schemas.TimelineUpdate, db: Session = Depends(get_db)):
    t = db.get(models.TimelinePoint, tid)
    if not t:
        raise HTTPException(404, "时间线节点不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/timeline/{tid}")
def delete_timeline(tid: int, db: Session = Depends(get_db)):
    t = db.get(models.TimelinePoint, tid)
    if not t:
        raise HTTPException(404, "时间线节点不存在")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ---------- 项目阶段 ----------
@router.post("/{pid}/phases", response_model=schemas.PhaseOut)
def create_phase(pid: int, body: schemas.PhaseCreate, db: Session = Depends(get_db)):
    _get(db, pid)
    ph = models.ProjectPhase(project_id=pid, **body.model_dump())
    db.add(ph)
    db.commit()
    db.refresh(ph)
    return ph


@router.put("/phases/{phid}", response_model=schemas.PhaseOut)
def update_phase(phid: int, body: schemas.PhaseUpdate, db: Session = Depends(get_db)):
    ph = db.get(models.ProjectPhase, phid)
    if not ph:
        raise HTTPException(404, "阶段不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ph, k, v)
    db.commit()
    db.refresh(ph)
    return ph


@router.delete("/phases/{phid}")
def delete_phase(phid: int, db: Session = Depends(get_db)):
    ph = db.get(models.ProjectPhase, phid)
    if not ph:
        raise HTTPException(404, "阶段不存在")
    db.delete(ph)
    db.commit()
    return {"ok": True}


# ---------- 阶段实验记录 ----------
@router.post("/phases/{phid}/experiments", response_model=schemas.ExperimentOut)
def create_experiment(phid: int, body: schemas.ExperimentCreate, db: Session = Depends(get_db)):
    if not db.get(models.ProjectPhase, phid):
        raise HTTPException(404, "阶段不存在")
    e = models.PhaseExperiment(phase_id=phid, **body.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.put("/phases/experiments/{eid}", response_model=schemas.ExperimentOut)
def update_experiment(eid: int, body: schemas.ExperimentUpdate, db: Session = Depends(get_db)):
    e = db.get(models.PhaseExperiment, eid)
    if not e:
        raise HTTPException(404, "实验记录不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    return e


@router.delete("/phases/experiments/{eid}")
def delete_experiment(eid: int, db: Session = Depends(get_db)):
    e = db.get(models.PhaseExperiment, eid)
    if not e:
        raise HTTPException(404, "实验记录不存在")
    db.delete(e)
    db.commit()
    return {"ok": True}


# ---------- 阶段-文献证据 ----------
@router.post("/phases/{phid}/references")
def link_reference(phid: int, body: schemas.PhaseRefLink, db: Session = Depends(get_db)):
    if not db.get(models.ProjectPhase, phid):
        raise HTTPException(404, "阶段不存在")
    if not db.get(models.Reference, body.reference_id):
        raise HTTPException(404, "文献不存在")
    exists = (
        db.query(models.PhaseReference)
        .filter_by(phase_id=phid, reference_id=body.reference_id)
        .first()
    )
    if not exists:
        db.add(models.PhaseReference(phase_id=phid, reference_id=body.reference_id))
        db.commit()
    return {"ok": True}


@router.delete("/phases/{phid}/references/{rid}")
def unlink_reference(phid: int, rid: int, db: Session = Depends(get_db)):
    link = (
        db.query(models.PhaseReference)
        .filter_by(phase_id=phid, reference_id=rid)
        .first()
    )
    if not link:
        raise HTTPException(404, "关联不存在")
    db.delete(link)
    db.commit()
    return {"ok": True}


# ---------- 阶段-关联任务 ----------
@router.post("/phases/{phid}/tasks")
def link_task(phid: int, body: schemas.PhaseTaskLink, db: Session = Depends(get_db)):
    if not db.get(models.ProjectPhase, phid):
        raise HTTPException(404, "阶段不存在")
    if not db.get(models.Todo, body.todo_id):
        raise HTTPException(404, "待办不存在")
    exists = (
        db.query(models.PhaseTask)
        .filter_by(phase_id=phid, todo_id=body.todo_id)
        .first()
    )
    if not exists:
        db.add(models.PhaseTask(phase_id=phid, todo_id=body.todo_id))
        db.commit()
    return {"ok": True}


@router.delete("/phases/{phid}/tasks/{tid}")
def unlink_task(phid: int, tid: int, db: Session = Depends(get_db)):
    link = db.query(models.PhaseTask).filter_by(phase_id=phid, todo_id=tid).first()
    if not link:
        raise HTTPException(404, "关联不存在")
    db.delete(link)
    db.commit()
    return {"ok": True}


# ---------- 结项复盘 ----------
@router.get("/{pid}/review", response_model=schemas.ReviewOut)
def get_review(pid: int, db: Session = Depends(get_db)):
    _get(db, pid)
    r = db.query(models.ProjectReview).filter_by(project_id=pid).first()
    if not r:
        r = models.ProjectReview(project_id=pid)
        db.add(r)
        db.commit()
        db.refresh(r)
    return r


@router.put("/{pid}/review", response_model=schemas.ReviewOut)
def update_review(pid: int, body: schemas.ReviewUpdate, db: Session = Depends(get_db)):
    _get(db, pid)
    r = db.query(models.ProjectReview).filter_by(project_id=pid).first()
    if not r:
        r = models.ProjectReview(project_id=pid)
        db.add(r)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r


# ---------- 风险与阻塞 ----------
@router.get("/{pid}/risks", response_model=list[schemas.RiskOut])
def list_risks(pid: int, db: Session = Depends(get_db)):
    _get(db, pid)
    risks = db.query(models.ProjectRisk).filter_by(project_id=pid).order_by(
        models.ProjectRisk.status != "已解决", models.ProjectRisk.severity
    ).all()
    return risks


@router.post("/{pid}/risks", response_model=schemas.RiskOut)
def create_risk(pid: int, body: schemas.RiskCreate, db: Session = Depends(get_db)):
    _get(db, pid)
    r = models.ProjectRisk(project_id=pid, **body.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.put("/risks/{rid}", response_model=schemas.RiskOut)
def update_risk(rid: int, body: schemas.RiskUpdate, db: Session = Depends(get_db)):
    r = db.get(models.ProjectRisk, rid)
    if not r:
        raise HTTPException(404, "风险不存在")
    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        r.status = data["status"]
        r.resolved_at = datetime.now() if data["status"] == "已解决" else None
    for k, v in data.items():
        if k != "status":
            setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/risks/{rid}")
def delete_risk(rid: int, db: Session = Depends(get_db)):
    r = db.get(models.ProjectRisk, rid)
    if not r:
        raise HTTPException(404, "风险不存在")
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---------- 模板复制 / 阶段建议 ----------
@router.post("/{pid}/copy-template", response_model=schemas.ProjectOut)
def copy_template(pid: int, db: Session = Depends(get_db)):
    """从项目复制阶段结构创建新项目（名称加「副本」）。"""
    p = _get(db, pid, detail=True)
    np_ = models.Project(
        title=f"{p.title}（副本）",
        ptype=p.ptype,
        status="进行中",
        description=p.description,
        start_date=p.start_date,
        end_date=p.end_date,
    )
    db.add(np_)
    db.flush()
    for ph in p.phases:
        db.add(models.ProjectPhase(
            project_id=np_.id, name=ph.name, description=ph.description,
            sort_order=ph.sort_order, status="未开始", is_default=False,
        ))
    db.commit()
    db.refresh(np_)
    return _out(np_)


@router.get("/{pid}/phase-suggestions")
def phase_suggestions(pid: int, db: Session = Depends(get_db)):
    """阶段自动推进建议：实验≥3 条 且 任务完成率≥70% → 建议推进。"""
    p = _get(db, pid, detail=True)
    suggestions = []
    phases = sorted(p.phases, key=lambda x: x.sort_order)
    for i, ph in enumerate(phases):
        if ph.status != "进行中":
            continue
        exp_count = len(ph.experiments)
        tasks = db.query(models.PhaseTask).filter_by(phase_id=ph.id).all()
        todo_ids = [t.todo_id for t in tasks]
        done = 0
        for tid in todo_ids:
            t = db.get(models.Todo, tid)
            if t and t.status == "已完成":
                done += 1
        rate = round(done / len(todo_ids) * 100) if todo_ids else 0
        if exp_count >= 3 and (not todo_ids or rate >= 70):
            nxt = phases[i + 1] if i + 1 < len(phases) else None
            suggestions.append({
                "phase_id": ph.id,
                "phase_name": ph.name,
                "experiments": exp_count,
                "tasks_done": done,
                "tasks_total": len(todo_ids),
                "task_rate": rate,
                "suggestion": f"推进至「{nxt.name}」" if nxt else "可标记为已完成",
                "next_phase_id": nxt.id if nxt else None,
                "next_phase_name": nxt.name if nxt else None,
            })
    return {"suggestions": suggestions}
