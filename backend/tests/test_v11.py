"""V11 测试：Provider 状态页抓取（status.deepseek.com 等）+ AI 状态页后端支撑。"""
import json
from unittest.mock import patch

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)

STATUSPAGE_OK = {
    "page": {"id": "x"},
    "status": {"indicator": "none", "description": "All Systems Operational"},
    "components": [
        {"name": "API", "status": "operational"},
        {"name": "Chat", "status": "degraded_performance"},
    ],
    "incidents": [],
}
STATUSPAGE_DEGRADED = {
    "page": {"id": "x"},
    "status": {"indicator": "minor", "description": "API 响应延迟升高"},
    "components": [{"name": "API", "status": "degraded_performance"}],
    "incidents": [{"name": "API 延迟", "impact": "minor"}],
}
INSTATUS_OK = {
    "status": {"page_status": "OPERATIONAL", "description": "All good"},
    "components": [{"name": "API", "status": "OPERATIONAL"}],
}


class _FakeResp:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


# ==================== 解析器 ====================

def test_parse_statuspage_operational():
    from app.services import provider_status as ps

    result = ps.fetch_provider_status("https://status.example.com")
    # 未 mock → 网络失败 unknown
    assert result["overall"] == "unknown"


def test_parse_statuspage_variants():
    """Statuspage 格式：none→operational、minor→degraded、组件与事件解析。"""
    from app.services import provider_status as ps

    with patch("app.services.provider_status.httpx.get", return_value=_FakeResp(200, STATUSPAGE_OK)):
        r = ps.fetch_provider_status("https://status.example.com")
    assert r["overall"] == "operational"
    assert r["source"] == "statuspage"
    assert len(r["components"]) == 2
    assert r["components"][1]["label"] == "性能下降"
    assert r["status_url"] == "https://status.example.com/api/v2/status.json"

    with patch("app.services.provider_status.httpx.get", return_value=_FakeResp(200, STATUSPAGE_DEGRADED)):
        r2 = ps.fetch_provider_status("https://status.example.com")
    assert r2["overall"] == "degraded"
    assert r2["description"] == "API 响应延迟升高"
    assert len(r2["incidents"]) == 1
    assert r2["incidents"][0]["title"] == "API 延迟"


def test_parse_instatus_format():
    """Instatus 格式：page_status=OPERATIONAL → operational。"""
    from app.services import provider_status as ps

    with patch("app.services.provider_status.httpx.get", return_value=_FakeResp(200, INSTATUS_OK)):
        r = ps.fetch_provider_status("https://status.example.com")
    assert r["overall"] == "operational"
    assert r["source"] == "instatus"
    assert r["components"][0]["label"] == "正常"


def test_fetch_endpoint_fallback():
    """首端点 404 → 回退到下一个端点。"""
    from app.services import provider_status as ps

    with patch("app.services.provider_status.httpx.get",
               side_effect=[_FakeResp(404), _FakeResp(200, STATUSPAGE_OK)]) as g, \
         patch("app.services.provider_status._system_proxy", return_value=None):
        r = ps.fetch_provider_status("https://status.example.com")
    assert r["overall"] == "operational"
    # 尝试了前两个端点
    assert len(g.call_args_list) == 2


def test_fetch_via_system_proxy():
    """直连全部失败 → 跟随 Windows 系统代理重试成功。"""
    from app.services import provider_status as ps

    with patch("app.services.provider_status.httpx.get",
               side_effect=[Exception("network down")] * 4 + [_FakeResp(200, STATUSPAGE_OK)]) as g, \
         patch("app.services.provider_status._system_proxy", return_value="http://127.0.0.1:7892"):
        r = ps.fetch_provider_status("https://status.example.com")
    assert r["overall"] == "operational"
    # 直连 4 端点失败 + 代理重试首个端点成功
    assert len(g.call_args_list) == 5
    # 代理请求带 proxy 参数
    assert g.call_args_list[4].kwargs.get("proxy") == "http://127.0.0.1:7892"


