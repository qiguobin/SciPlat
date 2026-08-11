"""软件更新：版本检测接口 + 更新源配置（settings 表）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import config, models
from ..database import get_db
from ..services import updater

router = APIRouter(prefix="/api", tags=["update"])

SOURCE_KEY = "update_source_url"


def _get_source(db: Session) -> str:
    s = db.query(models.Setting).filter_by(key=SOURCE_KEY).first()
    return (s.value if s and s.value else updater.default_update_url()).strip() or updater.default_update_url()


@router.get("/update/check")
def update_check(db: Session = Depends(get_db)):
    """检查更新：拉取更新源 latest.json 并与当前版本比较。"""
    source = _get_source(db)
    data, error = updater.fetch_latest(source)
    if data is None:
        return {
            "has_update": False,
            "current_version": config.APP_VERSION,
            "latest_version": "",
            "download_url": "",
            "sha256": "",
            "notes": "",
            "mandatory": False,
            "published_at": "",
            "error": error,
            "source": source,
        }
    latest = str(data.get("version", "")).strip()
    has_update = updater.compare_versions(config.APP_VERSION, latest) > 0
    return {
        "has_update": has_update,
        "current_version": config.APP_VERSION,
        "latest_version": latest,
        "download_url": data.get("url", ""),
        "sha256": data.get("sha256", ""),
        "notes": data.get("notes", ""),
        "mandatory": bool(data.get("mandatory", False)),
        "published_at": data.get("published_at", ""),
        "error": "",
        "source": source,
    }


@router.get("/settings/update")
def get_update_settings(db: Session = Depends(get_db)):
    return {"source_url": _get_source(db)}


@router.put("/settings/update")
def update_settings(body: dict, db: Session = Depends(get_db)):
    url = str(body.get("source_url", "")).strip()
    s = db.query(models.Setting).filter_by(key=SOURCE_KEY).first()
    if s:
        s.value = url
    else:
        db.add(models.Setting(key=SOURCE_KEY, value=url))
    db.commit()
    return {"ok": True, "source_url": url or updater.default_update_url()}
