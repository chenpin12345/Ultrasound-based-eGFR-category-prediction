"""醫師端轉入研究（M3-7）。

- 不重新匯入、不重做去識別化：直接帶入醫師端的去識別化影像、側別、像素間距、超音波師量的腎長。
- 研究病人（P-編號）由使用者人工指定；年齡、性別、糖尿病、eGFR 不從醫師端帶過去（eGFR 標籤只從病人表來）。
- 轉入後在研究端是一個新的匯入批次，來源為「醫師端」（source_kind = clinical）；已經在研究端的影像（相同 SHA-256）略過。
- 原始檔仍留在醫師端受限區；研究端的 source_map 指向它（和其他批次一樣只有匯入模組會讀）。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..core.errors import AppError
from ..core.ids import image_id as new_image_id
from ..core.ids import next_dated, now_iso
from ..data import deid, storage
from ..db.models_clinical import ClinicalExam, ClinicalImage
from ..db.models_research import Batch, Image, Patient, SourceMap
from ..db.session import session_scope
from . import exams


def to_research(exam_id: str, patient_id: str, image_ids: list[str], actor: str) -> dict[str, Any]:
    patient_id = (patient_id or '').strip().upper()
    with session_scope('research') as db:
        if db.get(Patient, patient_id) is None:
            raise AppError(422, 'PATIENT_REQUIRED', f'研究端沒有 {patient_id or "（空白）"} 這位病人；請填已存在的 P-編號（病人資料 › 病人表）。')
        known = {s for (s,) in db.query(Image.sha256).all()}
    with session_scope('clinical') as db:
        exam = db.get(ClinicalExam, exam_id)
        if exam is None or exam.trashed_at:
            raise AppError(404, 'EXAM_NOT_FOUND', '找不到這筆檢查。')
        q = db.query(ClinicalImage).filter(ClinicalImage.exam_id == exam_id, ClinicalImage.status == 'ok')
        if image_ids:
            q = q.filter(ClinicalImage.id.in_(image_ids))
        rows = [(i.id, i.sha256, i.side, i.side_source, i.pixel_spacing_mm, i.spacing_source, i.template_id, i.width, i.height, i.raw_relpath, json.loads(i.deid_json or '{}'))
                for i in q.order_by(ClinicalImage.seq).all()]
    todo = [r for r in rows if r[1] not in known]
    if not rows:
        raise AppError(409, 'NOTHING_TO_TRANSFER', '這筆檢查沒有可轉入的影像（版面不符、有殘留或已排除的不轉入）。')
    if not todo:
        raise AppError(409, 'ALREADY_TRANSFERRED', '這些影像都已經在研究端了。')
    with session_scope('research') as db:
        batch_id = next_dated('B', [b for (b,) in db.query(Batch.id).all()])
        db.add(Batch(id=batch_id, source_kind='clinical', source_label=f'醫師端 {exam_id}', status='running', created_by=actor, created_at=now_iso()))
    created = []
    for cid, sha, side, side_source, spacing, spacing_source, template_id, w, h, raw_rel, info in todo:
        new_id = new_image_id()
        model = exams.image_file(exam_id, cid, 'model')
        storage.image_path(new_id, 'model').parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(model, storage.image_path(new_id, 'model'))
        for kind in ('calc', 'thumb'):
            storage.image_path(new_id, kind).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(exams.image_file(exam_id, cid, kind), storage.image_path(new_id, kind))
        gray = deid.read_image(model)
        gray = gray[..., 0] if gray.ndim == 3 else gray
        with session_scope('research') as db:
            db.add(Image(id=new_id, batch_id=batch_id, sha256=sha, phash=deid.phash(gray), machine='', template_id=template_id, width=w, height=h,
                         side=side, side_source='manual' if side_source in ('manual', 'demo_list', 'upload') else side_source, pixel_spacing_mm=spacing,
                         spacing_check='ok' if spacing else 'missing', sonographer_length_mm=info.get('sonographer_length_mm'),
                         caliper_pixels=int(info.get('calipers') or 0), patient_id=patient_id, status='pending_review',
                         review_reasons_json=json.dumps(['由醫師端轉入，請確認側別與病人對照'], ensure_ascii=False), deid_check='pass', created_at=now_iso()))
            db.flush()
            # 原始檔複製一份到研究端的原始封存：醫師端檢查之後被永久刪除時，研究端仍找得到原始檔（重新去識別化要用）
            archived = storage.batch_archive(batch_id) / f'{new_id}{exams.image_suffix(storage.from_root(raw_rel))}'
            archived.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(storage.from_root(raw_rel), archived)
            db.add(SourceMap(image_id=new_id, batch_id=batch_id, original_relpath=storage.relative_to_root(archived)))
        created.append(new_id)
    with session_scope('research') as db:
        b = db.get(Batch, batch_id)
        b.status, b.finished_at = 'completed', now_iso()
        b.counts_json = json.dumps({'imported': len(created), 'pending_review': len(created), 'skipped_known': len(rows) - len(todo)}, ensure_ascii=False)
    exams.log_edit(exam_id, None, 'transfer', None, {'batch_id': batch_id, 'patient_id': patient_id, 'images': len(created)}, '', actor)
    return {'batch_id': batch_id, 'images': len(created), 'skipped': len(rows) - len(todo)}
