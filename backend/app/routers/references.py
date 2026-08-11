"""文献库：CRUD、BibTeX 导入导出、DOI 元数据抓取、PDF 附件、关联图谱、全文检索与阅读。"""
from datetime import date, datetime
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import bibtex, doi, fulltext, network as network_service, pdfextract, storage

router = APIRouter(prefix="/api/references", tags=["references"])


def _get(db: Session, rid: int) -> models.Reference:
    r = db.get(models.Reference, rid)
    if not r:
        raise HTTPException(404, "文献不存在")
    return r


@router.get("")
def list_references(
    q: Optional[str] = None,
    read_status: Optional[str] = None,
    tag: Optional[str] = None,
    category: Optional[str] = None,
    year: Optional[int] = None,
    collection_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Reference)
    if q:
        kw = f"%{q}%"
        query = query.filter(models.Reference.title.like(kw) | models.Reference.tags.like(kw) | models.Reference.doi.like(kw))
    if read_status:
        query = query.filter(models.Reference.read_status == read_status)
    if tag:
        query = query.filter(models.Reference.tags.like(f"%{tag}%"))
    if category:
        query = query.filter(models.Reference.category == category)
    if year:
        query = query.filter(models.Reference.year == year)
    if collection_id:
        query = query.join(models.ReferenceCollectionLink, models.ReferenceCollectionLink.reference_id == models.Reference.id)                    .filter(models.ReferenceCollectionLink.collection_id == collection_id)
    refs = query.order_by(models.Reference.updated_at.desc()).all()
    return [schemas.ReferenceOut.model_validate(r) for r in refs]


@router.post("")
def create_reference(body: schemas.ReferenceCreate, db: Session = Depends(get_db)):
    r = models.Reference(**body.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.get("/export-bib")
def export_bib(db: Session = Depends(get_db)):
    """注意：必须定义在 /{rid} 之前，否则被 int 路径参数吞掉。"""
    refs = db.query(models.Reference).order_by(models.Reference.created_at).all()
    content = bibtex.export_bibtex(refs)
    disposition = "attachment; filename=\"references.bib\""
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": disposition})


# ---------- 引用格式 / 全文搜索 / 阅读统计 / 重复检测（静态路由，须在 /{rid} 前） ----------
@router.post("/citations/format")
def format_citations(body: schemas.CitationRequest, db: Session = Depends(get_db)):
    """一键生成 GB/T 7714 / APA / IEEE 格式引用。"""
    from ..services import citation

    refs = []
    for rid in body.ids:
        r = db.get(models.Reference, rid)
        if r:
            refs.append(r)
    try:
        texts = citation.format_citations(refs, body.format)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"format": body.format, "citations": texts}


@router.get("/search-fulltext")
def search_fulltext(q: str, limit: int = 10, db: Session = Depends(get_db)):
    """在已提取的文献全文文本中检索，返回命中文献与上下文片段。"""
    from sqlalchemy import func

    kw = f"%{q.strip()}%"
    hits = []
    for rt in db.query(models.ReferenceText).filter(models.ReferenceText.text.like(kw)).limit(limit).all():
        r = db.get(models.Reference, rt.reference_id)
        if not r:
            continue
        idx = rt.text.lower().find(q.strip().lower())
        start = max(0, idx - 80)
        snippet = "…" + rt.text[start:start + 220].replace("\n", " ") + "…"
        hits.append({"reference_id": r.id, "title": r.title, "snippet": snippet})
    return {"hits": hits}


