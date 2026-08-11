"""生成 latest.json + 同步 sciplat.iss 版本号（版本单点：config.APP_VERSION）。

用法：构建完安装包后执行 python scripts/gen_latest.py
产物：desktop/release/latest.json（上传 GitHub Release 用，与安装包一起作为资产）
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402

GITHUB_REPO = "qiguobin/SciPlat"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    version = config.APP_VERSION
    setup = ROOT / "desktop" / "release" / f"SciPlatSetup-{version}.exe"
    if not setup.exists():
        print(f"未找到安装包：{setup}（请先运行 build-release.bat）", file=sys.stderr)
        return 1

    # 同步 sciplat.iss 版本号（消除硬编码漂移）
    iss = ROOT / "scripts" / "sciplat.iss"
    text = iss.read_text(encoding="utf-8")
    new_text = re.sub(r'#define MyAppVersion ".*?"', f'#define MyAppVersion "{version}"', text)
    if new_text != text:
        iss.write_text(new_text, encoding="utf-8")
        print(f"已同步 sciplat.iss 版本号 → {version}")

    latest = {
        "version": version,
        "url": f"https://github.com/{GITHUB_REPO}/releases/latest/download/SciPlatSetup-{version}.exe",
        "sha256": sha256(setup),
        "notes": "（发布时在 GitHub Release 中补充说明）",
        "mandatory": False,
        "published_at": "",
    }
    out = ROOT / "desktop" / "release" / "latest.json"
    out.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"latest.json 已生成：{out}")
    print(f"请上传 GitHub Release：{setup.name} + latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
