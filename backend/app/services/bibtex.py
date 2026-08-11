"""BibTeX 解析与导出（简化实现，覆盖常见期刊/会议条目）。"""
import re

_FIELD_NAME = re.compile(r"([A-Za-z0-9_\-]+)\s*=")


def _read_value(s: str, i: int) -> tuple[str, int]:
    """从位置 i 读取一个字段值（{} / "" / 裸文本），返回 (值, 消费长度)。"""
    if i >= len(s):
        return "", 0
    if s[i] == "{":
        depth = 0
        j = i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1 : j], j - i + 1
            j += 1
        return s[i + 1 :], len(s) - i
    if s[i] == '"':
        j = s.find('"', i + 1)
        if j == -1:
            return s[i + 1 :], len(s) - i
        return s[i + 1 : j], j - i + 1
    j = i
    while j < len(s) and s[j] not in ",}":
        j += 1
    return s[i:j].strip(), j - i


def _find_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        m = _FIELD_NAME.match(body[i:])
        if not m:
            nxt = body.find(",", i)
            i = nxt + 1 if nxt != -1 else n
            continue
        name = m.group(1).lower()
        i += m.end()
        while i < n and body[i] in " \t\r\n":
            i += 1
        val, consumed = _read_value(body, i)
        if name and val:
            fields[name] = val
        i += consumed
    return fields


def _clean(v: str) -> str:
    return v.strip().strip("{}").replace("\\&", "&")


def _split_authors(v: str) -> list[str]:
    parts: list[str] = []
    for p in v.split(" and "):
        p = p.strip()
        if not p:
            continue
        if "," in p:  # BibTeX 惯用 "Last, First"，规范化为 "First Last"
            last, first = p.split(",", 1)
            p = f"{first.strip()} {last.strip()}".strip()
        parts.append(p)
    return parts[:50]


def _to_year(v: str) -> int | None:
    m = re.search(r"\d{4}", v)
    return int(m.group(0)) if m else None


def _split_tags(v: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,;]", _clean(v)) if t.strip()]


def parse_bibtex(text: str) -> list[dict]:
    """解析 .bib 文本，返回可直接入库的字段字典列表。"""
    entries: list[dict] = []
    start = 0
    while True:
        at = text.find("@", start)
        if at == -1:
            break
        m = re.match(r"@\s*(\w+)\s*\{\s*([^,\s}]+)\s*,", text[at:])
        if not m:
            start = at + 1
            continue
        etype, key = m.group(1).lower(), m.group(2).strip()
        body_start = at + m.end()
        depth = 1
        j = body_start
        while j < len(text) and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[body_start : max(j - 1, body_start)]
        fields = _find_fields(body)
        entry = {
            "bibkey": key,
            "title": _clean(fields.get("title", "")),
            "authors": _split_authors(fields.get("author", "")),
            "year": _to_year(fields.get("year", "")),
            "venue": _clean(fields.get("journal") or fields.get("booktitle") or ""),
            "doi": _clean(fields.get("doi", "")),
            "tags": ", ".join(_split_tags(fields.get("keywords", ""))),
        }
        if entry["title"]:
            entries.append(entry)
        start = j
    return entries


def export_bibtex(references: list) -> str:
    """导出文献列表为 .bib 文本。references 为 ORM 对象。"""
    lines: list[str] = []
    for r in references:
        key = r.bibkey or f"ref{r.id}"
        lines.append(f"@article{{{key},")
        lines.append(f"  title = {{{r.title}}},")
        lines.append(f"  author = {{{' and '.join(r.authors or [])}}},")
        if r.year:
            lines.append(f"  year = {{{r.year}}},")
        if r.venue:
            lines.append(f"  journal = {{{r.venue}}},")
        if r.doi:
            lines.append(f"  doi = {{{r.doi}}},")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)
