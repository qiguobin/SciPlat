"""文献重复检测与合并（DOI 归一化 / 标题相似度），合并采用软标记不物理删除。"""
import difflib


def _norm_title(s: str) -> str:
    return " ".join((s or "").lower().split())


def find_duplicates(refs: list) -> list[dict]:
    """返回重复组列表：每组含 ids 与原因。"""
    groups: list[dict] = []
    used: set[int] = set()
    n = len(refs)
    for i in range(n):
        a = refs[i]
        if a.id in used:
            continue
        group = [a.id]
        reason = ""
        for j in range(i + 1, n):
            b = refs[j]
            if b.id in used:
                continue
            if a.doi and b.doi and a.doi.strip().lower() == b.doi.strip().lower():
                group.append(b.id)
                reason = "DOI 相同"
            elif _norm_title(a.title) and _norm_title(a.title) == _norm_title(b.title):
                group.append(b.id)
                reason = "标题相同"
            elif (
                _norm_title(a.title) and _norm_title(b.title)
                and difflib.SequenceMatcher(None, _norm_title(a.title), _norm_title(b.title)).ratio() > 0.9
            ):
                group.append(b.id)
                reason = "标题高度相似"
        if len(group) > 1:
            groups.append({"ids": group, "reason": reason})
            used.update(group)
    return groups


def merge(db, source, target) -> dict:
    """把 source 并入 target：并集保留标签/分类/附件/精读/引用，软标记 merged_into。"""
    from .. import models

    # 标签并集
    src_tags = {t.strip() for t in (source.tags or "").split(",") if t.strip()}
    tgt_tags = {t.strip() for t in (target.tags or "").split(",") if t.strip()}
    target.tags = ", ".join(sorted(tgt_tags | src_tags))
    # 分类：目标为空则继承
    if not target.category or target.category == "其他":
        target.category = source.category or "其他"
    # 作者并集
    tgt_authors = {x.strip().lower() for x in (target.authors or [])}
    for x in (source.authors or []):
        if x.strip().lower() not in tgt_authors:
            target.authors = list(target.authors or []) + [x]
    # 附件：目标无附件则继承
    if not target.stored_path and source.stored_path:
        target.file_name = source.file_name
        target.stored_path = source.stored_path
        target.fulltext_source = source.fulltext_source
    # 精读并集（非空字段合并）
    tgt_dr = db.query(models.DeepReading).filter_by(reference_id=target.id).first()
    src_dr = db.query(models.DeepReading).filter_by(reference_id=source.id).first()
    if src_dr and not tgt_dr:
        db.add(models.DeepReading(
            reference_id=target.id,
            question=src_dr.question, method=src_dr.method,
            conclusion=src_dr.conclusion, insight=src_dr.insight,
        ))
    elif src_dr and tgt_dr:
        for f in ("question", "method", "conclusion", "insight"):
            if not getattr(tgt_dr, f) and getattr(src_dr, f):
                setattr(tgt_dr, f, getattr(src_dr, f))
    # 文本提取继承
    src_text = db.query(models.ReferenceText).filter_by(reference_id=source.id).first()
    tgt_text = db.query(models.ReferenceText).filter_by(reference_id=target.id).first()
    if src_text and not tgt_text:
        src_text.reference_id = target.id
    # 阶段文献关联重定向
    db.query(models.PhaseReference).filter_by(reference_id=source.id).update(
        {"reference_id": target.id}, synchronize_session=False
    )
    # AI 关联重定向：涉及 source 的行改为 target；若与现有行重复则删除
    existing_ai: set[tuple[int, int]] = set()
    for l in db.query(models.ReferenceAiLink).all():
        existing_ai.add((l.ref_a, l.ref_b))
    for l in db.query(models.ReferenceAiLink).filter(
        (models.ReferenceAiLink.ref_a == source.id) | (models.ReferenceAiLink.ref_b == source.id)
    ).all():
        a = l.ref_a if l.ref_a != source.id else l.ref_b
        b = l.ref_b if l.ref_b != source.id else l.ref_a
        a, b = (target.id, b) if a == source.id else (a, target.id)
        a, b = sorted((a, b))
        if a == b:
            db.delete(l)
        elif (a, b) in existing_ai:
            db.delete(l)
        else:
            l.ref_a, l.ref_b = a, b
            existing_ai.add((a, b))
    # 引用记录并集
    src_cits = {c.cited_doi for c in source.citations}
    tgt_cits = {c.cited_doi for c in target.citations}
    for doi in src_cits - tgt_cits:
        db.add(models.ReferenceCitation(reference_id=target.id, cited_doi=doi))
    # 笔记重定向
    db.query(models.Note).filter_by(target_type="reference", target_id=source.id).update(
        {"target_id": target.id}, synchronize_session=False
    )
    # 软标记
    source.title = f"[已合并] {source.title}"
    source.tags = ""
    if source.stored_path and source.stored_path != target.stored_path:
        from . import storage as storage_service
        try:
            storage_service.storage.delete(source.stored_path)
        except (ValueError, OSError):
            pass
        source.stored_path = None
        source.file_name = None
    db.commit()
    return {
        "tags": sorted(tgt_tags | src_tags),
        "authors": target.authors,
        "attachment_kept": bool(target.stored_path),
        "notes_redirected": True,
    }
