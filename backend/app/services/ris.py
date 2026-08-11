"""RIS 格式解析（Zotero / EndNote 导出互通）。"""
import re

_ENTRY_START = re.compile(r"^TY\s*-\s*(\w+)")


def parse_ris(text: str) -> list[dict]:
    """解析 RIS 文本，返回可直接入库的字段字典列表。"""
    entries: list[dict] = []
    current: dict | None = None
    authors: list[str] = []
    keywords: list[str] = []

    def _flush() -> None:
        nonlocal current, authors, keywords
        if current:
            current["authors"] = authors
            current["tags"] = ", ".join(keywords)
            if current.get("title"):
                entries.append(current)
        current = None
        authors = []
        keywords = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _ENTRY_START.match(line)
        if m:
            _flush()
            current = {"title": "", "venue": "", "year": None, "doi": "", "bibkey": ""}
            continue
        if not current:
            continue
        fm = re.match(r"^([A-Z0-9]{2})\s*-\s*(.*)$", line)
        if not fm:
            continue
        tag, value = fm.group(1), fm.group(2).strip()
        if tag == "T1" or tag == "TI":
            current["title"] = (current["title"] + " " + value).strip()
        elif tag == "AU":
            authors.append(value)
        elif tag == "PY":
            mm = re.search(r"\d{4}", value)
            if mm:
                current["year"] = int(mm.group(0))
        elif tag == "JO" or tag == "JF" or tag == "T2":
            current["venue"] = value
        elif tag == "DO":
            current["doi"] = value
        elif tag == "ID" or tag == "KW":
            keywords.extend(re.split(r"[,;]", value))
        elif tag == "PB":
            if not current["venue"]:
                current["venue"] = value
        elif tag == "ER":
            _flush()
    _flush()
    return entries
