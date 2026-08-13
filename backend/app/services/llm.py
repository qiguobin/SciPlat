"""统一 LLM 客户端：OpenAI 兼容 API + Ollama 双通道。

配置存于 settings 表（key: llm_provider/llm_base_url/llm_api_key/llm_model/llm_ollama_url）。
未配置时抛 LLMNotConfigured；调用失败抛 LLMError（含原因）。

chat() 是全部 AI 调用的单一漏斗：内部捕获 usage 并写入 llm_usage_logs
（返回类型保持 str，不破坏任何调用点；记录失败静默不影响主流程）。
"""
import threading
from contextlib import contextmanager

import httpx

DEFAULT_TIMEOUT = 90.0

# 运行中的 AI 批任务计数（状态栏「子智能体」实时状态）
_ACTIVE_TASKS = 0
_TASKS_LOCK = threading.Lock()


def active_tasks() -> int:
    return _ACTIVE_TASKS


@contextmanager
def ai_task():
    """批任务上下文：进入 +1、退出 -1（ai-auto-link / ai-match 等批量操作）。"""
    global _ACTIVE_TASKS
    with _TASKS_LOCK:
        _ACTIVE_TASKS += 1
    try:
        yield
    finally:
        with _TASKS_LOCK:
            _ACTIVE_TASKS = max(0, _ACTIVE_TASKS - 1)


# 模型元数据预设：上下文窗口 + 单价（每百万 tokens，估算价，可编辑）
MODEL_PRESETS: list[tuple] = [
    ("deepseek-chat", 128_000, 2.0, 8.0, 0.5, "CNY"),
    ("deepseek-reasoner", 128_000, 4.0, 16.0, 1.0, "CNY"),
    ("deepseek-v4-flash", 128_000, 2.0, 8.0, 0.5, "CNY"),
    ("qwen-plus", 131_072, 0.8, 2.0, 0.0, "CNY"),
    ("qwen-max", 32_768, 20.0, 60.0, 0.0, "CNY"),
    ("gpt-4o-mini", 128_000, 0.15, 0.6, 0.075, "USD"),
    ("qwen2.5", 32_768, 0.0, 0.0, 0.0, "CNY"),  # Ollama 本地免费
]

# 任务 → 模型 路由（空值 = 使用配置默认模型）；键：任务类型 + default
ROUTE_KEYS = ["default", "chat", "summary", "review", "polish", "link", "metadata", "report"]
DEFAULT_MODEL_ROUTE = {k: "" for k in ROUTE_KEYS}


class LLMNotConfigured(Exception):
    pass


class LLMError(Exception):
    pass


def _get_cfg(db) -> dict:
    def v(key: str) -> str:
        s = db.execute(__import__("sqlalchemy").text("SELECT value FROM settings WHERE key = :k"), {"k": key}).first()
        return (s[0] if s else "") or ""

    api_key_raw = v("llm_api_key")
    api_key = api_key_raw
    if v("llm_api_key_encrypted") == "1" and api_key_raw:
        from . import crypto

        api_key = crypto.decrypt_text(api_key_raw)  # 解密失败返回空 → 视为未配置

    cfg = {
        "provider": v("llm_provider") or "openai",
        "base_url": v("llm_base_url"),
        "api_key": api_key,
        "model": v("llm_model"),
        "ollama_url": v("llm_ollama_url") or "http://127.0.0.1:11434",
    }
    return cfg


def is_configured(db) -> bool:
    cfg = _get_cfg(db)
    if cfg["provider"] == "ollama":
        return True  # 本地 Ollama 视为已配置（连不上时调用报错）
    return bool(cfg["base_url"] and cfg["model"])


def get_model_route(db) -> dict:
    """读取任务→模型路由表（settings 存 JSON，合并默认键）。"""
    import json

    from .. import models

    s = db.query(models.Setting).filter_by(key="llm_model_route").first()
    route = dict(DEFAULT_MODEL_ROUTE)
    if s and s.value:
        try:
            saved = json.loads(s.value)
            if isinstance(saved, dict):
                route.update({k: str(v) for k, v in saved.items() if k in ROUTE_KEYS})
        except json.JSONDecodeError:
            pass
    return route


