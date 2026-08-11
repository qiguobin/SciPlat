"""文献全文检索：Unpaywall（按 DOI 查合法 OA PDF）+ arXiv API（按标题搜预印本）。

全部为合法开放获取渠道；网络不可用时返回 None，由路由层降级提示。
"""
import urllib.parse
import xml.etree.ElementTree as ET

import httpx

USER_AGENT = "sci-plat/1.0 (local research manager; mailto:local@example.com)"


def find_unpaywall_pdf(doi: str) -> str | None:
    """Unpaywall API：按 DOI 返回合法 OA PDF 直链。"""
    url = f"https://api.unpaywall.org/v2/{doi.strip()}?email=local@example.com"
    try:
        resp = httpx.get(url, timeout=12.0, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        msg = resp.json()
    except Exception:
        return None
    best = msg.get("best_oa_location") or {}
    return best.get("url_for_pdf")


def search_arxiv_pdf(title: str) -> str | None:
    """arXiv API：按标题检索预印本，返回最匹配条目的 PDF 链接。"""
    words = [w for w in title.replace(":", " ").split() if len(w) > 1][:8]
    if not words:
        return None
    url = (
        "http://export.arxiv.org/api/query?"
        + urllib.parse.urlencode({"search_query": "all:" + "+".join(words), "max_results": 5})
    )
    try:
        resp = httpx.get(url, timeout=15.0, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except Exception:
        return None

    ns = {"a": "http://www.w3.org/2005/Atom"}
    query_words = set(" ".join(title.lower().split()).split())
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None
    for entry in root.findall("a:entry", ns):
        t = " ".join((entry.findtext("a:title", "", ns) or "").lower().split())
        overlap = len(query_words & set(t.split()))
        if overlap >= max(2, len(query_words) // 2):
            for link in entry.findall("a:link", ns):
                if link.get("title") == "pdf":
                    return link.get("href")
    return None


def fetch_fulltext(doi: str, title: str) -> tuple[bytes, str, str] | None:
    """按 Unpaywall → arXiv 顺序检索并下载 PDF。

    返回 (PDF 字节, 文件名, 来源) 或 None（未找到/网络失败/非 PDF）。
    """
    pdf_url = None
    source = ""
    if doi:
        pdf_url = find_unpaywall_pdf(doi)
        source = "unpaywall"
    if not pdf_url:
        pdf_url = search_arxiv_pdf(title)
        source = "arxiv"
    if not pdf_url:
        return None
    try:
        resp = httpx.get(pdf_url, timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            return None
    except Exception:
        return None
    return resp.content, f"fulltext_{source}.pdf", source
