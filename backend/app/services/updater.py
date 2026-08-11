"""软件更新：版本检测（latest.json 协议）、SHA256 校验。

版本信息协议（随 Release 发布的 latest.json）：
{
  "version": "0.5.0",
  "url": "https://…/SciPlatSetup-0.5.0.exe",
  "sha256": "…",
  "notes": "发布说明",
  "mandatory": false,
  "published_at": "2026-08-11"
}
"""
import hashlib
import json
from typing import Optional

import httpx

USER_AGENT = "sci-plat/1.0 (local update checker)"
DEFAULT_UPDATE_URL = "https://github.com/qiguobin/SciPlat/releases/latest/download/latest.json"
CHECK_TIMEOUT = 15.0


def default_update_url() -> str:
    return DEFAULT_UPDATE_URL


def compare_versions(current: str, latest: str) -> int:
    """版本比较：latest > current 返回 1，等于 0，小于 -1。容忍非法分段（按 0 处理）。"""
    def _parts(v: str) -> list[int]:
        out = []
        for seg in (v or "").strip().split("."):
            digits = "".join(ch for ch in seg if ch.isdigit())
            out.append(int(digits) if digits else 0)
        return out

    a, b = _parts(current), _parts(latest)
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else 0
        y = b[i] if i < len(b) else 0
        if x > y:
            return -1
        if x < y:
            return 1
    return 0


def fetch_latest(update_url: str) -> tuple[Optional[dict], str]:
    """拉取并解析 latest.json。成功返回 (data, "")，失败返回 (None, 错误信息)。"""
    try:
        resp = httpx.get(
            update_url,
            timeout=CHECK_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # 网络/解析失败
        return None, f"更新源不可达：{e}"
    if not isinstance(data, dict) or not data.get("version"):
        return None, "更新源返回的数据格式不正确（缺少 version 字段）"
    return data, ""


def compute_sha256(path) -> str:
    """计算文件 SHA256（发布端与校验端共用）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