@router.get("/reading-stats")
def reading_stats(db: Session = Depends(get_db)):
    """每篇文献累计阅读时长（分钟）。"""
    from sqlalchemy import func

    rows = db.query(
        models.ReadingSession.reference_id,
        func.sum(models.ReadingSession.seconds),
    ).group_by(models.ReadingSession.reference_id).all()
    stats = {rid: secs // 60 for rid, secs in rows}
    return {"minutes": stats}


@router.get("/duplicates")
def duplicates(db: Session = Depends(get_db)):
    """重复检测：DOI 归一化相同 或 标题相似度 > 0.9。"""
    from ..services import duplicate

    return duplicate.find_duplicates(db.query(models.Reference).all())


@router.get("/similar/{rid}")
def similar_references(rid: int, limit: int = 5, db: Session = Depends(get_db)):
    """相似文献推荐：复用 network 相似度算法，按权重取 topN。"""
    target = db.get(models.Reference, rid)
    if not target:
        raise HTTPException(404, "文献不存在")
    refs = db.query(models.Reference).filter(models.Reference.id != rid).all()
    links = network_service.similarity([target] + refs)
    top = sorted(links, key=lambda l: l["weight"], reverse=True)[:limit]
    out = []
    for l in top:
        other_id = l["target"] if l["source"] == rid else l["source"]
        r = db.get(models.Reference, other_id)
        if r:
            out.append({
                "id": r.id, "title": r.title, "year": r.year, "venue": r.venue,
                "weight": l["weight"], "factors": l["factors"],
            })
    return {"similar": out}


@router.get("/queue")
def reading_queue(db: Session = Depends(get_db)):
    """阅读队列：按计划日期 + 优先级排序（priority>0）。"""
    refs = (
        db.query(models.Reference)
        .filter(models.Reference.queue_priority > 0)
        .order_by(models.Reference.queue_date, models.Reference.queue_priority.desc())
        .all()
    )
    return [{
        "id": r.id, "title": r.title, "year": r.year, "venue": r.venue,
        "queue_priority": r.queue_priority, "queue_date": r.queue_date.isoformat() if r.queue_date else None,
        "read_status": r.read_status, "reading_progress": r.reading_progress,
    } for r in refs]


# ---------- 关联图谱（静态路由须在 /{rid} 之前注册） ----------
def _citations_map(db: Session) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for row in db.query(models.ReferenceCitation).all():
        result.setdefault(row.ref_id, set()).add(row.cited_doi)
    return result


@router.get("/network")
def network(tag: Optional[str] = None, min_weight: int = 0, db: Session = Depends(get_db)):
    """文献关联图谱：节点 + 加权边（自动相似 + 引用关系 + 手动关联 + AI 自动关联）。"""
    query = db.query(models.Reference)
    if tag:
        query = query.filter(models.Reference.tags.like(f"%{tag}%"))
    refs = query.all()
    related: dict[int, set[int]] = {}
    for link in db.query(models.RelatedReference).all():
        related.setdefault(link.ref_a, set()).add(link.ref_b)
        related.setdefault(link.ref_b, set()).add(link.ref_a)
    ai_map: dict[tuple[int, int], dict] = {}
    for link in db.query(models.ReferenceAiLink).all():
        a, b = sorted((link.ref_a, link.ref_b))
        ai_map[(a, b)] = {"weight": link.weight, "reason": link.reason, "tags": link.tags or []}
    return network_service.build_network(
        refs, _citations_map(db), min_weight=min_weight, related_map=related, ai_links_map=ai_map
    )


@router.post("/fts-search")
def fts_search(body: dict, db: Session = Depends(get_db)):
    """FTS5 全文检索（trigram 支持中文）：返回带高亮片段的结果。"""
    q = str(body.get("q") or "").strip()
    limit = max(1, min(int(body.get("limit") or 20), 50))
    if not q:
        raise HTTPException(400, "请输入检索词")
    from ..database import engine

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                __import__("sqlalchemy").text(
                    "SELECT ref_id, title, snippet(refs_fts, 1, '«', '»', '…', 14) AS snip "
                    "FROM refs_fts WHERE refs_fts MATCH :q ORDER BY rank LIMIT :lim"
                ),
                {"q": q, "lim": limit},
            ).all()
    except Exception as e:  # FTS 语法错误等
        raise HTTPException(400, f"检索失败：{e}") from e
    if not rows:
        return {"items": [], "query": q}
    ids = [r[0] for r in rows]
    titles: dict[int, str] = {r.id: r.title for r in db.query(models.Reference).filter(models.Reference.id.in_(ids)).all()}
    return {
        "items": [{
            "reference_id": r[0],
            "title": titles.get(r[0], "") or r[1],
            "snippet": r[2] or "",
        } for r in rows],
        "query": q,
    }


