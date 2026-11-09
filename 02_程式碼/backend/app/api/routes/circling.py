"""M2.5 醫師圈選：建立批次、匯出、上傳傳回的圈選、檢查、匯入（決策 D16–D21）。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ...annotation import circling
from ...core import audit
from ...services import index
from ..deps import operator

router = APIRouter(tags=['醫師圈選'])


class BatchIn(BaseModel):
    kind: str = Field(pattern='^(test|train|all)$')
    size: int = 100
    note: str = Field(default='', max_length=200)


@router.get('/circling/batches')
def list_batches():
    return {'batches': circling.list_batches(), 'progress': circling.progress()}


@router.post('/circling/batches', status_code=201)
def create_batch(payload: BatchIn, request: Request):
    result = circling.create_batch(payload.kind, payload.size, payload.note, operator(request))
    audit.record(operator(request), '建立醫師圈選批次', 'circling_batch', result['id'], {'kind': payload.kind, 'count': result['count']})
    index.refresh_quietly()
    return result


@router.get('/circling/batches/{batch_id}')
def batch_detail(batch_id: str):
    return circling.batch_detail(batch_id)


class ExportIn(BaseModel):
    include_original: bool = False
    confirm: str = ''


@router.post('/circling/batches/{batch_id}/export', status_code=202)
def export_batch(batch_id: str, payload: ExportIn, request: Request):
    result = circling.start_export(batch_id, payload.include_original, payload.confirm, operator(request))
    audit.record(operator(request), '匯出醫師圈選批次（含原始影像）' if payload.include_original else '匯出醫師圈選批次', 'circling_batch', batch_id, {'include_original': payload.include_original, 'job_id': result['job_id']})
    return result


class UploadIn(BaseModel):
    folder: str = Field(min_length=1, max_length=500)
    circler: str = Field(default='', max_length=40)


@router.post('/circling/batches/{batch_id}/upload', status_code=202)
def upload(batch_id: str, payload: UploadIn, request: Request):
    result = circling.start_upload(batch_id, payload.folder, payload.circler, operator(request))
    audit.record(operator(request), '上傳醫師圈選', 'circling_batch', batch_id, {'circler': payload.circler, 'job_id': result['job_id']})
    return result


class ImportIn(BaseModel):
    item_ids: list[int] | None = None


@router.post('/circling/batches/{batch_id}/import')
def import_batch(batch_id: str, payload: ImportIn, request: Request):
    result = circling.import_batch(batch_id, payload.item_ids, operator(request))
    audit.record(operator(request), '匯入醫師圈選遮罩', 'circling_batch', batch_id, {'imported': result['imported']})
    index.refresh_quietly()
    return result


@router.get('/circling/items/{item_id}/overlay')
def overlay(item_id: int):
    return Response(circling.overlay_png(item_id), media_type='image/png', headers={'Cache-Control': 'no-store'})


class StructuresIn(BaseModel):
    structures: dict[str, str]


@router.patch('/circling/items/{item_id}')
def update_item(item_id: int, payload: StructuresIn, request: Request):
    result = circling.update_structures(item_id, payload.structures)
    audit.record(operator(request), '修改圈選構造狀態', 'circling_item', str(item_id), payload.structures)
    return result


class RejectIn(BaseModel):
    reason: str = Field(default='', max_length=200)


@router.post('/circling/items/{item_id}/reject')
def reject_item(item_id: int, payload: RejectIn, request: Request):
    result = circling.reject_item(item_id, payload.reason)
    audit.record(operator(request), '退回醫師圈選（需重圈）', 'circling_item', str(item_id), {'reason': payload.reason})
    return result


class DetectIn(BaseModel):
    path: str = Field(min_length=1, max_length=500)


@router.post('/circling/colors/detect')
def detect_colors(payload: DetectIn):
    return circling.detect_colors(payload.path)


@router.get('/circling/colors')
def colors():
    return circling.colors_summary()
