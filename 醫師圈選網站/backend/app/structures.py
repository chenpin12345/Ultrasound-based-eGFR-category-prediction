"""圈選項目（顏色與意義）。資料一律用固定代碼存，顏色和名稱只是顯示，所以可以改。"""
from __future__ import annotations

import re
import secrets
from typing import Any

from .core import AppError, Store, now_iso

CORE = ('kidney', 'sinus', 'liver', 'spleen')  # 對應主系統的四種構造
LABEL_VALUE = {'kidney': 1, 'sinus': 2, 'liver': 3, 'spleen': 4}

DEFAULTS = (
    ('kidney', '腎臟外框', '整顆腎的外框，含腎竇。沿腎被膜亮線的外緣畫，不含腎周脂肪；被陰影遮住處依兩側邊緣自然連接。', '#00E5FF', 'solid', 'core'),
    ('sinus', '腎竇', '中央高回音區，含腎盂；積水時擴張的腎盂腎盞也算。畫在腎臟外框內。', '#FF4FD8', 'solid', 'core'),
    ('liver', '肝', '右腎影像中看得到的整個肝。器官內血管算在內；膽囊、腸道、肋骨陰影不算。', '#FFC400', 'solid', 'core'),
    ('spleen', '脾', '左腎影像中看得到的整個脾。器官內血管算在內；腸道、肋骨陰影不算。', '#7CFF4F', 'solid', 'core'),
    ('cyst', '囊腫（水泡）', '無回音、薄壁的囊腫。腎內囊腫仍保留在腎臟外框內。', '#4D8DFF', 'solid', 'preset'),
    ('stone', '結石', '局部強回音，下方常有聲影。圈結石本身，不含聲影。', '#FF3B30', 'solid', 'preset'),
    ('shadow', '聲影／看不清', '被遮住或看不清楚的區域；訓練和計算回音時可以忽略。', '#FFFFFF', 'dashed', 'preset'),
)

PALETTE = ('#F97316', '#A3E635', '#14B8A6', '#A78BFA', '#F472B6', '#FDE047', '#38BDF8', '#FB7185', '#C084FC', '#2DD4BF', '#FACC15', '#E879F9')

HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
TOO_CLOSE = 25  # CIE76 色差
TOO_GRAY_CHROMA = 20
WHITE_LIGHTNESS = 85


def seed(store: Store) -> None:
    with store.connect() as db:
        if db.execute('SELECT COUNT(*) FROM structures').fetchone()[0]:
            return
        for n, (code, name, meaning, color, line, kind) in enumerate(DEFAULTS, start=1):
            db.execute('INSERT INTO structures (code, name, meaning, color, line, kind, sort, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)',
                       (code, name, meaning, color, line, kind, n, now_iso()))