@router.post("/semantic-search")
def semantic_search(body: dict, db: Session = Depends(get_db)):
    """AI 语义搜索：LLM 把自然语言查询扩展为关键词集 → FTS5 检索（未配置 LLM 时直接原文检索）。"""
    q = str(body.get("q") or "").strip()
    limit = max(1, min(int(body.get("limit") or 20), 50))
    if not q:
        raise HTTPException(400, "请输入查询内容")
    from ..services import llm as llm_service

    keywords = q
    expanded = False
    if llm_service.is_configured(db):
        try:
            system = (
                "你是文献检索助手。把用户的自然语言查询改写为 3-6 个检索关键词或短语（中文用中文，"
                "保留英文术语），只输出关键词，用空格分隔，不要任何解释。"
            )
            reply = llm_service.chat(db, system, [{"role": "user", "content": q}],
                                     max_tokens=100, task="chat", timeout=30)
            cleaned = " ".join(reply.split())
            if cleaned and len(cleaned) <= 200:
                keywords = cleaned
                expanded = True
        except Exception:
            pass
    # FTS OR 查询：关键词空格分隔即 OR（trigram 子串匹配）
    try:
        from ..database import engine

        with engine.connect() as conn:
            rows = conn.execute(
                __import__("sqlalchemy").text(
                    "SELECT ref_id, title, snippet(refs_fts, 1, '«', '»', '…', 14) AS snip "
                    "FROM refs_fts WHERE refs_fts MATCH :q ORDER BY rank LIMIT :lim"
                ),
                {"q": keywords, "lim": limit},
            ).all()
    except Exception as e:
        raise HTTPException(400, f"检索失败：{e}") from e
    ids = [r[0] for r in rows]
    titles: dict[int, str] = {r.id: r.title for r in db.query(models.Reference).filter(models.Reference.id.in_(ids)).all()}
    return {
        "items": [{
            "reference_id": r[0],
            "title": titles.get(r[0], "") or r[1],
            "snippet": r[2] or "",
        } for r in rows],
        "query": q,
        "keywords": keywords,
        "expanded": expanded,
    }


# ---------- AI 自动关联（本地 TF-IDF 预筛 + LLM 批量评分，整体覆盖） ----------
@router.post("/ai-auto-link")
def ai_auto_link(db: Session = Depends(get_db)):
    """一键执行 AI 自动关联：文本相似 + 结构化特征双路候选 → LLM 批量评分 → 持久化覆盖旧结果。"""
    from ..services import ai_link, llm as llm_service

    with llm_service.ai_task():
        stats = ai_link.run_auto_link(db)
    if stats["created"] == 0:
        return {
            **stats,
            "message": (
                "未发现可关联的候选对。可先用「AI 补全信息」为文献补充摘要/标签后重试，"
                "或检查文献主题是否过于分散。"
            ),
        }
    return {
        **stats,
        "message": (
            f"已生成 {stats['created']} 条 AI 关联"
            + (f"（LLM 语义评分，共 {stats['llm_calls']} 次调用）" if stats["method"] == "llm" else "（本地特征相似度，未配置 LLM）")
            + (f"，其中 {stats['struct_pairs']} 对来自标签/作者等特征" if stats.get("struct_pairs") else "")
        ),
    }


@router.get("/ai-links")
def list_ai_links(db: Session = Depends(get_db)):
    """列出全部 AI 关联（含双方标题，供管理）。"""
    links = db.query(models.ReferenceAiLink).order_by(models.ReferenceAiLink.weight.desc()).all()
    titles: dict[int, str] = {r.id: r.title for r in db.query(models.Reference).all()}
    return [{
        "id": l.id,
        "ref_a": l.ref_a, "ref_b": l.ref_b,
        "title_a": titles.get(l.ref_a, ""), "title_b": titles.get(l.ref_b, ""),
        "weight": l.weight, "reason": l.reason, "tags": l.tags or [],
        "method": l.method, "updated_at": l.updated_at,
    } for l in links]