def save_model_route(db, route: dict) -> None:
    import json

    from .. import models

    cleaned = {k: str(route.get(k) or "").strip() for k in ROUTE_KEYS if k in route}
    s = db.query(models.Setting).filter_by(key="llm_model_route").first()
    if s:
        s.value = json.dumps(cleaned, ensure_ascii=False)
    else:
        db.add(models.Setting(key="llm_model_route", value=json.dumps(cleaned, ensure_ascii=False)))
    db.commit()


def resolve_model(db, cfg: dict, task: str = "", explicit: str = "") -> str:
    """解析实际调用模型：显式指定 > 任务路由 > default 路由 > 配置默认模型。"""
    if explicit and explicit.strip():
        return explicit.strip()
    route = get_model_route(db)
    for key in (task or "", "default"):
        m = (route.get(key) or "").strip()
        if m:
            return m
    return cfg["model"]


def ensure_model_meta(db) -> None:
    """首次使用时播种模型元数据预设（仿 journals_preset）。"""
    from .. import models

    if db.query(models.LlmModelMeta).count() > 0:
        return
    for model, ctx, in_p, out_p, cache_p, cur in MODEL_PRESETS:
        db.add(models.LlmModelMeta(
            model=model, context_window=ctx,
            input_price_per_m=in_p, output_price_per_m=out_p,
            cache_price_per_m=cache_p, currency=cur,
        ))
    db.commit()


def _meta_for(db, model: str):
    from .. import models

    ensure_model_meta(db)
    return db.query(models.LlmModelMeta).filter_by(model=model).first()


def _calc_cost(db, model: str, prompt: int, completion: int, cache_hit: int) -> tuple[float, str]:
    """按模型单价折算费用（估算）；未知模型 0 价。"""
    meta = _meta_for(db, model)
    if not meta:
        return 0.0, "CNY"
    hit = min(cache_hit, prompt)
    miss = prompt - hit
    cache_price = meta.cache_price_per_m if meta.cache_price_per_m > 0 else meta.input_price_per_m
    cost = miss / 1_000_000 * meta.input_price_per_m + hit / 1_000_000 * cache_price + completion / 1_000_000 * meta.output_price_per_m
    return round(cost, 6), meta.currency