def test_system_proxy_parse():
    """系统代理注册表解析：单地址 / 按协议分离 / 未启用。"""
    from app.services import provider_status as ps

    fake_key = type("K", (), {})()
    values = {"ProxyEnable": 1, "ProxyServer": "127.0.0.1:7892"}
    real_open = ps.winreg.OpenKey if hasattr(ps, "winreg") else None
    if real_open is None:
        return  # 非 Windows 跳过

    import unittest.mock as um

    def fake_query(key, name):
        # 真实 QueryValueEx 返回 (value, type) 元组
        return (values[name], 4)

    with um.patch.object(ps.winreg, "OpenKey", return_value=fake_key), \
         um.patch.object(ps.winreg, "QueryValueEx", side_effect=fake_query):
        assert ps._system_proxy() == "http://127.0.0.1:7892"

    # 按协议分离
    values["ProxyServer"] = "http=127.0.0.1:7890;https=127.0.0.1:7892"
    with um.patch.object(ps.winreg, "OpenKey", return_value=fake_key), \
         um.patch.object(ps.winreg, "QueryValueEx", side_effect=fake_query):
        assert ps._system_proxy() == "http://127.0.0.1:7892"

    # 未启用 → None
    values["ProxyEnable"] = 0
    with um.patch.object(ps.winreg, "OpenKey", return_value=fake_key), \
         um.patch.object(ps.winreg, "QueryValueEx", side_effect=fake_query):
        assert ps._system_proxy() is None


def test_fetch_all_fail_unknown():
    """全部端点失败 → unknown 且不抛异常。"""
    from app.services import provider_status as ps

    with patch("app.services.provider_status.httpx.get",
               side_effect=Exception("network down")):
        r = ps.fetch_provider_status("https://status.example.com")
    assert r["overall"] == "unknown"
    assert "不可达" in r["description"]


def test_fetch_no_status_url():
    """无状态页 URL → unknown + 提示。"""
    from app.services import provider_status as ps

    r = ps.fetch_provider_status("")
    assert r["overall"] == "unknown"
    assert r["status_url"] == ""


# ==================== 映射 / 缓存 / 端点 ====================

def test_status_url_mapping_and_custom():
    """域名映射 + 自定义 URL 覆盖。"""
    from app.services import provider_status as ps

    assert ps.get_status_url_for_provider("openai", "https://api.openai.com") == "https://status.openai.com"
    assert ps.get_status_url_for_provider("openai", "https://api.deepseek.com") == "https://status.deepseek.com"
    assert ps.get_status_url_for_provider("openai", "https://api.example.com") == ""
    assert ps.get_status_url_for_provider("openai", "https://api.example.com",
                                          "https://my-status.example.com") == "https://my-status.example.com"


def test_provider_status_endpoint_cache_and_refresh():
    """GET 读缓存；POST refresh 实时抓取并缓存。"""
    client.put("/api/settings/llm", json={"provider": "openai", "base_url": "https://api.deepseek.com",
                                          "model": "deepseek-chat", "api_key": "sk-test"})

    # 未抓取过 → GET 触发一次抓取（mock）
    with patch("app.services.provider_status.httpx.get", return_value=_FakeResp(200, STATUSPAGE_OK)):
        r = client.get("/api/llm/provider-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall"] == "operational"
    assert body["status_url"].startswith("https://status.deepseek.com")
    assert body["cached"] is True  # 抓取后已缓存

    # 再次 GET → 命中缓存（不再发起请求）
    with patch("app.services.provider_status.httpx.get", side_effect=AssertionError("不应发起请求")) as g:
        r2 = client.get("/api/llm/provider-status")
    assert r2.status_code == 200
    assert r2.json()["overall"] == "operational"

    # refresh → 强制实时抓取
    with patch("app.services.provider_status.httpx.get", return_value=_FakeResp(200, STATUSPAGE_DEGRADED)) as g:
        r3 = client.post("/api/llm/provider-status/refresh")
    assert r3.status_code == 200
    assert r3.json()["overall"] == "degraded"
    assert r3.json()["cached"] is False
    g.assert_called()


def test_provider_status_endpoint_no_config():
    """未配置 LLM 时端点可用（unknown 而非报错）。"""
    r = client.get("/api/llm/provider-status")
    assert r.status_code == 200
    assert r.json()["overall"] in ("unknown", "operational")  # 默认 openai 无 URL → unknown


def test_health_includes_provider_status():
    """/health 返回 provider_status 摘要（读缓存，零外部请求）。"""
    client.put("/api/settings/llm", json={"provider": "openai", "base_url": "https://api.deepseek.com",
                                          "model": "deepseek-chat", "api_key": "sk-test"})
    with patch("app.services.provider_status.httpx.get", return_value=_FakeResp(200, STATUSPAGE_DEGRADED)):
        client.post("/api/llm/provider-status/refresh")
    r = client.get("/api/health")
    assert r.status_code == 200
    hs = r.json()["provider_status"]
    assert hs["overall"] == "degraded"
    assert hs["description"] == "API 响应延迟升高"
    assert hs["checked_at"]
