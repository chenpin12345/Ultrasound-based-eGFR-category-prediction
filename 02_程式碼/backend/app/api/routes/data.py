"""匯入、影像、版面範本。"""

from __future__ import annotations

import json
from typing import Any

import cv2
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ...core import audit
from ...core.errors import AppError
from ...core.ids import now_iso
from ...data import deid, importer, storage
from ...data.patients import egfr_group
from ...data.templates import template_dict
from ...db.models_research import Image, LayoutTemplate, MaskAnnotation, Patient
from ...db.session import session_scope
from ...jobs.manager import get_manager
from ...services import settings_store
from ..deps import operator

router = APIRouter(tags=['資料'])


# ---- 匯入 ----
@router.get('/inbox')
def inbox():
    return {'original': importer.original_status(), 'folders': importer.inbox_folders()}


class ImportIn(BaseModel):
    source: str
    folder: str | None = None


@router.post('/imports/preview')
def import_preview(payload: ImportIn):
    return importer.preview(payload.source, payload.folder)


@router.post('/imports', status_code=202)
def start_import(payload: ImportIn, request: Request):
    residual = bool(settings_store.get_all().get('residual_check', True))
    result = importer.start_import(get_manager(), payload.source, payload.folder, operator(request), residual)
    audit.record(operator(request), '開始匯入', 'batch', result['batch_id'], {'source': payload.source})
    return result


@router.get('/imports')
def list_imports():
    return {'batches': importer.list_batches()}


@router.get('/imports/{batch_id}')
def get_import(batch_id: str):
    return importer.batch_report(batch_id)


# ---- 影像 ----
def _image_dict(i: Image, patient: Patient | None = None) -> dict[str, Any]:
    return {
        'id': i.id,
        'batch_id': i.batch_id,
        'patient_id': i.patient_id,
        'machine': i.machine,
        'template_id': i.template_id,
        'width': i.width,
        'height': i.height,
        'side': i.side,
        'side_source': i.side_source,
        'view': i.view,
        'pixel_spacing_mm': i.pixel_spacing_mm,
        'spacing_check': i.spacing_check,
        'sonographer_length_mm': i.sonographer_length_mm,
        'sonographer_width_mm': i.sonographer_width_mm,
        'gain': json.loads(i.scan_params_json or '{}').get('gain'),
        'caliper_pixels': i.caliper_pixels,
        'status': i.status,
        'review_reasons': json.loads(i.review_reasons_json or '[]'),
        'exclude_reason': i.exclude_reason,
        'deid_check': i.deid_check,
        'created_at': i.created_at,
        'egfr_group': egfr_group(patient.egfr) if patient else None,
    }


@router.get('/images')
def list_images(
    status: str | None = None,
    machine: str | None = None,
    side: str | None = None,
    batch_id: str | None = None,
    patient_id: str | None = None,
    unmatched: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=500),
):
    with session_scope('research') as db:
        q = db.query(Image)
        if status:
            q = q.filter(Image.status == status)
        if machine:
            q = q.filter(Image.machine == machine)
        if side:
            q = q.filter(Image.side.is_(None)) if side == 'unknown' else q.filter(Image.side == side)
        if batch_id:
            q = q.filter(Image.batch_id == batch_id)
        if patient_id:
            q = q.filter(Image.patient_id == patient_id)
        if unmatched:
            q = q.filter(Image.patient_id.is_(None))
        total = q.count()
        rows = q.order_by(Image.created_at, Image.id).offset(offset).limit(limit).all()
        patients = {p.id: p for p in db.query(Patient).filter(Patient.id.in_([r.patient_id for r in rows if r.patient_id])).all()}
        return {'total': total, 'images': [_image_dict(r, patients.get(r.patient_id)) for r in rows]}


@router.get('/images/stats')
def image_stats():
    with session_scope('research') as db:
        rows = db.query(Image.machine, Image.width, Image.height, Image.status).all()
    stats: dict[tuple, int] = {}
    for machine, w, h, status in rows:
        stats[(machine, f'{w} × {h}', status)] = stats.get((machine, f'{w} × {h}', status), 0) + 1
    return {'rows': [{'machine': m, 'size': s, 'status': st, 'count': c} for (m, s, st), c in sorted(stats.items())]}


