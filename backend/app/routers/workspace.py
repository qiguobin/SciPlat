"""工作区 API：查看/创建/切换/注销。切换后前端 reload 刷新全部数据。"""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import config
from ..services import workspace as ws_service

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("")
def get_workspace():
    """当前工作区 + 全部列表（带 current 标记）。"""
    return {"current": str(config.DATA_DIR), "workspaces": ws_service.list_workspaces()}


@router.post("")
def create_workspace(body: dict):
    """创建新工作区：注册 + 立即切换进入。"""
    name = (body.get("name") or "").strip()
    path = (body.get("path") or "").strip()
    if not name or not path:
        raise HTTPException(400, "名称与路径不能为空")
    try:
        ws = ws_service.add_workspace(name, path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    _switch(ws["path"])
    return {"ok": True, "workspace": ws}


@router.post("/switch")
def switch_workspace(body: dict):
    """切换到已注册工作区（或任意存在的目录）。"""
    path = (body.get("path") or "").strip()
    if not path:
        raise HTTPException(400, "缺少路径")
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise HTTPException(400, "工作区目录不存在")
    _switch(str(p))
    return {"ok": True, "current": str(p)}


@router.delete("")
def remove_workspace(body: dict):
    """注销工作区（不删除任何文件）。当前工作区不可注销。"""
    path = (body.get("path") or "").strip()
    try:
        ws_service.remove_workspace(path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


def _switch(path: str) -> None:
    """执行切换（延迟 import 避免 main ↔ routers 循环依赖）。"""
    from ..main import switch_workspace as _do_switch

    _do_switch(path)
    ws_service.touch(path)
