"""截图脱敏：对指定矩形区域做马赛克或模糊，发布前处理截图用。

用法（区域格式 x,y,w,h，可重复多个）：
    python tools/blur_region.py 输入.png 输出.png 320,180,240,28 320,220,240,28
    python tools/blur_region.py 输入.png 输出.png 300,150,400,40 --blur 12

提示：
- 坐标以图片左上角为原点，单位是图片像素；150% 缩放下 1 逻辑像素 = 1.5 像素。
- 需要精确坐标时，用 Windows「画图」打开图片，鼠标移到目标左上角看状态栏坐标。
- 马赛克块越大越难还原；一般 8~14 即可让文字不可读。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageFilter


def parse_box(text: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"区域格式应为 x,y,w,h：{text}")
    x, y, w, h = (int(p) for p in parts)
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError(f"区域宽高必须为正：{text}")
    return x, y, w, h


def pixelate(img: Image.Image, box: tuple[int, int, int, int], block: int) -> None:
    x, y, w, h = box
    w = min(w, img.width - x)
    h = min(h, img.height - y)
    if w <= 0 or h <= 0:
        return
    region = img.crop((x, y, x + w, y + h))
    small = region.resize((max(1, w // block), max(1, h // block)), Image.BILINEAR)
    img.paste(small.resize((w, h), Image.NEAREST), (x, y))


def blur(img: Image.Image, box: tuple[int, int, int, int], radius: float) -> None:
    x, y, w, h = box
    w = min(w, img.width - x)
    h = min(h, img.height - y)
    if w <= 0 or h <= 0:
        return
    region = img.crop((x, y, x + w, y + h)).filter(ImageFilter.GaussianBlur(radius))
    img.paste(region, (x, y))


def main() -> int:
    ap = argparse.ArgumentParser(description="对截图的指定区域打马赛克/模糊")
    ap.add_argument("src", help="输入图片")
    ap.add_argument("dst", nargs="?", help="输出图片（省略时覆盖输入）")
    ap.add_argument("boxes", nargs="*", type=parse_box, help="区域 x,y,w,h，可多个")
    ap.add_argument("--pixel", type=int, default=10, help="马赛克块大小，默认 10")
    ap.add_argument("--blur", type=float, default=0, help="改用高斯模糊半径（>0 时生效）")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"[错误] 找不到图片：{src}")
        return 1
    if not args.boxes:
        print("[错误] 至少提供一个区域，例如 320,180,240,28")
        return 1

    img = Image.open(src).convert("RGB")
    for box in args.boxes:
        if args.blur > 0:
            blur(img, box, args.blur)
        else:
            pixelate(img, box, max(2, args.pixel))

    dst = Path(args.dst or args.src)
    img.save(dst)
    print(f"[完成] {dst}  已处理 {len(args.boxes)} 个区域")
    return 0


if __name__ == "__main__":
    sys.exit(main())