def _record_usage(db, cfg: dict, usage: dict) -> None:
    """记录一次调用用量；任何失败静默（不打断 AI 主流程）。"""
    try:
        from datetime import datetime, timedelta

        from .. import models

        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or 0)
        cache_hit = int(usage.get("cache_hit_tokens") or 0)
        if total <= 0:
            total = prompt + completion
        cost, currency = _calc_cost(db, cfg.get("model", ""), prompt, completion, cache_hit)
        db.add(models.LlmUsageLog(
            provider=cfg.get("provider", "openai"),
            model=cfg.get("model", ""),
            prompt_tokens=prompt, completion_tokens=completion,
            total_tokens=total, cache_hit_tokens=cache_hit,
            cost=cost, currency=currency,
        ))
        # 保留最近 30 天
        cutoff = datetime.now() - timedelta(days=30)
        old = db.query(models.LlmUsageLog).filter(models.LlmUsageLog.created_at < cutoff).all()
        for row in old:
            db.delete(row)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def chat(db, system: str, messages: list[dict], max_tokens: int = 4000, timeout: float | None = None,
         task: str = "", model: str = "") -> str:
    """统一对话入口。messages: [{role, content}]，system 可选。

    task：任务类型（chat/summary/review/polish/link/metadata/report），按路由表选模型；
    model：显式指定模型（覆盖路由）；usage 按实际调用模型记录。
    """
    cfg = _get_cfg(db)
    if not is_configured(db):
        raise LLMNotConfigured("未配置 LLM。请在顶栏 ⚙️ 设置中配置 OpenAI 兼容 API 或 Ollama。")
    actual_model = resolve_model(db, cfg, task, model)
    if not actual_model:
        raise LLMNotConfigured("未配置默认模型。请在顶栏 ⚙️ 设置中填写模型名。")
    cfg = {**cfg, "model": actual_model}
    payload_msgs = ([{"role": "system", "content": system}] if system else []) + messages
    conn_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

    try:
        if cfg["provider"] == "ollama":
            resp = httpx.post(
                f"{cfg['ollama_url']}/api/chat",
                json={"model": cfg["model"] or "qwen2.5", "messages": payload_msgs, "stream": False,
                      "options": {"num_predict": max_tokens}},
                timeout=conn_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "").strip()
            # Ollama 非流式返回 prompt_eval_count / eval_count
            _record_usage(db, cfg, {
                "prompt_tokens": data.get("prompt_eval_count") or 0,
                "completion_tokens": data.get("eval_count") or 0,
            })
            return content
        # OpenAI 兼容
        url = cfg["base_url"].rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        resp = httpx.post(
            url,
            json={"model": cfg["model"], "messages": payload_msgs, "max_tokens": max_tokens},
            headers={"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {},
            timeout=conn_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # OpenAI 兼容响应含 usage（DeepSeek 另有 prompt_cache_hit_tokens）
        usage = data.get("usage") or {}
        _record_usage(db, cfg, {
            "prompt_tokens": usage.get("prompt_tokens") or 0,
            "completion_tokens": usage.get("completion_tokens") or 0,
            "total_tokens": usage.get("total_tokens") or 0,
            "cache_hit_tokens": usage.get("prompt_cache_hit_tokens") or 0,
        })
        return content
    except LLMNotConfigured:
        raise
    except Exception as e:
        raise LLMError(f"LLM 调用失败：{e}") from e


# 连通性测试超时：地址不可达/填错时快速失败，避免页面长时间无响应
TEST_TIMEOUT = 20.0


def test_connection(db) -> dict:
    """连通性测试：发送最小请求（20s 超时，防止错误地址卡死页面）。"""
    try:
        # max_tokens 需足够大：推理模型（如 deepseek-v4-flash）的 reasoning 也占用 tokens
        reply = chat(db, "你是测试助手。", [{"role": "user", "content": "回复 OK"}], max_tokens=128, timeout=TEST_TIMEOUT)
        return {"ok": True, "reply": reply[:50]}
    except LLMNotConfigured as e:
        return {"ok": False, "error": str(e)}
    except LLMError as e:
        return {"ok": False, "error": str(e)}


def fetch_balance(db) -> dict:
    """查询账户余额：DeepSeek / 月之暗面自动获取；Ollama/其他服务商给出说明。

    返回 {is_available, total_balance, currency, note}。
    """
    cfg = _get_cfg(db)
    if cfg["provider"] == "ollama":
        return {"is_available": False, "total_balance": 0.0, "currency": "CNY", "note": "Ollama 为本地模型，无余额概念"}
    base = cfg["base_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}

    if "deepseek.com" in base:
        api_base = base.replace("/chat/completions", "").replace("/v1", "")
        try:
            resp = httpx.get(f"{api_base}/user/balance", headers=headers, timeout=15.0)
            resp.raise_for_status()
            infos = (resp.json().get("balance_infos") or [{}])
            info = infos[0] if infos else {}
            return {"is_available": True, "total_balance": float(info.get("total_balance") or 0.0),
                    "currency": info.get("currency") or "CNY", "note": ""}
        except Exception as e:  # noqa: BLE001
            return {"is_available": False, "total_balance": 0.0, "currency": "CNY",
                    "note": f"余额查询失败：{e}"}

    if "moonshot.cn" in base:
        api_base = base.replace("/chat/completions", "").replace("/v1", "")
        try:
            resp = httpx.get(f"{api_base}/v1/users/me/balance", headers=headers, timeout=15.0)
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            balance = float(data.get("available_balance") or 0.0)
            return {"is_available": True, "total_balance": balance, "currency": "CNY", "note": ""}
        except Exception as e:  # noqa: BLE001
            return {"is_available": False, "total_balance": 0.0, "currency": "CNY",
                    "note": f"余额查询失败：{e}"}

    return {"is_available": False, "total_balance": 0.0, "currency": "CNY",
            "note": "该服务商暂不支持自动查询余额，可在设置中手动填写"}


def get_usage_summary(db) -> dict:
    """用量聚合：今日/本月/累计 tokens 与费用 + 分模型明细 + 近 30 天趋势。"""
    from datetime import datetime, timedelta

    from .. import models

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    def _agg(since) -> dict:
        q = db.query(models.LlmUsageLog).filter(models.LlmUsageLog.created_at >= since)
        rows = q.all()
        return {
            "calls": len(rows),
            "prompt_tokens": sum(r.prompt_tokens for r in rows),
            "completion_tokens": sum(r.completion_tokens for r in rows),
            "total_tokens": sum(r.total_tokens for r in rows),
            "cache_hit_tokens": sum(r.cache_hit_tokens for r in rows),
            "cost": round(sum(r.cost for r in rows), 4),
            "currency": rows[0].currency if rows else "CNY",
        }

    by_model = {}
    for row in db.query(models.LlmUsageLog).order_by(models.LlmUsageLog.created_at.desc()).limit(1000).all():
        m = by_model.setdefault(row.model, {
            "model": row.model, "calls": 0, "total_tokens": 0,
            "prompt_tokens": 0, "completion_tokens": 0, "cache_hit_tokens": 0, "cost": 0.0,
        })
        m["calls"] += 1
        m["total_tokens"] += row.total_tokens
        m["prompt_tokens"] += row.prompt_tokens
        m["completion_tokens"] += row.completion_tokens
        m["cache_hit_tokens"] += row.cache_hit_tokens
        m["cost"] = round(m["cost"] + row.cost, 4)

    # 近 30 天每日趋势（tokens / 费用）
    start30 = today_start - timedelta(days=29)
    day_map: dict[str, dict] = {}
    for row in db.query(models.LlmUsageLog).filter(models.LlmUsageLog.created_at >= start30).all():
        key = row.created_at.strftime("%Y-%m-%d")
        d = day_map.setdefault(key, {"date": key, "total_tokens": 0, "cost": 0.0})
        d["total_tokens"] += row.total_tokens
        d["cost"] = round(d["cost"] + row.cost, 4)
    trend = []
    for i in range(30):
        key = (start30 + timedelta(days=i)).strftime("%Y-%m-%d")
        trend.append(day_map.get(key, {"date": key, "total_tokens": 0, "cost": 0.0}))

    return {
        "today": _agg(today_start),
        "month": _agg(month_start),
        "total": _agg(datetime(2000, 1, 1)),
        "by_model": sorted(by_model.values(), key=lambda m: -m["total_tokens"]),
        "trend": trend,
    }


# ---------- API 服务状态探测（零 token 消耗：GET /models 或 Ollama /api/tags） ----------

HEALTH_HISTORY_LEN = 30   # 可用性滑动窗口（最近 N 次探测）
HEALTH_KEY = "llm_health_stats"


def _health_stats(db) -> dict:
    """读缓存探测统计（settings 键存 JSON，与余额缓存同模式）。"""
    import json

    from .. import models

    s = db.query(models.Setting).filter_by(key=HEALTH_KEY).first()
    if not s or not s.value:
        return {"total": 0, "ok": 0, "last_ok": False, "latency_ms": None,
                "endpoint": "", "checked_at": "", "history": []}
    try:
        data = json.loads(s.value)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"total": 0, "ok": 0, "last_ok": False, "latency_ms": None,
            "endpoint": "", "checked_at": "", "history": []}


def _record_health(db, ok: bool, latency_ms, endpoint: str) -> dict:
    """记录一次探测结果并保存统计（history 保留最近 30 次）。"""
    import json
    from datetime import datetime

    from .. import models

    stats = _health_stats(db)
    history = list(stats.get("history") or [])
    history.append(bool(ok))
    del history[:-HEALTH_HISTORY_LEN]
    stats.update({
        "total": int(stats.get("total") or 0) + 1,
        "ok": int(stats.get("ok") or 0) + (1 if ok else 0),
        "last_ok": bool(ok),
        "latency_ms": latency_ms,
        "endpoint": endpoint,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "history": history,
    })
    s = db.query(models.Setting).filter_by(key=HEALTH_KEY).first()
    if s:
        s.value = json.dumps(stats, ensure_ascii=False)
    else:
        db.add(models.Setting(key=HEALTH_KEY, value=json.dumps(stats, ensure_ascii=False)))
    db.commit()
    return stats


def probe_api_status(db) -> dict:
    """轻量探测当前配置的 LLM API（OpenAI 兼容 /models、Ollama /api/tags）。

    返回 {ok, latency_ms, endpoint, error}；未配置返回 {configured: False}。
    base_url 存储格式不统一（裸域名/带 /v1/完整 /chat/completions），候选端点逐个试。
    """
    import time as _time

    import httpx

    cfg = _get_cfg(db)
    if not is_configured(db):
        return {"configured": False}
    headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg.get("api_key") else {}
    start = _time.monotonic()
    try:
        if cfg["provider"] == "ollama":
            url = f"{cfg['ollama_url'].rstrip('/')}/api/tags"
            resp = httpx.get(url, timeout=8.0)
            resp.raise_for_status()
        else:
            base = cfg["base_url"].rstrip("/").replace("/chat/completions", "")
            candidates: list[str] = []
            for u in (base + "/models", base + "/v1/models"):
                if u not in candidates:
                    candidates.append(u)
            resp = None
            last_err = "连接失败"
            for url in candidates:
                try:
                    r = httpx.get(url, headers=headers, timeout=8.0)
                    if r.status_code < 400:
                        resp = r
                        break
                    last_err = f"HTTP {r.status_code}"
                except Exception as e:  # noqa: BLE001
                    last_err = str(e)[:120]
            if resp is None:
                raise RuntimeError(last_err)
        latency = int((_time.monotonic() - start) * 1000)
        return {"ok": True, "latency_ms": latency, "endpoint": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "latency_ms": int((_time.monotonic() - start) * 1000),
                "endpoint": "", "error": str(e)[:200]}


def probe_and_record(db) -> dict:
    """探测一次并写入历史统计，返回合并状态（供端点 / 后台线程 / 手动刷新复用）。"""
    result = probe_api_status(db)
    if not result.get("configured", True):
        return {"configured": False, "stats": _health_stats(db)}
    result.pop("configured", None)
    stats = _record_health(db, result["ok"], result.get("latency_ms"), result.get("endpoint", ""))
    return {"configured": True, **result, "stats": stats}


def get_llm_status(db) -> dict:
    """读缓存的服务状态（零外部请求）：在线状态 / 可用性百分比 / 最近探测统计。"""
    cfg = _get_cfg(db)
    stats = _health_stats(db)
    total = int(stats.get("total") or 0)
    ok = int(stats.get("ok") or 0)
    availability = round(ok * 100 / total) if total else None
    return {
        "configured": is_configured(db),
        "provider": cfg["provider"],
        "model": cfg["model"],
        "online": bool(stats.get("last_ok")),
        "availability_pct": availability,
        "total_checks": total,
        "ok_checks": ok,
        "latency_ms": stats.get("latency_ms"),
        "endpoint": stats.get("endpoint", ""),
        "checked_at": stats.get("checked_at", ""),
        "history": list(stats.get("history") or []),
    }
