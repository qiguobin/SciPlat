"""WebDAV 云备份：PUT/GET/LIST（httpx，Basic 认证）。

兼容坚果云（dav.jianguoyun.com）、Nextcloud 等标准 WebDAV 服务。
远程文件命名：sciplat-backup-{ts}.zip（支持 .enc 加密包）。
"""
import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

TIMEOUT = 20.0
WEBDAV_NS = {"d": "DAV:"}


def _normalize_dir(url: str) -> str:
    return url.rstrip("/") + "/"


def test_connection(url: str, user: str, password: str) -> tuple[bool, str]:
    """连通测试：PROPFIND 目标目录。返回 (ok, 说明)。"""
    try:
        resp = httpx.request(
            "PROPFIND", _normalize_dir(url), auth=(user, password),
            headers={"Depth": "0", "Content-Type": "application/xml"},
            content=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>',
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return True, "连接成功"
    except Exception as e:  # noqa: BLE001
        return False, f"连接失败：{e}"


def list_files(url: str, user: str, password: str) -> list[dict]:
    """列出目录下的备份文件：{name, size, modified}。"""
    try:
        resp = httpx.request(
            "PROPFIND", _normalize_dir(url), auth=(user, password),
            headers={"Depth": "1", "Content-Type": "application/xml"},
            content=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
                    b'<d:displayname/><d:getcontentlength/><d:getlastmodified/><d:resourcetype/></d:prop></d:propfind>',
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"列表获取失败：{e}") from e

    items = []
    try:
        root = ET.fromstring(resp.text)
        for resp_el in root.findall("d:response", WEBDAV_NS):
            href = resp_el.findtext("d:href", default="", namespaces=WEBDAV_NS)
            rtype = resp_el.find("d:propstat/d:prop/d:resourcetype", WEBDAV_NS)
            is_collection = rtype is not None and rtype.find("d:collection", WEBDAV_NS) is not None
            if is_collection:
                continue
            name = href.rstrip("/").split("/")[-1]
            if not name:
                continue
            size = resp_el.findtext("d:propstat/d:prop/d:getcontentlength", default="0", namespaces=WEBDAV_NS)
            modified = resp_el.findtext("d:propstat/d:prop/d:getlastmodified", default="", namespaces=WEBDAV_NS)
            items.append({"name": name, "size": int(size or 0), "modified": modified})
    except ET.ParseError:
        pass
    items.sort(key=lambda x: x["name"], reverse=True)
    return items


def upload(url: str, user: str, password: str, remote_name: str, data: bytes) -> str:
    """上传文件（PUT）。返回远程完整 URL。"""
    remote = _normalize_dir(url) + remote_name
    try:
        resp = httpx.put(remote, auth=(user, password), content=data, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"上传失败：{e}") from e
    return remote


def download(url: str, user: str, password: str, remote_name: str) -> bytes:
    """下载文件（GET）。"""
    remote = _normalize_dir(url) + remote_name
    try:
        resp = httpx.get(remote, auth=(user, password), timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"下载失败：{e}") from e
    return resp.content
