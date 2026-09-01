#!/usr/bin/env python3
"""生成 SummitWorkbench 应用图标源图（1024×1024 PNG）。

summit/「峰」主题：蓝色竖向渐变圆角底 + 双峰雪山 + 一颗晨星。用 Pillow 绘制，
小尺寸仍高对比可辨。无需装依赖：``uv run --with pillow python scripts/make-icon.py``。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
RADIUS = 224
# 与 Web 面板 CSS 的 accent 蓝一致的调色。
TOP = (99, 179, 237)      # 顶部亮蓝
BOTTOM = (35, 78, 112)    # 底部深蓝
SNOW = (245, 249, 252)
FRONT = (26, 44, 66)      # 前峰（深）
BACK = (58, 96, 138)      # 后峰（中）


def _gradient() -> Image.Image:
    grad = Image.new("RGB", (1, SIZE))
    for y in range(SIZE):
        t = y / (SIZE - 1)
        grad.putpixel(
            (0, y),
            tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)),  # type: ignore[arg-type]
        )
    return grad.resize((SIZE, SIZE))


def _rounded_mask() -> Image.Image:
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], RADIUS, fill=255)
    return mask


def build() -> Image.Image:
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bg = _gradient().convert("RGBA")
    base.paste(bg, (0, 0), _rounded_mask())

    d = ImageDraw.Draw(base)
    # 晨星
    d.ellipse([760, 210, 856, 306], fill=(245, 249, 252, 235))

    # 后峰（中蓝）
    d.polygon([(300, 760), (560, 360), (820, 760)], fill=BACK)
    # 前峰（深蓝），略偏左更靠前
    d.polygon([(150, 780), (430, 300), (720, 780)], fill=FRONT)
    # 前峰雪帽
    d.polygon([(430, 300), (355, 430), (400, 415), (445, 470), (495, 405), (505, 430)],
              fill=SNOW)
    # 后峰雪帽
    d.polygon([(560, 360), (512, 440), (545, 428), (575, 462), (610, 428), (612, 442)],
              fill=SNOW)

    # 地平线阴影（前峰底部一条深带，增加层次）
    d.rectangle([150, 762, 820, 800], fill=(20, 34, 52))
    # 应用圆角裁切最终一遍，抹掉越界像素
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(base, (0, 0), _rounded_mask())
    return out


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/icon-1024.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    build().save(out_path)
    print(f"✓ 已生成 {out_path}")


if __name__ == "__main__":
    main()
