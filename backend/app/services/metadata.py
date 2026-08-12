"""AI 自动匹配文献信息：CrossRef 结构化补全 + LLM 语义推断。

流程：
1. 有 DOI → CrossRef 补全基础字段（标题/作者/年份/期刊/摘要）
2. LLM 从标题/摘要/PDF 文本推断剩余字段（分类/标签/关键词/JCR·中科院·新锐分区/影响因子）
3. 只填空缺字段、不覆盖已有值（merge_metadata 保证），推断结果全部可手动修改

未配置 LLM 时仅执行 CrossRef 步骤；CrossRef 不可用时仅执行 LLM 步骤。
"""
import json
import re
from typing import Optional

from . import llm as llm_service
from .. import models

MAX_TEXT_CTX = 60000   # 注入 LLM 的文本上限（沿用 ai.py 约定）
CATEGORY_OPTIONS = ["经典必读", "综述", "方法", "数据", "工具", "其他"]
JCR_OPTIONS = ["Q1", "Q2", "Q3", "Q4"]
QUARTILE_OPTIONS = ["1区", "2区", "3区", "4区"]


def _parse_crossref_msg(msg: dict) -> dict:
    """CrossRef message → 统一字段结构。"""
    title = (msg.get("title") or [""])[0]
    authors = []
    for a in msg.get("author", [])[:20]:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x)
        if name:
            authors.append(name)
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = msg.get(key, {}).get("date-parts", [[]])
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    venue = (msg.get("container-title") or [""])[0] or msg.get("publisher", "")
    abstract = re.sub(r"<[^>]+>", "", msg.get("abstract", "")).strip()
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
        "abstract": abstract,
    }


def fetch_crossref(doi: str) -> dict:
    """CrossRef DOI 精确查询：标题/作者/年份/期刊/摘要。网络或解析失败返回 {}。"""
    import httpx

    url = f"https://api.crossref.org/works/{doi.strip()}"
    try:
        resp = httpx.get(
            url,
            timeout=8.0,
            headers={"User-Agent": "sci-plat/1.0 (local research manager)"},
        )
        resp.raise_for_status()
        msg = resp.json().get("message", {})
    except Exception:
        return {}
    return _parse_crossref_msg(msg)


def fetch_crossref_search(query: str, limit: int = 3) -> list[dict]:
    """CrossRef 标题检索（query.bibliographic，补充收录的中文期刊）。失败返回 []。"""
    import httpx

    q = (query or "").strip()
    if not q:
        return []
    try:
        resp = httpx.get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": q, "rows": limit},
            timeout=10.0,
            headers={"User-Agent": "sci-plat/1.0 (local research manager; mailto:local@example.com)"},
        )
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", []) or []
    except Exception:
        return []
    out = []
    for msg in items:
        parsed = _parse_crossref_msg(msg)
        parsed["doi"] = (msg.get("DOI") or "").strip()
        if parsed.get("title"):
            out.append(parsed)
    return out


def fetch_openalex(query: str, limit: int = 3) -> list[dict]:
    """OpenAlex 标题检索：中英文均覆盖（中文期刊收录充分、title 为中文原文）。失败返回 []。"""
    import httpx

    q = (query or "").strip()
    if not q:
        return []
    try:
        resp = httpx.get(
            "https://api.openalex.org/works",
            params={"search": q, "per-page": limit, "mailto": "sciplat@example.com"},
            timeout=10.0,
            headers={"User-Agent": "sci-plat/1.0 (local research manager)"},
        )
        resp.raise_for_status()
        items = resp.json().get("results", []) or []
    except Exception:
        return []
    out = []
    for w in items:
        title = (w.get("title") or "").strip()
        if not title:
            continue
        authors = []
        for a in w.get("authorships", []) or []:
            name = ((a.get("author") or {}).get("display_name") or "").strip()
            if name:
                authors.append(name)
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        doi = (w.get("doi") or "").replace("https://doi.org/", "").strip()
        out.append({
            "title": title,
            "authors": authors,
            "year": w.get("publication_year"),
            "venue": (src.get("display_name") or "").strip(),
            "doi": doi,
            "language": (w.get("language") or "").lower(),
        })
    return out


def _norm_title(t: str) -> str:
    """标题归一化：小写并去除空白与常见标点（中英文通用）。"""
    return re.sub(r"[\s\-_·.,:;()\[\]{}“”\"'‘’、]+", "", (t or "").lower())


def title_similarity(a: str, b: str) -> float:
    """标题归一化相似度（0-1），用于自动补全时过滤不相关候选。"""
    import difflib

    return difflib.SequenceMatcher(None, _norm_title(a), _norm_title(b)).ratio()


def match_candidates(q: str, source: str = "auto", limit: int = 5) -> list[dict]:
    """多来源候选检索：auto 按优先级全查。返回统一结构，按 DOI/标题去重，每条带 source 标记。"""
    from . import pubmed

    q = (q or "").strip()
    if not q:
        return []
    results: list[dict] = []
    if source in ("auto", "pubmed"):
        for item in pubmed.search_pubmed(q, retmax=limit):
            item["source"] = "pubmed"
            results.append(item)
    if source in ("auto", "openalex"):
        for item in fetch_openalex(q, limit=limit):
            item["source"] = "openalex"
            results.append(item)
    if source in ("auto", "crossref"):
        for item in fetch_crossref_search(q, limit=limit):
            item["source"] = "crossref"
            results.append(item)
    # 去重：优先按 DOI，其次按归一化标题
    seen_doi, seen_title, dedup = set(), set(), []
    for item in results:
        d = (item.get("doi") or "").strip().lower()
        if d:
            if d in seen_doi:
                continue
            seen_doi.add(d)
        t = _norm_title(item.get("title", ""))
        if t and t in seen_title:
            continue
        seen_title.add(t)
        dedup.append(item)
    return dedup


