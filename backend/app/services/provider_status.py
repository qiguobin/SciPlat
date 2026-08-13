"""Provider 状态页抓取（status.deepseek.com 等）：性能下降/中断信息。

- 端点候选：Statuspage（/api/v2/status.json、/api/v2/summary.json）→ Instatus（/api/status）→ 裸 URL
- 双格式容错解析；全部失败 → overall: unknown
- 结果缓存 10 分钟（settings 键，/health 读缓存零外部请求）
"""
import json
from datetime import datetime

import httpx

try:
    import winreg  # Windows 系统代理读取（非 Windows 平台为 None）
except ImportError:  # pragma: no cover
    winreg = None

# Provider → 官方状态页（可按 provider 域名匹配；可用 settings llm_provider_status_url 覆盖）
PROVIDER_STATUS_URLS: dict[str, str] = {
    "deepseek.com": "https://status.deepseek.com",
    "openai.com": "https://status.openai.com",
    "anthropic.com": "https://status.anthropic.com",
}

CACHE_KEY = "llm_provider_status_cache"
CACHE_AT_KEY = "llm_provider_status_at"
CACHE_MINUTES = 10
_TIMEOUT = 10.0

# 端点候选顺序（按成功率/信息量优先）
_ENDPOINTS = (
    "/api/v2/status.json",
    "/api/v2/summary.json",
    "/api/status",
    "",
)

# Statuspage indicator → overall
_INDICATOR_MAP = {
    "none": "operational",
    "minor": "degraded",
    "major": "outage",
    "critical": "outage",
}
# Statuspage component status → 展示名
_COMPONENT_LABELS = {
    "operational": "正常",
    "degraded_performance": "性能下降",
    "partial_outage": "部分中断",
    "major_outage": "重大中断",
    "under_maintenance": "维护中",
    "OPERATIONAL": "正常",
    "DEGRADED": "性能下降",
    "PARTIAL_OUTAGE": "部分中断",
    "MAJOR_OUTAGE": "重大中断",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_status_url_for_provider(provider: str, base_url: str, custom: str = "") -> str:
    """解析当前 provider 的状态页 URL：自定义 > 域名匹配映射 > 空。"""
    if custom and custom.strip():
        return custom.strip().rstrip("/")
    for key, url in PROVIDER_STATUS_URLS.items():
        if key in (base_url or ""):
            return url
    return ""


def _parse_statuspage(msg: dict) -> dict | None:
    """Atlassian Statuspage 格式：{page, status:{indicator,description}, components:[], incidents:[]}。"""
    status = msg.get("status") or {}
    indicator = (status.get("indicator") or "").lower()
    if not indicator:
        return None
    overall = _INDICATOR_MAP.get(indicator, "unknown")
    components = []
    for c in msg.get("components", []) or []:
        name = (c.get("name") or "").strip()
        st = (c.get("status") or "").lower()
        if name and st:
            components.append({"name": name, "status": st, "label": _COMPONENT_LABELS.get(st, st)})
    incidents = []
    for inc in msg.get("incidents", []) or []:
        title = (inc.get("name") or "").strip()
        impact = (inc.get("impact") or "").replace("_", " ")
        if title:
            incidents.append({"title": title, "impact": impact or "未知"})
    return {
        "source": "statuspage",
        "overall": overall,
        "description": (status.get("description") or "").strip(),
        "components": components,
        "incidents": incidents,
    }


def _parse_instatus(msg: dict) -> dict | None:
    """Instatus 格式：{status:{page_status}, components:[{name,status}]}。"""
    status = msg.get("status") or {}
    page_status = (status.get("page_status") or "").upper()
    if not page_status:
        return None
    overall = "operational" if page_status == "OPERATIONAL" else (
        "outage" if "OUTAGE" in page_status else "degraded")
    components = []
    for c in msg.get("components", []) or []:
        name = (c.get("name") or "").strip()
        st = (c.get("status") or "").upper()
        if name and st:
            components.append({"name": name, "status": st.lower(), "label": _COMPONENT_LABELS.get(st, st)})
    return {
        "source": "instatus",
        "overall": overall,
        "description": (status.get("description") or "").strip(),
        "components": components,
        "incidents": [],
    }


def _system_proxy() -> str | None:
    """读取 Windows 系统代理（WinINET 注册表）URL，供直连失败时重试。

    返回 http://127.0.0.1:7892 形式；多协议配置取 https 项优先。
    """
    if winreg is None:
        return None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        enabled = 0
        server = ""
        try:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
        except OSError:
            pass
        if enabled and server:
            if "=" in server:  # 按协议分离：http=127.0.0.1:7890;https=127.0.0.1:7892
                parts = {p.split("=")[0].strip().lower(): p.split("=", 1)[1].strip()
                         for p in server.split(";") if "=" in p}
                return f"http://{parts.get('https') or parts.get('http')}"
            return f"http://{server}"
    except Exception:
        pass
    return None


def _attempt(base: str, endpoints, proxy) -> dict | None:
    """按端点顺序尝试抓取解析；全部失败返回 None。"""
    for ep in endpoints:
        url = base + ep
        try:
            resp = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True, proxy=proxy,
                             headers={"User-Agent": "sci-plat/1.0 (local research manager)"})
            if resp.status_code >= 400:
                continue
            msg = resp.json()
        except Exception:
            continue
        parsed = _parse_statuspage(msg) or _parse_instatus(msg)
        if parsed:
            parsed["status_url"] = url
            parsed["fetched_at"] = _now()
            return parsed
    return None


