"""標註：遮罩（版本化）、回音分級（雙醫師）、品質、側別，以及標註佇列。

盲測：佇列與標註資料只回傳影像 ID、側別與必要的顯示資訊，不回傳 eGFR、
病人臨床資料、AI 結果或其他人的分級。
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import cv2
import numpy as np

from ..core.errors import AppError
from ..core.ids import now_iso
from ..data import deid, storage
from ..db.models_research import GradeLabel, Image, ImageLabel, MaskAnnotation
from ..db.session import session_scope

STRUCTURES = {'parenchyma': 1, 'sinus': 2, 'liver': 3, 'spleen': 4}
TASKS = {
    'mask': '腎實質、腎竇、肝、脾遮罩',
    'grade': '回音分級 Grade 0–3',
    'side': '側別與切面',
}


DRAW_ORDER = ('liver', 'spleen', 'parenchyma', 'sinus')


def rasterize(shapes: list[dict[str, Any]], width: int, height: int) -> np.ndarray:
    """形狀（影像像素座標）→ 標籤圖。依固定順序疊放：肝／脾 → 腎實質（整顆腎外框）→ 腎竇，
    和畫的先後無關（先畫腎竇再畫腎外框，腎竇也不會被蓋掉）；同一構造內依原順序。"""
    label = np.zeros((height, width), np.uint8)
    order = {name: n for n, name in enumerate(DRAW_ORDER)}
    for s in sorted(shapes, key=lambda s: order.get(s.get('structure', ''), len(order))):
        value = STRUCTURES.get(s.get('structure', ''))
        if not value:
            raise AppError(422, 'BAD_STRUCTURE', f'不認識的結構：{s.get("structure")}')
        pts = np.array([[round(x), round(y)] for x, y in s.get('points', [])], dtype=np.int32)
        if len(pts) == 0:
            continue
        if s.get('kind') == 'polygon':
            if len(pts) >= 3:
                cv2.fillPoly(label, [pts], value)
        else:
            thickness = max(1, int(round(s.get('width', 10))))
            cv2.polylines(label, [pts], False, value, thickness, lineType=cv2.LINE_8)
            for x, y in pts[:: max(1, len(pts) // 50)]:
                cv2.circle(label, (int(x), int(y)), thickness // 2, value, -1)
    return label


def _image(db, image_id: str) -> Image:
    image = db.get(Image, image_id)
    if image is None:
        raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像。')
    return image


CLIENT_FLAGS = ('occluded', 'no_reference')  # 編輯器可以設定的旗標；其他旗標（labeled、review…）由系統產生，不沿用草稿


def save_mask(image_id: str, shapes: list[dict[str, Any]], annotator: str, flags: dict[str, Any], status: str) -> dict[str, Any]:
    if not annotator:
        raise AppError(422, 'ANNOTATOR_REQUIRED', '請先在右上角選擇操作者。')
    if status not in {'draft', 'done'}:
        raise AppError(422, 'BAD_STATUS', '狀態只能是 draft 或 done。')
    with session_scope('research') as db:
        image = _image(db, image_id)
        label = rasterize(shapes, image.width, image.height)
        last = db.query(MaskAnnotation.version).filter(MaskAnnotation.image_id == image_id).order_by(MaskAnnotation.version.desc()).first()
        version = (last[0] + 1) if last else 1
        clean = {k: v for k, v in (flags or {}).items() if k in CLIENT_FLAGS}
        base = (
            db.query(MaskAnnotation)
            .filter(MaskAnnotation.image_id == image_id, MaskAnnotation.trashed_at.is_(None), MaskAnnotation.status != 'rejected')
            .order_by(MaskAnnotation.version.desc())
            .first()
        )
        source, verified = 'manual', {}
        if base is not None and base.source in ('physician_upload', 'edited_upload'):
            # 修正醫師圈選的小錯誤：保留醫師的構造狀態與代號，標記「修改自醫師圈選」
            prior = json.loads(base.flags_json or '{}')
            clean = {**{k: prior[k] for k in ('structures', 'labeled', 'circler', 'batch_id') if k in prior}, **clean, 'edited_from': base.id}
            source = 'edited_upload'
            if status == 'done':
                verified = {'verified_by': annotator, 'verified_at': now_iso()}
        path = storage.mask_path(image_id, version, source)
        deid.write_png(path, label)
        record = MaskAnnotation(
            image_id=image_id,
            version=version,
            annotator=annotator,
            relpath=storage.relative_to_root(path),
            shapes_json=json.dumps(shapes, ensure_ascii=False),
            flags_json=json.dumps(clean, ensure_ascii=False),
            status=status,
            source=source,
            created_at=now_iso(),
            **verified,
        )
        db.add(record)
        db.flush()
        counts = {name: int((label == v).sum()) for name, v in STRUCTURES.items()}
        return {'id': record.id, 'version': version, 'pixels': counts}


def latest_mask(image_id: str, annotator: str | None = None) -> dict[str, Any] | None:
    with session_scope('research') as db:
        q = db.query(MaskAnnotation).filter(MaskAnnotation.image_id == image_id, MaskAnnotation.trashed_at.is_(None), MaskAnnotation.status != 'rejected')
        if annotator:
            q = q.filter(MaskAnnotation.annotator == annotator)
        m = q.order_by(MaskAnnotation.version.desc()).first()
        if m is None:
            return None
        return {
            'id': m.id,
            'version': m.version,
            'annotator': m.annotator,
            'status': m.status,
            'shapes': json.loads(m.shapes_json),
            'flags': json.loads(m.flags_json),
            'created_at': m.created_at,
        }


def mask_history(image_id: str) -> list[dict[str, Any]]:
    with session_scope('research') as db:
        return [
            {'id': m.id, 'version': m.version, 'annotator': m.annotator, 'status': m.status, 'created_at': m.created_at}
            for m in db.query(MaskAnnotation).filter(MaskAnnotation.image_id == image_id, MaskAnnotation.trashed_at.is_(None)).order_by(MaskAnnotation.version.desc())
        ]


def save_grade(patient_id: str, side: str, grade: int | None, unsure_reason: str | None, rater: str, image_id: str | None) -> dict[str, Any]:
    if not rater:
        raise AppError(422, 'RATER_REQUIRED', '請先選擇分級的醫師。')
    if side not in {'right', 'left'}:
        raise AppError(422, 'BAD_SIDE', '側別只能是 right 或 left。')
    if grade is None and not unsure_reason:
        raise AppError(422, 'REASON_REQUIRED', '選「無法判斷」時請寫原因。')
    if grade is not None and grade not in (0, 1, 2, 3):
        raise AppError(422, 'BAD_GRADE', '分級只能是 0 到 3。')
    with session_scope('research') as db:
        row = (
            db.query(GradeLabel)
            .filter(GradeLabel.patient_id == patient_id, GradeLabel.side == side, GradeLabel.rater == rater, GradeLabel.is_consensus.is_(False))
            .one_or_none()
        )
        if row is None:
            row = GradeLabel(patient_id=patient_id, side=side, rater=rater, is_consensus=False, created_at=now_iso())
            db.add(row)
        row.grade, row.unsure_reason, row.image_id, row.created_at = grade, (unsure_reason if grade is None else None), image_id, now_iso()
        db.flush()
        return {'id': row.id}


def save_label(image_id: str, kind: str, value: dict[str, Any], annotator: str) -> dict[str, Any]:
    if not annotator:
        raise AppError(422, 'ANNOTATOR_REQUIRED', '請先在右上角選擇操作者。')
    if kind == 'side' and (value.get('side') not in {'right', 'left'} or value.get('view') not in {'long', 'short', 'oblique'}):
        raise AppError(422, 'BAD_SIDE', '側別或切面選項不正確。')
    if kind != 'side':  # 影像品質標註已移除（決策 D25）
        raise AppError(422, 'BAD_KIND', '標註類型只能是 side。')
    with session_scope('research') as db:
        _image(db, image_id)
        row = db.query(ImageLabel).filter(ImageLabel.image_id == image_id, ImageLabel.kind == kind, ImageLabel.annotator == annotator).one_or_none()
        if row is None:
            row = ImageLabel(image_id=image_id, kind=kind, annotator=annotator, value_json='{}', created_at=now_iso())
            db.add(row)
        row.value_json, row.created_at = json.dumps(value, ensure_ascii=False), now_iso()
        if kind == 'side':
            db.query(Image).filter(Image.id == image_id).update({'side': value['side'], 'side_source': 'manual', 'view': value['view']})
        db.flush()
        return {'id': row.id}


def _usable(db):
    return db.query(Image).filter(Image.status == 'usable').order_by(Image.id)


def summary() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        usable = _usable(db).all()
        total_images = len(usable)
        # 完成＝人工畫完或確認過；草稿與被退回的草稿都不算（退回只表示草稿不能用，影像仍待標註）
        masked = {r[0] for r in db.query(MaskAnnotation.image_id).filter(MaskAnnotation.status.notin_(('draft', 'rejected')), MaskAnnotation.trashed_at.is_(None)).distinct()}
        sides = {r[0] for r in db.query(ImageLabel.image_id).filter(ImageLabel.kind == 'side').distinct()}
        kidney_sides = {(i.patient_id, i.side) for i in usable if i.patient_id and i.side}
        graded = defaultdict(set)
        for pid, side, rater in db.query(GradeLabel.patient_id, GradeLabel.side, GradeLabel.rater).filter(GradeLabel.is_consensus.is_(False)).all():
            graded[(pid, side)].add(rater)
        usable_ids = {i.id for i in usable}
    return [
        {'id': 'mask', 'name': TASKS['mask'], 'done': len(masked & usable_ids), 'total': total_images},
        {'id': 'grade', 'name': TASKS['grade'], 'done': sum(1 for k in kidney_sides if graded.get(k)), 'double': sum(1 for k in kidney_sides if len(graded.get(k, ())) >= 2), 'total': len(kidney_sides)},
        {'id': 'side', 'name': TASKS['side'], 'done': len(sides & usable_ids), 'total': total_images},
    ]


def _image_view(i: Image) -> dict[str, Any]:
    """標註畫面需要的影像資訊（盲測：不含 eGFR 與臨床資料）。"""
    return {
        'id': i.id,
        'width': i.width,
        'height': i.height,
        'side': i.side,
        'view': i.view,
        'machine': i.machine,
        'pixel_spacing_mm': i.pixel_spacing_mm,
    }


def queue(task: str, rater: str, limit: int | None = None) -> dict[str, Any]:
    # 不再限制 200 筆（M2.5）：975 張影像、約 362 個腎臟側都要能標
    """標註佇列：依順序列出項目與「這位標註者是否已完成」。"""
    if task not in TASKS:
        raise AppError(404, 'TASK_NOT_FOUND', '找不到這個標註任務。')
    with session_scope('research') as db:
        usable = _usable(db).all()
        if task == 'grade':
            groups: dict[tuple[str, str], list[Image]] = defaultdict(list)
            for i in usable:
                if i.patient_id and i.side:
                    groups[(i.patient_id, i.side)].append(i)
            mine = {(g.patient_id, g.side) for g in db.query(GradeLabel).filter(GradeLabel.rater == rater, GradeLabel.is_consensus.is_(False)).all()} if rater else set()
            items = []
            for (pid, side), imgs in sorted(groups.items()):
                imgs.sort(key=lambda x: -(x.sonographer_length_mm or 0))
                items.append({'key': f'{pid}:{side}', 'patient_id': pid, 'side': side, 'images': [_image_view(x) for x in imgs], 'done': (pid, side) in mine})
            return {'task': task, 'items': items[:limit] if limit else items, 'total': len(items)}
        if task == 'mask':
            done = {r[0] for r in db.query(MaskAnnotation.image_id).filter(MaskAnnotation.annotator == rater, MaskAnnotation.status != 'draft', MaskAnnotation.trashed_at.is_(None))} if rater else set()
        else:
            done = {r[0] for r in db.query(ImageLabel.image_id).filter(ImageLabel.kind == task, ImageLabel.annotator == rater)} if rater else set()
        items = [{'key': i.id, 'image': _image_view(i), 'done': i.id in done} for i in usable]
        return {'task': task, 'items': items[:limit] if limit else items, 'total': len(items)}


def item_state(task: str, key: str, rater: str) -> dict[str, Any]:
    """單一項目目前這位標註者的標註（用來在編輯器裡還原）。"""
    if task == 'mask':
        return {'mask': latest_mask(key, rater) or latest_mask(key)}
    if task == 'grade':
        pid, _, side = key.partition(':')
        if side not in ('right', 'left'):
            raise AppError(422, 'BAD_KEY', '回音分級的項目要寫成「病人:側別」，例如 P-0001:right。')
        with session_scope('research') as db:
            row = db.query(GradeLabel).filter(GradeLabel.patient_id == pid, GradeLabel.side == side, GradeLabel.rater == rater, GradeLabel.is_consensus.is_(False)).one_or_none()
            return {'grade': None if row is None else {'grade': row.grade, 'unsure_reason': row.unsure_reason}}
    with session_scope('research') as db:
        row = db.query(ImageLabel).filter(ImageLabel.image_id == key, ImageLabel.kind == task, ImageLabel.annotator == rater).one_or_none()
        return {'label': json.loads(row.value_json) if row else None}
