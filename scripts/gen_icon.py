"""生成应用图标：深空底色 + 霓虹「研」印章风格 .ico（desktop/build/icon.ico）。"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "desktop" / "build" / "icon.ico"
SIZE = 256
BG = (11, 17, 32, 255)          # 深空底色
CARD = (15, 23, 42, 255)        # 卡片深蓝
NEON = (52, 211, 153, 255)      # 霓虹绿
RING = (30, 58, 95, 255)


def main() -> int:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角卡片
    d.rounded_rectangle([12, 12, SIZE - 12, SIZE - 12], radius=48, fill=BG)
    # 内层描边（霓虹）
    d.rounded_rectangle([16, 16, SIZE - 16, SIZE - 16], radius=44, outline=NEON, width=5)
    # 角落光点（装饰）
    for (x, y) in ((46, 46), (SIZE - 46, 46), (46, SIZE - 46), (SIZE - 46, SIZE - 46)):
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=RING)

    # 「研」字印章
    text = "研"
    font = None
    for candidate in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ):
        try:
            font = ImageFont.truetype(candidate, 150)
            break
        except OSError:
            continue
    if font is None:
        print("未找到中文字体，图标省略文字", file=sys.stderr)
    else:
        bbox = d.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((SIZE - w) / 2 - bbox[0], (SIZE - h) / 2 - bbox[1] - 8), text, font=font, fill=NEON)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"图标已生成：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
