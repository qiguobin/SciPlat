"""工作区管理：工作区 = 独立数据目录（独立 sci.db / files / secret.key / auto-backups）。

注册表文件默认 `~/.sciplat/workspaces.json`（可用 SCI_WORKSPACES_FILE 覆盖，测试友好），
独立于任何数据目录，保证「工作区列表」在任何工作区下都可读。

首次访问自动把当前数据目录注册为「默认」工作区 —— 旧版本升级无感。
"""
import json
import os
from datetime import datetime
from pathlib import Path

from .. import config


def _registry_path() -> Path:
    env = os.environ.get("SCI_WORKSPACES_FILE")
    if env:
        return Path(env)
    return Path.home() / ".sciplat" / "workspaces.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> list[dict]:
    try:
        return json.loads(_registry_path().read_text(encoding="utf-8")) or []
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    p = _registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_default() -> None:
    """首次使用：把当前数据目录注册为「默认」工作区。"""
    items = _load()
    cur = str(config.DATA_DIR)
    if not any(i.get("path") == cur for i in items):
        items.append({"name": "默认", "path": cur, "created_at": _now(), "last_opened": _now()})
        _save(items)


def list_workspaces() -> list[dict]:
    """全部工作区，带 current 标记。"""
    _ensure_default()
    items = _load()
    cur = str(config.DATA_DIR)
    for i in items:
        i["current"] = i.get("path") == cur
    return items


def add_workspace(name: str, path: str) -> dict:
    """注册（并创建目录）新工作区。名称/路径校验失败抛 ValueError。"""
    name = (name or "").strip()[:50]
    p = Path(path).expanduser().resolve()
    if not name:
        raise ValueError("工作区名称不能为空")
    if not path or not p.is_absolute():
        raise ValueError("请输入绝对路径")
    items = _load()
    if any(i.get("path") == str(p) for i in items):
        raise ValueError("该路径已在工作区列表中")
    p.mkdir(parents=True, exist_ok=True)
    ws = {"name": name, "path": str(p), "created_at": _now(), "last_opened": _now()}
    items.append(ws)
    _save(items)
    return ws


def remove_workspace(path: str) -> None:
    """注销工作区（不删除任何文件）。当前工作区不可注销。"""
    p = str(Path(path).expanduser().resolve())
    if str(config.DATA_DIR) == p:
        raise ValueError("不能注销当前正在使用的工作区")
    _save([i for i in _load() if i.get("path") != p])


def touch(path: str) -> None:
    """记录最近打开时间。"""
    items = _load()
    changed = False
    for i in items:
        if i.get("path") == path:
            i["last_opened"] = _now()
            changed = True
    if changed:
        _save(items)
