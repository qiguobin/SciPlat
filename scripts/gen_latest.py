"""生成 latest.json + 同步 sciplat.iss 版本号（版本单点：config.APP_VERSION）。

用法（在仓库根目录执行）：
    # GitHub 发布（默认）
    python scripts/gen_latest.py
    # 公网对象存储（OSS/COS）等自建更新源
    python scripts/gen_latest.py --url-prefix https://your-bucket.oss-cn-hangzhou.aliyuncs.com/sciplat
    # Gitee 发布（latest.json 提交入库走 raw 直链，安装包放 Gitee Releases 附件）
    python scripts/gen_latest.py --gitee-user 你的用户名 --gitee-repo SciPlat
    # 附加发布说明 / 强制更新
    python scripts/gen_latest.py --url-prefix https://…/sciplat --notes "修复若干问题" --mandatory

产物：desktop/release/latest.json（提交入库；客户端更新源指向其 raw 直链）
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402

GITHUB_REPO = "qiguobin/SciPlat"
GITHUB_PREFIX = f"https://github.com/{GITHUB_REPO}/releases/latest/download"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sync_iss(version: str) -> None:
    """同步 sciplat.iss 版本号（消除硬编码漂移）。"""
    iss = ROOT / "scripts" / "sciplat.iss"
    text = iss.read_text(encoding="utf-8")
    new_text = re.sub(r'#define MyAppVersion ".*?"', f'#define MyAppVersion "{version}"', text)
    if new_text != text:
        iss.write_text(new_text, encoding="utf-8")
        print(f"已同步 sciplat.iss 版本号 → {version}")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 latest.json 更新版本信息")
    parser.add_argument("--url-prefix", default="",
                        help="下载 URL 前缀（默认 GitHub Releases；自建源填 https://桶.端点/路径）")
    parser.add_argument("--gitee-user", default="", help="Gitee 用户名（提供则启用 Gitee 模式）")
    parser.add_argument("--gitee-repo", default="SciPlat", help="Gitee 仓库名（默认 SciPlat）")
    parser.add_argument("--gitee-tag", default="", help="Gitee Release tag（默认 v{版本号}）")
    parser.add_argument("--notes", default="", help="发布说明（Markdown）")
    parser.add_argument("--mandatory", action="store_true", help="标记为强制更新")
    parser.add_argument("--sync-iss", action="store_true",
                        help="仅同步 sciplat.iss 版本号后退出（编译安装包前调用）")
    args = parser.parse_args()

    version = config.APP_VERSION
    if args.sync_iss:
        sync_iss(version)
        return 0

    setup = ROOT / "desktop" / "release" / f"SciPlatSetup-{version}.exe"
    if not setup.exists():
        print(f"未找到安装包：{setup}（请先运行 build-release.bat）", file=sys.stderr)
        return 1

    sync_iss(version)

    if args.gitee_user:
        # Gitee 模式：安装包放 Releases 附件（带 tag），latest.json 提交入库走 raw 直链
        tag = args.gitee_tag or f"v{version}"
        prefix = f"https://gitee.com/{args.gitee_user}/{args.gitee_repo}/releases/download/{tag}"
        source_hint = (
            f"客户端更新源（raw 直链，提交 latest.json 后恒定）：\n"
            f"  https://gitee.com/{args.gitee_user}/{args.gitee_repo}/raw/main/desktop/release/latest.json"
        )
    else:
        prefix = (args.url_prefix or GITHUB_PREFIX).rstrip("/")
        source_hint = "客户端更新源：latest.json 所在地址（GitHub/OSS/内网均可）"

    latest = {
        "version": version,
        "url": f"{prefix}/SciPlatSetup-{version}.exe",
        "sha256": sha256(setup),
        "notes": args.notes or "（发布时补充说明）",
        "mandatory": args.mandatory,
        "published_at": "",
    }
    out = ROOT / "desktop" / "release" / "latest.json"
    out.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"latest.json 已生成：{out}")
    print(f"  下载 URL：{latest['url']}")
    print(source_hint)
    if args.gitee_user:
        print(f"  待办：1) git 提交并推送 latest.json  2) 在 Gitee 仓库创建 Release（tag={tag}）上传安装包 {setup.name}")
    else:
        print(f"  上传文件：{setup.name} + latest.json 到更新源根目录（两者同级）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