@router.get('/images/{image_id}')
def get_image(image_id: str):
    with session_scope('research') as db:
        i = db.get(Image, image_id)
        if i is None:
            raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像。')
        patient = db.get(Patient, i.patient_id) if i.patient_id else None
        masks = db.query(MaskAnnotation).filter(MaskAnnotation.image_id == image_id, MaskAnnotation.trashed_at.is_(None)).count()
        return {**_image_dict(i, patient), 'mask_versions': masks}


@router.get('/images/{image_id}/file')
def image_file(image_id: str, kind: str = Query('model', pattern='^(model|calc|thumb)$')):
    path = storage.image_path(image_id, kind)
    if not path.exists():
        raise AppError(404, 'FILE_NOT_FOUND', '找不到影像檔。')
    return FileResponse(path, media_type='image/jpeg' if kind == 'thumb' else 'image/png', headers={'Cache-Control': 'private, max-age=3600'})


class ImagePatch(BaseModel):
    status: str | None = Field(default=None, pattern='^(usable|excluded|pending_review)$')
    exclude_reason: str | None = None
    side: str | None = Field(default=None, pattern='^(right|left)$')
    view: str | None = Field(default=None, pattern='^(long|short|oblique)$')


@router.patch('/images/{image_id}')
def patch_image(image_id: str, payload: ImagePatch, request: Request):
    with session_scope('research') as db:
        i = db.get(Image, image_id)
        if i is None:
            raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像。')
        if payload.status:
            if payload.status == 'excluded' and not payload.exclude_reason:
                raise AppError(422, 'REASON_REQUIRED', '排除影像時請選擇原因。')
            i.status = payload.status
            i.exclude_reason = payload.exclude_reason if payload.status == 'excluded' else None
        if payload.side:
            i.side, i.side_source = payload.side, 'manual'
        if payload.view:
            i.view = payload.view
    audit.record(operator(request), '修改影像', 'image', image_id, payload.model_dump(exclude_none=True))
    return {'ok': True}


class BulkPatch(BaseModel):
    image_ids: list[str]
    status: str = Field(pattern='^(usable|excluded)$')
    exclude_reason: str | None = None


@router.post('/images/bulk-status')
def bulk_status(payload: BulkPatch, request: Request):
    if payload.status == 'excluded' and not payload.exclude_reason:
        raise AppError(422, 'REASON_REQUIRED', '排除影像時請選擇原因。')
    with session_scope('research') as db:
        n = (
            db.query(Image)
            .filter(Image.id.in_(payload.image_ids))
            .update({'status': payload.status, 'exclude_reason': payload.exclude_reason if payload.status == 'excluded' else None}, synchronize_session=False)
        )
    audit.record(operator(request), '批次修改影像狀態', 'image', f'{n} 張', {'status': payload.status})
    return {'updated': n}


class BulkSide(BaseModel):
    image_ids: list[str]
    side: str = Field(pattern='^(right|left)$')


@router.post('/images/bulk-side')
def bulk_side(payload: BulkSide, request: Request):
    with session_scope('research') as db:
        n = (
            db.query(Image)
            .filter(Image.id.in_(payload.image_ids))
            .update({'side': payload.side, 'side_source': 'manual'}, synchronize_session=False)
        )
    audit.record(operator(request), '批次設定側別', 'image', f'{n} 張', {'side': payload.side})
    return {'updated': n}


class RedeidIn(BaseModel):
    template_id: str | None = None
    batch_id: str | None = None


@router.post('/images/redeid', status_code=202)
def redeid(payload: RedeidIn, request: Request):
    if not payload.template_id and not payload.batch_id:
        raise AppError(422, 'SCOPE_REQUIRED', '請指定版面範本或匯入批次，避免一次重做全部影像。')
    target = payload.template_id or payload.batch_id
    job_id = get_manager().submit('redeid', payload.model_dump(exclude_none=True), target=f'{target}', created_by=operator(request))
    audit.record(operator(request), '重新去識別化', 'job', job_id, payload.model_dump(exclude_none=True))
    return {'job_id': job_id}


