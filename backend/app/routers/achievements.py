"""成果管理：独立成果 CRUD + 论文自动同步（Accepted/Published）+ 统计。"""
from datetime import date
from typing import Optional

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/achievements", tags=["achievements"])

SYNC_PAPER_STATUSES = ("Accepted", "Published")
ACHIEVEMENT_TYPES = ("论文", "专利", "软件", "获奖", "其他")


def _get(db: Session, aid: int) -> models.Achievement:
    a = db.get(models.Achievement, aid)
    if not a:
        raise HTTPException(404, "成果不存在")
    return a


def _paper_entries(db: Session) -> list[dict]:
    """论文模块自动同步：状态为已接收/已发表的论文映射为成果条目。"""
    papers = (
        db.query(models.Paper)
        .filter(models.Paper.status.in_(SYNC_PAPER_STATUSES))
        .order_by(models.Paper.updated_at.desc())
        .all()
    )
    entries = []
    for p in papers:
        entries.append({
            "id": -p.id,  # 负数避免与独立成果 id 冲突
            "synced": True,
            "atype": "论文",
            "title": p.title,
            "status": "已接收" if p.status == "Accepted" else "已发表",
            "date": None,
            "venue": p.target_journal,
            "identifier": "",
            "authors": "",
            "detail": p.abstract[:500],
            "link": "",
            "notes": "来自论文模块自动同步",
        })
    return entries


@router.get("")
def list_achievements(atype: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Achievement)
    if atype:
        query = query.filter(models.Achievement.atype == atype)
    own = [schemas.AchievementOut.model_validate(a) for a in query.order_by(models.Achievement.date.desc()).all()]
    # 论文同步条目附在末尾（synced 标记）
    return [a.model_dump() | {"synced": False} for a in own] + _paper_entries(db)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    by_type: dict[str, int] = {t: 0 for t in ACHIEVEMENT_TYPES}
    for a in db.query(models.Achievement).all():
        by_type[a.atype] = by_type.get(a.atype, 0) + 1
    by_type["论文"] += len(_paper_entries(db))  # 同步论文计入
    by_status: dict[str, int] = {}
    for a in db.query(models.Achievement).all():
        by_status[a.status or "未填写"] = by_status.get(a.status or "未填写", 0) + 1
    return {"by_type": by_type, "by_status": by_status, "total": sum(by_type.values())}


@router.post("", response_model=schemas.AchievementOut)
def create_achievement(body: schemas.AchievementCreate, db: Session = Depends(get_db)):
    if body.atype not in ACHIEVEMENT_TYPES:
        raise HTTPException(400, f"类型仅支持：{'/'.join(ACHIEVEMENT_TYPES)}")
    a = models.Achievement(**body.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.put("/{aid}", response_model=schemas.AchievementOut)
def update_achievement(aid: int, body: schemas.AchievementUpdate, db: Session = Depends(get_db)):
    a = _get(db, aid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return a


@router.delete("/{aid}")
def delete_achievement(aid: int, db: Session = Depends(get_db)):
    a = _get(db, aid)
    if a.stored_path:
        from ..services import storage
        try:
            storage.storage.delete(a.stored_path)
        except (ValueError, OSError):
            pass
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------- 附件与 CV 导出 ----------
@router.post("/{aid}/attachment", response_model=schemas.AchievementOut)
async def upload_attachment(aid: int, file: UploadFile, db: Session = Depends(get_db)):
    from ..services import storage

    a = _get(db, aid)
    if a.stored_path:
        try:
            storage.storage.delete(a.stored_path)
        except (ValueError, OSError):
            pass
    data = await file.read()
    rel, safe = storage.storage.save(data, file.filename or "attachment.pdf")
    a.file_name = safe
    a.stored_path = rel
    db.commit()
    db.refresh(a)
    return a


@router.get("/{aid}/download")
def download_attachment(aid: int, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    from ..services import storage

    a = _get(db, aid)
    if not a.stored_path:
        raise HTTPException(404, "暂无附件")
    path = storage.storage.abs_path(a.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    from urllib.parse import quote
    disposition = f"attachment; filename*=UTF-8''{quote(a.file_name or 'attachment.pdf')}"
    return FileResponse(path, media_type="application/octet-stream", headers={"Content-Disposition": disposition})


@router.get("/cv-export")
def cv_export(db: Session = Depends(get_db)):
    """导出 CV 成果列表（Markdown）：论文（同步）+ 专利/软件/获奖。"""
    from fastapi.responses import PlainTextResponse

    own = db.query(models.Achievement).order_by(models.Achievement.date.desc()).all()
    synced = _paper_entries(db)
    lines = ["# 科研成果列表", ""]

    def _section(title: str, items: list) -> None:
        if not items:
            return
        lines.append(f"## {title}")
        for it in items:
            date_str = f"（{it['date']}）" if it.get("date") else ""
            venue = f"，{it['venue']}" if it.get("venue") else ""
            ident = f"，{it['identifier']}" if it.get("identifier") else ""
            status = f" [{it['status']}]" if it.get("status") else ""
            authors = f"，{it['authors']}" if it.get("authors") else ""
            lines.append(f"- {it['title']}{authors}{date_str}{venue}{ident}{status}")
        lines.append("")

    _section("论文", synced)
    for t in ("专利", "软件", "获奖", "其他"):
        _section(t, [{"title": a.title, "date": a.date, "venue": a.venue, "identifier": a.identifier,
                      "authors": a.authors, "status": a.status} for a in own if a.atype == t])
    content = "\n".join(lines)
    disposition = "attachment; filename*=UTF-8''" + quote("科研成果列表.md")
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": disposition})
