"""CrossRef DOI 元数据抓取。网络不可用时返回 None，由调用方降级为手动填写。"""
import httpx


def fetch_doi_metadata(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{doi.strip()}"
    try:
        resp = httpx.get(
            url,
            timeout=8.0,
            headers={"User-Agent": "sci-plat/1.0 (local research manager; mailto:local@example.com)"},
        )
        resp.raise_for_status()
        msg = resp.json()["message"]
    except Exception:
        return None

    title = (msg.get("title") or [""])[0]
    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in msg.get("author", [])
        if a.get("family")
    ]
    year = None
    for k in ("published-print", "published-online", "issued", "created"):
        v = msg.get(k)
        if v and v.get("date-parts") and v["date-parts"][0]:
            year = v["date-parts"][0][0]
            break
    venue = (msg.get("container-title") or [""])[0] or (msg.get("publisher") or "")
    return {"title": title, "authors": authors, "year": year, "venue": venue}
