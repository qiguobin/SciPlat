"""AI 自动关联：本地 TF-IDF 相似度预筛 + LLM 批量语义评分。

流程：
1. 本地 TF-IDF（纯 Python，标题×2 + 摘要 + 关键词）两两余弦相似度，
   按阈值筛出候选对（上限 MAX_PAIRS），秒级完成、无需联网；
2. 候选对分批交给 LLM 做语义评分（输出权重 + 理由 + 标签）；
3. LLM 未配置 / 解析失败时自动降级为纯本地权重（weight = cos×80，上限 70），
   保证功能离线可用。

结果持久化到 reference_ai_links 表，重新生成时整体覆盖。
"""
import json
import math
import re
from collections import Counter
from typing import Optional

from . import llm as llm_service
from .. import models
from ..database import SessionLocal

SIM_THRESHOLD = 0.12      # 候选对余弦相似度下限
MAX_PAIRS = 80            # 候选对总数上限
BATCH_SIZE = 20           # 每批交给 LLM 的文献对数
LOCAL_CAP = 70            # 本地降级权重上限

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[a-z0-9]{2,}")


def _tokens(text: str) -> list[str]:
    """轻量分词：英文/数字单词 + 中文 2-gram（无第三方依赖）。"""
    t = (text or "").lower()
    tokens = _LATIN.findall(t)
    cjk = "".join(_CJK.findall(t))
    if len(cjk) >= 2:
        tokens += [cjk[i:i + 2] for i in range(len(cjk) - 1)]
    return tokens


def _build_docs(refs: list) -> list[tuple[int, Counter]]:
    """每条文献 → (id, 词频 Counter)，标题权重 ×2。"""
    docs: list[tuple[int, Counter]] = []
    for r in refs:
        title = r.title or ""
        summary = ""
        keywords = ""
        if r.text:
            summary = r.text.summary or ""
            keywords = r.text.keywords or ""
        counter = Counter(_tokens(f"{title} {title} {summary} {keywords}"))
        docs.append((r.id, counter))
    return docs


def _cosine(a: Counter, b: Counter, idf: dict[str, float]) -> float:
    """TF-IDF 加权余弦相似度（稀疏点积）。"""
    if not a or not b:
        return 0.0
    dot = 0.0
    na = nb = 0.0
    for token, count in a.items():
        w = count * idf.get(token, 1.0)
        na += w * w
        if token in b:
            dot += w * b[token] * idf.get(token, 1.0)
    for token, count in b.items():
        w = count * idf.get(token, 1.0)
        nb += w * w
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _structural_features(a, b) -> tuple[float, list[str]]:
    """结构化特征分（标签/作者/期刊/年份），与 network.similarity 同口径。

    文本余弦低的同主题文献（如共享标签）也能进入候选，保证任何文献库都能产生关联。
    """
    score = 0.0
    factors: list[str] = []
    a_tags = {t.strip().lower() for t in (a.tags or "").split(",") if t.strip()}
    b_tags = {t.strip().lower() for t in (b.tags or "").split(",") if t.strip()}
    shared_tags = a_tags & b_tags
    if shared_tags:
        score += 3.0 * len(shared_tags)
        factors.append("tags")
    a_authors = {x.strip().lower() for x in (a.authors or []) if x.strip()}
    b_authors = {x.strip().lower() for x in (b.authors or []) if x.strip()}
    if a_authors & b_authors:
        score += 2.0
        factors.append("authors")
    if a.venue and b.venue and a.venue.strip().lower() == b.venue.strip().lower():
        score += 1.0
        factors.append("venue")
    if a.year and b.year and abs(a.year - b.year) <= 1:
        score += 0.5
        factors.append("year")
    return score, factors


def _candidate_pairs(refs: list) -> list[dict]:
    """候选对生成：TF-IDF 文本余弦（≥阈值）∪ 结构化特征候选（共享标签/作者等）。

    文本相似度低的同主题文献也能进入候选，避免「0 候选无法关联」。
    """
    docs = _build_docs(refs)
    n = len(docs)
    if n < 2:
        return []
    df: Counter = Counter()
    for _, counter in docs:
        df.update(counter.keys())
    idf = {token: math.log(n / (1 + freq)) + 1 for token, freq in df.items()}

    pairs: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine(docs[i][1], docs[j][1], idf)
            if sim >= SIM_THRESHOLD:
                pairs.append({
                    "a": docs[i][0], "b": docs[j][0],
                    "sim": round(sim, 3), "struct_score": 0.0, "struct_factors": [],
                })

    # 结构化兜底：文本相似度不足但共享标签/作者/期刊/年份（特征分 ≥ 1.5）
    seen = {(p["a"], p["b"]) for p in pairs}
    for i in range(n):
        for j in range(i + 1, n):
            a_id, b_id = docs[i][0], docs[j][0]
            if (a_id, b_id) in seen:
                continue
            s, factors = _structural_features(refs[i], refs[j])
            if s >= 1.5:
                pairs.append({
                    "a": a_id, "b": b_id,
                    "sim": 0.0, "struct_score": s, "struct_factors": factors,
                })
                seen.add((a_id, b_id))
    pairs.sort(key=lambda p: p["sim"], reverse=True)
    return pairs[:MAX_PAIRS]


def _ref_map(refs: list) -> dict[int, object]:
    return {r.id: r for r in refs}


