"""论文管理：CRUD、投稿状态机、版本管理、审稿记录。"""
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..services import paper_states, storage

router = APIRouter(prefix="/api/papers", tags=["papers"])

_LOAD = (
    selectinload(models.Paper.versions),
    selectinload(models.Paper.review_rounds),
    selectinload(models.Paper.sections),
)


def _get(db: Session, pid: int, detail: bool = False) -> models.Paper:
    q = db.query(models.Paper)
    if detail:
        q = q.options(*_LOAD)
    p = q.filter(models.Paper.id == pid).first()
    if not p:
        raise HTTPException(404, "论文不存在")
    return p


def _out(p: models.Paper) -> schemas.PaperOut:
    return schemas.PaperOut(
        id=p.id,
        title=p.title,
        project_id=p.project_id,
        project_title=p.project.title if p.project else None,
        paper_type=p.paper_type,
        abstract=p.abstract,
        keywords=p.keywords,
        status=p.status,
        target_journal=p.target_journal,
        journal_quartile=p.journal_quartile,
        journal_if=p.journal_if,
        submission_deadline=p.submission_deadline,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _delete_file(rel: str | None) -> None:
    if rel:
        try:
            storage.storage.delete(rel)
        except (ValueError, OSError):
            pass


@router.get("")
def list_papers(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    paper_scale: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Paper)
    if project_id:
        query = query.filter(models.Paper.project_id == project_id)
    if status:
        query = query.filter(models.Paper.status == status)
    if paper_scale:
        query = query.filter(models.Paper.paper_scale == paper_scale)
    if q:
        kw = f"%{q}%"
        query = query.filter(
            models.Paper.title.like(kw)
            | models.Paper.keywords.like(kw)
            | models.Paper.abstract.like(kw)
            | models.Paper.target_journal.like(kw)
        )
    papers = query.order_by(models.Paper.updated_at.desc()).all()
    return [_out(p) for p in papers]


@router.post("")
def create_paper(body: schemas.PaperCreate, db: Session = Depends(get_db)):
    p = models.Paper(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _out(p)


# ---------- 目标期刊库 ----------
@router.get("/journals", response_model=list[schemas.JournalOut])
def list_journals(db: Session = Depends(get_db)):
    journals = db.query(models.Journal).order_by(models.Journal.name).all()
    if not journals:
        from ..services.journals_preset import JOURNAL_PRESETS
        for name, q, if_, weeks, notes in JOURNAL_PRESETS:
            db.add(models.Journal(name=name, quartile=q, impact_factor=if_, review_weeks=weeks, notes=notes))
        db.commit()
        journals = db.query(models.Journal).order_by(models.Journal.name).all()
    return journals


@router.post("/journals", response_model=schemas.JournalOut)
def create_journal(body: schemas.JournalCreate, db: Session = Depends(get_db)):
    exists = db.query(models.Journal).filter_by(name=body.name).first()
    if exists:
        raise HTTPException(400, "期刊已存在")
    j = models.Journal(**body.model_dump())
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


@router.put("/journals/{jid}", response_model=schemas.JournalOut)
def update_journal(jid: int, body: schemas.JournalUpdate, db: Session = Depends(get_db)):
    j = db.get(models.Journal, jid)
    if not j:
        raise HTTPException(404, "期刊不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(j, k, v)
    db.commit()
    db.refresh(j)
    return j


@router.delete("/journals/{jid}")
def delete_journal(jid: int, db: Session = Depends(get_db)):
    j = db.get(models.Journal, jid)
    if not j:
        raise HTTPException(404, "期刊不存在")
    db.delete(j)
    db.commit()
    return {"ok": True}



# ---------- 投稿跟踪看板 ----------
BOARD_GROUPS = [
    ("draft", "草稿", ["Draft"]),
    ("underway", "在审", ["Submitted", "Under Review", "Resubmitted"]),
    ("revision", "修回", ["Revision"]),
    ("accepted", "已录用", ["Accepted"]),
    ("published", "已发表", ["Published"]),
    ("rejected", "已拒", ["Rejected"]),
]


@router.get("/submission-board")
def submission_board(db: Session = Depends(get_db)):
    """投稿跟踪看板：小论文按状态分组 + 审稿预期日（提交时间 + 期刊审稿周期推算）+ 期刊对比。"""
    papers = db.query(models.Paper).filter(models.Paper.paper_scale == "小论文").all()
    journals = {j.name: j for j in db.query(models.Journal).all()}
    # 每篇论文的首个 Submitted/Under Review 时间 = 提交时间
    submitted_at: dict[int, date] = {}
    for log in db.query(models.PaperStatusLog).order_by(models.PaperStatusLog.created_at).all():
        if log.to_status in ("Submitted", "Under Review") and log.paper_id not in submitted_at:
            submitted_at[log.paper_id] = log.created_at.date()
    round_counts: dict[int, int] = {}
    for r in db.query(models.ReviewRound).all():
        round_counts[r.paper_id] = round_counts.get(r.paper_id, 0) + 1

    today = date.today()
    cards = []
    for p in papers:
        j = journals.get(p.target_journal)
        sub = submitted_at.get(p.id)
        expected = None
        days_left = None
        if sub and j and j.review_weeks:
            expected = sub + timedelta(weeks=j.review_weeks)
            days_left = (expected - today).days
        cards.append({
            "id": p.id,
            "title": p.title,
            "status": p.status,
            "target_journal": p.target_journal or "",
            "journal_quartile": (j.quartile if j else None) or p.journal_quartile or "",
            "journal_if": (j.impact_factor if j else None) or p.journal_if or "",
            "review_weeks": j.review_weeks if j else None,
            "submitted_at": sub.isoformat() if sub else None,
            "expected_review_date": expected.isoformat() if expected else None,
            "days_left": days_left,
            "overdue": p.status == "Under Review" and expected is not None and days_left < 0,
            "review_rounds": round_counts.get(p.id, 0),
            "next_statuses": paper_states.next_statuses(p.status),
        })
    overdue_count = sum(1 for c in cards if c["overdue"])
    groups = [
        {
            "key": key, "label": label, "statuses": statuses,
            "cards": [c for c in cards if c["status"] in statuses],
        }
        for key, label, statuses in BOARD_GROUPS
    ]
    return {
        "overdue_count": overdue_count,
        "groups": groups,
        "journals": [{
            "name": j.name, "quartile": j.quartile, "impact_factor": j.impact_factor,
            "review_weeks": j.review_weeks, "notes": j.notes,
            "in_use": any(c["target_journal"] == j.name for c in cards),
        } for j in journals.values()],
    }


@router.get("/{pid}", response_model=schemas.PaperDetailOut)
def get_paper(pid: int, db: Session = Depends(get_db)):
    p = _get(db, pid, detail=True)
    # 各章节已打卡字数
    written: dict[int, int] = {}
    for w in db.query(models.WritingLog).filter(models.WritingLog.paper_id == pid, models.WritingLog.section_id.is_not(None)).all():
        written[w.section_id] = written.get(w.section_id, 0) + w.word_count
    sections = []
    for s in p.sections:
        out = schemas.PaperSectionOut.model_validate(s)
        out.written_words = written.get(s.id, 0)
        sections.append(out)
    return schemas.PaperDetailOut(
        **_out(p).model_dump(),
        versions=[schemas.PaperVersionOut.model_validate(v) for v in p.versions],
        review_rounds=[schemas.ReviewRoundOut.model_validate(r) for r in p.review_rounds],
        next_statuses=paper_states.next_statuses(p.status),
        sections=sections,
    )


@router.put("/{pid}")
def update_paper(pid: int, body: schemas.PaperUpdate, db: Session = Depends(get_db)):
    p = _get(db, pid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.updated_at = datetime.now()
    db.commit()
    db.refresh(p)
    return _out(p)


@router.delete("/{pid}")
def delete_paper(pid: int, db: Session = Depends(get_db)):
    p = _get(db, pid, detail=True)
    for v in p.versions:
        _delete_file(v.stored_path)
    for r in p.review_rounds:
        _delete_file(r.stored_path)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------- 状态流转 ----------
@router.post("/{pid}/status")
def change_status(pid: int, body: schemas.StatusChange, db: Session = Depends(get_db)):
    p = _get(db, pid)
    if not paper_states.can_transition(p.status, body.to):
        raise HTTPException(400, f"非法状态转移：{p.status} → {body.to}")
    db.add(models.PaperStatusLog(paper_id=pid, from_status=p.status, to_status=body.to))
    p.status = body.to
    p.updated_at = datetime.now()
    db.commit()
    return {"status": p.status, "next_statuses": paper_states.next_statuses(p.status)}


@router.get("/{pid}/status-history", response_model=list[schemas.StatusLogOut])
def status_history(pid: int, db: Session = Depends(get_db)):
    _get(db, pid)
    logs = (
        db.query(models.PaperStatusLog)
        .filter_by(paper_id=pid)
        .order_by(models.PaperStatusLog.created_at)
        .all()
    )
    return logs


# ---------- 引用文献关联 ----------
@router.get("/{pid}/references")
def paper_references(pid: int, db: Session = Depends(get_db)):
    """论文引用的文献列表（写作证据链）。"""
    _get(db, pid)
    links = db.query(models.PaperReference).filter_by(paper_id=pid).all()
    out = []
    for l in links:
        r = db.get(models.Reference, l.reference_id)
        if r:
            out.append({"id": r.id, "title": r.title, "year": r.year, "venue": r.venue})
    return out


@router.post("/{pid}/references")
def link_paper_reference(pid: int, body: schemas.PaperRefLink, db: Session = Depends(get_db)):
    _get(db, pid)
    if not db.get(models.Reference, body.reference_id):
        raise HTTPException(404, "文献不存在")
    exists = db.query(models.PaperReference).filter_by(paper_id=pid, reference_id=body.reference_id).first()
    if not exists:
        db.add(models.PaperReference(paper_id=pid, reference_id=body.reference_id))
        db.commit()
    return {"ok": True}


@router.delete("/{pid}/references/{rid}")
def unlink_paper_reference(pid: int, rid: int, db: Session = Depends(get_db)):
    l = db.query(models.PaperReference).filter_by(paper_id=pid, reference_id=rid).first()
    if not l:
        raise HTTPException(404, "关联不存在")
    db.delete(l)
    db.commit()
    return {"ok": True}


# ---------- 审稿意见转待办 ----------
@router.post("/review-rounds/{rid}/convert")
def convert_review_to_todo(rid: int, body: dict, db: Session = Depends(get_db)):
    r = db.get(models.ReviewRound, rid)
    if not r:
        raise HTTPException(404, "审稿记录不存在")
    text = (body.get("text") or r.summary or "").strip()
    if not text:
        raise HTTPException(400, "无可转换的审稿意见")
    t = models.Todo(date=date.today(), title=text[:200], description=text, priority="高")
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"ok": True, "todo_id": t.id}



# ---------- 版本管理 ----------
@router.post("/{pid}/versions", response_model=schemas.PaperVersionOut)
async def add_version(
    pid: int,
    file: UploadFile,
    changelog: str = Form(""),
    db: Session = Depends(get_db),
):
    p = _get(db, pid)
    data = await file.read()
    rel, safe = storage.storage.save(data, file.filename or "version.pdf")
    vno = max((v.version_no for v in p.versions), default=0) + 1
    v = models.PaperVersion(
        paper_id=pid,
        version_no=vno,
        file_name=safe,
        stored_path=rel,
        file_size=len(data),
        changelog=changelog,
    )
    db.add(v)
    p.updated_at = datetime.now()
    db.commit()
    db.refresh(v)
    return v


@router.get("/versions/{vid}/download")
def download_version(vid: int, db: Session = Depends(get_db)):
    v = db.get(models.PaperVersion, vid)
    if not v:
        raise HTTPException(404, "版本不存在")
    path = storage.storage.abs_path(v.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    disposition = f"attachment; filename*=UTF-8''{quote(v.file_name)}"
    return FileResponse(path, media_type="application/octet-stream", headers={"Content-Disposition": disposition})


@router.delete("/versions/{vid}")
def delete_version(vid: int, db: Session = Depends(get_db)):
    v = db.get(models.PaperVersion, vid)
    if not v:
        raise HTTPException(404, "版本不存在")
    _delete_file(v.stored_path)
    db.delete(v)
    db.commit()
    return {"ok": True}


# ---------- 审稿记录 ----------
@router.post("/{pid}/review-rounds", response_model=schemas.ReviewRoundOut)
async def add_review_round(
    pid: int,
    decision: str = Form(...),
    summary: str = Form(""),
    review_date: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    p = _get(db, pid)
    vno = max((r.round_no for r in p.review_rounds), default=0) + 1
    r = models.ReviewRound(paper_id=pid, round_no=vno, decision=decision, summary=summary)
    if review_date:
        try:
            r.review_date = date.fromisoformat(review_date)
        except ValueError:
            r.review_date = None
    if file and file.filename:
        data = await file.read()
        rel, safe = storage.storage.save(data, file.filename)
        r.file_name = safe
        r.stored_path = rel
    db.add(r)
    p.updated_at = datetime.now()
    db.commit()
    db.refresh(r)
    return r


@router.get("/review-rounds/{rid}/download")
def download_review_round(rid: int, db: Session = Depends(get_db)):
    r = db.get(models.ReviewRound, rid)
    if not r or not r.stored_path:
        raise HTTPException(404, "审稿记录或文件不存在")
    path = storage.storage.abs_path(r.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    disposition = f"attachment; filename*=UTF-8''{quote(r.file_name or 'review.pdf')}"
    return FileResponse(path, media_type="application/octet-stream", headers={"Content-Disposition": disposition})


@router.put("/review-rounds/{rid}", response_model=schemas.ReviewRoundOut)
def update_review_round(rid: int, body: dict, db: Session = Depends(get_db)):
    r = db.get(models.ReviewRound, rid)
    if not r:
        raise HTTPException(404, "审稿记录不存在")
    if "decision" in body:
        r.decision = str(body["decision"])
    if "summary" in body:
        r.summary = str(body["summary"])
    if "review_date" in body:
        try:
            r.review_date = date.fromisoformat(str(body["review_date"])) if body["review_date"] else None
        except ValueError:
            r.review_date = None
    db.commit()
    db.refresh(r)
    return r


@router.delete("/review-rounds/{rid}")
def delete_review_round(rid: int, db: Session = Depends(get_db)):
    r = db.get(models.ReviewRound, rid)
    if not r:
        raise HTTPException(404, "审稿记录不存在")
    _delete_file(r.stored_path)
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---------- 论文章节进度 ----------
@router.post("/{pid}/sections", response_model=schemas.PaperSectionOut)
def create_section(pid: int, body: schemas.PaperSectionCreate, db: Session = Depends(get_db)):
    _get(db, pid)
    s = models.PaperSection(paper_id=pid, **body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.put("/sections/{sid}", response_model=schemas.PaperSectionOut)
def update_section(sid: int, body: schemas.PaperSectionUpdate, db: Session = Depends(get_db)):
    s = db.get(models.PaperSection, sid)
    if not s:
        raise HTTPException(404, "章节不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/sections/{sid}")
def delete_section(sid: int, db: Session = Depends(get_db)):
    s = db.get(models.PaperSection, sid)
    if not s:
        raise HTTPException(404, "章节不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}