@router.delete("/ai-links")
def clear_ai_links(db: Session = Depends(get_db)):
    """一键清除全部 AI 关联。"""
    db.query(models.ReferenceAiLink).delete()
    db.commit()
    return {"ok": True}


@router.delete("/ai-links/{link_id}")
def delete_ai_link(link_id: int, db: Session = Depends(get_db)):
    """删除单条 AI 关联。"""
    link = db.get(models.ReferenceAiLink, link_id)
    if not link:
        raise HTTPException(404, "AI 关联不存在")
    db.delete(link)
    db.commit()
    return {"ok": True}


# ---------- AI 自动匹配文献信息（CrossRef 结构化补全 + LLM 语义推断，只填空缺） ----------
def _ai_metadata_for(db: Session, ref: models.Reference) -> dict:
    """单篇补全流水线：自动提取 PDF 文本 → CrossRef → LLM 推断 → 写回。"""
    from ..services import metadata, pdfextract, storage as storage_service

    # 1) 有 PDF 未提取 → 自动提取文本（供 LLM 上下文）
    rt = db.query(models.ReferenceText).filter_by(reference_id=ref.id).first()
    if ref.stored_path and (not rt or not rt.text):
        path = storage_service.storage.abs_path(ref.stored_path)
        if path.exists():
            text = pdfextract.extract_pdf_text(path)
            if text:
                info = pdfextract.make_summary(text)
                if rt is None:
                    rt = models.ReferenceText(reference_id=ref.id)
                rt.text = text
                if not rt.summary:
                    rt.summary = info.get("summary", "")
                if not rt.keywords:
                    rt.keywords = info.get("keywords", "")
                db.add(rt)
                db.commit()

    filled: list[str] = []
    source = "none"

    # 2) CrossRef 结构化补全（有 DOI 时免费准确）
    if ref.doi:
        crossref_data = metadata.fetch_crossref(ref.doi)
        if crossref_data:
            step_filled, rt = metadata.merge_metadata(ref, rt, crossref_data)
            filled += step_filled
            source = "crossref"

    # 3) LLM 语义推断（含分区/影响因子；未配置 LLM 时跳过）
    text_ctx = ""
    if rt and rt.text:
        text_ctx = rt.text
    elif rt and rt.summary:
        text_ctx = rt.summary
    llm_data = metadata.infer_metadata_llm(db, ref, text_ctx)
    if llm_data:
        step_filled, rt = metadata.merge_metadata(ref, rt, llm_data)
        filled += step_filled
        source = "llm" if source == "none" else "mixed"

    if rt is not None:
        db.add(rt)
    db.commit()
    return {"filled": sorted(set(filled)), "source": source}


@router.post("/{rid}/ai-metadata")
def ai_metadata(rid: int, db: Session = Depends(get_db)):
    """AI 自动匹配单篇文献信息：只填空缺字段，不覆盖已有值。"""
    ref = _get(db, rid)
    result = _ai_metadata_for(db, ref)
    if not result["filled"]:
        raise HTTPException(400, "未能补全任何字段（可配置 LLM 后重试；或检查 DOI 与网络）")
    return result


@router.post("/ai-match")
def ai_match(body: dict, db: Session = Depends(get_db)):
    """批量 AI 补全：默认只处理信息不完整的文献（缺 DOI/期刊/年份/分区之一），逐篇补全。"""
    from ..services import llm as llm_service

    limit = max(1, min(int(body.get("limit", 20)), 50))
    only_incomplete = body.get("only_incomplete", True)
    query = db.query(models.Reference)
    if only_incomplete:
        from sqlalchemy import or_

        query = query.filter(or_(
            models.Reference.doi == "",
            models.Reference.venue == "",
            models.Reference.year.is_(None),
            models.Reference.jcr_quartile == "",
        ))
    refs = query.order_by(models.Reference.updated_at.desc()).limit(limit).all()
    results = []
    with llm_service.ai_task():
        for ref in refs:
            try:
                r = _ai_metadata_for(db, ref)
                results.append({"id": ref.id, "filled": r["filled"], "source": r["source"]})
            except Exception:
                results.append({"id": ref.id, "filled": [], "source": "error"})
    filled_total = sum(len(r["filled"]) for r in results)
    return {
        "processed": len(results),
        "filled_total": filled_total,
        "results": results,
    }