def _parse_json_object(text: str) -> Optional[dict]:
    """容错解析 LLM 返回的 JSON 对象（容忍 markdown 代码块与前后缀文本）。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(t[start:end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def infer_metadata_llm(db, ref: models.Reference, text: str = "") -> dict:
    """LLM 推断缺失元数据。未配置 LLM / 调用失败 / 解析失败返回 {}。"""
    if not llm_service.is_configured(db):
        return {}
    system = (
        "你是文献信息自动补全助手。根据给定文献信息推断缺失的元数据，只输出一个 JSON 对象（不要任何其他文字），格式："
        '{"abstract": "摘要（300字内）", "keywords": "3-8个关键词，逗号分隔", "category": "分类（只能从：'
        + "、".join(CATEGORY_OPTIONS) + ' 中选择一个）", "tags": "2-5个标签，逗号分隔", "venue": "期刊/会议全称",'
        '"year": 2024, "authors": ["作者1"], "jcr_quartile": "Q1到Q4", "cas_quartile": "1区到4区",'
        '"xinrui_quartile": "1区到4区", "journal_if": "影响因子数字"}。'
        "不知道的字段用 null；分区与影响因子基于期刊名按你的知识判断，不确定就 null。"
    )
    known = (
        f"标题：{ref.title}\nDOI：{ref.doi or '无'}\n"
        f"作者：{'、'.join((ref.authors or [])[:5]) or '未知'}\n"
        f"期刊：{ref.venue or '未知'}\n年份：{ref.year or '未知'}"
    )
    excerpt = ""
    if text:
        excerpt = f"\n\n文献摘要/全文片段：\n{text[:MAX_TEXT_CTX]}"
    try:
        raw = llm_service.chat(db, system, [{"role": "user", "content": known + excerpt}], max_tokens=2000, task="metadata")
    except Exception:
        return {}
    data = _parse_json_object(raw)
    if not data:
        return {}
    return {k: v for k, v in data.items() if v not in (None, "", [])}


def merge_metadata(ref: models.Reference, rt: Optional[models.ReferenceText], data: dict) -> tuple[list[str], models.ReferenceText]:
    """只填空缺字段，不覆盖已有值；返回 (补全字段列表, ReferenceText)。"""
    filled: list[str] = []
    if rt is None:
        rt = models.ReferenceText(reference_id=ref.id)

    def _norm_list(v) -> list:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return [x.strip() for x in str(v).split(",") if x.strip()]

    # Reference 字段
    if not ref.title and data.get("title"):
        ref.title = str(data["title"]).strip()[:500]
        filled.append("title")
    if not ref.doi and data.get("doi"):
        d = str(data["doi"]).strip()
        if re.match(r"^10\.\d{4,9}/\S+$", d):
            ref.doi = d[:200]
            filled.append("doi")
    if not ref.venue and data.get("venue"):
        ref.venue = str(data["venue"]).strip()[:200]
        filled.append("venue")
    if not ref.year and data.get("year") not in (None, ""):
        try:
            ref.year = int(data["year"])
            filled.append("year")
        except (ValueError, TypeError):
            pass
    if not ref.authors and data.get("authors"):
        authors = _norm_list(data["authors"])[:20]
        if authors:
            ref.authors = authors
            filled.append("authors")
    if not ref.tags and data.get("tags"):
        tags = ", ".join(_norm_list(data["tags"])[:8])
        if tags:
            ref.tags = tags
            filled.append("tags")
    if not ref.category and data.get("category"):
        cat = str(data["category"]).strip()
        if cat in CATEGORY_OPTIONS:
            ref.category = cat
            filled.append("category")
    if not ref.journal_if and data.get("journal_if"):
        ref.journal_if = str(data["journal_if"]).strip()[:20]
        filled.append("journal_if")
    if not ref.jcr_quartile and data.get("jcr_quartile"):
        q = str(data["jcr_quartile"]).strip().upper()
        if q in JCR_OPTIONS:
            ref.jcr_quartile = q
            filled.append("jcr_quartile")
    for attr, options in (("cas_quartile", QUARTILE_OPTIONS), ("xinrui_quartile", QUARTILE_OPTIONS)):
        if not getattr(ref, attr) and data.get(attr):
            q = str(data[attr]).strip()
            if q in options:
                setattr(ref, attr, q)
                filled.append(attr)

    # ReferenceText：摘要 / 关键词（仅空缺时补）
    if not rt.summary and data.get("abstract"):
        rt.summary = str(data["abstract"]).strip()[:20000]
        filled.append("summary")
    if not rt.keywords and data.get("keywords"):
        rt.keywords = ", ".join(_norm_list(data["keywords"])[:12])[:2000]
        filled.append("keywords")
    return filled, rt