def fetch_provider_status(status_url: str) -> dict:
    """抓取状态页并解析。直连失败 → 跟随系统代理重试；全部失败 → overall: unknown（不抛异常）。"""
    if not status_url:
        return {
            "source": "", "overall": "unknown", "description": "当前 Provider 无已知状态页",
            "components": [], "incidents": [], "status_url": "", "fetched_at": _now(),
        }
    base = status_url.rstrip("/")
    parsed = _attempt(base, _ENDPOINTS, None)
    if not parsed:
        proxy = _system_proxy()
        if proxy:
            parsed = _attempt(base, _ENDPOINTS, proxy)
    if parsed:
        return parsed
    return {
        "source": "", "overall": "unknown",
        "description": "状态页不可达或格式未知（可稍后刷新，或在模型设置中自定义状态页地址）",
        "components": [], "incidents": [], "status_url": base, "fetched_at": _now(),
    }


def get_provider_status(db, force: bool = False) -> dict:
    """读缓存（10 分钟）或实时抓取。缓存/抓取失败 → unknown。"""
    from .. import models

    def v(key: str) -> str:
        s = db.query(models.Setting).filter_by(key=key).first()
        return s.value if s and s.value else ""

    if not force:
        at = v(CACHE_AT_KEY)
        cache = v(CACHE_KEY)
        if at and cache:
            try:
                age = (datetime.now() - datetime.fromisoformat(at)).total_seconds()
                if age < CACHE_MINUTES * 60:
                    return json.loads(cache)
            except Exception:
                pass
    result = fetch_provider_status(get_status_url_for_provider(
        v("llm_provider"), v("llm_base_url"), v("llm_provider_status_url")))
    s = db.query(models.Setting).filter_by(key=CACHE_KEY).first()
    if s:
        s.value = json.dumps(result, ensure_ascii=False)
    else:
        db.add(models.Setting(key=CACHE_KEY, value=json.dumps(result, ensure_ascii=False)))
    t = db.query(models.Setting).filter_by(key=CACHE_AT_KEY).first()
    if t:
        t.value = result["fetched_at"]
    else:
        db.add(models.Setting(key=CACHE_AT_KEY, value=result["fetched_at"]))
    db.commit()
    return result


def get_provider_status_summary(db) -> dict:
    """/health 用缓存摘要（零外部请求）。"""
    from .. import models

    s = db.query(models.Setting).filter_by(key=CACHE_KEY).first()
    at = db.query(models.Setting).filter_by(key=CACHE_AT_KEY).first()
    if not s or not s.value:
        return {"overall": "unknown", "description": "", "checked_at": ""}
    try:
        data = json.loads(s.value)
    except json.JSONDecodeError:
        return {"overall": "unknown", "description": "", "checked_at": ""}
    return {
        "overall": data.get("overall", "unknown"),
        "description": data.get("description", ""),
        "checked_at": data.get("fetched_at", "") or (at.value if at else ""),
    }