@router.get("/network/stats")
def network_stats(db: Session = Depends(get_db)):
    """图谱统计：节点/边/引用抓取情况。"""
    refs = db.query(models.Reference).all()
    citations = db.query(models.ReferenceCitation).all()
    cmap = _citations_map(db)
    data = network_service.build_network(refs, cmap)
    return {
        "node_count": len(data["nodes"]),
        "link_count": len(data["links"]),
        "citation_link_count": sum(1 for l in data["links"] if l["citation"]),
        "citations_fetched": len(cmap),          # 已抓取引用的文献数
        "citation_records": len(citations),      # 引用记录条数
    }


@router.post("/fetch-all-citations")
def fetch_all_citations(db: Session = Depends(get_db)):
    """批量抓取全部有 DOI 文献的引用（逐篇覆盖更新）。"""
    refs = [r for r in db.query(models.Reference).all() if r.doi]
    fetched_total = 0
    errors = 0
    for r in refs:
        try:
            cited = network_service.fetch_citations_from_openalex(r.doi)
        except ValueError:
            errors += 1
            continue
        db.query(models.ReferenceCitation).filter_by(ref_id=r.id).delete()
        for doi in cited:
            db.add(models.ReferenceCitation(ref_id=r.id, cited_doi=doi))
        fetched_total += len(cited)
        db.commit()

    doi_index = {network_service._normalize_doi(x.doi): x.id for x in db.query(models.Reference).all() if x.doi}
    matched_total = 0
    for row in db.query(models.ReferenceCitation).all():
        if network_service._normalize_doi(row.cited_doi) in doi_index and doi_index[network_service._normalize_doi(row.cited_doi)] != row.ref_id:
            matched_total += 1
    return {"refs": len(refs), "fetched": fetched_total, "matched": matched_total, "errors": errors}


@router.delete("/citations/{cid}")
def delete_citation(cid: int, db: Session = Depends(get_db)):
    c = db.get(models.ReferenceCitation, cid)
    if not c:
        raise HTTPException(404, "引用记录不存在")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/{rid}")
def get_reference(rid: int, db: Session = Depends(get_db)):
    return _get(db, rid)


