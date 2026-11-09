"""匯入影像、自動儲存、完成檢查。"""
from __future__ import annotations

import csv
import json
import re
import shutil
import statistics
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from . import raster
from .core import AppError, Store, now_iso
from .structures import CORE, list_structures

IMAGE_ID = re.compile(r'^IMG-[0-9A-Fa-f]{12}$')
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
SIDES = {'右': 'right', '左': 'left'}
DEFAULT_ABSENT = {'right': 'spleen', 'left': 'liver'}
STATES = {'absent', 'unlabeled'}
ESTIMATE_AFTER = 20
SINUS_OUTSIDE_LIMIT = 0.02
SMALL_AREA = 100


# ---------- 匯入 ----------
def _read_manifest(folder: Path) -> dict[str, dict[str, Any]]:
    manifest = next(iter(sorted(folder.rglob('清單.csv'))), None)
    if manifest is None:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    with manifest.open(encoding='utf-8-sig', newline='') as fh:
        for n, row in enumerate(csv.DictReader(fh), start=1):
            image_id = (row.get('影像ID') or '').strip().upper()
            if image_id:
                rows[image_id] = {'order': n, 'side': SIDES.get((row.get('側別') or '').strip())}
    return rows


def default_states(side: str | None) -> dict[str, str]:
    organ = DEFAULT_ABSENT.get(side or '')
    return {organ: 'absent'} if organ else {}


