from __future__ import annotations

import json

from fastapi import APIRouter, Header, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from ...core import audit
from ...core.errors import AppError
from ...db.models_system import Job, JobEvent
from ...db.session import session_scope
from ...jobs.events import event_stream
from ...jobs.manager import HANDLERS, TERMINAL, get_manager
from ..deps import operator

router = APIRouter(tags=['背景工作'])


def _job_dict(job: Job) -> dict:
    return {
        'id': job.id,
        'kind': job.kind,
        'kind_label': HANDLERS[job.kind].label if job.kind in HANDLERS else job.kind,
        'target': job.target,
        'status': job.status,
        'progress': job.progress,
        'message': job.message,
        'error_code': job.error_code,
        'error_message': job.error_message,
        'created_by': job.created_by,
        'created_at': job.created_at,
        'started_at': job.started_at,
        'finished_at': job.finished_at,
        'retry_of': job.retry_of,
        'resumable': HANDLERS[job.kind].resumable if job.kind in HANDLERS else False,
        'result': json.loads(job.result_json or '{}'),
    }


ZONE_KINDS = {
    'egfr': {'train_baseline', 'evaluate_egfr_test'},
    'segmentation': {'nnunet_train', 'mask_set'},
    'grade': set(),
    'clinical': {'clinical_warmup', 'clinical_receive', 'clinical_analysis'},  # 醫師端（M3）
}


def _zones(jobs: list[Job]) -> dict[str, str]:
    """每個工作屬於哪一區（決策 D28）：訓練與固定測試集評估依訓練或模型的任務決定；其他工作屬於「其他」。"""
    from ...db.models_research import TrainingRun
    from ...db.session import session_scope as research_scope

    run_ids = {json.loads(j.config_json or '{}').get('run_id') for j in jobs if j.kind == 'train'}
    with research_scope('research') as db:
        tasks = {r.id: r.task for r in db.query(TrainingRun).filter(TrainingRun.id.in_([r for r in run_ids if r])).all()}
    out = {}
    for j in jobs:
        cfg = json.loads(j.config_json or '{}')
        zone = next((z for z, kinds in ZONE_KINDS.items() if j.kind in kinds), 'other')
        if j.kind == 'train':
            zone = tasks.get(cfg.get('run_id'), 'other')
        elif j.kind == 'evaluate_test':
            zone = str(cfg.get('model_id', '')).split('/', 1)[0] or 'other'
        out[j.id] = zone
    return out


@router.get('/jobs')
def list_jobs(status: str | None = None, zone: str | None = None, limit: int = Query(100, ge=1, le=500)):
    """zone：egfr、segmentation、grade、other（不指定時全部）。"""
    with session_scope('system') as db:
        q = db.query(Job)
        if status:
            q = q.filter(Job.status == status)
        jobs = q.order_by(Job.created_at.desc()).limit(limit if not zone else 2000).all()
        zones = _zones(jobs)
        if zone:
            jobs = [j for j in jobs if zones[j.id] == zone][:limit]
        return {'jobs': [{**_job_dict(j), 'zone': zones[j.id]} for j in jobs]}


class DeleteJobsIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=1000)


@router.post('/jobs/delete')
def delete_jobs(payload: DeleteJobsIn, request: Request):
    """刪除任務紀錄（永久）：只刪已結束的工作；排隊中、執行中的會略過。
    只刪紀錄與事件，不影響工作產生的資料（影像、草稿、訓練結果）。"""
    with session_scope('system') as db:
        ids = [j.id for j in db.query(Job).filter(Job.id.in_(payload.ids)).all() if j.status in TERMINAL]
        if ids:
            db.query(JobEvent).filter(JobEvent.job_id.in_(ids)).delete(synchronize_session=False)
            db.query(Job).filter(Job.id.in_(ids)).delete(synchronize_session=False)
    audit.record(operator(request), '刪除任務紀錄', 'job', f'{len(ids)} 筆', {'ids': ids[:100]})
    return {'deleted': len(ids), 'skipped': len(set(payload.ids)) - len(ids)}


@router.get('/jobs/{job_id}')
def get_job(job_id: str):
    with session_scope('system') as db:
        job = db.get(Job, job_id)
        if job is None:
            raise AppError(404, 'JOB_NOT_FOUND', '找不到這個工作。')
        events = db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.id.desc()).limit(50).all()
        return {
            **_job_dict(job),
            'zone': _zones([job])[job.id],
            'events': [{'id': e.id, 'type': e.type, 'data': json.loads(e.data_json), 'created_at': e.created_at} for e in reversed(events) if e.type != 'progress'],
        }


@router.get('/jobs/{job_id}/events')
async def job_events(job_id: str, after: int | None = None, last_event_id: str | None = Header(default=None)):
    cursor = after
    if cursor is None and last_event_id:
        try:
            cursor = int(last_event_id)
        except ValueError as exc:
            raise AppError(422, 'BAD_CURSOR', 'Last-Event-ID 必須是數字。') from exc
    return StreamingResponse(event_stream(job_id, cursor or 0), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@router.post('/jobs/{job_id}/stop')
def stop(job_id: str, request: Request):
    state = get_manager().stop(job_id)
    audit.record(operator(request), '停止工作', 'job', job_id)
    return {'status': state}


@router.post('/jobs/{job_id}/resume')
def resume(job_id: str, request: Request):
    get_manager().resume(job_id)
    audit.record(operator(request), '恢復工作', 'job', job_id)
    return {'status': 'queued'}


@router.post('/jobs/{job_id}/retry')
def retry(job_id: str, request: Request):
    new_id = get_manager().retry(job_id, operator(request))
    audit.record(operator(request), '重試工作', 'job', job_id, {'new_job': new_id})
    return {'job_id': new_id}
