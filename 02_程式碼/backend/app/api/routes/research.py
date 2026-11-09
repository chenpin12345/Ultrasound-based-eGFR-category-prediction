"""病人、切分、資料集版本、標註、臨床回饋、回收桶。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel, Field

from ...annotation import agreement, service as annotation
from ...core import audit
from ...core.errors import AppError
from ...core.ids import now_iso
from ...data import patients, splits, versions
from ...db.models_research import ClinicalFeedback
from ...db.session import session_scope
from ...trash import service as trash
from ..deps import operator

router = APIRouter(tags=['研究資料'])


# ---- 病人 ----
@router.get('/patients')
def list_patients():
    return {'patients': patients.list_patients()}


@router.post('/patients/tables', status_code=201)
async def upload_table(request: Request, file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise AppError(413, 'TABLE_TOO_LARGE', '病人表太大（上限 20 MB）。')
    result = patients.save_table(file.filename or 'table.xlsx', content)
    audit.record(operator(request), '上傳病人表', 'patient_table', result['table_id'], {'rows': result['rows']})
    return result


class TableRef(BaseModel):
    table_id: str


@router.post('/patients/match-preview')
def match_preview(payload: TableRef):
    return patients.preview(payload.table_id)


@router.post('/patients/match')
def match(payload: TableRef, request: Request):
    result = patients.apply(payload.table_id)
    audit.record(operator(request), '病人對照', 'patient_table', payload.table_id, result)
    return result


@router.get('/patients/review')
def review():
    return patients.review_state()


class Resolve(BaseModel):
    table_id: str
    image_ids: list[str]
    row_key: str


@router.post('/patients/review/rematch', status_code=202)
def rematch(request: Request):
    from ...jobs.manager import get_manager

    job_id = get_manager().submit('rematch_patients', {}, target='待確認的病人對照', created_by=operator(request))
    audit.record(operator(request), '重新比對待確認的病人', 'job', job_id)
    return {'job_id': job_id}


@router.post('/patients/review/resolve')
def resolve(payload: Resolve, request: Request):
    pid = patients.resolve(payload.table_id, payload.image_ids, payload.row_key)
    audit.record(operator(request), '人工確認病人對照', 'patient', pid, {'images': len(payload.image_ids)})
    return {'patient_id': pid}


# ---- 切分 ----
class SplitIn(BaseModel):
    seed: int = 42
    folds: int = 5
    test_ratio: float = 0.2
    note: str = ''


@router.get('/splits')
def list_splits():
    return {'splits': splits.list_splits()}


@router.post('/splits/preview')
def split_preview(payload: SplitIn):
    return splits.preview(payload.seed, payload.folds, payload.test_ratio)


@router.post('/splits', status_code=201)
def create_split(payload: SplitIn, request: Request):
    result = splits.create(payload.seed, payload.folds, payload.test_ratio, payload.note, operator(request))
    audit.record(operator(request), '建立資料切分', 'split', result['id'])
    return result


class ExtendIn(BaseModel):
    mode: str = Field(pattern='^(folds|prospective)$')
    note: str = ''


@router.post('/splits/{split_id}/extend', status_code=201)
def extend_split(split_id: str, payload: ExtendIn, request: Request):
    result = splits.extend(split_id, payload.mode, payload.note, operator(request))
    audit.record(operator(request), '增量分配新病人', 'split', result['id'], {'parent': split_id, 'mode': payload.mode})
    return result


@router.get('/splits/{split_id}')
def get_split(split_id: str):
    return splits.detail(split_id)


@router.get('/splits/{split_id}/leakage')
def split_leakage(split_id: str):
    return splits.leakage(split_id)


# ---- 資料集版本 ----
class VersionIn(BaseModel):
    note: str = ''


@router.get('/dataset-versions')
def list_versions():
    return {'versions': versions.list_versions()}


@router.post('/dataset-versions', status_code=201)
def create_version(payload: VersionIn, request: Request):
    result = versions.create(payload.note, operator(request))
    audit.record(operator(request), '凍結資料集版本', 'dataset_version', result['id'])
    return result


# ---- 標註 ----
@router.get('/annotation/tasks')
def tasks():
    return {'tasks': annotation.summary()}


@router.get('/annotation/queue/{task}')
def queue(task: str, rater: str = ''):
    return annotation.queue(task, rater)


@router.get('/annotation/state/{task}/{key}')
def state(task: str, key: str, rater: str = ''):
    return annotation.item_state(task, key, rater)


class MaskIn(BaseModel):
    shapes: list[dict[str, Any]]
    flags: dict[str, Any] = {}
    status: str = 'done'


@router.put('/annotation/masks/{image_id}')
def save_mask(image_id: str, payload: MaskIn, request: Request):
    result = annotation.save_mask(image_id, payload.shapes, operator(request) if operator(request) != '本機' else '', payload.flags, payload.status)
    audit.record(operator(request), '儲存遮罩', 'image', image_id, {'version': result['version']})
    return result


@router.get('/annotation/masks/{image_id}')
def get_masks(image_id: str):
    return {'latest': annotation.latest_mask(image_id), 'history': annotation.mask_history(image_id)}


class GradeIn(BaseModel):
    patient_id: str
    side: str
    grade: int | None = None
    unsure_reason: str | None = None
    rater: str
    image_id: str | None = None


@router.put('/annotation/grades')
def save_grade(payload: GradeIn, request: Request):
    result = annotation.save_grade(payload.patient_id, payload.side, payload.grade, payload.unsure_reason, payload.rater, payload.image_id)
    audit.record(operator(request), '回音分級', 'patient', payload.patient_id, {'side': payload.side, 'rater': payload.rater})
    return result


class LabelIn(BaseModel):
    kind: str
    value: dict[str, Any]


@router.put('/annotation/labels/{image_id}')
def save_label(image_id: str, payload: LabelIn, request: Request):
    name = operator(request)
    return annotation.save_label(image_id, payload.kind, payload.value, name if name != '本機' else '')


@router.get('/annotation/agreement')
def get_agreement():
    return {'report': agreement.latest_report()}


@router.post('/annotation/agreement')
def compute_agreement(request: Request):
    result = agreement.compute_and_save()
    audit.record(operator(request), '計算標註一致性', 'agreement', result['id'])
    return result


# ---- 臨床回饋 ----
@router.get('/feedback')
def list_feedback():
    with session_scope('research') as db:
        rows = db.query(ClinicalFeedback).order_by(ClinicalFeedback.id.desc()).all()
        return {
            'items': [
                {'id': f.id, 'exam_id': f.exam_id, 'item': f.item, 'ai': f.ai_value, 'doctor': f.doctor_value, 'by': f.by, 'created_at': f.created_at, 'decision': f.decision,
                 'kind': f.kind, 'side': f.side, 'image_id': f.image_id, 'reason': f.reason, 'model_id': f.model_id, 'decided_by': f.decided_by, 'decided_at': f.decided_at}
                for f in rows
            ]
        }


@router.post('/feedback/{item_id}/{decision}')
def decide_feedback(item_id: int, decision: str, request: Request):
    if decision not in {'accept', 'reject'}:
        raise AppError(404, 'NOT_FOUND', '不支援的操作。')
    with session_scope('research') as db:
        f = db.get(ClinicalFeedback, item_id)
        if f is None:
            raise AppError(404, 'NOT_FOUND', '找不到這筆回饋。')
        f.decision = '採用' if decision == 'accept' else '不採用'
        f.decided_by, f.decided_at = operator(request), now_iso()
    audit.record(operator(request), f'臨床回饋{"採用" if decision == "accept" else "不採用"}', 'feedback', str(item_id))
    return {'ok': True}


# ---- 回收桶 ----
class TrashIn(BaseModel):
    kind: str
    id: str
    reason: str = ''


@router.get('/trash')
def list_trash(kind: str | None = None):
    return {'groups': trash.list_groups(kind)}


@router.post('/trash', status_code=201)
def move_to_trash(payload: TrashIn, request: Request):
    result = trash.move_to_trash(payload.kind, payload.id, payload.reason, operator(request))
    audit.record(operator(request), '移入回收桶', payload.kind, payload.id)
    return result


@router.post('/trash/{group_id}/restore')
def restore(group_id: str, request: Request):
    from ...services import index

    trash.restore(group_id)
    audit.record(operator(request), '從回收桶還原', 'trash', group_id)
    index.refresh_quietly()
    index.refresh_clinical_quietly()
    return {'ok': True}


class PurgeIn(BaseModel):
    confirm: str


@router.post('/trash/{group_id}/purge')
def purge(group_id: str, payload: PurgeIn, request: Request):
    if payload.confirm != '永久刪除':
        raise AppError(422, 'CONFIRM_REQUIRED', '請輸入「永久刪除」以確認。')
    from ...services import index

    result = trash.purge(group_id)
    audit.record(operator(request), '永久刪除', 'trash', group_id, {'removed': result['removed'][:50]})
    index.refresh_quietly()
    index.refresh_clinical_quietly()
    return {'ok': True, **result}