@router.put("/{rid}")
def update_reference(rid: int, body: schemas.ReferenceUpdate, db: Session = Depends(get_db)):
    r = _get(db, rid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    r.updated_at = datetime.now()
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{rid}")
def delete_reference(rid: int, db: Session = Depends(get_db)):
    r = _get(db, rid)
    if r.stored_path:
        try:
            storage.storage.delete(r.stored_path)
        except (ValueError, OSError):
            pass
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---------- 附件 ----------
@router.post("/{rid}/attachment")
async def upload_attachment(rid: int, file: UploadFile, db: Session = Depends(get_db)):
    r = _get(db, rid)
    if r.stored_path:
        try:
            storage.storage.delete(r.stored_path)
        except (ValueError, OSError):
            pass
    data = await file.read()
    rel, safe = storage.storage.save(data, file.filename or "paper.pdf")
    r.file_name = safe
    r.stored_path = rel
    r.updated_at = datetime.now()
    db.commit()
    return schemas.ReferenceOut.model_validate(r)


@router.get("/{rid}/download")
def download_attachment(rid: int, db: Session = Depends(get_db)):
    r = _get(db, rid)
    if not r.stored_path:
        raise HTTPException(404, "暂无附件")
    path = storage.storage.abs_path(r.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    disposition = f"attachment; filename*=UTF-8''{quote(r.file_name or 'paper.pdf')}"
    return FileResponse(path, media_type="application/octet-stream", headers={"Content-Disposition": disposition})


# ---------- BibTeX ----------
@router.post("/import-bib")
async def import_bib(file: UploadFile, db: Session = Depends(get_db)):
    text = (await file.read()).decode("utf-8", errors="replace")
    entries = bibtex.parse_bibtex(text)
    created = 0
    skipped = 0
    for e in entries:
        if e["doi"] and db.query(models.Reference).filter(models.Reference.doi == e["doi"]).first():
            skipped += 1
            continue
        r = models.Reference(**e)
        db.add(r)
        db.commit()
        created += 1
    return {"imported": created, "skipped": skipped, "total": len(entries)}


# ---------- DOI ----------
@router.post("/doi-metadata")
def doi_metadata(body: schemas.DoiRequest):
    """从 CrossRef 抓取 DOI 元数据；网络不可用或未找到时返回 404，前端降级为手动填写。"""
    meta = doi.fetch_doi_metadata(body.doi)
    if not meta or not meta.get("title"):
        raise HTTPException(404, "未能获取该 DOI 的元数据（请检查网络或 DOI 是否正确）")
    return meta


# ---------- 阅读队列 / RIS 导入 / PDF 批注 ----------
@router.patch("/{rid}/queue")
def update_queue(rid: int, body: dict, db: Session = Depends(get_db)):
    """加入/调整队列：{priority: 1-3, date}；priority=0 出队。"""
    r = _get(db, rid)
    priority = max(0, min(3, int(body.get("priority", 0))))
    r.queue_priority = priority
    d = body.get("date")
    r.queue_date = date.fromisoformat(d) if d else (date.today() if priority > 0 else None)
    db.commit()
    return {"queue_priority": r.queue_priority, "queue_date": r.queue_date.isoformat() if r.queue_date else None}


@router.post("/import-ris")
async def import_ris(file: UploadFile, db: Session = Depends(get_db)):
    """导入 RIS 格式（Zotero/EndNote 导出），DOI 去重。"""
    from ..services import ris as ris_service

    text = (await file.read()).decode("utf-8", errors="replace")
    entries = ris_service.parse_ris(text)
    created = 0
    skipped = 0
    for e in entries:
        if e["doi"] and db.query(models.Reference).filter(models.Reference.doi == e["doi"]).first():
            skipped += 1
            continue
        db.add(models.Reference(**e))
        db.commit()
        created += 1
    return {"imported": created, "skipped": skipped, "total": len(entries)}


@router.get("/{rid}/annotations", response_model=list[schemas.AnnotationOut])
def list_annotations(rid: int, db: Session = Depends(get_db)):
    _get(db, rid)
    anns = db.query(models.PdfAnnotation).filter_by(reference_id=rid).order_by(models.PdfAnnotation.page, models.PdfAnnotation.id).all()
    return anns


@router.post("/{rid}/annotations", response_model=schemas.AnnotationOut)
def create_annotation(rid: int, body: schemas.AnnotationCreate, db: Session = Depends(get_db)):
    _get(db, rid)
    a = models.PdfAnnotation(reference_id=rid, **body.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.put("/annotations/{aid}", response_model=schemas.AnnotationOut)
def update_annotation(aid: int, body: schemas.AnnotationUpdate, db: Session = Depends(get_db)):
    a = db.get(models.PdfAnnotation, aid)
    if not a:
        raise HTTPException(404, "批注不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return a


@router.delete("/annotations/{aid}")
def delete_annotation(aid: int, db: Session = Depends(get_db)):
    a = db.get(models.PdfAnnotation, aid)
    if not a:
        raise HTTPException(404, "批注不存在")
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------- 引用抓取（需联网） ----------
@router.post("/{rid}/fetch-citations")
def fetch_citations(rid: int, db: Session = Depends(get_db)):
    """抓取单篇文献的引用（OpenAlex），覆盖更新其引用记录。"""
    r = _get(db, rid)
    if not r.doi:
        raise HTTPException(400, "该文献没有 DOI，无法抓取引用")
    try:
        cited = network_service.fetch_citations_from_openalex(r.doi)
    except ValueError as e:
        raise HTTPException(502, str(e)) from e

    db.query(models.ReferenceCitation).filter_by(ref_id=rid).delete()
    for doi in cited:
        db.add(models.ReferenceCitation(ref_id=rid, cited_doi=doi))
    db.commit()

    doi_index = {network_service._normalize_doi(x.doi): x.id for x in db.query(models.Reference).all() if x.doi}
    matched = sum(
        1 for d in cited
        if network_service._normalize_doi(d) in doi_index and doi_index[network_service._normalize_doi(d)] != rid
    )
    return {"fetched": len(cited), "matched": matched, "total": len(cited)}


# ---------- 精读 / 阅读进度 / 时长 / 重复合并 ----------
@router.get("/{rid}/deep-reading", response_model=schemas.DeepReadingOut)
def get_deep_reading(rid: int, db: Session = Depends(get_db)):
    _get(db, rid)
    dr = db.query(models.DeepReading).filter_by(reference_id=rid).first()
    if not dr:
        dr = models.DeepReading(reference_id=rid)
        db.add(dr)
        db.commit()
        db.refresh(dr)
    return dr


@router.put("/{rid}/deep-reading", response_model=schemas.DeepReadingOut)
def update_deep_reading(rid: int, body: schemas.DeepReadingUpdate, db: Session = Depends(get_db)):
    _get(db, rid)
    dr = db.query(models.DeepReading).filter_by(reference_id=rid).first()
    if not dr:
        dr = models.DeepReading(reference_id=rid)
        db.add(dr)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(dr, k, v)
    db.commit()
    db.refresh(dr)
    return dr


@router.patch("/{rid}/progress")
def update_progress(rid: int, body: dict, db: Session = Depends(get_db)):
    r = _get(db, rid)
    progress = max(0, min(100, int(body.get("progress", 0))))
    r.reading_progress = progress
    if progress >= 100:
        r.read_status = "已读"
    elif progress > 0 and r.read_status == "未读":
        r.read_status = "在读"
    db.commit()
    return {"progress": r.reading_progress, "read_status": r.read_status}


@router.post("/{rid}/reading-session")
def add_reading_session(rid: int, body: dict, db: Session = Depends(get_db)):
    _get(db, rid)
    seconds = max(0, min(86400, int(body.get("seconds", 0))))
    if seconds >= 10:  # 少于 10 秒忽略（防误触）
        db.add(models.ReadingSession(reference_id=rid, seconds=seconds))
        db.commit()
    return {"ok": True}


@router.post("/{rid}/merge")
def merge_reference(rid: int, body: dict, db: Session = Depends(get_db)):
    """合并重复文献：被合并项（rid）并入目标项（target_id），软标记不物理删除。"""
    from ..services import duplicate

    target_id = int(body.get("target_id", 0))
    if target_id == rid:
        raise HTTPException(400, "不能合并到自身")
    r = _get(db, rid)
    t = db.get(models.Reference, target_id)
    if not t:
        raise HTTPException(404, "目标文献不存在")
    result = duplicate.merge(db, r, t)
    return {"ok": True, "merged_into": target_id, "kept": result}


# ---------- 全文检索（合法 OA：Unpaywall + arXiv） ----------
@router.post("/{rid}/fetch-fulltext")
def fetch_fulltext(rid: int, db: Session = Depends(get_db)):
    """自动检索并下载全文 PDF（Unpaywall → arXiv），需联网。"""
    r = _get(db, rid)
    try:
        result = fulltext.fetch_fulltext(r.doi, r.title)
    except Exception as e:
        raise HTTPException(502, f"全文检索失败：{e}") from e
    if not result:
        raise HTTPException(404, "未找到合法开放获取全文（可尝试手动上传 PDF）")
    data, fname, source = result
    rel, safe = storage.storage.save(data, fname)
    if r.stored_path:
        try:
            storage.storage.delete(r.stored_path)
        except (ValueError, OSError):
            pass
    r.file_name = safe
    r.stored_path = rel
    r.fulltext_source = "auto"
    r.updated_at = datetime.now()
    db.commit()
    return {"ok": True, "source": source, "file_name": safe, "size": len(data)}


@router.post("/fetch-all-fulltext")
def fetch_all_fulltext(db: Session = Depends(get_db)):
    """批量检索全文（逐篇，可中途离线）。"""
    refs = db.query(models.Reference).filter(models.Reference.file_name.is_(None)).all()
    ok = 0
    failed = 0
    for r in refs:
        try:
            result = fulltext.fetch_fulltext(r.doi, r.title)
        except Exception:
            result = None
        if not result:
            failed += 1
            continue
        data, fname, source = result
        rel, safe = storage.storage.save(data, fname)
        r.file_name = safe
        r.stored_path = rel
        r.fulltext_source = "auto"
        r.updated_at = datetime.now()
        db.commit()
        ok += 1
    return {"total": len(refs), "ok": ok, "failed": failed}


# ---------- 在线阅读与文本提取 ----------
@router.get("/{rid}/read")
def read_reference(rid: int, db: Session = Depends(get_db)):
    """在线阅读：PDF inline 响应（浏览器内嵌查看）。"""
    r = _get(db, rid)
    if not r.stored_path:
        raise HTTPException(404, "该文献暂无 PDF 附件，请先上传或自动检索全文")
    path = storage.storage.abs_path(r.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    disposition = f"inline; filename*=UTF-8''{quote(r.file_name or 'paper.pdf')}"
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": disposition})


@router.post("/{rid}/extract-text", response_model=schemas.ReferenceTextOut)
def extract_text(rid: int, db: Session = Depends(get_db)):
    """提取 PDF 全文文本 + 启发式摘要（pypdf，离线）。"""
    r = _get(db, rid)
    if not r.stored_path:
        raise HTTPException(400, "该文献暂无 PDF 附件")
    path = storage.storage.abs_path(r.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    text = pdfextract.extract_pdf_text(path)
    if not text:
        raise HTTPException(422, "未能提取文本：该 PDF 可能为扫描版（无文本层）")
    info = pdfextract.make_summary(text)
    existing = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
    if existing:
        existing.text = text
        existing.summary = info["summary"]
        existing.keywords = info["keywords"]
        existing.extracted_at = datetime.now()
        db.commit()
        db.refresh(existing)
        return existing
    rt = models.ReferenceText(
        reference_id=rid, text=text, summary=info["summary"], keywords=info["keywords"]
    )
    db.add(rt)
    db.commit()
    db.refresh(rt)
    return rt


@router.get("/{rid}/text", response_model=schemas.ReferenceTextOut)
def get_text(rid: int, db: Session = Depends(get_db)):
    rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
    if not rt:
        raise HTTPException(404, "尚未提取文本，请先执行提取")
    return rt


@router.get("/{rid}/export-text")
def export_text(rid: int, db: Session = Depends(get_db)):
    """导出全文文本（.md），供 ZCode 学术技能链（nature-reader/deep-research）消费。"""
    r = _get(db, rid)
    rt = db.query(models.ReferenceText).filter_by(reference_id=rid).first()
    if not rt:
        raise HTTPException(404, "尚未提取文本，请先执行提取")
    content = (
        f"# {r.title}\n\n"
        f"- 作者：{'、'.join(r.authors or [])}\n"
        f"- 年份：{r.year or '—'}　期刊：{r.venue or '—'}　DOI：{r.doi or '—'}\n\n"
        f"## 摘要\n{rt.summary}\n\n"
        f"## 关键词\n{rt.keywords or '—'}\n\n"
        f"## 全文\n{rt.text}\n"
    )
    disposition = "attachment; filename*=UTF-8''" + quote(f"{r.title[:50]}.md")
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": disposition})