def _lab(color: str) -> tuple[float, float, float]:
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    xyz = ((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * b, (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
    fx, fy, fz = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in xyz]
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def color_warnings(color: str, others: list[dict[str, Any]]) -> list[str]:
    """顏色太接近現有項目，或太灰、在灰階超音波上看不清楚時提醒。"""
    lab = _lab(color)
    warnings = []
    if (lab[1] ** 2 + lab[2] ** 2) ** 0.5 < TOO_GRAY_CHROMA and lab[0] < WHITE_LIGHTNESS:
        warnings.append('這個顏色太灰，在超音波影像上不容易看清楚。')
    for other in others:
        o = _lab(other['color'])
        if sum((a - b) ** 2 for a, b in zip(lab, o)) ** 0.5 < TOO_CLOSE:
            warnings.append(f'這個顏色和「{other["name"]}」太接近，容易看錯。')
    return warnings


def _shape_counts(db) -> dict[str, int]:
    import json

    counts: dict[str, int] = {}
    for row in db.execute("SELECT shapes_json FROM images WHERE shapes_json != '[]'"):
        for shape in json.loads(row['shapes_json']):
            counts[shape['structure']] = counts.get(shape['structure'], 0) + 1
    return counts


def list_structures(store: Store) -> list[dict[str, Any]]:
    with store.connect() as db:
        used = _shape_counts(db)
        rows = db.execute('SELECT * FROM structures ORDER BY sort').fetchall()
    return [{**dict(r), 'active': bool(r['active']), 'used': used.get(r['code'], 0)} for r in rows]


def _clean(data: dict[str, Any], field: str, label: str, limit: int) -> str:
    value = str(data.get(field) or '').strip()
    if not value:
        raise AppError(422, 'FIELD_REQUIRED', f'請填寫{label}。')
    if len(value) > limit:
        raise AppError(422, 'FIELD_TOO_LONG', f'{label}最多 {limit} 個字。')
    return value


def _color(data: dict[str, Any]) -> str:
    color = str(data.get('color') or '')
    if not HEX.match(color):
        raise AppError(422, 'BAD_COLOR', '請選擇一個顏色。')
    return color.upper()


def _line(data: dict[str, Any]) -> str:
    line = data.get('line') or 'solid'
    if line not in ('solid', 'dashed'):
        raise AppError(422, 'BAD_LINE', '線型只能是實線或虛線。')
    return line


def _check_name(db, name: str, code: str | None = None) -> None:
    if db.execute('SELECT 1 FROM structures WHERE name = ? AND code != ?', (name, code or '')).fetchone():
        raise AppError(409, 'NAME_TAKEN', f'已經有「{name}」這個項目，請換一個名稱。')


def create_structure(store: Store, data: dict[str, Any]) -> dict[str, Any]:
    name, meaning = _clean(data, 'name', '名稱', 20), _clean(data, 'meaning', '意義說明', 200)
    color, line = _color(data), _line(data)
    code = f'custom_{secrets.token_hex(4)}'
    with store.connect() as db:
        _check_name(db, name)
        sort = db.execute('SELECT COALESCE(MAX(sort), 0) + 1 FROM structures').fetchone()[0]
        db.execute('INSERT INTO structures (code, name, meaning, color, line, kind, sort, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)',
                   (code, name, meaning, color, line, 'custom', sort, now_iso()))
    return next(s for s in list_structures(store) if s['code'] == code)


def update_structure(store: Store, code: str, data: dict[str, Any]) -> dict[str, Any]:
    current = next((s for s in list_structures(store) if s['code'] == code), None)
    if current is None:
        raise AppError(404, 'STRUCTURE_NOT_FOUND', '找不到這個項目。')
    core = current['kind'] == 'core'
    if core and ('name' in data and data['name'] != current['name'] or 'active' in data and not data['active']):
        raise AppError(409, 'CORE_LOCKED', '基本項目對應主系統，不能改名或停用，只能改顏色。')
    name = _clean(data, 'name', '名稱', 20) if 'name' in data else current['name']
    meaning = _clean(data, 'meaning', '意義說明', 200) if 'meaning' in data else current['meaning']
    color = _color(data) if 'color' in data else current['color']
    line = _line(data) if 'line' in data else current['line']
    active = bool(data['active']) if 'active' in data else current['active']
    with store.connect() as db:
        _check_name(db, name, code)
        db.execute('UPDATE structures SET name = ?, meaning = ?, color = ?, line = ?, active = ? WHERE code = ?', (name, meaning, color, line, int(active), code))
    return next(s for s in list_structures(store) if s['code'] == code)


def delete_structure(store: Store, code: str) -> None:
    current = next((s for s in list_structures(store) if s['code'] == code), None)
    if current is None:
        raise AppError(404, 'STRUCTURE_NOT_FOUND', '找不到這個項目。')
    if current['kind'] == 'core':
        raise AppError(409, 'CORE_LOCKED', '基本項目對應主系統，不能刪除。')
    if current['used']:
        raise AppError(409, 'IN_USE', f'「{current["name"]}」已經圈了 {current["used"]} 處，不能刪除；可以改成停用，已圈的資料會保留。')
    with store.connect() as db:
        db.execute('DELETE FROM structures WHERE code = ?', (code,))
