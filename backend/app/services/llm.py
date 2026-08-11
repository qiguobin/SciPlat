"""统一 LLM 客户端：OpenAI 兼容 API + Ollama 双通道。

配置存于 settings 表（key: llm_provider/llm_base_url/llm_api_key/llm_model/llm_ollama_url）。
未配置时抛 LLMNotConfigured；调用失败抛 LLMError（含原因）。
"""
import httpx

DEFAULT_TIMEOUT = 90.0


class LLMNotConfigured(Exception):
    pass


class LLMError(Exception):
    pass


def _get_cfg(db) -> dict:
    def v(key: str) -> str:
        s = db.execute(__import__("sqlalchemy").text("SELECT value FROM settings WHERE key = :k"), {"k": key}).first()
        return (s[0] if s else "") or ""

    cfg = {
        "provider": v("llm_provider") or "openai",
        "base_url": v("llm_base_url"),
        "api_key": v("llm_api_key"),
        "model": v("llm_model"),
        "ollama_url": v("llm_ollama_url") or "http://127.0.0.1:11434",
    }
    return cfg


def is_configured(db) -> bool:
    cfg = _get_cfg(db)
    if cfg["provider"] == "ollama":
        return True  # 本地 Ollama 视为已配置（连不上时调用报错）
    return bool(cfg["base_url"] and cfg["model"])


def chat(db, system: str, messages: list[dict], max_tokens: int = 4000, timeout: float | None = None) -> str:
    """统一对话入口。messages: [{role, content}]，system 可选。timeout 覆盖默认值（秒）。"""
    cfg = _get_cfg(db)
    if not is_configured(db):
        raise LLMNotConfigured("未配置 LLM。请在顶栏 ⚙️ 设置中配置 OpenAI 兼容 API 或 Ollama。")
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
            return resp.json().get("message", {}).get("content", "").strip()
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
        return resp.json()["choices"][0]["message"]["content"].strip()
    except LLMNotConfigured:
        raise
    except Exception as e:
        raise LLMError(f"LLM 调用失败：{e}") from e


# 连通性测试超时：地址不可达/填错时快速失败，避免页面长时间无响应
TEST_TIMEOUT = 20.0


def test_connection(db) -> dict:
    """连通性测试：发送最小请求（20s 超时，防止错误地址卡死页面）。"""
    try:
        reply = chat(db, "你是测试助手。", [{"role": "user", "content": "回复 OK"}], max_tokens=10, timeout=TEST_TIMEOUT)
        return {"ok": True, "reply": reply[:50]}
    except LLMNotConfigured as e:
        return {"ok": False, "error": str(e)}
    except LLMError as e:
        return {"ok": False, "error": str(e)}
