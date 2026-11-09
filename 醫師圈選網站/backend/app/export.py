"""輸出結果給主系統。輸出資料夾只有標籤 PNG、JSON、CSV，不含影像內容。

主系統會掃描資料夾內所有影像檔，同一個影像 ID 有兩個檔案時只留較新的，
所以這裡不能放預覽圖或額外圖層，否則會蓋掉標籤。
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from . import __version__
from . import raster
from .core import Store, now_iso
from .structures import LABEL_VALUE, list_structures

DRAW_ORDER = ('liver', 'spleen', 'kidney', 'sinus')  # 肝／脾 → 腎實質 → 腎竇，和畫的先後無關
SIDE_LABEL = {'right': '右', 'left': '左'}
STATE_LABEL = {'drawn': '已圈', 'absent': '不在影像中', 'unlabeled': '未標', 'not_seen': '未見'}


def rasterize(shapes: list[dict[str, Any]], width: int, height: int) -> Image.Image:
    label = Image.new('L', (width, height), 0)
    draw = ImageDraw.Draw(label)
    for code in DRAW_ORDER:
        for shape in shapes:
            if shape['structure'] == code:
                raster.fill(draw, shape['points'], LABEL_VALUE[code], width, height)
    return label


def _new_folder(output: Path) -> Path:
    base = f'{date.today():%Y-%m-%d}_圈選結果'
    folder, n = output / base, 1
    while folder.exists():
        n += 1
        folder = output / f'{base}_{n}'
    (folder / '標籤').mkdir(parents=True)
    return folder


def export_results(store: Store) -> dict[str, Any]:
    structures = list_structures(store)
    with store.connect() as db:
        rows = db.execute("SELECT * FROM images WHERE status IN ('done', 'unusable') ORDER BY seq").fetchall()
    folder = _new_folder(store.paths.output)
    images, labels = [], 0
    for row in rows:
        shapes = json.loads(row['shapes_json'])
        label_file = None
        if row['status'] == 'done' and any(s['structure'] in LABEL_VALUE for s in shapes):
            label_file = f'標籤/{row["id"]}.png'
            rasterize(shapes, row['width'], row['height']).save(folder / label_file)  # 全 0 的圖主系統會當成彩色圈選，所以不輸出
            labels += 1
        images.append({
            'image_id': row['id'], 'status': row['status'], 'side': row['side'], 'label_file': label_file, 'states': json.loads(row['states_json']),
            'shapes': [{'structure': s['structure'], 'points': s['points']} for s in shapes], 'grade': row['grade'], 'grade_unsure': bool(row['grade_unsure']),
            'grade_reason': row['grade_reason'], 'note': row['note'], 'discuss': bool(row['discuss']), 'unusable_reason': row['unusable_reason'],
            'circler': row['circler'], 'seconds': round(row['seconds']), 'completed_at': row['completed_at'],
        })
    result = {
        'schema': 'kidney-circling-result', 'version': 1, 'app_version': __version__, 'created_at': now_iso(),
        'coordinates': '影像像素的邊：像素 (i, j) 的中心是 (i+0.5, j+0.5)；中心落在多邊形內（奇偶規則）才算圈到',
        'structures': [{k: s[k] for k in ('code', 'name', 'meaning', 'color', 'line', 'kind', 'active')} | {'label_value': LABEL_VALUE.get(s['code'])} for s in structures],
        'images': images,
    }
    (folder / '圈選結果.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    with (folder / '圈選結果.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['影像ID', '狀態', '側別', '回音分級', '無法判斷原因', '圈選者', '秒數', '需要討論', '備註', '不能用原因'] + [s['name'] for s in structures])
        for image in images:
            grade = '無法判斷' if image['grade_unsure'] else image['grade']
            writer.writerow([image['image_id'], '完成' if image['status'] == 'done' else '不能用', SIDE_LABEL.get(image['side'] or '', '未知'), grade, image['grade_reason'],
                             image['circler'], image['seconds'], '是' if image['discuss'] else '', image['note'], image['unusable_reason']]
                            + [STATE_LABEL.get(image['states'].get(s['code'], ''), '') for s in structures])
    return {'folder': str(folder), 'images': len(images), 'labels': labels}