def import_folder(store: Store, folder_text: str) -> dict[str, Any]:
    """匯入主系統匯出的資料夾。只收檔名是影像 ID 的檔案，已有的影像不覆蓋，圈選資料不會被改動。"""
    folder = Path(folder_text.strip().strip('"'))
    if not folder_text.strip() or not folder.is_dir():
        raise AppError(422, 'FOLDER_NOT_FOUND', '找不到這個資料夾。請確認路徑，或從檔案總管複製資料夾路徑貼上。')
    files: dict[str, Path] = {}
    skipped = 0
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        if IMAGE_ID.match(path.stem):
            files.setdefault('IMG-' + path.stem[4:].upper(), path)
        else:
            skipped += 1
    if not files:
        raise AppError(422, 'NO_IMAGES', '這個資料夾沒有檔名是影像 ID 的影像。請使用主系統「醫師圈選」匯出的資料夾，不要直接選原始資料夾。')
    manifest = _read_manifest(folder)
    with store.connect() as db:
        known = {r['id'] for r in db.execute('SELECT id FROM images')}
        seq = db.execute('SELECT COALESCE(MAX(seq), 0) FROM images').fetchone()[0]
    new_ids = sorted((i for i in files if i not in known), key=lambda i: (manifest.get(i, {}).get('order', 10 ** 9), i))
    rows, failed = [], 0
    for image_id in new_ids:
        source = files[image_id]
        try:
            with Image.open(source) as image:
                width, height = image.size
        except OSError:
            failed += 1
            continue
        target = store.paths.images / f'{image_id}{source.suffix.lower()}'
        shutil.copyfile(source, target)
        side = manifest.get(image_id, {}).get('side')
        seq += 1
        rows.append((image_id, seq, target.name, width, height, side, json.dumps(default_states(side))))
    with store.connect() as db:
        db.executemany('INSERT INTO images (id, seq, file, width, height, side, states_json) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
    return {'added': len(rows), 'existing': len(files) - len(new_ids), 'failed': failed, 'skipped': skipped}


# ---------- 查詢 ----------
def _image_row(db, image_id: str):
    row = db.execute('SELECT * FROM images WHERE id = ?', (image_id,)).fetchone()
    if row is None:
        raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像。')
    return row


def summary(store: Store) -> dict[str, Any]:
    with store.connect() as db:
        counts = {r['status']: r['n'] for r in db.execute('SELECT status, COUNT(*) AS n FROM images GROUP BY status')}
        discuss = db.execute('SELECT COUNT(*) FROM images WHERE discuss = 1').fetchone()[0]
        seconds = [r['seconds'] for r in db.execute("SELECT seconds FROM images WHERE status = 'done' AND seconds > 0")]
        nxt = db.execute("SELECT id FROM images WHERE status IN ('todo', 'in_progress') ORDER BY seq LIMIT 1").fetchone()
    total = sum(counts.values())
    finished = counts.get('done', 0) + counts.get('unusable', 0)
    estimate = None
    if len(seconds) >= ESTIMATE_AFTER:
        per_image = statistics.median(seconds)
        estimate = {'seconds_per_image': round(per_image), 'remaining_hours': round(per_image * (total - finished) / 3600, 1)}
    return {
        'total': total, 'finished': finished, 'todo': counts.get('todo', 0), 'in_progress': counts.get('in_progress', 0), 'done': counts.get('done', 0),
        'unusable': counts.get('unusable', 0), 'discuss': discuss, 'next_id': nxt['id'] if nxt else None, 'estimate': estimate, 'circler': store.get_meta('circler'),
    }


def list_images(store: Store, status: str = '') -> list[dict[str, Any]]:
    """清單不含分級，判讀時看不到其他影像的結果。"""
    query = 'SELECT id, seq, side, status, discuss FROM images'
    args: tuple = ()
    if status == 'discuss':
        query += ' WHERE discuss = 1'
    elif status:
        query += ' WHERE status = ?'
        args = (status,)
    with store.connect() as db:
        return [{**dict(r), 'discuss': bool(r['discuss'])} for r in db.execute(query + ' ORDER BY seq', args)]


def image_detail(store: Store, image_id: str) -> dict[str, Any]:
    with store.connect() as db:
        row = _image_row(db, image_id)
        before = db.execute('SELECT id FROM images WHERE seq < ? ORDER BY seq DESC LIMIT 1', (row['seq'],)).fetchone()
        after = db.execute('SELECT id FROM images WHERE seq > ? ORDER BY seq LIMIT 1', (row['seq'],)).fetchone()
        total = db.execute('SELECT COUNT(*) FROM images').fetchone()[0]
        position = db.execute('SELECT COUNT(*) FROM images WHERE seq <= ?', (row['seq'],)).fetchone()[0]
    return {
        'id': row['id'], 'position': position, 'total': total, 'width': row['width'], 'height': row['height'], 'side': row['side'], 'status': row['status'],
        'shapes': json.loads(row['shapes_json']), 'states': json.loads(row['states_json']), 'grade': row['grade'], 'grade_unsure': bool(row['grade_unsure']),
        'grade_reason': row['grade_reason'], 'note': row['note'], 'discuss': bool(row['discuss']), 'unusable_reason': row['unusable_reason'],
        'prev_id': before['id'] if before else None, 'next_id': after['id'] if after else None,
    }


def image_file(store: Store, image_id: str) -> Path:
    with store.connect() as db:
        return store.paths.images / _image_row(db, image_id)['file']


# ---------- 自動儲存 ----------
def _clean_shapes(shapes: Any, width: int, height: int, codes: set[str]) -> list[dict[str, Any]]:
    if not isinstance(shapes, list):
        raise AppError(422, 'BAD_SHAPES', '圈選資料格式不正確。')
    cleaned = []
    for shape in shapes:
        code = shape.get('structure') if isinstance(shape, dict) else None
        if code not in codes:
            raise AppError(422, 'BAD_STRUCTURE', '圈選資料有不認識的項目。')
        points = [[round(min(max(float(x), 0), width), 1), round(min(max(float(y), 0), height), 1)] for x, y in shape.get('points', [])]
        if len(points) >= 3:
            cleaned.append({'id': shape.get('id'), 'structure': code, 'points': points})
    return cleaned


def save_image(store: Store, image_id: str, data: dict[str, Any]) -> dict[str, Any]:
    codes = {s['code'] for s in list_structures(store)}
    with store.connect() as db:
        row = _image_row(db, image_id)
        shapes = _clean_shapes(data['shapes'], row['width'], row['height'], codes) if 'shapes' in data else json.loads(row['shapes_json'])
        states = json.loads(row['states_json'])
        if 'states' in data:
            states = {k: v for k, v in data['states'].items() if k in codes and v in STATES}
        side = row['side']
        if 'side' in data and data['side'] != side:
            if data['side'] not in ('right', 'left', None):
                raise AppError(422, 'BAD_SIDE', '側別只能是右、左或未知。')
            old = DEFAULT_ABSENT.get(side or '')
            if old and states.get(old) == 'absent':
                del states[old]
            side = data['side']
            states = {**default_states(side), **states}
        grade = data['grade'] if 'grade' in data else row['grade']
        if grade is not None and grade not in (0, 1, 2, 3):
            raise AppError(422, 'BAD_GRADE', '回音分級只能是 0–3。')
        unsure = bool(data.get('grade_unsure', row['grade_unsure']))
        if unsure:
            grade = None
        reason = str(data.get('grade_reason', row['grade_reason']))[:80]
        note = str(data.get('note', row['note']))[:500]
        discuss = bool(data.get('discuss', row['discuss']))
        unusable = str(data.get('unusable_reason', row['unusable_reason']))[:200]
        changed = (json.dumps(shapes) != row['shapes_json'] or json.dumps(states) != row['states_json'] or grade != row['grade'] or unsure != bool(row['grade_unsure'])
                   or reason != row['grade_reason'] or side != row['side'] or unusable != row['unusable_reason'])
        status = row['status']
        if changed:
            status = 'in_progress'  # 完成後又修改，要重新按完成，才會再檢查一次
        elif status == 'todo' and (note or discuss):
            status = 'in_progress'
        seconds = row['seconds'] + min(max(float(data.get('seconds', 0) or 0), 0), 600)
        circler = store_circler(db) or row['circler']
        db.execute('UPDATE images SET shapes_json = ?, states_json = ?, side = ?, grade = ?, grade_unsure = ?, grade_reason = ?, note = ?, discuss = ?, unusable_reason = ?,'
                   ' status = ?, seconds = ?, circler = ?, updated_at = ? WHERE id = ?',
                   (json.dumps(shapes), json.dumps(states), side, grade, int(unsure), reason, note, int(discuss), unusable, status, seconds, circler, now_iso(), image_id))
    store.backup()
    return {'status': status, 'saved_at': now_iso()}


def store_circler(db) -> str:
    row = db.execute("SELECT value FROM meta WHERE key = 'circler'").fetchone()
    return row['value'] if row else ''


# ---------- 完成檢查 ----------
def _area(points: list[list[float]]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))) / 2