def _chunk_context(pair: dict, refs_by_id: dict[int, object], title_only: bool = False) -> str:
    a, b = refs_by_id.get(pair["a"]), refs_by_id.get(pair["b"])
    if not a or not b:
        return ""
    if title_only:
        return f"{pair['a']}: {a.title}\n{pair['b']}: {b.title}"

    def _desc(r) -> str:
        abstract = (r.text.summary if r.text and r.text.summary else "").strip()
        abstract = abstract[:400] if abstract else "（无摘要）"
        return f"[{r.id}] 标题：{r.title}\n作者：{'、'.join((r.authors or [])[:3])}\n年份：{r.year or '未知'}\n期刊：{r.venue or '未知'}\n摘要：{abstract}"

    return f"### 文献 {pair['a']}\n{_desc(a)}\n\n### 文献 {pair['b']}\n{_desc(b)}"


def _parse_json_array(text: str) -> Optional[list[dict]]:
    """容错解析 LLM 返回的 JSON 数组（容忍 markdown 代码块与前后缀文本）。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    start, end = t.find("["), t.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(t[start:end + 1])
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


def _llm_score_batch(db, batch: list[dict], refs_by_id: dict[int, object]) -> list[dict]:
    """一批候选对交给 LLM 评分；失败/未配置返回空列表（由调用方降级）。"""
    lines = "\n\n".join(_chunk_context(p, refs_by_id) for p in batch)
    pairs = ", ".join(f'{{"a": {p["a"]}, "b": {p["b"]}}}' for p in batch)
    system = (
        "你是文献计量学专家。请评估以下每对文献的语义关联强度："
        "同一主题/方法/数据/结论互补/引用依赖等都算关联。"
        "只输出一个 JSON 数组（不要任何其他文字），每个元素格式："
        '{"a": 文献ID, "b": 文献ID, "weight": 0到100的整数, "reason": "一句话中文理由（20字内）", "tags": ["标签"]}。'
        "标签只能从以下选择：方法相似、结论互补、同领域、同技术路线、理论支撑、引用依赖。"
    )
    user = (
        f"请评估下面 {len(batch)} 对文献的关联强度，权重 0-100（0=无关，100=高度相关）。\n\n"
        f"{lines}\n\n输出 JSON 数组，元素按文献 ID 对应对应上面给出的 a/b 顺序。"
    )
    try:
        # 单批 60s 超时：LLM 慢/不可用时快速降级，避免整个请求长时间挂起
        raw = llm_service.chat(db, system, [{"role": "user", "content": user}], max_tokens=3000, timeout=60, task="link")
    except Exception:
        return []
    data = _parse_json_array(raw)
    if data is None:
        return []
    results = []
    for item in data:
        if not isinstance(item, dict) or "a" not in item or "b" not in item:
            continue
        weight = int(item.get("weight") or 0)
        weight = max(0, min(100, weight))
        tags = [str(x) for x in (item.get("tags") or [])][:4]
        results.append({
            "a": int(item["a"]), "b": int(item["b"]),
            "weight": weight,
            "reason": str(item.get("reason") or "")[:200],
            "tags": tags,
            "method": "llm",
        })
    return results


def run_auto_link(db) -> dict:
    """执行完整 AI 自动关联流程，整体覆盖旧结果。返回统计信息。"""
    refs = db.query(models.Reference).all()
    if len(refs) < 2:
        return {"created": 0, "method": "local", "llm_calls": 0, "pairs": 0, "skipped": 0}

    pairs = _candidate_pairs(refs)
    refs_by_id = _ref_map(refs)
    llm_configured = llm_service.is_configured(db)

    scored: list[dict] = []
    llm_calls = 0
    if llm_configured:
        for i in range(0, len(pairs), BATCH_SIZE):
            batch = pairs[i:i + BATCH_SIZE]
            llm_calls += 1
            results = _llm_score_batch(db, batch, refs_by_id)
            if results:
                by_key = {(r["a"], r["b"]): r for r in results}
                for p in batch:
                    hit = by_key.get((p["a"], p["b"])) or by_key.get((p["b"], p["a"]))
                    scored.append(hit if hit else _local_score(p))
            else:
                scored += [_local_score(p) for p in batch]
    else:
        scored = [_local_score(p) for p in pairs]

    # 整体覆盖旧结果（过滤 LLM 判定为 0 的「无关」对，避免噪音）
    db.query(models.ReferenceAiLink).delete()
    kept = 0
    for s in scored:
        if s["weight"] <= 0:
            continue
        kept += 1
        a, b = sorted((s["a"], s["b"]))
        db.add(models.ReferenceAiLink(
            ref_a=a, ref_b=b, weight=s["weight"], reason=s["reason"],
            tags=s.get("tags") or [], method=s["method"],
        ))
    db.commit()

    return {
        "created": kept,
        "method": "llm" if llm_configured else "local",
        "llm_calls": llm_calls,
        "pairs": len(pairs),
        "struct_pairs": sum(1 for p in pairs if p.get("struct_factors")),
        "skipped": len(scored) - kept,
    }


def _local_score(pair: dict) -> dict:
    """LLM 不可用时的本地降级评分（文本相似 / 结构化特征双口径）。"""
    text_weight = pair.get("sim", 0.0) * 80
    struct_weight = pair.get("struct_score", 0.0) * 12
    weight = min(LOCAL_CAP, round(max(text_weight, struct_weight)))
    if pair.get("struct_factors"):
        factor_names = {
            "tags": "共享标签", "authors": "共享作者", "venue": "同期刊/会议", "year": "年份相近",
        }
        reason = "、".join(factor_names.get(f, f) for f in pair["struct_factors"])
        tags = ["特征关联"]
    else:
        reason = f"标题/摘要文本相似度 {pair['sim']:.2f}"
        tags = ["文本相似"]
    return {
        "a": pair["a"], "b": pair["b"],
        "weight": max(1, weight),
        "reason": reason,
        "tags": tags,
        "method": "local",
    }
