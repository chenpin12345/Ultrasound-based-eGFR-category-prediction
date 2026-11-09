"""多邊形 → 像素，和畫面上看到的一致。

座標是影像像素的「邊」：像素 (i, j) 涵蓋 [i, i+1) × [j, j+1)，中心在 (i+0.5, j+0.5)，
和網頁 SVG 疊在影像上的座標相同。像素中心落在多邊形內（奇偶規則，和畫面的 fill-rule 相同）才算圈到。
PIL 的 ImageDraw.polygon 把座標當成像素中心、還會連同輪廓線一起填，邊緣會往外多半個到一個像素，所以不用它。
"""
from __future__ import annotations

import math
from typing import Iterator

from PIL import Image, ImageDraw

Point = tuple[float, float] | list[float]


def spans(points: list[Point], width: int, height: int) -> Iterator[tuple[int, int, int]]:
    """逐列產生 (列, 起始欄, 結束欄)（含兩端）。"""
    if len(points) < 3:
        return
    edges = list(zip(points, points[1:] + points[:1]))
    top = max(0, math.floor(min(p[1] for p in points) - 0.5))
    bottom = min(height - 1, math.ceil(max(p[1] for p in points) - 0.5))
    for row in range(top, bottom + 1):
        y = row + 0.5
        xs = sorted(
            x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            for (x0, y0), (x1, y1) in edges
            if (y0 <= y < y1) or (y1 <= y < y0)  # 半開區間：頂點剛好在掃描線上時只算一次
        )
        for a, b in zip(xs[::2], xs[1::2]):
            first = max(0, math.ceil(a - 0.5))
            last = min(width - 1, math.ceil(b - 0.5) - 1)
            if first <= last:
                yield row, first, last


def fill(draw: ImageDraw.ImageDraw, points: list[Point], value: int, width: int, height: int) -> None:
    for row, first, last in spans(points, width, height):
        draw.line([(first, row), (last, row)], fill=value)


def mask(shapes: list[dict], width: int, height: int) -> Image.Image:
    image = Image.new('L', (width, height), 0)
    draw = ImageDraw.Draw(image)
    for shape in shapes:
        fill(draw, shape['points'], 255, width, height)
    return image