def _crosses(p1, p2, p3, p4) -> bool:
    def turn(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    return turn(p1, p2, p3) * turn(p1, p2, p4) < 0 and turn(p3, p4, p1) * turn(p3, p4, p2) < 0


def self_intersects(points: list[list[float]]) -> bool:
    edges = list(zip(points, points[1:] + points[:1]))
    for i, (a, b) in enumerate(edges):
        for j in range(i + 2, len(edges)):
            if i == 0 and j == len(edges) - 1:
                continue
            if _crosses(a, b, *edges[j]):
                return True
    return False




def _outside_ratio(inner: list[dict[str, Any]], outer: list[dict[str, Any]], width: int, height: int) -> float:
    a, b = raster.mask(inner, width, height).convert('1'), raster.mask(outer, width, height).convert('1')
    total = a.histogram()[255]
    return 1 - ImageChops.logical_and(a, b).histogram()[255] / total if total else 0.0


def check_image(row, structures: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """errors 一定要處理才能完成；warnings 提醒後可以選擇仍要完成。"""
    shapes = json.loads(row['shapes_json'])
    states = json.loads(row['states_json'])
    names = {s['code']: s['name'] for s in structures}
    by_code: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        by_code.setdefault(shape['structure'], []).append(shape)
    errors, warnings = [], []
    for code in CORE:
        if code not in by_code and states.get(code) not in STATES:
            errors.append(f'{names[code]}：請圈選，或選「不在影像中」／「未標」。')
    if row['grade'] is None and not row['grade_unsure']:
        errors.append('回音分級：請選 0–3，或選「無法判斷」。')
    if row['grade_unsure'] and not row['grade_reason'].strip():
        errors.append('回音分級：選「無法判斷」時請寫原因。')
    if 'sinus' in by_code and 'kidney' not in by_code and states.get('kidney') == 'absent':
        errors.append('有圈腎竇，腎臟外框卻選「不在影像中」：請圈腎臟外框，或改成「未標」。')  # 否則主系統會把腎竇周圍當成確定沒有腎臟
    elif 'sinus' in by_code and 'kidney' not in by_code:
        warnings.append('有圈腎竇，但沒有圈腎臟外框。')
    elif 'sinus' in by_code and _outside_ratio(by_code['sinus'], by_code['kidney'], row['width'], row['height']) > SINUS_OUTSIDE_LIMIT:
        warnings.append('腎竇有一部分超出腎臟外框。')
    for shape in shapes:
        name = names.get(shape['structure'], shape['structure'])
        if self_intersects(shape['points']):
            warnings.append(f'{name}：輪廓有交叉，建議重畫或調整。')
        elif shape['structure'] in CORE and _area(shape['points']) < SMALL_AREA:
            warnings.append(f'{name}：圈選範圍非常小，請確認不是誤觸。')
    return errors, list(dict.fromkeys(warnings))


def complete_image(store: Store, image_id: str, force: bool) -> dict[str, Any]:
    structures = list_structures(store)
    with store.connect() as db:
        row = _image_row(db, image_id)
        if row['unusable_reason'].strip():
            db.execute("UPDATE images SET status = 'unusable', completed_at = ? WHERE id = ?", (now_iso(), image_id))
            return {'ok': True, 'status': 'unusable', 'errors': [], 'warnings': []}
        errors, warnings = check_image(row, structures)
        if errors or (warnings and not force):
            return {'ok': False, 'status': row['status'], 'errors': errors, 'warnings': warnings}
        states = json.loads(row['states_json'])
        drawn = {s['structure'] for s in json.loads(row['shapes_json'])}
        for s in structures:
            if s['code'] in drawn:
                states[s['code']] = 'drawn'
            elif s['code'] not in CORE:
                states[s['code']] = 'not_seen'  # 完成時沒圈的選填項目：醫師看過但沒有看到
        db.execute("UPDATE images SET status = 'done', states_json = ?, completed_at = ? WHERE id = ?", (json.dumps(states), now_iso(), image_id))
    store.backup()
    return {'ok': True, 'status': 'done', 'errors': [], 'warnings': warnings}
