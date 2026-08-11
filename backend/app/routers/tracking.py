"""科研动态追踪路由：订阅源管理、论文流、手动抓取、一键入库、概览。"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..services import tracker as tracker_service

router = APIRouter(prefix="/api/tracking", tags=["tracking"])

# 预置 RSS 源（实施时实测可用性，不可达默认禁用）
PRESET_SOURCES = [
    ("arXiv AI (RSS)", "rss", "https://rss.arxiv.org/rss/cs.AI"),
    ("arXiv 机器学习 (RSS)", "rss", "https://rss.arxiv.org/rss/cs.LG"),
    ("arXiv NLP (RSS)", "rss", "https://rss.arxiv.org/rss/cs.CL"),
    ("arXiv 计算机视觉 (RSS)", "rss", "https://rss.arxiv.org/rss/cs.CV"),
    ("Nature News", "rss", "https://www.nature.com/nature/articles.rss"),
    ("ScienceDaily", "rss", "https://www.sciencedaily.com/rss/all.xml"),
    ("MIT Technology Review", "rss", "https://www.technologyreview.com/feed/"),
    ("OpenAI Blog", "rss", "https://openai.com/blog/rss.xml"),
    ("Google DeepMind", "rss", "https://deepmind.google/blog/rss.xml"),
    ("Meta AI Blog", "rss", "https://ai.meta.com/blog/rss/"),
    ("Microsoft Research", "rss", "https://www.microsoft.com/en-us/research/feed/"),
    ("HN 前沿", "rss", "https://hnrss.org/frontpage"),
    ("阮一峰的网络日志", "rss", "https://www.ruanyifeng.com/blog/atom.xml"),
    ("酷壳 CoolShell", "rss", "https://coolshell.cn/feed"),
    ("V2EX 热门", "rss", "https://www.v2ex.com/feed/tab/hot.xml"),
    ("LinuxDo", "rss", "https://linux.do/latest.rss"),
    ("GitHub Blog", "rss", "https://github.blog/feed/"),
    ("TechCrunch", "rss", "https://techcrunch.com/feed/"),
    ("The Verge", "rss", "https://www.theverge.com/rss/index.xml"),
    ("NPR News", "rss", "https://feeds.npr.org/1001/rss.xml"),
    ("NHK World", "rss", "https://www3.nhk.or.jp/rss/news/cat0.xml"),
    ("联合早报", "rss", "https://www.zaobao.com.sg/rss.xml"),
    ("Lex Fridman Podcast", "rss", "https://lexfridman.com/feed/podcast/"),
    ("New Scientist", "rss", "https://www.newscientist.com/section/news/feed/"),
    ("CVE 公告", "rss", "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss-analyzed.xml"),
]
# 预置 arXiv 分类源（走 API）
PRESET_ARXIV = [
    ("arXiv cs.AI（新论文）", "arxiv_category", "cat:cs.AI"),
    ("arXiv cs.LG（新论文）", "arxiv_category", "cat:cs.LG"),
    ("arXiv cs.CL（新论文）", "arxiv_category", "cat:cs.CL"),
]

FETCH_INTERVAL_HOURS = 6  # 后台自动抓取周期


def _init_presets(db: Session) -> None:
    """首次启动时初始化预置源（RSS 并发实测可用性，不可达默认禁用）。"""
    if db.query(models.TrackingSource).count() > 0:
        return
    from concurrent.futures import ThreadPoolExecutor

    def check(query: str) -> tuple[bool, str]:
        try:
            items = tracker_service.fetch_rss(query, max_items=1, timeout=6.0)
            return (True, "") if items else (False, "空响应")
        except ValueError as e:
            return (False, str(e)[:200])

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(check, [q for _, _, q in PRESET_SOURCES]))
    for (name, stype, query), (ok, err) in zip(PRESET_SOURCES, results):
        db.add(models.TrackingSource(name=name, stype=stype, query=query, active=ok, last_error=err))
    for name, stype, query in PRESET_ARXIV:
        db.add(models.TrackingSource(name=name, stype=stype, query=query, active=True))
    db.commit()


def fetch_source(db: Session, src: models.TrackingSource) -> int:
    """抓取单个源并入库去重，返回新增数。"""
    try:
        if src.stype.startswith("arxiv"):
            items = tracker_service.fetch_arxiv(src.query)
        else:
            items = tracker_service.fetch_rss(src.query)
        src.last_error = ""
    except ValueError as e:
        src.last_error = str(e)[:200]
        db.commit()
        return 0

    created = 0
    for it in items:
        exists = db.query(models.TrackingItem).filter_by(source_id=src.id, external_id=it["external_id"]).first()
        if exists:
            continue
        db.add(models.TrackingItem(
            source_id=src.id,
            external_id=it["external_id"],
            title=it["title"][:500],
            authors=it["authors"],
            abstract=it["abstract"],
            link=it["link"],
            published=date.fromisoformat(it["published"]) if it["published"] else None,
            is_new=True,
        ))
        created += 1
    src.last_fetched_at = datetime.now()
    db.commit()
    return created


def auto_fetch_all(db: Session) -> dict:
    """抓取全部活跃源（后台线程用），新条目写系统通知。"""
    results = {"sources": 0, "new_items": 0}
    for src in db.query(models.TrackingSource).filter(models.TrackingSource.active.is_(True)).all():
        results["sources"] += 1
        created = fetch_source(db, src)
        if created:
            results["new_items"] += created
            # 新条目通知（合并为一条摘要）
            recent = db.query(models.TrackingItem).filter_by(source_id=src.id).order_by(models.TrackingItem.id.desc()).limit(created).all()
            titles = "；".join(i.title[:40] for i in recent[:3])
            db.add(models.Notification(
                message=f"📄 {src.name} 新增 {created} 条：{titles}",
                category="info",
                target_type="tracking",
                target_id=src.id,
            ))
            db.commit()
    return results


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    _init_presets(db)
    sources = db.query(models.TrackingSource).order_by(models.TrackingSource.active.desc(), models.TrackingSource.id).all()
    out = []
    for s in sources:
        count = db.query(models.TrackingItem).filter_by(source_id=s.id).count()
        out.append({
            "id": s.id, "name": s.name, "stype": s.stype, "query": s.query,
            "active": s.active, "item_count": count,
            "last_fetched_at": s.last_fetched_at.isoformat() if s.last_fetched_at else None,
            "last_error": s.last_error,
        })
    return out


@router.post("/sources")
def create_source(body: dict, db: Session = Depends(get_db)):
    s = models.TrackingSource(
        name=str(body.get("name", ""))[:200],
        stype=str(body.get("stype", "arxiv_keyword")),
        query=str(body.get("query", ""))[:500],
        active=bool(body.get("active", True)),
    )
    if not s.name or not s.query:
        raise HTTPException(400, "名称与查询内容不能为空")
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "name": s.name, "active": s.active}


@router.put("/sources/{sid}")
def update_source(sid: int, body: dict, db: Session = Depends(get_db)):
    s = db.get(models.TrackingSource, sid)
    if not s:
        raise HTTPException(404, "订阅源不存在")
    if "name" in body:
        s.name = str(body["name"])[:200]
    if "query" in body:
        s.query = str(body["query"])[:500]
    if "active" in body:
        s.active = bool(body["active"])
    db.commit()
    return {"id": s.id, "active": s.active}


@router.delete("/sources/{sid}")
def delete_source(sid: int, db: Session = Depends(get_db)):
    s = db.get(models.TrackingSource, sid)
    if not s:
        raise HTTPException(404, "订阅源不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/items")
def list_items(source_id: Optional[int] = None, days: int = 7, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(models.TrackingItem)
    if source_id:
        query = query.filter(models.TrackingItem.source_id == source_id)
    cutoff = date.today() - timedelta(days=days)
    query = query.filter(models.TrackingItem.published >= cutoff)
    items = query.order_by(models.TrackingItem.published.desc(), models.TrackingItem.id.desc()).limit(limit).all()
    return [{
        "id": i.id, "source_id": i.source_id, "title": i.title,
        "authors": i.authors, "abstract": i.abstract, "link": i.link,
        "published": i.published.isoformat() if i.published else None,
        "is_new": i.is_new,
    } for i in items]


@router.post("/fetch")
def manual_fetch(body: dict, db: Session = Depends(get_db)):
    """手动抓取：全量或指定源，返回新增数。"""
    sid = body.get("source_id")
    if sid:
        s = db.get(models.TrackingSource, int(sid))
        if not s:
            raise HTTPException(404, "订阅源不存在")
        created = fetch_source(db, s)
        if created:
            db.add(models.Notification(message=f"📄 {s.name} 新增 {created} 条", category="info", target_type="tracking", target_id=s.id))
            db.commit()
        return {"created": created, "source": s.name}
    return auto_fetch_all(db)


@router.post("/items/{iid}/to-library")
def item_to_library(iid: int, db: Session = Depends(get_db)):
    """一键入库：追踪条目 → 文献库 Reference（标题去重）。"""
    item = db.get(models.TrackingItem, iid)
    if not item:
        raise HTTPException(404, "条目不存在")
    exists = db.query(models.Reference).filter(models.Reference.title == item.title).first()
    if exists:
        item.is_new = False
        db.commit()
        return {"ok": True, "already_exists": True, "reference_id": exists.id}
    ref = models.Reference(
        title=item.title,
        authors=item.authors,
        year=item.published.year if item.published else None,
        venue="arXiv 预印本" if "arxiv" in item.link else "RSS 追踪",
        tags="追踪",
        category="其他",
        read_status="未读",
    )
    db.add(ref)
    item.is_new = False
    db.commit()
    db.refresh(ref)
    return {"ok": True, "already_exists": False, "reference_id": ref.id}


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """仪表盘概览：活跃源数、近 7 天新增、最新 5 条。"""
    _init_presets(db)
    active = db.query(models.TrackingSource).filter(models.TrackingSource.active.is_(True)).count()
    cutoff = date.today() - timedelta(days=7)
    week_new = db.query(models.TrackingItem).filter(models.TrackingItem.published >= cutoff).count()
    recent = db.query(models.TrackingItem).order_by(models.TrackingItem.published.desc(), models.TrackingItem.id.desc()).limit(5).all()
    return {
        "active_sources": active,
        "week_new": week_new,
        "recent": [{
            "id": i.id, "title": i.title, "link": i.link, "published": i.published.isoformat() if i.published else None,
            "is_new": i.is_new, "source_id": i.source_id,
        } for i in recent],
    }
