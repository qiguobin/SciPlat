"""PDF 文本提取与启发式摘要（pypdf，离线可用，无需 LLM）。"""
import re
from pathlib import Path

from pypdf import PdfReader

MAX_TEXT_CHARS = 200_000  # 全文截断上限
MAX_PAGES = 50


def extract_pdf_text(path: Path) -> str:
    """提取 PDF 文本。扫描版 PDF 返回空串（无文本层）。"""
    try:
        reader = PdfReader(str(path))
    except Exception:
        return ""
    parts: list[str] = []
    for page in reader.pages[:MAX_PAGES]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)[:MAX_TEXT_CHARS].strip()


def make_summary(text: str) -> dict:
    """启发式摘要：优先提取 Abstract/摘要 区与关键词行，失败时取首段。

    返回 {"summary": str, "keywords": str}。
    """
    summary = ""
    keywords = ""
    if text:
        # 英文 Abstract 区（Abstract → Introduction / 1. / Keywords）
        m = re.search(
            r"\babstract\b(.*?)(?=\b(?:introduction|1\.\s|keywords)\b)",
            text, re.IGNORECASE | re.DOTALL,
        )
        if m and len(m.group(1).strip()) > 60:
            summary = re.sub(r"\s+", " ", m.group(1)).strip()[:1500]
        if not summary:
            # 中文摘要区
            m = re.search(r"摘要[：:]\s*(.*?)(?=\n(?:关键词|关键字|引言))", text, re.DOTALL)
            if m:
                summary = re.sub(r"\s+", " ", m.group(1)).strip()[:1500]
        if not summary:
            summary = re.sub(r"\s+", " ", text[:800]).strip()
        # 关键词行
        m = re.search(r"\bkeywords?\b\s*[：:]\s*(.+)", text[:20000], re.IGNORECASE)
        if m:
            keywords = re.sub(r"\s+", " ", m.group(1)).strip()[:300]
        m = re.search(r"关键词[：:]\s*(.+)", text[:20000])
        if not keywords and m:
            keywords = m.group(1).strip()[:300]
    return {"summary": summary, "keywords": keywords}
