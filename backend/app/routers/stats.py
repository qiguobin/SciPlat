"""仪表盘聚合、全局搜索、AI 集成能力接口（二期预留口）。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import config, models
from ..database import get_db
from ..services import paper_states

router = APIRouter(prefix="/api", tags=["stats"])

DEADLINE_DAYS = 30  # 提醒窗口：30 天内


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    projects = db.query(models.Project).all()
    papers = db.query(models.Paper).all()
    refs = db.query(models.Reference).all()
    materials = db.query(models.Material).all()

    project_by_status: dict[str, int] = {}
    for p in projects:
        project_by_status[p.status] = project_by_status.get(p.status, 0) + 1

    paper_by_status = {s: 0 for s in paper_states.TRANSITIONS}
    for p in papers:
        paper_by_status[p.status] = paper_by_status.get(p.status, 0) + 1

    read_by_status: dict[str, int] = {}
    for r in refs:
        read_by_status[r.read_status] = read_by_status.get(r.read_status, 0) + 1

    # 截止提醒：里程碑（30 天内）+ 期刊截稿（30 天内，非终态）
    today = date.today()
    deadlines = []
    for m in db.query(models.Milestone).filter(models.Milestone.status.in_(["未开始", "进行中"])).all():
        days = (m.due_date - today).days
        if 0 <= days <= DEADLINE_DAYS:
            deadlines.append({
                "type": "milestone",
                "title": m.title,
                "extra": m.project.title if m.project else "",
                "date": m.due_date.isoformat(),
                "link": f"/projects/{m.project_id}",
                "days_left": days,
            })
    for p in papers:
        if p.submission_deadline and p.status not in ("Accepted", "Published"):
            days = (p.submission_deadline - today).days
            if 0 <= days <= DEADLINE_DAYS:
                deadlines.append({
                    "type": "journal",
                    "title": f"期刊截稿：{p.title}",
                    "extra": p.target_journal,
                    "date": p.submission_deadline.isoformat(),
                    "link": f"/papers/{p.id}",
                    "days_left": days,
                })

    # 审稿超时提醒：Under Review 且已过审稿预期日（提交时间 + 期刊审稿周期推算）
    journals = {j.name: j for j in db.query(models.Journal).all()}
    submitted_at: dict[int, date] = {}
    for log in db.query(models.PaperStatusLog).order_by(models.PaperStatusLog.created_at).all():
        if log.to_status in ("Submitted", "Under Review") and log.paper_id not in submitted_at:
            submitted_at[log.paper_id] = log.created_at.date()
    from datetime import timedelta
    for p in papers:
        if p.status != "Under Review":
            continue
        j = journals.get(p.target_journal)
        sub = submitted_at.get(p.id)
        if not (sub and j and j.review_weeks):
            continue
        expected = sub + timedelta(weeks=j.review_weeks)
        days = (expected - today).days
        if days < 0:
            deadlines.append({
                "type": "review",
                "title": f"审稿超时：{p.title}",
                "extra": f"{p.target_journal}（已超 {abs(days)} 天）",
                "date": expected.isoformat(),
                "link": f"/papers/{p.id}",
                "days_left": days,
            })
    deadlines.sort(key=lambda d: d["days_left"])

    # 最近更新（合并四类实体）
    recent: list[dict] = []
    for p in projects:
        recent.append({"kind": "project", "id": p.id, "title": p.title, "updated_at": p.updated_at.isoformat()})
    for p in papers:
        recent.append({"kind": "paper", "id": p.id, "title": p.title, "updated_at": p.updated_at.isoformat()})
    for m in materials:
        recent.append({"kind": "material", "id": m.id, "title": m.name, "updated_at": m.created_at.isoformat()})
    for r in refs:
        recent.append({"kind": "reference", "id": r.id, "title": r.title, "updated_at": r.updated_at.isoformat()})
    recent.sort(key=lambda x: x["updated_at"], reverse=True)
    recent = recent[:10]

    return {
        "projects": {"total": len(projects), "by_status": project_by_status},
        "papers": {"total": len(papers), "by_status": paper_by_status},
        "references": {"total": len(refs), "read": read_by_status},
        "materials": {"total": len(materials), "total_size": sum(m.size for m in materials)},
        "deadlines": deadlines,
        "recent": recent,
    }


@router.get("/search")
def search(q: str, db: Session = Depends(get_db)):
    kw = f"%{q.strip()}%"
    projects = (
        db.query(models.Project)
        .filter(or_(models.Project.title.like(kw), models.Project.description.like(kw)))
        .limit(5).all()
    )
    papers = (
        db.query(models.Paper)
        .filter(or_(models.Paper.title.like(kw), models.Paper.keywords.like(kw)))
        .limit(5).all()
    )
    materials = (
        db.query(models.Material)
        .filter(or_(models.Material.name.like(kw), models.Material.tags.like(kw)))
        .limit(5).all()
    )
    references = (
        db.query(models.Reference)
        .filter(or_(models.Reference.title.like(kw), models.Reference.tags.like(kw), models.Reference.doi.like(kw)))
        .limit(5).all()
    )
    return {
        "projects": [{"id": p.id, "title": p.title, "status": p.status} for p in projects],
        "papers": [{"id": p.id, "title": p.title, "status": p.status} for p in papers],
        "materials": [{"id": m.id, "name": m.name, "category": m.category} for m in materials],
        "references": [{"id": r.id, "title": r.title, "read_status": r.read_status} for r in references],
    }


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """健康检查：状态栏数据源（版本/数据库/LLM/错误计数）。"""
    from datetime import datetime, timedelta
    from pathlib import Path

    import sys

    from .. import config
    from ..services import llm as llm_service

    db_size = 0
    try:
        db_size = Path(config.DB_PATH).stat().st_size
    except OSError:
        pass
    since = datetime.now() - timedelta(days=7)
    error_count = db.query(models.SystemEvent).filter(
        models.SystemEvent.level == "error",
        models.SystemEvent.created_at >= since,
    ).count()
    cfg = llm_service._get_cfg(db)
    return {
        "status": "ok",
        "version": config.APP_VERSION,
        "app_name": config.APP_NAME,
        "data_dir": str(config.DATA_DIR),
        "db_path": str(config.DB_PATH),
        "db_size": db_size,
        "llm_configured": llm_service.is_configured(db),
        "llm_provider": cfg["provider"],
        "llm_model": cfg["model"],
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "error_count": error_count,
        "uptime_seconds": int(datetime.now().timestamp() - _main_uptime()),
    }


def _main_uptime() -> float:
    import app.main as main_module

    return main_module._UPTIME_START


@router.get("/system-events")
def list_system_events(limit: int = 50, db: Session = Depends(get_db)):
    """系统事件列表（状态栏错误日志弹窗）。"""
    rows = db.query(models.SystemEvent).order_by(models.SystemEvent.created_at.desc()).limit(min(limit, 100)).all()
    return [{
        "id": e.id, "level": e.level, "source": e.source,
        "message": e.message, "created_at": e.created_at.isoformat(),
    } for e in rows]


@router.post("/system-events/clear")
def clear_system_events(db: Session = Depends(get_db)):
    """清空系统事件。"""
    db.query(models.SystemEvent).delete()
    db.commit()
    return {"ok": True}


@router.get("/ai/capabilities")
def ai_capabilities(db: Session = Depends(get_db)):
    """二期 AI 技能集成入口：返回平台可消费的数据索引与导出能力。"""
    projects = []
    for p in db.query(models.Project).all():
        projects.append({
            "id": p.id,
            "title": p.title,
            "status": p.status,
            "materials_count": len(p.materials),
            "papers_count": len(p.papers),
            "export_url": f"/api/projects/{p.id}/export",
        })
    return {
        "platform": "sci-plat",
        "version": config.APP_VERSION,
        "data_dir": str(config.DATA_DIR),
        "projects": projects,
        "papers_endpoint": "/api/papers",
        "references_endpoint": "/api/references",
    }
