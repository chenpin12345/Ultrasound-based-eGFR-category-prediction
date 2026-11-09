"""資料集版本：把目前的影像、病人、標註狀態凍結成 manifest，訓練紀錄會引用版本編號。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_sequential, now_iso
from ..db.models_research import DatasetVersion, GradeLabel, Image, ImageGrade, ImageLabel, MaskAnnotation, Patient
from ..db.session import session_scope


def mask_verified(m: MaskAnnotation) -> bool:
    """人畫的（manual 且完成）或人工確認過的草稿。"""
    return (m.source == 'manual' and m.status in {'done', 'reviewed'}) or bool(m.verified_by)


def load_manifest(version_id: str) -> dict[str, Any]:
    path = get_settings().path('dataset_versions') / version_id / 'manifest.json'
    if not path.exists():
        raise AppError(404, 'VERSION_NOT_FOUND', '找不到這個資料集版本。')
    return json.loads(path.read_text(encoding='utf-8'))


def create(note: str, operator: str) -> dict[str, Any]:
    with session_scope('research') as db:
        images = (
            db.query(Image)
            .filter(Image.status == 'usable', Image.patient_id.isnot(None))
            .order_by(Image.id)
            .all()
        )
        if not images:
            raise AppError(409, 'NOTHING_TO_FREEZE', '沒有可用且已對到病人的影像，無法建立資料集版本。')
        # 每張影像最新的遮罩（草稿也算，退回的不算），並記下來源與是否經人工確認：
        # 訓練可以用草稿，固定測試集的評估只接受人工確認過的遮罩
        latest_mask: dict[str, MaskAnnotation] = {}
        for m in db.query(MaskAnnotation).filter(MaskAnnotation.trashed_at.is_(None), MaskAnnotation.status != 'rejected').order_by(MaskAnnotation.version).all():
            latest_mask[m.image_id] = m
        patient_ids = sorted({i.patient_id for i in images})
        patient_rows = {p.id: p for p in db.query(Patient).filter(Patient.id.in_(patient_ids)).all()}
        labels = [(l.id, l.image_id, l.kind) for l in db.query(ImageLabel).all()]
        grades = [g.id for g in db.query(GradeLabel).all()]
        image_grades = [g.id for g in db.query(ImageGrade).filter(ImageGrade.grade.isnot(None)).all()]
        manifest = {
            'images': [
                {
                    'id': i.id,
                    'sha256': i.sha256,
                    'patient_id': i.patient_id,
                    'side': i.side,
                    'machine': i.machine,
                    'pixel_spacing_mm': i.pixel_spacing_mm,
                    'mask_annotation_id': latest_mask[i.id].id if i.id in latest_mask else None,
                    'mask_source': latest_mask[i.id].source if i.id in latest_mask else None,
                    'mask_verified': bool(i.id in latest_mask and mask_verified(latest_mask[i.id])),
                }
                for i in images
            ],
            'patients': [
                {
                    'id': pid,
                    'egfr': patient_rows[pid].egfr,
                    'age': patient_rows[pid].age,
                    'sex': patient_rows[pid].sex,
                    'has_diabetes': patient_rows[pid].has_diabetes,
                    'has_fatty_liver': patient_rows[pid].has_fatty_liver,
                }
                for pid in patient_ids
                if pid in patient_rows
            ],
            'image_label_ids': [l[0] for l in labels],
            'grade_label_ids': grades,
            'image_grade_ids': image_grades,
        }
        body = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        sha = hashlib.sha256(body.encode()).hexdigest()
        version_id = next_sequential('dsv-', [r[0] for r in db.query(DatasetVersion.id).all()])
        folder = get_settings().path('dataset_versions') / version_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'manifest.json').write_text(
            json.dumps({'id': version_id, 'created_at': now_iso(), 'note': note, 'sha256': sha, **manifest}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        patients = {i.patient_id for i in images}
        db.add(
            DatasetVersion(
                id=version_id,
                note=note,
                image_count=len(images),
                patient_count=len(patients),
                manifest_sha256=sha,
                created_by=operator,
                created_at=now_iso(),
            )
        )
        return {'id': version_id, 'images': len(images), 'patients': len(patients), 'masks': len(latest_mask), 'sha256': sha}


def list_versions() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        return [
            {
                'id': v.id,
                'note': v.note,
                'image_count': v.image_count,
                'patient_count': v.patient_count,
                'sha256': v.manifest_sha256,
                'created_by': v.created_by,
                'created_at': v.created_at,
            }
            for v in db.query(DatasetVersion).filter(DatasetVersion.trashed_at.is_(None)).order_by(DatasetVersion.id.desc()).all()
        ]