@router.post('/images/reread-side', status_code=202)
def reread_side(request: Request):
    job_id = get_manager().submit('reread_side', {}, target='全部影像', created_by=operator(request))
    audit.record(operator(request), '重新判斷側別', 'job', job_id)
    return {'job_id': job_id}


# ---- 版面範本 ----
@router.get('/templates')
def list_templates():
    with session_scope('research') as db:
        counts: dict[str, int] = {}
        for (tid,) in db.query(Image.template_id).all():
            counts[tid] = counts.get(tid, 0) + 1
        return {'templates': [{**template_dict(t), 'images': counts.get(t.id, 0)} for t in db.query(LayoutTemplate).order_by(LayoutTemplate.id).all()]}


@router.get('/templates/{template_id}')
def get_template(template_id: str):
    with session_scope('research') as db:
        t = db.get(LayoutTemplate, template_id)
        if t is None:
            raise AppError(404, 'TEMPLATE_NOT_FOUND', '找不到這份版面範本。')
        return template_dict(t)


class TemplateIn(BaseModel):
    regions: list[dict[str, Any]]
    readers: dict[str, dict[str, float]]


def _validate_rects(rects: list[dict[str, Any]]) -> None:
    for r in rects:
        for k in ('x', 'y', 'w', 'h'):
            v = r.get(k)
            if not isinstance(v, (int, float)) or v < 0 or v > 100:
                raise AppError(422, 'BAD_RECT', '區域座標必須是 0 到 100 的百分比。')
        if r['x'] + r['w'] > 100.01 or r['y'] + r['h'] > 100.01:
            raise AppError(422, 'BAD_RECT', '區域超出影像範圍。')


@router.put('/templates/{template_id}')
def put_template(template_id: str, payload: TemplateIn, request: Request):
    _validate_rects(payload.regions)
    _validate_rects(list(payload.readers.values()))
    missing = {'header', 'params', 'measure', 'side', 'ruler'} - set(payload.readers)
    if missing:
        raise AppError(422, 'READERS_REQUIRED', '缺少讀取區：' + '、'.join(sorted(missing)))
    with session_scope('research') as db:
        t = db.get(LayoutTemplate, template_id)
        if t is None:
            raise AppError(404, 'TEMPLATE_NOT_FOUND', '找不到這份版面範本。')
        t.regions_json = json.dumps(payload.regions, ensure_ascii=False)
        t.readers_json = json.dumps(payload.readers, ensure_ascii=False)
        t.version += 1
        t.updated_at, t.updated_by = now_iso(), operator(request)
        version = t.version
    audit.record(operator(request), '修改版面範本', 'template', template_id, {'version': version})
    return {'version': version}


@router.get('/templates/{template_id}/samples')
def template_samples(template_id: str, limit: int = Query(6, ge=1, le=12)):
    """範本測試用的樣本：已匯入批次中同尺寸的影像（只回傳 ID）。"""
    with session_scope('research') as db:
        t = db.get(LayoutTemplate, template_id)
        if t is None:
            raise AppError(404, 'TEMPLATE_NOT_FOUND', '找不到這份版面範本。')
        rows = db.query(Image.id).filter(Image.width == t.width, Image.height == t.height).order_by(Image.id).limit(limit).all()
    return {'image_ids': [r[0] for r in rows]}


@router.post('/templates/{template_id}/preview')
def template_preview(template_id: str, payload: TemplateIn, image_id: str = Query(...)):
    """用指定範本處理原圖，回傳「模糊後疊上區域框」的預覽（文字無法辨識），用來確認位置。"""
    _validate_rects(payload.regions)
    bgr = importer.load_original(image_id)
    preview = deid.blurred_preview(bgr, payload.regions, payload.readers)
    ok, buf = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise AppError(500, 'ENCODE_FAILED', '無法產生預覽。')
    return Response(buf.tobytes(), media_type='image/jpeg', headers={'Cache-Control': 'no-store'})
