"""醫師圈選（M2.5，決策 D16–D21）：醫師不在系統裡畫圖，而是在匯出的影像上用顏色圈選後傳回。

流程：建立批次 → 匯出（去識別化影像；可選原始影像）→ 醫師圈選 → 上傳傳回的資料夾
→ 比對差異法（或標籤 PNG）轉成遮罩 → 檢查疊圖 → 匯入成正式遮罩（來源 physician_upload，算已確認）。

醫師圈的是「整顆腎外框（含腎竇）」「腎竇」「肝」「脾」；腎實質＝外框扣掉腎竇。
顏色代表什麼由使用者在設定頁「顏色對照」設定（circling_colors），沒設定前不能匯入彩色圈選。
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_dated, now_iso
from ..data import deid, storage
from ..data.patients import egfr_group
from ..db.models_research import CirclingBatch, CirclingItem, Image, ImageGrade, MaskAnnotation, Patient, SourceMap, Split, SplitEntry
from ..db.session import session_scope
from ..jobs.manager import JobContext, register
from .service import STRUCTURES

# 醫師圈的構造 → 標籤值；疊放順序：肝／脾 → 腎外框（腎實質）→ 腎竇蓋在上面
CIRCLED = ('kidney', 'sinus', 'liver', 'spleen')
CIRCLED_LABEL = {'kidney': '腎臟外框', 'sinus': '腎竇', 'liver': '肝', 'spleen': '脾'}
LABEL_VALUE = {'kidney': STRUCTURES['parenchyma'], 'sinus': STRUCTURES['sinus'], 'liver': STRUCTURES['liver'], 'spleen': STRUCTURES['spleen']}
FILL_ORDER = ('liver', 'spleen', 'kidney', 'sinus')
STATES = ('drawn', 'absent', 'unlabeled')
SITE_RESULT = '圈選結果.json'
SITE_SCHEMA = 'kidney-circling-result'
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
ID_RE = re.compile(r'IMG-[0-9A-Fa-f]{12}')
ORIGINAL_CONFIRM = '我了解原始影像含有個資'
DIFF_THRESHOLD = 30  # 傳回的圖和原本影像的差異大於這個值（0–255）才算筆畫
OVERLAY_COLORS = {1: (214, 196, 94), 2: (234, 146, 199), 3: (85, 180, 224), 4: (107, 203, 156)}  # BGR：腎實質、腎竇、肝、脾


# ---------- 主切分與測試集保護 ----------
def primary_split_id() -> str:
    from ..services.settings_store import get_all

    wanted = get_all().get('primary_split_id')
    with session_scope('research') as db:
        q = db.query(Split).filter(Split.trashed_at.is_(None))
        if wanted and q.filter(Split.id == wanted).first():
            return wanted
        latest = q.order_by(Split.created_at.desc()).first()
    if latest is None:
        raise AppError(409, 'NO_SPLIT', '還沒有資料切分。請先在「資料集 › 切分」建立，再到設定頁選主切分。')
    return latest.id


def protected_test_image_ids() -> set[str]:
    """主切分測試集病人的所有影像：不產生任何草稿、不能進分割訓練（決策 D20）。"""
    try:
        split_id = primary_split_id()
    except AppError:
        return set()
    with session_scope('research') as db:
        patients = [p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == split_id, SplitEntry.group == 'test').all()]
        if not patients:
            return set()
        return {i for (i,) in db.query(Image.id).filter(Image.patient_id.in_(patients)).all()}


def protected_test_patients() -> set[str]:
    try:
        split_id = primary_split_id()
    except AppError:
        return set()
    with session_scope('research') as db:
        return {p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == split_id, SplitEntry.group == 'test').all()}


# ---------- 建立批次 ----------
def _rank(i: Image) -> tuple:
    """同一位病人同一側，優先選：長軸、技師量過腎長、腎長最長；同分取 ID 小的。"""
    return (0 if i.view == 'long' else 1, 0 if i.sonographer_length_mm else 1, -(i.sonographer_length_mm or 0), i.id)


def _already_batched(db) -> set[str]:
    return {i for (i,) in db.query(CirclingItem.image_id).all()}


def _has_physician_mask(db) -> set[str]:
    rows = db.query(MaskAnnotation.image_id).filter(MaskAnnotation.trashed_at.is_(None), MaskAnnotation.source.in_(('physician_upload', 'edited_upload')), MaskAnnotation.status != 'rejected')
    return {i for (i,) in rows.all()}


def _all_image_ids(db, groups: dict[str, str], done: set[str]) -> list[str]:
    """全部影像批次：排除的影像和已有醫師遮罩的不再圈。順序：測試集每側代表影像 → 測試病人其餘影像 → 訓練影像，
    測試集先圈完，分割訓練就可以提早開始。"""
    rows = [i for i in db.query(Image).filter(Image.status != 'excluded').all() if i.id not in done]
    by_side: dict[tuple[str, str], list[Image]] = defaultdict(list)
    for i in rows:
        if groups.get(i.patient_id) == 'test' and i.side:
            by_side[(i.patient_id, i.side)].append(i)
    first = {min(imgs, key=_rank).id for imgs in by_side.values()}
    return [i.id for i in sorted(rows, key=lambda i: (0 if i.id in first else 1 if groups.get(i.patient_id) == 'test' else 2, i.id))]


def create_batch(kind: str, size: int, note: str, operator: str) -> dict[str, Any]:
    if kind not in ('test', 'train', 'all'):
        raise AppError(422, 'BAD_KIND', '批次種類只能是 test（測試集）、train（訓練影像）或 all（全部影像）。')
    if kind == 'train' and not 1 <= size <= 500:
        raise AppError(422, 'BAD_SIZE', '每批張數必須在 1 到 500 之間。')
    split_id = primary_split_id()
    with session_scope('research') as db:
        groups = dict(db.query(SplitEntry.patient_id, SplitEntry.group).filter(SplitEntry.split_id == split_id).all())
        taken = _already_batched(db)
        done = _has_physician_mask(db)
        images = [i for i in db.query(Image).filter(Image.status == 'usable', Image.patient_id.isnot(None), Image.side.isnot(None)).all() if i.patient_id in groups]
        patients = {p.id: p for p in db.query(Patient).all()}
        by_side: dict[tuple[str, str], list[Image]] = defaultdict(list)
        for i in images:
            by_side[(i.patient_id, i.side)].append(i)
        for imgs in by_side.values():
            imgs.sort(key=_rank)
        chosen: list[str] = []
        if kind == 'all':
            chosen = _all_image_ids(db, groups, done)
            round_no = 0
        elif kind == 'test':
            for (pid, side), imgs in sorted(by_side.items()):
                if groups[pid] != 'test':
                    continue
                if any(i.id in taken for i in imgs):  # 這個病人側已經在某個測試批次
                    continue
                chosen.append(imgs[0].id)
            round_no = 0
        else:
            covered = {(i.patient_id, i.side) for i in images if i.id in taken or i.id in done}
            strata: dict[tuple, list[list[Image]]] = defaultdict(list)
            for (pid, side), imgs in by_side.items():
                if not groups[pid].startswith('fold-'):
                    continue
                free = [i for i in imgs if i.id not in taken and i.id not in done]
                if free:
                    p = patients.get(pid)
                    key = (groups[pid], egfr_group(p.egfr if p else None), free[0].machine or '', side)
                    strata[key].append(free)
            rng = random.Random(f'{split_id}:{len(taken)}')
            for lst in strata.values():
                rng.shuffle(lst)
                lst.sort(key=lambda imgs: (imgs[0].patient_id, imgs[0].side) in covered)  # 還沒涵蓋到的病人側優先
            keys = sorted(strata)
            rng.shuffle(keys)
            while len(chosen) < size and any(strata[k] for k in keys):
                for k in keys:
                    if strata[k] and len(chosen) < size:
                        chosen.append(strata[k].pop(0)[0].id)
            round_no = db.query(CirclingBatch).filter(CirclingBatch.kind == 'train').count() + 1
        if not chosen:
            raise AppError(409, 'NOTHING_TO_CIRCLE', {'test': '沒有可以加入的影像：測試集每側都已在批次中，或訓練影像都已圈選。', 'train': '沒有還沒圈選的訓練影像。', 'all': '所有影像都已有醫師遮罩。'}[kind])
        batch_id = next_dated('CB-', [r[0] for r in db.query(CirclingBatch.id).all()], width=3)
        db.add(CirclingBatch(id=batch_id, kind=kind, split_id=split_id, round=round_no, note=note, created_by=operator, created_at=now_iso()))
        db.flush()
        for seq, image_id in enumerate(chosen if kind == 'all' else sorted(chosen), start=1):
            db.add(CirclingItem(batch_id=batch_id, image_id=image_id, seq=seq, updated_at=now_iso()))
    return {'id': batch_id, 'kind': kind, 'count': len(chosen), 'split_id': split_id}


# ---------- 清單與詳細 ----------
def _counts(items: list[CirclingItem]) -> dict[str, int]:
    out = {s: 0 for s in ('pending', 'exported', 'parsed', 'imported', 'needs_redraw', 'unusable')}
    for i in items:
        out[i.status] = out.get(i.status, 0) + 1
    out['total'] = len(items)
    out['errors'] = sum(1 for i in items if json.loads(i.parse_json or '{}').get('errors'))
    return out


def _batch_dict(b: CirclingBatch, items: list[CirclingItem]) -> dict[str, Any]:
    return {
        'id': b.id, 'kind': b.kind, 'split_id': b.split_id, 'round': b.round, 'note': b.note, 'exported_at': b.exported_at,
        'export_relpath': b.export_relpath, 'include_original': b.include_original, 'created_by': b.created_by,
        'created_at': b.created_at, 'counts': _counts(items),
    }


def list_batches() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        items: dict[str, list[CirclingItem]] = defaultdict(list)
        for i in db.query(CirclingItem).all():
            items[i.batch_id].append(i)
        return [_batch_dict(b, items[b.id]) for b in db.query(CirclingBatch).order_by(CirclingBatch.created_at.desc()).all()]


def _item_dict(i: CirclingItem, image: Image | None) -> dict[str, Any]:
    return {
        'id': i.id, 'seq': i.seq, 'image_id': i.image_id, 'side': image.side if image else None, 'status': i.status,
        'circler': i.circler, 'return_kind': i.return_kind, 'parse': json.loads(i.parse_json or '{}'),
        'structures': json.loads(i.structures_json or '{}'), 'mask_id': i.mask_id, 'reject_reason': i.reject_reason, 'updated_at': i.updated_at,
    }


def batch_detail(batch_id: str) -> dict[str, Any]:
    with session_scope('research') as db:
        b = db.get(CirclingBatch, batch_id)
        if b is None:
            raise AppError(404, 'BATCH_NOT_FOUND', '找不到這個圈選批次。')
        items = db.query(CirclingItem).filter(CirclingItem.batch_id == batch_id).order_by(CirclingItem.seq).all()
        images = {i.id: i for i in db.query(Image).filter(Image.id.in_([x.image_id for x in items])).all()}
        return {**_batch_dict(b, items), 'items': [_item_dict(i, images.get(i.image_id)) for i in items]}


def progress() -> dict[str, Any]:
    """測試集完成度：每個測試病人側是否已有醫師遮罩。"""
    protected = protected_test_patients()
    with session_scope('research') as db:
        sides = {(i.patient_id, i.side) for i in db.query(Image).filter(Image.status == 'usable', Image.patient_id.in_(protected), Image.side.isnot(None)).all()} if protected else set()
        done = _has_physician_mask(db)
        covered = {(i.patient_id, i.side) for i in db.query(Image).filter(Image.id.in_(done)).all()} if done else set()
        train_masks = len([i for i in db.query(Image.id, Image.patient_id).filter(Image.id.in_(done)).all() if i[1] not in protected]) if done else 0
    return {'test_sides': len(sides), 'test_sides_done': len(sides & covered), 'train_images_done': train_masks}


# ---------- 匯出 ----------
def _need(side: str | None) -> str:
    organ = '肝' if side == 'right' else '脾' if side == 'left' else '肝或脾'
    return f'腎臟外框、腎竇、{organ}'


def _colors() -> tuple[list[dict[str, Any]], int]:
    from ..services.settings_store import get_all

    s = get_all()
    return list(s.get('circling_colors') or []), int(s.get('circling_color_tolerance') or 40)


def _instructions(batch: dict[str, Any]) -> str:
    colors, _ = _colors()
    mapping = '\n'.join(f'  {c["color"]}：{CIRCLED_LABEL.get(c["structure"], c["structure"])}' for c in colors) or '  （尚未設定；請用四種不同的顏色區分，並維持同一種畫法）'
    kind = {'test': '測試集（每位病人每側 1 張）', 'all': '全部影像'}.get(batch['kind'], f'訓練影像第 {batch["round"]} 批')
    return f'''醫師圈選說明（批次 {batch["id"]}，{kind}）

請在每張影像上圈出：
  1. 腎臟外框（整顆腎，含腎竇）
  2. 腎竇（中央高回音區，含腎盂；積水時擴張的腎盂腎盞也算）
  3. 右腎影像圈「肝」、左腎影像圈「脾」：圈影像中看得到的整個器官（器官內的血管算在內；膽囊、腸道、陰影不算）

顏色：
{mapping}

注意：
  - 檔名不能改（檔名就是影像 ID），尺寸不能縮放或裁切。
  - 建議存成 PNG；輪廓要封閉，可以畫輪廓線或塗滿，同一批請用同一種方式。
  - 不要在圖上寫字或畫其他記號。需要說明（例如「這張沒有肝」「看不清楚腎竇」）請寫在 清單.csv 的備註欄。
  - 影像中沒有肝（或脾）時不用畫，並在備註欄註記。

完整規則見 01_計畫與文件/標註規範（草稿）.md。
'''


def start_export(batch_id: str, include_original: bool, confirm: str, operator: str) -> dict[str, Any]:
    from ..jobs.manager import get_manager

    if include_original and confirm.strip() != ORIGINAL_CONFIRM:
        raise AppError(422, 'CONFIRM_REQUIRED', f'匯出原始影像需要輸入「{ORIGINAL_CONFIRM}」。')
    batch_detail(batch_id)
    job_id = get_manager().submit('circling_export', {'batch_id': batch_id, 'include_original': include_original, 'operator': operator}, target=batch_id, created_by=operator)
    return {'job_id': job_id}


@register('circling_export', label='匯出醫師圈選批次')
def export_job(ctx: JobContext) -> dict[str, Any]:
    from ..services.workspace import new_export_dir

    batch_id, include_original = ctx.config['batch_id'], bool(ctx.config.get('include_original'))
    batch = batch_detail(batch_id)
    items = [i for i in batch['items'] if i['status'] != 'imported']
    if not items:
        raise AppError(409, 'NOTHING_TO_EXPORT', '這一批的影像都已匯入，沒有需要匯出的。')
    folder = new_export_dir(f'醫師圈選_{batch_id}')
    image_dir = folder / '影像'
    image_dir.mkdir()
    root = get_settings().root
    raw_dir = None
    if include_original:
        raw_dir = get_settings().path('raw_archive') / '醫師圈選匯出' / folder.name
        raw_dir.mkdir(parents=True, exist_ok=True)
    with session_scope('research') as db:
        originals = dict(db.query(SourceMap.image_id, SourceMap.original_relpath).filter(SourceMap.image_id.in_([i['image_id'] for i in items])).all())
    missing_original = []
    for n, item in enumerate(items, start=1):
        image_id = item['image_id']
        shutil.copyfile(storage.image_path(image_id, 'model'), image_dir / f'{image_id}.png')
        if raw_dir is not None:
            source = root / originals[image_id] if image_id in originals else None
            if source is not None and source.is_file():
                shutil.copyfile(source, raw_dir / f'{image_id}{source.suffix.lower()}')  # 原始檔名可能含個資，改成影像 ID
            else:
                missing_original.append(image_id)
        ctx.progress(n / len(items) * 90, f'複製影像 {n}／{len(items)}')
    rows = [[i['seq'], i['image_id'], {'right': '右', 'left': '左'}.get(i['side'] or '', '未知'), _need(i['side']), ''] for i in items]
    header = ['序號', '影像ID', '側別', '要圈的構造', '備註（例如：沒有肝、腎竇看不清楚）']
    for target in [folder] + ([raw_dir] if raw_dir else []):
        with (target / '清單.csv').open('w', encoding='utf-8-sig', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        (target / '圈選說明.txt').write_text(_instructions(batch), encoding='utf-8')
    zip_path = shutil.make_archive(str(folder), 'zip', root_dir=folder)
    ctx.progress(98, '寫入紀錄')
    with session_scope('research') as db:
        b = db.get(CirclingBatch, batch_id)
        b.exported_at, b.export_relpath = now_iso(), folder.relative_to(root).as_posix()
        b.include_original = b.include_original or include_original
        for i in db.query(CirclingItem).filter(CirclingItem.batch_id == batch_id, CirclingItem.status.in_(('pending', 'needs_redraw'))).all():
            i.status, i.updated_at = 'exported', now_iso()
    return {'folder': folder.relative_to(root).as_posix(), 'zip': Path(zip_path).relative_to(root).as_posix(), 'images': len(items),
            'original_folder': raw_dir.relative_to(root).as_posix() if raw_dir else None, 'missing_original': len(missing_original)}


# ---------- 讀取傳回的圈選 ----------
def _hex_to_bgr(color: str) -> np.ndarray:
    c = color.lstrip('#')
    return np.array([int(c[4:6], 16), int(c[2:4], 16), int(c[0:2], 16)], np.float32)


def scan_sector(image_id: str, shape: tuple[int, int]) -> np.ndarray:
    """掃描扇形區（含 caliper 修補處），往外放寬一點；只取這個範圍內的筆畫，標頭與文字不會被誤認。"""
    calc = cv2.imdecode(np.fromfile(str(storage.image_path(image_id, 'calc')), np.uint8), cv2.IMREAD_UNCHANGED)
    if calc is None or calc.ndim != 3 or calc.shape[2] < 4:
        return np.ones(shape, bool)
    valid = (calc[:, :, 3] > 0).astype(np.uint8)
    k = max(5, int(0.02 * max(shape)) | 1)
    sector = cv2.morphologyEx(valid, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    sector = cv2.dilate(sector, np.ones((k, k), np.uint8))
    return sector > 0


def _fill_structure(stroke: np.ndarray) -> tuple[np.ndarray, str | None]:
    """筆畫 → 區域：封閉的輪廓填滿（輪廓線本身算在內）；塗滿的直接使用；沒封閉的回傳警告。"""
    h, w = stroke.shape
    min_area = max(30, int(0.0003 * h * w))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(stroke.astype(np.uint8), 8)
    clean = np.isin(labels, [k for k in range(1, n) if stats[k, cv2.CC_STAT_AREA] >= min_area // 3])
    if not clean.any():
        return np.zeros(stroke.shape, bool), None
    k = max(3, int(0.006 * max(h, w)) | 1)
    closed = cv2.morphologyEx(clean.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros(stroke.shape, np.uint8)
    cv2.drawContours(filled, [c for c in contours if cv2.contourArea(c) >= min_area], -1, 1, -1)
    filled = filled > 0
    gain = int(filled.sum()) - int((closed > 0).sum())
    thickness = 2 * float(cv2.distanceTransform(closed, cv2.DIST_L2, 3).max())
    if gain < 0.5 * int((closed > 0).sum()) and thickness < 0.03 * min(h, w):
        return np.zeros(stroke.shape, bool), 'unclosed'  # 細線但圍不起來：輪廓沒有封閉
    return filled, None


def parse_color_drawing(drawn: np.ndarray, references: dict[str, np.ndarray], sector: np.ndarray, colors: list[dict[str, Any]], tolerance: int) -> tuple[np.ndarray, dict[str, Any]]:
    """比對差異法：和系統原本的影像逐像素比較，只取出醫師新加的筆畫，再依顏色對照分類。"""
    h, w = drawn.shape[:2]
    best_name, best_diff, best_score = '', None, None
    for name, ref in references.items():
        if ref.shape[:2] != (h, w):
            continue
        diff = np.abs(drawn.astype(np.int16) - ref.astype(np.int16)).max(axis=2)
        score = float(np.median(diff[sector])) if sector.any() else float(np.median(diff))
        if best_score is None or score < best_score:
            best_name, best_diff, best_score = name, diff, score
    if best_diff is None:
        raise AppError(422, 'SIZE_MISMATCH', '尺寸和系統的影像不同。')
    changed = (best_diff > DIFF_THRESHOLD) & sector
    pixels = drawn.reshape(-1, 3).astype(np.float32)
    assigned = np.zeros(h * w, np.int16) - 1
    best_dist = np.full(h * w, np.inf, np.float32)
    idx = np.flatnonzero(changed.reshape(-1))
    for n, c in enumerate(colors):
        dist = np.linalg.norm(pixels[idx] - _hex_to_bgr(c['color']), axis=1)
        better = (dist <= tolerance) & (dist < best_dist[idx])
        best_dist[idx[better]] = dist[better]
        assigned[idx[better]] = n
    assigned = assigned.reshape(h, w)
    label = np.zeros((h, w), np.uint8)
    info: dict[str, Any] = {'reference': best_name, 'background_diff': best_score, 'areas': {}, 'warnings': [], 'unknown_color_px': int((changed & (assigned < 0)).sum())}
    regions: dict[str, np.ndarray] = {}
    for structure in CIRCLED:
        stroke = np.zeros((h, w), bool)
        for n, c in enumerate(colors):
            if c.get('structure') == structure:
                stroke |= assigned == n
        if not stroke.any():
            continue
        region, warn = _fill_structure(stroke)
        if warn:
            info['warnings'].append(f'{CIRCLED_LABEL[structure]}的輪廓沒有封閉')
            info.setdefault('unclosed', []).append(structure)
        if region.any():
            regions[structure] = region
    if 'sinus' in regions and 'kidney' not in regions:
        regions.pop('sinus')  # 沒有腎外框就無法區分腎實質，腎竇先不用（兩者都設為未標）
        info['warnings'].append('有腎竇但沒有腎臟外框：腎臟與腎竇都設為未標')
    for structure in FILL_ORDER:
        if structure in regions:
            label[regions[structure]] = LABEL_VALUE[structure]
    if info['unknown_color_px'] > 0.001 * h * w:
        info['warnings'].append(f'有 {info["unknown_color_px"]} 個像素的顏色不在顏色對照中')
    return label, info


def parse_label_png(raw: np.ndarray) -> np.ndarray | None:
    """標註軟體輸出的標籤 PNG：單通道，數值只有 0–4。不是的話回傳 None（當成彩色圈選處理）。"""
    arr = raw
    if arr.ndim == 3:
        if arr.shape[2] == 4:
            arr = arr[:, :, :3]
        if not (np.array_equal(arr[:, :, 0], arr[:, :, 1]) and np.array_equal(arr[:, :, 1], arr[:, :, 2])):
            return None
        arr = arr[:, :, 0]
    values = set(np.unique(arr).tolist())
    if not values <= {0, 1, 2, 3, 4} or values == {0}:
        return None
    return arr.astype(np.uint8)


def default_structures(label: np.ndarray, side: str | None, unclosed: list[str] | None = None) -> dict[str, str]:
    present = set(np.unique(label).tolist())
    out = {
        'kidney': 'drawn' if 1 in present else 'unlabeled',
        'sinus': 'drawn' if 2 in present else 'unlabeled',
        'liver': 'drawn' if 3 in present else 'unlabeled',
        'spleen': 'drawn' if 4 in present else 'unlabeled',
    }
    if side == 'right' and out['spleen'] != 'drawn':
        out['spleen'] = 'absent'
    if side == 'left' and out['liver'] != 'drawn':
        out['liver'] = 'absent'
    for s in unclosed or []:
        if out.get(s) != 'drawn':
            out[s] = 'unlabeled'
    return out


def load_site_results(folder: Path) -> tuple[Path | None, dict[str, dict[str, Any]]]:
    """醫師圈選網站輸出的 圈選結果.json：項目狀態、回音分級、備註、其他圈選。選到 標籤 子資料夾時也找得到。"""
    path = next((p for p in (folder / SITE_RESULT, folder.parent / SITE_RESULT) if p.is_file()), None)
    if path is None:
        return None, {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        raise AppError(422, 'BAD_SITE_RESULT', f'{SITE_RESULT} 讀不出來，請到圈選網站重新輸出。') from None
    if not isinstance(data, dict) or data.get('schema') != SITE_SCHEMA or data.get('version') != 1:
        raise AppError(422, 'BAD_SITE_RESULT', f'{SITE_RESULT} 的格式不是這個版本的圈選網站輸出的。')
    return path, {str(i['image_id']).upper(): i for i in data.get('images', [])}


def site_structures(label: np.ndarray, side: str | None, entry: dict[str, Any]) -> dict[str, str]:
    """醫師在網站上標的狀態優先；有圈到的一律是已畫。"""
    out = default_structures(label, side)
    states = entry.get('states') or {}
    present = set(np.unique(label).tolist())
    for code in CIRCLED:
        if states.get(code) == 'drawn' and (LABEL_VALUE[code] in present or (code == 'kidney' and LABEL_VALUE['sinus'] in present)):
            out[code] = 'drawn'
        elif out[code] != 'drawn' and states.get(code) in ('absent', 'unlabeled'):
            out[code] = states[code]
    return out


def site_extras(entry: dict[str, Any]) -> dict[str, Any]:
    """基本四項以外的圈選（囊腫、結石、聲影、自訂項目）：跟著遮罩保存，才不會只剩一份會被覆蓋的檔案。"""
    return {
        'shapes': [s for s in entry.get('shapes') or [] if s.get('structure') not in CIRCLED],
        'states': {k: v for k, v in (entry.get('states') or {}).items() if k not in CIRCLED},
    }


def _same_as_imported(db, row: CirclingItem, label: np.ndarray, structures: dict[str, str]) -> bool:
    """已匯入的影像再次傳回、內容完全相同時不重新匯入（網站每次輸出都包含全部已完成的影像）。"""
    if row.status != 'imported' or not row.mask_id:
        return False
    mask = db.get(MaskAnnotation, row.mask_id)
    if mask is None or mask.trashed_at:
        return False
    stored = cv2.imdecode(np.fromfile(str(storage.from_root(mask.relpath)), np.uint8), cv2.IMREAD_GRAYSCALE)
    return stored is not None and stored.shape == label.shape and np.array_equal(stored, label) and json.loads(mask.flags_json or '{}').get('structures') == structures


def save_image_grade(db, image_id: str, site: dict[str, Any], rater: str) -> None:
    """每張影像的回音分級（決策 D49）。一位判讀者一張一筆，重新匯入時更新。"""
    grade = site.get('grade')
    unsure = bool(site.get('grade_unsure'))
    if grade is None and not unsure:
        return
    row = db.query(ImageGrade).filter(ImageGrade.image_id == image_id, ImageGrade.rater == rater).one_or_none()
    if row is None:
        row = ImageGrade(image_id=image_id, rater=rater, created_at=now_iso())
        db.add(row)
    row.grade = None if unsure else int(grade)
    row.unsure_reason = str(site.get('grade_reason') or '')[:80] if unsure else None


SIDE_NAME = {'right': '右腎', 'left': '左腎', None: '未知'}
STATUS_NAME = {'usable': '可用', 'pending_review': '待確認', 'excluded': '排除'}


def apply_site_decisions(db, image_id: str, entry: dict[str, Any]) -> list[str]:
    """醫師圈選網站的判斷一律為準：側別（含改成未知）與能否使用不同時，改成網站的值。回傳改了什麼（給人看）。

    側別來源記成 circling，之後重新去識別化不會蓋掉；「不能用」排除並附醫師的原因；
    「完成」的影像改成可用（原本待確認或被排除也一樣）。去識別化殘留的標記不動，資料集頁仍會提示。
    """
    img = db.get(Image, image_id)
    status = entry.get('status')
    if img is None or status not in ('done', 'unusable'):
        return []
    notes: list[str] = []
    if 'side' in entry:
        side = entry['side'] if entry['side'] in ('right', 'left') else None
        if side != img.side:
            notes.append(f'側別 {SIDE_NAME[img.side if img.side in ("right", "left") else None]} → {SIDE_NAME[side]}')
            img.side = side
        if img.side_source != 'circling':
            img.side_source = 'circling'
    if status == 'unusable':
        reason = ('醫師圈選：' + (str(entry.get('unusable_reason') or '').strip() or '不能用'))[:80]
        if img.status != 'excluded' or img.exclude_reason != reason:
            notes.append(f'狀態 {STATUS_NAME.get(img.status, img.status)} → 排除（{reason}）')
            img.status, img.exclude_reason = 'excluded', reason
    elif img.status != 'usable':
        notes.append(f'狀態 {STATUS_NAME.get(img.status, img.status)} → 可用' + ('（去識別化殘留仍待確認）' if img.deid_check == 'residual' else ''))
        img.status, img.exclude_reason, img.review_reasons_json = 'usable', None, '[]'
    return notes


def labeled_from_structures(structures: dict[str, str]) -> list[str]:
    """構造狀態 → 遮罩旗標 labeled（部分標註訓練用；見 ml/data.class_groups）。
    已畫或確定不在影像中的才算「標了」；未標的在訓練時忽略、不當背景。"""
    out: list[str] = []
    kidney, sinus = structures.get('kidney'), structures.get('sinus')
    if kidney in ('drawn', 'absent') and sinus in ('drawn', 'absent'):
        out += ['parenchyma', 'sinus']
    elif kidney == 'drawn':
        out.append('kidney')  # 腎竇沒標：腎實質與腎竇合成一組
    for organ in ('liver', 'spleen'):
        if structures.get(organ) in ('drawn', 'absent'):
            out.append(organ)
    return out


def start_upload(batch_id: str, folder: str, circler: str, operator: str) -> dict[str, Any]:
    from ..jobs.manager import get_manager

    path = Path(folder.strip().strip('"'))
    if not path.is_dir():
        raise AppError(422, 'FOLDER_NOT_FOUND', '找不到這個資料夾，請確認路徑。')
    if len(circler) > 40:
        raise AppError(422, 'BAD_CIRCLER', '圈選者代號太長（最多 40 字）。')
    batch_detail(batch_id)
    job_id = get_manager().submit('circling_parse', {'batch_id': batch_id, 'folder': str(path), 'circler': circler.strip(), 'operator': operator}, target=batch_id, created_by=operator)
    return {'job_id': job_id}


def _returned_dir(batch_id: str, restricted: bool) -> Path:
    if restricted:
        return get_settings().path('raw_archive') / '醫師圈選回傳' / batch_id
    return get_settings().path('annotations') / '醫師圈選回傳' / batch_id / '原檔'


def parsed_path(batch_id: str, image_id: str) -> Path:
    return get_settings().path('annotations') / '醫師圈選回傳' / batch_id / '解析' / f'{image_id}.png'


@register('circling_parse', label='讀取醫師傳回的圈選')
def parse_job(ctx: JobContext) -> dict[str, Any]:
    from ..data.importer import load_original

    batch_id, folder, circler = ctx.config['batch_id'], Path(ctx.config['folder']), ctx.config.get('circler', '')
    batch = batch_detail(batch_id)
    items = {i['image_id'].upper(): i for i in batch['items']}
    colors, tolerance = _colors()
    site_path, site = load_site_results(folder)
    if site_path is not None:
        dest = get_settings().path('annotations') / '醫師圈選回傳' / batch_id
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(site_path, dest / SITE_RESULT)  # 最新一份；囊腫、結石、聲影與自訂項目也存在各遮罩的 flags
        shutil.copyfile(site_path, dest / f'圈選結果_{now_iso().replace(":", "")}.json')  # 每次上傳另留一份，不會被覆蓋
    files: dict[str, Path] = {}
    not_in_batch, duplicates = [], []
    for f in sorted(folder.rglob('*')):
        if not f.is_file() or f.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        m = ID_RE.search(f.stem)
        if not m:
            not_in_batch.append(f.name)
            continue
        key = m.group(0).upper()
        if key not in items:
            not_in_batch.append(f.name)
            continue
        if key in files:
            duplicates.append(f.name)
            if f.stat().st_mtime <= files[key].stat().st_mtime:
                continue
        files[key] = f
    results = {'parsed': 0, 'errors': 0, 'not_in_batch': not_in_batch[:50], 'not_in_batch_count': len(not_in_batch), 'duplicates': duplicates[:50]}
    results['unchanged'] = 0
    applied: dict[str, list[str]] = {}
    if site_path is not None:
        in_batch = {k: v for k, v in site.items() if k in items}
        results['site'] = {
            'images': len(site), 'in_batch': len(in_batch),
            'unusable': sorted(items[k]['image_id'] for k, v in in_batch.items() if v.get('status') == 'unusable'),
            'no_label': sorted(items[k]['image_id'] for k, v in in_batch.items() if v.get('status') == 'done' and not v.get('label_file')),
            'label_file_missing': sorted(items[k]['image_id'] for k, v in in_batch.items() if v.get('label_file') and k not in files),
        }
        # 回音分級和遮罩無關，每張完成的影像都寫入（包括沒有基本構造、不會產生標籤的影像）
        # 側別、能否使用以醫師圈選網站為準（使用者指示，2026-11-09）
        with session_scope('research') as db:
            for key, entry in in_batch.items():
                image_id = items[key]['image_id']
                if entry.get('status') == 'done':
                    save_image_grade(db, image_id, entry, entry.get('circler') or circler or '醫師圈選')
                notes = apply_site_decisions(db, image_id, entry)
                if notes:
                    applied[key] = notes
                if entry.get('status') == 'unusable':
                    row = db.get(CirclingItem, items[key]['id'])
                    row.status, row.circler = 'unusable', entry.get('circler') or circler or row.circler
                    row.parse_json = json.dumps({'errors': [], 'warnings': [f'已依圈選網站更新：{n}' for n in notes],
                                                 'unusable_reason': entry.get('unusable_reason') or ''}, ensure_ascii=False)
                    row.updated_at = now_iso()
        results['site']['applied'] = [{'image_id': items[k]['image_id'], 'changes': v} for k, v in sorted(applied.items())]
        if applied:
            from ..core import audit

            audit.record(ctx.config.get('operator') or '醫師圈選', '依醫師圈選網站更新影像', 'circling', batch_id,
                         {'images': len(applied), 'changes': results['site']['applied'][:200]})
    for n, (key, f) in enumerate(sorted(files.items()), start=1):
        item = items[key]
        image_id = item['image_id']
        info: dict[str, Any] = {'file': f.name, 'errors': [], 'warnings': []}
        structures: dict[str, str] = {}
        kind, restricted = 'color', False
        try:
            raw = cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_UNCHANGED)
            if raw is None:
                raise AppError(422, 'UNREADABLE', '無法讀取這個檔案。')
            model = cv2.imread(str(storage.image_path(image_id, 'model')), cv2.IMREAD_GRAYSCALE)
            if model is None:
                model = cv2.imdecode(np.fromfile(str(storage.image_path(image_id, 'model')), np.uint8), cv2.IMREAD_GRAYSCALE)
            h, w = model.shape
            if raw.shape[:2] != (h, w):
                raise AppError(422, 'SIZE_MISMATCH', f'尺寸 {raw.shape[1]}×{raw.shape[0]} 和系統的影像（{w}×{h}）不同；請不要縮放或裁切。')
            label = parse_label_png(raw)
            if label is not None:
                kind = 'label'
                info.update({'reference': 'label_png', 'areas': {}})
            else:
                if not colors:
                    raise AppError(422, 'COLORS_NOT_SET', '尚未設定顏色對照：請到「設定 › 顏色對照」指定每種顏色代表的構造，再重新上傳。')
                drawn = raw[:, :, :3] if raw.ndim == 3 else cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
                refs = {'deid': cv2.cvtColor(model, cv2.COLOR_GRAY2BGR)}
                if batch['include_original']:
                    try:
                        refs['original'] = load_original(image_id)
                    except AppError:
                        pass
                label, parsed = parse_color_drawing(drawn, refs, scan_sector(image_id, (h, w)), colors, tolerance)
                info.update(parsed)
                restricted = parsed['reference'] == 'original'
            info['areas'] = {name: int((label == v).sum()) for name, v in STRUCTURES.items()}
            if not label.any():
                info['errors'].append('沒有找到任何圈選')
            entry = site.get(key)
            structures = site_structures(label, item['side'], entry) if entry else default_structures(label, item['side'], info.get('unclosed'))
            if entry:
                info['site'] = {**{k: entry.get(k) for k in ('grade', 'grade_unsure', 'grade_reason', 'note', 'discuss', 'seconds', 'side')}, 'extras': site_extras(entry)}
                info['warnings'] += [f'已依圈選網站更新：{n}' for n in applied.get(key, [])]
                structures = site_structures(label, entry.get('side') if 'side' in entry else item['side'], entry)
            if not info['errors']:
                with session_scope('research') as db:
                    if _same_as_imported(db, db.get(CirclingItem, item['id']), label, structures):
                        results['unchanged'] += 1
                        ctx.progress(n / max(1, len(files)) * 100, f'讀取 {n}／{len(files)}')
                        continue
            deid.write_png(parsed_path(batch_id, image_id), label)
            dest = _returned_dir(batch_id, restricted)
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest / f'{image_id}{f.suffix.lower()}')  # 傳回的原檔（原始影像版本存在受限區）
        except AppError as exc:
            info['errors'].append(exc.message)
        status = 'parsed' if not info['errors'] else 'exported'
        results['parsed' if status == 'parsed' else 'errors'] += 1
        with session_scope('research') as db:
            row = db.get(CirclingItem, item['id'])
            row.parse_json = json.dumps(info, ensure_ascii=False)
            row.return_kind, row.circler = kind, (site.get(key) or {}).get('circler') or circler or row.circler
            row.structures_json = json.dumps(structures, ensure_ascii=False)
            row.parsed_relpath = storage.relative_to_root(parsed_path(batch_id, image_id)) if status == 'parsed' else None
            row.status = status if row.status != 'imported' or status == 'parsed' else row.status
            if row.status == 'parsed' and row.mask_id:
                row.mask_id = None  # 重新傳回：匯入時會建立新版本
            row.reject_reason = '' if status == 'parsed' else row.reject_reason
            row.updated_at = now_iso()
        ctx.progress(n / max(1, len(files)) * 100, f'讀取 {n}／{len(files)}')
    results['matched'] = len(files)
    return results


# ---------- 檢查與匯入 ----------
def _item(db, item_id: int) -> CirclingItem:
    row = db.get(CirclingItem, item_id)
    if row is None:
        raise AppError(404, 'ITEM_NOT_FOUND', '找不到這個圈選項目。')
    return row


def overlay_png(item_id: int) -> bytes:
    """去識別化影像＋轉出的遮罩（不顯示醫師傳回的原檔，原始影像版本含個資）。"""
    with session_scope('research') as db:
        row = _item(db, item_id)
        image_id, relpath = row.image_id, row.parsed_relpath
    base = cv2.imdecode(np.fromfile(str(storage.image_path(image_id, 'model')), np.uint8), cv2.IMREAD_GRAYSCALE)
    out = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    if relpath:
        label = cv2.imdecode(np.fromfile(str(storage.from_root(relpath)), np.uint8), cv2.IMREAD_GRAYSCALE)
        if label is not None and label.shape == base.shape:
            color = out.copy()
            for value, bgr in OVERLAY_COLORS.items():
                color[label == value] = bgr
            out = cv2.addWeighted(out, 0.55, color, 0.45, 0)
            for value, bgr in OVERLAY_COLORS.items():
                contours, _ = cv2.findContours((label == value).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(out, contours, -1, bgr, max(1, out.shape[1] // 400))
    scale = min(1.0, 900 / out.shape[1])
    if scale < 1:
        out = cv2.resize(out, (int(out.shape[1] * scale), int(out.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode('.png', out)
    return buf.tobytes()


def update_structures(item_id: int, structures: dict[str, str]) -> dict[str, Any]:
    bad = {k: v for k, v in structures.items() if k not in CIRCLED or v not in STATES}
    if bad:
        raise AppError(422, 'BAD_STRUCTURES', '構造狀態只能是 drawn、absent、unlabeled。')
    with session_scope('research') as db:
        row = _item(db, item_id)
        current = json.loads(row.structures_json or '{}')
        areas = json.loads(row.parse_json or '{}').get('areas', {})
        drawn_now = {'kidney': areas.get('parenchyma', 0) + areas.get('sinus', 0), 'sinus': areas.get('sinus', 0), 'liver': areas.get('liver', 0), 'spleen': areas.get('spleen', 0)}
        for k, v in structures.items():
            if v == 'drawn' and not drawn_now.get(k):
                raise AppError(422, 'NOT_DRAWN', f'{CIRCLED_LABEL[k]}沒有圈選，不能設為「已畫」。')
            if v != 'drawn' and drawn_now.get(k):
                raise AppError(422, 'IS_DRAWN', f'{CIRCLED_LABEL[k]}已經有圈選；要改成其他狀態請請醫師重圈。')
        current.update(structures)
        row.structures_json, row.updated_at = json.dumps(current, ensure_ascii=False), now_iso()
        return _item_dict(row, db.get(Image, row.image_id))


def reject_item(item_id: int, reason: str) -> dict[str, Any]:
    with session_scope('research') as db:
        row = _item(db, item_id)
        if row.status == 'imported':
            raise AppError(409, 'ALREADY_IMPORTED', '已經匯入的不能退回；請把遮罩移入回收桶後再請醫師重圈。')
        row.status, row.reject_reason, row.updated_at = 'needs_redraw', reason.strip()[:200] or '需要重圈', now_iso()
        return _item_dict(row, db.get(Image, row.image_id))


def import_batch(batch_id: str, item_ids: list[int] | None, operator: str) -> dict[str, Any]:
    """把檢查過的轉換結果匯入成正式遮罩：來源 physician_upload、狀態完成、算已確認。"""
    from .drafts import raster_to_shapes

    batch = batch_detail(batch_id)
    targets = [i for i in batch['items'] if i['status'] == 'parsed' and not i['parse'].get('errors') and (item_ids is None or i['id'] in item_ids)]
    if not targets:
        raise AppError(409, 'NOTHING_TO_IMPORT', '沒有可以匯入的項目（需要先上傳並轉換成功）。')
    imported = []
    for item in targets:
        image_id = item['image_id']
        label = cv2.imdecode(np.fromfile(str(parsed_path(batch_id, image_id)), np.uint8), cv2.IMREAD_GRAYSCALE)
        structures = item['structures']
        circler = item['circler']
        who = f'醫師圈選（{circler}）' if circler else '醫師圈選'
        with session_scope('research') as db:
            last = db.query(MaskAnnotation.version).filter(MaskAnnotation.image_id == image_id).order_by(MaskAnnotation.version.desc()).first()
            version = (last[0] + 1) if last else 1
            path = storage.mask_path(image_id, version, 'physician_upload')
            deid.write_png(path, label)
            site = item['parse'].get('site')
            flags = {'structures': structures, 'labeled': labeled_from_structures(structures), 'circler': circler, 'circling_item_id': item['id'],
                     'batch_id': batch_id, 'warnings': item['parse'].get('warnings', []), 'imported_by': operator}
            if site:
                flags['site'] = {k: site.get(k) for k in ('note', 'discuss', 'seconds', 'side', 'extras')}
            record = MaskAnnotation(image_id=image_id, version=version, annotator=who, relpath=storage.relative_to_root(path),
                                    shapes_json=json.dumps(raster_to_shapes(label), ensure_ascii=False), flags_json=json.dumps(flags, ensure_ascii=False),
                                    status='done', source='physician_upload', verified_by=who, verified_at=now_iso(), created_at=now_iso())
            db.add(record)
            db.flush()
            row = db.get(CirclingItem, item['id'])
            row.status, row.mask_id, row.updated_at = 'imported', record.id, now_iso()
            imported.append(record.id)
    return {'imported': len(imported), 'mask_ids': imported}


# ---------- 顏色偵測 ----------
def detect_colors(path: str, limit: int = 8) -> dict[str, Any]:
    """從一張醫師的圖找出使用的顏色，供設定顏色對照。只回傳顏色與像素數，不回傳影像內容。"""
    p = Path(path.strip().strip('"'))
    if not p.is_file() or p.suffix.lower() not in IMAGE_SUFFIXES:
        raise AppError(422, 'FILE_NOT_FOUND', '找不到這個影像檔。')
    raw = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    if raw is None:
        raise AppError(422, 'UNREADABLE', '無法讀取這個檔案。')
    mask = None
    m = ID_RE.search(p.stem)
    if m:
        ref_path = storage.image_path(m.group(0).upper(), 'model')
        ref = cv2.imdecode(np.fromfile(str(ref_path), np.uint8), cv2.IMREAD_GRAYSCALE) if ref_path.exists() else None
        if ref is not None and ref.shape == raw.shape[:2]:
            mask = np.abs(raw.astype(np.int16) - cv2.cvtColor(ref, cv2.COLOR_GRAY2BGR).astype(np.int16)).max(axis=2) > DIFF_THRESHOLD
    hsv = cv2.cvtColor(raw, cv2.COLOR_BGR2HSV)
    colored = (hsv[:, :, 1] >= 90) & (hsv[:, :, 2] >= 70)
    if mask is not None:
        colored &= mask
    pixels = raw[colored]
    if len(pixels) == 0:
        return {'colors': [], 'compared': mask is not None}
    q = (pixels // 32).astype(np.int32)
    keys = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    out = []
    for key in np.argsort(-np.bincount(keys))[:limit]:
        sel = pixels[keys == key]
        if len(sel) < 20:
            continue
        b, g, r = sel.mean(axis=0)
        out.append({'color': f'#{int(r):02x}{int(g):02x}{int(b):02x}', 'pixels': int(len(sel))})
    return {'colors': out, 'compared': mask is not None}


def colors_summary() -> dict[str, Any]:
    colors, tolerance = _colors()
    return {'colors': colors, 'tolerance': tolerance, 'structures': CIRCLED_LABEL, 'original_confirm': ORIGINAL_CONFIRM}


def image_bytes(png: np.ndarray) -> bytes:  # pragma: no cover - 保留給除錯
    ok, buf = cv2.imencode('.png', png)
    return io.BytesIO(buf.tobytes()).getvalue()
