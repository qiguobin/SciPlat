"""PubMed E-utilities 文献检索（无 API key，遵守 NCBI ≤3 req/s 限流）。网络失败一律返回空，由调用方降级。"""
import re
import time

import httpx

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_UA = "sci-plat/1.0 (local research manager; mailto:local@example.com)"
DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s]+$")


def _esearch(term: str, retmax: int = 5) -> list[str]:
    """esearch 返回 PMID 列表。"""
    try:
        resp = httpx.get(
            f"{_EUTILS}/esearch.fcgi",
            params={"db": "pubmed", "term": term, "retmode": "json", "retmax": retmax},
            timeout=10.0,
            headers={"User-Agent": _UA},
        )
        resp.raise_for_status()
        return resp.json().get("esearchresult", {}).get("idlist", []) or []
    except Exception:
        return []


def _esummary(pmids: list[str]) -> dict:
    """esummary 批量取文献摘要信息。"""
    if not pmids:
        return {}
    try:
        resp = httpx.get(
            f"{_EUTILS}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
            timeout=10.0,
            headers={"User-Agent": _UA},
        )
        resp.raise_for_status()
        return resp.json().get("result", {}) or {}
    except Exception:
        return {}


def _parse_one(doc: dict) -> dict | None:
    """esummary 单条 → 统一字段结构。"""
    title = (doc.get("title") or "").strip()
    if not title:
        return None
    authors = []
    for a in doc.get("authors", []) or []:
        name = (a.get("name") or "").strip()
        if name:
            authors.append(name)
    year = None
    m = re.search(r"\d{4}", doc.get("pubdate") or "")
    if m:
        year = int(m.group())
    doi = ""
    for item in doc.get("articleids", []) or []:
        if item.get("idtype") == "doi":
            doi = (item.get("value") or "").strip()
            break
    langs = [str(x).lower() for x in (doc.get("lang") or []) if x]
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "venue": (doc.get("fulljournalname") or doc.get("source") or "").strip(),
        "doi": doi,
        "pmid": str(doc.get("uid") or ""),
        "language": langs[0] if langs else "",
    }


def search_pubmed(query: str, retmax: int = 5) -> list[dict]:
    """按标题或 DOI 检索 PubMed，返回结构化结果列表。网络失败返回 []。"""
    q = (query or "").strip()
    if not q:
        return []
    if DOI_RE.match(q):
        term = f"{q}[doi]"                      # DOI 精确检索
    else:
        safe = re.sub(r'["\[\]]', " ", q)[:200]  # 移除会破坏查询语法的字符
        term = f"{safe}[Title]"                  # 无引号词级检索（隐含 AND + 相关度排序，比精确短语命中率高）
    pmids = _esearch(term, retmax)
    if not pmids:
        return []
    time.sleep(0.35)  # NCBI 限流 ≤3 req/s
    summary = _esummary(pmids)
    out = []
    for pmid in pmids:
        doc = summary.get(str(pmid))
        if doc:
            parsed = _parse_one(doc)
            if parsed:
                out.append(parsed)
    return out


def search_pubmed_single(query: str) -> dict | None:
    """取最匹配的一条（用于自动补全）。"""
    results = search_pubmed(query, retmax=3)
    return results[0] if results else None
