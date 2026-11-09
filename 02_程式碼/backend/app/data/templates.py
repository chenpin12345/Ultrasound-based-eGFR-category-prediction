"""版面範本：每種影像尺寸一份，定義要遮蓋的區域與要讀取的位置。

座標一律用百分比（0–100），與解析度無關，所以 Canon 1600×1200 與 666×500 可以共用比例。
這裡的預設值是依 2026-10-23 盤點的影像版面估計的初稿，請在「版面範本編輯」頁依實際影像調整。
"""

from __future__ import annotations

import json
from typing import Any

from ..core.ids import now_iso
from ..db.models_research import LayoutTemplate

Rect = dict[str, float]

TOSHIBA_REGIONS = [
    {'name': '上方標頭', 'x': 0, 'y': 0, 'w': 100, 'h': 10},
    {'name': '右側參數', 'x': 76, 'y': 8, 'w': 24, 'h': 34},
    {'name': '左側尺標與灰階條', 'x': 0, 'y': 8, 'w': 15.5, 'h': 72},
    {'name': '下方量測與文字', 'x': 0, 'y': 78, 'w': 100, 'h': 22},
    {'name': '右下示意圖', 'x': 82, 'y': 72, 'w': 18, 'h': 28},
]
TOSHIBA_READERS = {
    'header': {'x': 0, 'y': 0, 'w': 100, 'h': 9},
    'params': {'x': 86, 'y': 8, 'w': 14, 'h': 34},
    'measure': {'x': 3, 'y': 86, 'w': 55, 'h': 9},
    'side': {'x': 30, 'y': 78, 'w': 45, 'h': 10},
    'ruler': {'x': 11, 'y': 10, 'w': 7, 'h': 70},
    'bodymark': {'x': 80, 'y': 66, 'w': 20, 'h': 32},
}
CANON_REGIONS = [
    {'name': '上方標頭', 'x': 0, 'y': 0, 'w': 100, 'h': 13},
    {'name': '探頭標記', 'x': 64, 'y': 11, 'w': 6, 'h': 6},
    {'name': '右側參數', 'x': 88, 'y': 8, 'w': 12, 'h': 42},
    {'name': '左側尺標與灰階條', 'x': 0, 'y': 8, 'w': 11.5, 'h': 78},
    {'name': '下方量測與文字', 'x': 0, 'y': 82, 'w': 100, 'h': 18},
    {'name': '右下示意圖', 'x': 84, 'y': 70, 'w': 16, 'h': 30},
]
CANON_READERS = {
    'header': {'x': 0, 'y': 0, 'w': 100, 'h': 8},
    'params': {'x': 88, 'y': 18, 'w': 12, 'h': 32},
    'measure': {'x': 2, 'y': 89, 'w': 26, 'h': 10},
    'side': {'x': 30, 'y': 82, 'w': 45, 'h': 9},
    'ruler': {'x': 7, 'y': 12, 'w': 5, 'h': 72},
    'bodymark': {'x': 82, 'y': 66, 'w': 18, 'h': 32},
}

DEFAULTS: list[dict[str, Any]] = [
    {'id': 'TPL-T622', 'machine': 'Toshiba', 'width': 622, 'height': 500, 'regions': TOSHIBA_REGIONS, 'readers': TOSHIBA_READERS},
    {'id': 'TPL-T1493', 'machine': 'Toshiba', 'width': 1493, 'height': 1200, 'regions': TOSHIBA_REGIONS, 'readers': TOSHIBA_READERS},
    {'id': 'TPL-C1600', 'machine': 'Canon Aplio 300', 'width': 1600, 'height': 1200, 'regions': CANON_REGIONS, 'readers': CANON_READERS},
    {'id': 'TPL-C666', 'machine': 'Canon Aplio 300', 'width': 666, 'height': 500, 'regions': CANON_REGIONS, 'readers': CANON_READERS},
]


def seed_defaults(db) -> None:
    for item in DEFAULTS:
        if db.get(LayoutTemplate, item['id']) is None:
            db.add(
                LayoutTemplate(
                    id=item['id'],
                    machine=item['machine'],
                    width=item['width'],
                    height=item['height'],
                    version=1,
                    regions_json=json.dumps(item['regions'], ensure_ascii=False),
                    readers_json=json.dumps(item['readers'], ensure_ascii=False),
                    updated_at=now_iso(),
                    updated_by='系統預設',
                )
            )


def to_pixels(rect: Rect, width: int, height: int) -> tuple[int, int, int, int]:
    """百分比 → 像素 (x0, y0, x1, y1)，並限制在影像範圍內。"""
    x0 = max(0, int(round(rect['x'] / 100 * width)))
    y0 = max(0, int(round(rect['y'] / 100 * height)))
    x1 = min(width, int(round((rect['x'] + rect['w']) / 100 * width)))
    y1 = min(height, int(round((rect['y'] + rect['h']) / 100 * height)))
    return x0, y0, x1, y1


def template_dict(t: LayoutTemplate) -> dict[str, Any]:
    readers = json.loads(t.readers_json)
    # 較早建立的範本沒有後來新增的讀取區（例如體表示意圖），補上預設值
    for key, rect in (TOSHIBA_READERS if t.machine == 'Toshiba' else CANON_READERS).items():
        readers.setdefault(key, rect)
    return {
        'id': t.id,
        'machine': t.machine,
        'width': t.width,
        'height': t.height,
        'version': t.version,
        'regions': json.loads(t.regions_json),
        'readers': readers,
        'updated_at': t.updated_at,
        'updated_by': t.updated_by,
    }
