"""文献关联网络：特征相似度算法 + OpenAlex 引用抓取。

自动相似度基于结构化特征（标签/作者/期刊/年份），纯本地计算、可解释；
引用关系通过 OpenAlex 抓取（需联网），失败时自动降级为纯特征相似。
"""
import httpx

TAG_WEIGHT = 3        # 共享标签
AUTHOR_WEIGHT = 2     # 共享作者
VENUE_WEIGHT = 1      # 相同期刊/会议
YEAR_WEIGHT = 0.5     # 年份相差 ≤1
CITATION_WEIGHT = 30  # 引用关系
AUTO_CAP = 70         # 自动分上限（给引用关系留空间）
MAX_WEIGHT = 100


def _normalize_doi(s: str) -> str:
    """归一化 DOI：去掉 https://doi.org/ 等前缀，统一小写。"""
    d = (s or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "doi.org/"):
        if d.startswith(prefix):
            d = d[len(prefix):]
            break
    return d


def _tags(s: str) -> set[str]:
    return {t.strip().lower() for t in (s or "").split(",") if t.strip()}


def _authors(a: list) -> set[str]:
    return {x.strip().lower() for x in (a or []) if x.strip()}


def similarity(refs: list) -> list[dict]:
    """两两计算自动特征相似度，返回 links（按权重降序）。"""
    links: list[dict] = []
    n = len(refs)
    for i in range(n):
        a = refs[i]
        for j in range(i + 1, n):
            b = refs[j]
            score = 0.0
            factors: list[str] = []
            shared_tags = _tags(a.tags) & _tags(b.tags)
            if shared_tags:
                score += TAG_WEIGHT * len(shared_tags)
                factors.append("tags")
            shared_authors = _authors(a.authors) & _authors(b.authors)
            if shared_authors:
                score += AUTHOR_WEIGHT * len(shared_authors)
                factors.append("authors")
            if a.venue and b.venue and a.venue.strip().lower() == b.venue.strip().lower():
                score += VENUE_WEIGHT
                factors.append("venue")
            if a.year and b.year and abs(a.year - b.year) <= 1:
                score += YEAR_WEIGHT
                factors.append("year")
            if factors:
                links.append({
                    "source": a.id,
                    "target": b.id,
                    "weight": min(AUTO_CAP, round(score * 12)),
                    "factors": factors,
                    "citation": False,
                })
    links.sort(key=lambda l: l["weight"], reverse=True)
    return links


def build_network(refs: list, citations_map: dict[int, set[str]], min_weight: int = 0,
                  related_map: dict[int, set[int]] | None = None,
                  ai_links_map: dict[tuple[int, int], dict] | None = None) -> dict:
    """构建图谱数据：节点 + 边（自动相似 + 引用关系 + 手动关联 + AI 自动关联）。"""
    nodes = [{
        "id": r.id,
        "title": r.title,
        "tags": r.tags,
        "read_status": r.read_status,
        "author_count": len(r.authors or []),
    } for r in refs]

    # DOI -> 文献 id 索引（用于把引用命中到库内文献）
    doi_index: dict[str, int] = {}
    for r in refs:
        doi = _normalize_doi(r.doi)
        if doi:
            doi_index[doi] = r.id

    links = similarity(refs)
    related_map = related_map or {}

    def _add_or_merge(source: int, target: int, weight: int, factor: str, citation: bool,
                      extra: dict | None = None) -> None:
        for l in links:
            if (l["source"] == source and l["target"] == target) or (
                l["source"] == target and l["target"] == source
            ):
                l["weight"] = min(MAX_WEIGHT, l["weight"] + weight)
                if factor not in l["factors"]:
                    l["factors"].append(factor)
                if citation:
                    l["citation"] = True
                if extra:
                    for k, v in extra.items():
                        if k not in l:
                            l[k] = v
                return
        links.append({
            "source": source,
            "target": target,
            "weight": min(MAX_WEIGHT, weight),
            "factors": [factor],
            "citation": citation,
            **(extra or {}),
        })

    for ref in refs:
        for cited_doi in citations_map.get(ref.id, set()):
            target = doi_index.get(_normalize_doi(cited_doi))
            if target is None or target == ref.id:
                continue
            _add_or_merge(ref.id, target, CITATION_WEIGHT, "citation", True)

    # 手动关联（Zotero Related）：权重 25，因素 related
    for rid, targets in related_map.items():
        for t in targets:
            if rid == t:
                continue
            _add_or_merge(rid, t, 25, "related", False)

    # AI 自动关联：保留 LLM 权重/理由/标签，边标记 ai=True（前端可单独开关/着色）
    if ai_links_map:
        for (a, b), data in ai_links_map.items():
            if a == b:
                continue
            _add_or_merge(a, b, min(MAX_WEIGHT, int(data.get("weight") or 30)), "ai", False, {
                "ai": True,
                "reason": data.get("reason") or "",
                "ai_tags": data.get("tags") or [],
            })

    links = [l for l in links if l["weight"] >= min_weight]
    return {"nodes": nodes, "links": links}


def fetch_citations_from_openalex(doi: str) -> list[str]:
    """从 OpenAlex 抓取某文献的引用 DOI 列表。网络异常时抛 ValueError。"""
    url = f"https://api.openalex.org/works/https://doi.org/{doi.strip()}"
    try:
        resp = httpx.get(
            url,
            timeout=10.0,
            headers={"User-Agent": "sci-plat/1.0 (local research manager; mailto:local@example.com)"},
        )
        resp.raise_for_status()
        msg = resp.json()
    except Exception as e:  # 网络不可用 / HTTP 错误 / 解析失败
        raise ValueError(f"OpenAlex 抓取失败：{e}") from e
    return [w["doi"] for w in msg.get("referenced_works", []) if w.get("doi")]
