"""科研动态追踪：arXiv API + RSS 双源抓取（去重、限速、降级）。"""
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime

import httpx

USER_AGENT = "sci-plat/1.0 (local research tracker; mailto:local@example.com)"
ARXIV_INTERVAL = 3.0  # arXiv 限速：1 req / 3s
_last_arxiv_fetch = 0.0


def _respect_rate_limit() -> None:
    global _last_arxiv_fetch
    elapsed = time.time() - _last_arxiv_fetch
    if elapsed < ARXIV_INTERVAL:
        time.sleep(ARXIV_INTERVAL - elapsed)
    _last_arxiv_fetch = time.time()


def _clean_arxiv_id(raw: str) -> str:
    """arXiv ID 去版本后缀：2507.01234v2 → 2507.01234（用于去重）。"""
    return re.sub(r"v\d+$", "", raw.strip())


def fetch_arxiv(query: str, max_results: int = 30) -> list[dict]:
    """arXiv API 抓取：按提交日期倒序，返回条目列表。网络失败抛 ValueError。"""
    _respect_rate_limit()
    url = (
        "https://export.arxiv.org/api/query?"
        + urllib.parse.urlencode({
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        })
    )
    try:
        resp = httpx.get(url, timeout=15.0, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except Exception as e:
        raise ValueError(f"arXiv 抓取失败：{e}") from e

    ns = {"a": "http://www.w3.org/2005/Atom"}
    items: list[dict] = []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        raise ValueError(f"arXiv 响应解析失败：{e}") from e

    for entry in root.findall("a:entry", ns):
        aid = _clean_arxiv_id((entry.findtext("a:id", "", ns) or "").split("/abs/")[-1])
        published = entry.findtext("a:published", "", ns)
        items.append({
            "external_id": aid or published,
            "title": " ".join((entry.findtext("a:title", "", ns) or "").split()),
            "authors": [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns) if a.findtext("a:name", "", ns)],
            "abstract": " ".join((entry.findtext("a:summary", "", ns) or "").split()),
            "link": (entry.findtext("a:id", "", ns) or ""),
            "published": published[:10] if published else None,
        })
    return items


def fetch_rss(url: str, max_items: int = 30, timeout: float = 12.0) -> list[dict]:
    """RSS 2.0 / Atom 抓取。网络失败抛 ValueError。"""
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except Exception as e:
        raise ValueError(f"RSS 抓取失败：{e}") from e

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        raise ValueError(f"RSS 解析失败（非标准 XML）：{e}") from e

    items: list[dict] = []
    # RSS 2.0
    for item in root.findall(".//item"):
        if len(items) >= max_items:
            break
        title = " ".join((item.findtext("title") or "").split())
        guid = item.findtext("guid") or item.findtext("link") or title
        pub = item.findtext("pubDate") or item.findtext("dc:date", "", {"dc": "http://purl.org/dc/elements/1.1/"})
        items.append({
            "external_id": guid.strip()[:200],
            "title": title,
            "authors": [],
            "abstract": " ".join((item.findtext("description") or item.findtext("summary") or "").split())[:2000],
            "link": item.findtext("link") or "",
            "published": _parse_date(pub),
        })
    # Atom
    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        if len(items) >= max_items:
            break
        title = " ".join((entry.findtext("{http://www.w3.org/2005/Atom}title") or "").split())
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        pub = entry.findtext("{http://www.w3.org/2005/Atom}published") or entry.findtext("{http://www.w3.org/2005/Atom}updated")
        items.append({
            "external_id": (entry.findtext("{http://www.w3.org/2005/Atom}id") or title).strip()[:200],
            "title": title,
            "authors": [a.findtext("{http://www.w3.org/2005/Atom}name") for a in entry.findall("{http://www.w3.org/2005/Atom}author") if a.findtext("{http://www.w3.org/2005/Atom}name")],
            "abstract": " ".join((entry.findtext("{http://www.w3.org/2005/Atom}summary") or "").split())[:2000],
            "link": link_el.get("href") if link_el is not None else "",
            "published": pub[:10] if pub else None,
        })
    return items


def _parse_date(s: str | None) -> str | None:
    if not s:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m = re.search(r"\d{2}\s+\w{3}\s+\d{4}", s)  # RFC822: 17 Jun 2026
    if m:
        try:
            return datetime.strptime(m.group(0), "%d %b %Y").date().isoformat()
        except ValueError:
            return None
    return None


def tldr(abstract: str, max_len: int = 220) -> str:
    """启发式 TLDR：摘要首句 + 截断。"""
    if not abstract:
        return ""
    first = re.split(r"[.。]\s", abstract, maxsplit=1)[0]
    return (first[:max_len] + "…") if len(first) > max_len else first
