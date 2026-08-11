"""文献引用格式生成：GB/T 7714-2015 / APA 7 / IEEE（纯本地，无需联网）。"""

FORMATS = ("gbt7714", "apa", "ieee")


def _join_authors(authors: list[str], sep: str, and_word: str, max_keep: int = 3) -> str:
    """作者列表拼接：超过 max_keep 个时截断加省略。"""
    if not authors:
        return ""
    if len(authors) <= max_keep:
        return sep.join(authors)
    return sep.join(authors[:max_keep]) + and_word


def gbt7714(r) -> str:
    """GB/T 7714-2015 顺序编码制：作者. 题名[J]. 刊名, 年. DOI。"""
    authors = _join_authors(r.authors or [], "、", " 等", 3)
    s = f"{authors}. {r.title}[J]. {r.venue or '—'}, {r.year or '—'}."
    if r.doi:
        s += f" DOI: {r.doi}."
    return s


def apa(r) -> str:
    """APA 7：Author, A., & Author, B. (Year). Title. Venue. DOI。"""
    authors = r.authors or []
    if len(authors) == 0:
        a = ""
    elif len(authors) == 1:
        a = authors[0]
    elif len(authors) == 2:
        a = f"{authors[0]} & {authors[1]}"
    else:
        a = ", ".join(authors[:-1]) + f", & {authors[-1]}"
    year = f"({r.year})" if r.year else "(n.d.)"
    s = f"{a} {year}. {r.title}. {r.venue or '—'}"
    if r.doi:
        s += f". https://doi.org/{r.doi}"
    return s + "."


def ieee(r) -> str:
    """IEEE：A. Author and B. Author, "Title," Venue, year. doi。"""
    authors = r.authors or []
    if len(authors) == 0:
        a = ""
    elif len(authors) == 1:
        a = authors[0]
    elif len(authors) == 2:
        a = f"{authors[0]} and {authors[1]}"
    else:
        a = ", ".join(authors[:-1]) + f", and {authors[-1]}"
    s = f'{a}, "{r.title}," {r.venue or "—"}, {r.year or "n.d."}.'
    if r.doi:
        s += f" doi: {r.doi}."
    return s


def format_citations(refs: list, fmt: str) -> list[str]:
    """按格式批量生成引用文本。"""
    if fmt not in FORMATS:
        raise ValueError(f"不支持的引用格式：{fmt}（支持 {'/'.join(FORMATS)}）")
    fn = {"gbt7714": gbt7714, "apa": apa, "ieee": ieee}[fmt]
    return [fn(r) for r in refs]
