"""日程聚合：周/月进展卡、周报生成、热力图、阶段总览。"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..services import report

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("/summary")
def summary(period: str = "week", db: Session = Depends(get_db)):
    """本周/本月科研进展汇报卡数据。"""
    data = report.build_report(db, period)
    return data


@router.get("/report")
def weekly_report(period: str = "week", ai: bool = False, db: Session = Depends(get_db)):
    """生成周报/月报 Markdown。ai=true 时用 LLM 润色为结构化报告（失败自动降级模板）。"""
    if period not in ("week", "month"):
        period = "week"
    if ai:
        return report.build_report_ai(db, period)
    return report.build_report(db, period)


@router.get("/term-report")
def term_report(year: int, semester: int = 1, db: Session = Depends(get_db)):
    """学期科研总结报告（1=春季学期 1-6月，2=秋季学期 7-12月）。"""
    if semester not in (1, 2):
        semester = 1
    return report.build_term_report(db, year, semester)


@router.get("/meeting-material")
def meeting_material(db: Session = Depends(get_db)):
    """组会材料：本周进展 + 下周计划 + 待讨论事项。"""
    return report.build_meeting_material(db)


@router.get("/timeline")
def timeline(
    start: Optional[date] = None,
    end: Optional[date] = None,
    kinds: Optional[str] = None,  # 逗号分隔：phase/milestone/deadline/todo
    db: Session = Depends(get_db),
):
    """全局时间线：项目阶段、里程碑、期刊截稿、待办合并按日期排序。"""
    today = date.today()
    start = start or today - timedelta(days=90)
    end = end or today + timedelta(days=365)
    kinds_set = set(kinds.split(",")) if kinds else {"phase", "milestone", "deadline", "todo"}
    events: list[dict] = []

    if "phase" in kinds_set:
        for ph in db.query(models.ProjectPhase).filter(
            (models.ProjectPhase.start_date >= start) | (models.ProjectPhase.start_date.is_(None))
        ).all():
            d = ph.start_date or ph.end_date
            if d and start <= d <= end:
                events.append({
                    "date": d.isoformat(), "type": "phase", "title": f"{ph.project.title} · {ph.name}",
                    "status": ph.status, "link": f"/projects/{ph.project_id}",
                })
    if "milestone" in kinds_set:
        for m in db.query(models.Milestone).filter(models.Milestone.due_date >= start, models.Milestone.due_date <= end).all():
            events.append({
                "date": m.due_date.isoformat(), "type": "milestone", "title": m.title,
                "status": m.status, "link": f"/projects/{m.project_id}",
            })
    if "deadline" in kinds_set:
        for p in db.query(models.Paper).filter(
            models.Paper.submission_deadline.is_not(None),
            models.Paper.submission_deadline >= start,
            models.Paper.submission_deadline <= end,
            models.Paper.status.notin_(("Accepted", "Published")),
        ).all():
            events.append({
                "date": p.submission_deadline.isoformat(), "type": "deadline",
                "title": f"期刊截稿：{p.title}", "status": "截稿",
                "link": f"/papers/{p.id}",
            })
    if "todo" in kinds_set:
        for t in db.query(models.Todo).filter(models.Todo.date >= start, models.Todo.date <= end).all():
            events.append({
                "date": t.date.isoformat(), "type": "todo", "title": t.title,
                "status": t.status, "link": "/schedule",
            })
    events.sort(key=lambda e: (e["date"], e["type"]))
    return {"start": start.isoformat(), "end": end.isoformat(), "events": events}


@router.get("/heatmap")
def heatmap(year: Optional[int] = None, db: Session = Depends(get_db)):
    """GitHub 风格热力图数据：每日科研活跃计数（待办完成/写作/笔记）。"""
    year = year or date.today().year
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    counts: dict[str, int] = {}

    for t in db.query(models.Todo).filter(
        models.Todo.completed_at >= datetime.combine(start, datetime.min.time()),
        models.Todo.completed_at < datetime.combine(end, datetime.min.time()),
    ).all():
        key = t.completed_at.date().isoformat()
        counts[key] = counts.get(key, 0) + 2  # 待办完成权重 2

    for w in db.query(models.WritingLog).filter(
        models.WritingLog.date >= start, models.WritingLog.date < end
    ).all():
        key = w.date.isoformat()
        counts[key] = counts.get(key, 0) + 3  # 写作打卡权重 3

    for n in db.query(models.Note).filter(
        models.Note.created_at >= datetime.combine(start, datetime.min.time()),
        models.Note.created_at < datetime.combine(end, datetime.min.time()),
    ).all():
        key = n.created_at.date().isoformat()
        counts[key] = counts.get(key, 0) + 1

    return {"year": year, "days": [{"date": k, "count": v} for k, v in sorted(counts.items())]}


@router.get("/phases")
def phases_overview(db: Session = Depends(get_db)):
    """全项目阶段总览（日程页阶段状态区）。"""
    out = []
    for p in db.query(models.Project).order_by(models.Project.created_at).all():
        phases = (
            db.query(models.ProjectPhase)
            .filter(models.ProjectPhase.project_id == p.id)
            .order_by(models.ProjectPhase.sort_order)
            .all()
        )
        out.append({
            "project_id": p.id,
            "project_title": p.title,
            "phases": [{
                "id": ph.id,
                "name": ph.name,
                "status": ph.status,
                "sort_order": ph.sort_order,
            } for ph in phases],
            "done": sum(1 for ph in phases if ph.status == "已完成"),
            "total": len(phases),
        })
    return out
