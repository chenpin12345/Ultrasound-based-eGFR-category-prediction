"""UI workflow endpoints; delegates all numerical operations to existing workers."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Literal

from ...core.config import get_settings
from ...core.errors import AppError
from ...core.security import safe_resolve, relative_path, remove_tree_contained
from ...db.models import Job, uuid_str, utc_now
from ...db.session import get_db
from ...services.workflow_service import (
    SourceRef, InputSources, DerivedDatasetRequest, snapshot_inputs, source_summary, create_derived_dataset, resolve_source,
)
from .jobs import job_out, add_event, _validate_client_config, _apply_runtime_defaults, _attach_registered_models


from pathlib import Path
import json
import math
import io
import asyncio
from fastapi import Request
from fastapi.responses import StreamingResponse
from ...db.session import get_session_factory
from fastapi.responses import Response
from ...core.security import sha256_file
from sqlalchemy import select, func
from ...db.models import Dataset, DatasetSample, ModelRecord, TrainingJob
from ...services.workflow_service import read_rows
from .jobs import _preview_file_url
from ..worker_bridge import get_worker_manager, call_worker

router = APIRouter(tags=["workflow"])

def _display_revision():
    # Compact database state only; progress events remain on the job-specific stream.
    with get_session_factory()() as db:
        jobs = [tuple(row) for row in db.execute(select(Job.id, Job.status, Job.completed_at).order_by(Job.id))]
        datasets = [tuple(row) for row in db.execute(select(Dataset.id, Dataset.updated_at).order_by(Dataset.id))]
        models = [tuple(row) for row in db.execute(select(ModelRecord.id, ModelRecord.updated_at).order_by(ModelRecord.id))]
        training = [tuple(row) for row in db.execute(select(TrainingJob.id, TrainingJob.status, TrainingJob.completed_at).order_by(TrainingJob.id))]
    import hashlib
    return hashlib.sha256(json.dumps([jobs,datasets,models,training],default=str).encode()).hexdigest()

@router.get('/workflow/events')
async def display_events(request: Request):
    async def events():
        previous = None
        while not await request.is_disconnected():
            revision = await asyncio.to_thread(_display_revision)
            if revision != previous:
                yield 'data: ' + json.dumps({'revision':revision}) + '\n\n'
                previous = revision
            else:
                yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store'})

@router.get('/workflow/dashboard-summary')
def dashboard_summary(db: Session = Depends(get_db)):
    active = select(Job.id).where(Job.status.in_(['queued','running','stopping'])).union(
        select(TrainingJob.job_id).where(TrainingJob.status.in_(['queued','running','stopping'])))
    return {'datasets': db.scalar(select(func.count()).select_from(Dataset)) or 0,
            'models': db.scalar(select(func.count()).select_from(ModelRecord)) or 0,
            'active_jobs': db.scalar(select(func.count()).select_from(active.subquery())) or 0}


@router.get("/datasets/{dataset_id}/gallery-results")
def gallery_results(dataset_id: str, sample_ids: str = Query(default="", max_length=8000),
                    job_id: str | None = None, db: Session = Depends(get_db), settings=Depends(get_settings)):
    """Read existing feature-job assets only. Never run inference or recolor files."""
    if not db.get(Dataset, dataset_id):
        raise AppError(404, "DATASET_NOT_FOUND", "找不到資料集。")
    requested = set(filter(None, sample_ids.split(',')))
    if len(requested) > 200:
        raise AppError(422, "TOO_MANY_SAMPLES", "單次最多查詢 200 張。")
    query = select(Job).where(Job.dataset_id == dataset_id, Job.kind == 'features', Job.status == 'completed')
    jobs = db.scalars(query.order_by(Job.completed_at.desc())).all()
    job = next((j for j in jobs if j.id == job_id), None) if job_id else (jobs[0] if jobs else None)
    if job_id and job is None:
        raise AppError(404, "RESULT_VERSION_MISSING", "此資料集沒有指定的已完成特徵工作。")
    versions = [{'id':j.id, 'name':(j.config_json or {}).get('name', j.id), 'created_at':j.completed_at} for j in jobs]
    if job is None:
        return {'job_id':None,'versions':versions,'items':{}}
    workspace = safe_resolve(settings.data_dir, job.workspace_path)
    manifest = workspace / 'handoff.json'
    if not manifest.is_file():
        return {'job_id':job.id,'versions':versions,'items':{},'warning':'此歷史工作缺少可追溯樣本配對。'}
    bundle = json.loads(manifest.read_text(encoding='utf-8'))
    if bundle.get('dataset_id') != dataset_id:
        raise AppError(409, "SOURCE_MISMATCH", "工作與資料集來源不一致。")
    allowed = set(db.scalars(select(DatasetSample.id).where(DatasetSample.dataset_id == dataset_id, DatasetSample.id.in_(requested))))
    csv_file = (job.result_json or {}).get('output_csv')
    if not csv_file or not safe_resolve(settings.data_dir, csv_file).is_file():
        return {'job_id':job.id,'versions':versions,'items':{},'warning':'此結果版本缺少特徵產物，請重新執行特徵工作。'}
    rows = read_rows(safe_resolve(settings.data_dir, csv_file))
    items = {}
    for entry in bundle['entries']:
        sid = entry['sample_id']
        if sid not in allowed:
            continue
        def url(key):
            if not entry.get(key): return None
            path = safe_resolve(settings.data_dir, entry[key])
            if not path.is_relative_to(workspace): return None
            return _preview_file_url(job.id, path.relative_to(workspace).as_posix(), workspace)
        values = rows.get(Path(entry['image']).name, {})
        numeric = {}
        for key in ('Length_px','Entropy','Contrast_Ratio'):
            try: value = float(values.get(key, ''))
            except (TypeError, ValueError): value = None
            numeric[key] = value if value is not None and math.isfinite(value) else None
        items[sid] = {'processed_url':url('image'),'mask_url':url('mask'),'feature_values':numeric,
                      'overlay_source_url':f'/api/datasets/{dataset_id}/gallery-overlay-source/{job.id}/{sid}'}
    return {'job_id':job.id,'versions':versions,'items':items}


@router.get('/datasets/{dataset_id}/gallery-overlay-source/{job_id}/{sample_id}')
def gallery_overlay_source(dataset_id: str, job_id: str, sample_id: str,
                           db: Session = Depends(get_db), settings=Depends(get_settings)):
    """Read-only UNet-coordinate preview. Never resizes a mask or writes an artifact."""
    from PIL import Image
    job = db.get(Job, job_id)
    if not job or job.dataset_id != dataset_id or job.kind != 'features' or job.status != 'completed':
        raise AppError(404, 'RESULT_VERSION_MISSING', '找不到配對結果版本。')
    workspace = safe_resolve(settings.data_dir, job.workspace_path)
    if not (workspace/'handoff.json').is_file():
        raise AppError(404, 'MISSING_ARTIFACT', '缺少此版本的樣本配對。')
    bundle = json.loads((workspace/'handoff.json').read_text(encoding='utf-8'))
    entry = next((e for e in bundle['entries'] if e['sample_id'] == sample_id), None)
    if not entry or bundle.get('dataset_id') != dataset_id:
        raise AppError(404, 'SAMPLE_MISSING', '找不到此版本的樣本。')
    image_path = safe_resolve(settings.data_dir, entry['image'])
    mask_path = safe_resolve(settings.data_dir, entry.get('mask') or '')
    if not image_path.is_relative_to(workspace) or not mask_path.is_relative_to(workspace):
        raise AppError(409, 'SOURCE_MISMATCH', '來源超出工作範圍。')
    if not image_path.is_file() or not mask_path.is_file():
        raise AppError(404, 'MISSING_ARTIFACT', '缺少處理圖或遮罩產物。')
    with Image.open(image_path) as image, Image.open(mask_path) as mask:
        base = image.convert('RGB')
        if base.size != mask.size:
            refs = (job.config_json or {}).get('input_sources', {})
            ref = refs.get('masks') or refs.get('images') or {}
            source_job = db.get(Job, ref.get('id')) if ref.get('kind') == 'job' else None
            if not source_job or source_job.kind != 'masks' or source_job.status != 'completed' or mask.size != (512,512):
                raise AppError(409, 'UNVERIFIED_GEOMETRY', '尺寸不同且無可驗證 UNet 來源，禁止拉伸遮罩。')
            source_workspace = safe_resolve(settings.data_dir, source_job.workspace_path)
            source_manifest = source_workspace/'handoff.json'
            if not source_manifest.is_file() or source_job.dataset_id != dataset_id:
                raise AppError(409, 'SOURCE_MISMATCH', '分割來源缺少可追溯配對。')
            source = json.loads(source_manifest.read_text(encoding='utf-8'))
            original = next((e for e in source['entries'] if e['sample_id'] == sample_id), None)
            preview = next((p for p in (source_job.result_json or {}).get('previews', [])
                            if original and p['name'] == Path(original['image']).name), None)
            if original and preview:
                original['mask'] = relative_path(safe_resolve(source_workspace, preview['mask_file']), settings.data_dir)
            else:
                raise AppError(409, 'SOURCE_MISMATCH', '遮罩缺少分割來源配對。')
            if not original or any(sha256_file(safe_resolve(settings.data_dir, original[k])) != sha256_file(p)
                                   for k,p in [('image',image_path),('mask',mask_path)]):
                raise AppError(409, 'SOURCE_MISMATCH', '影像或遮罩與分割來源不一致。')
            # Matches torchvision Resize((512,512)) on the legacy PIL RGB input.
            base = base.resize((512,512), Image.Resampling.BILINEAR)
        output = io.BytesIO()
        base.save(output, format='PNG')
    return Response(output.getvalue(), media_type='image/png', headers={'Cache-Control':'private, no-store'})


@router.get('/workflow/inference-sources')
def inference_sources(dataset_id: str, db: Session = Depends(get_db), settings=Depends(get_settings)):
    """Only full, completed, dataset-bound and readable feature versions are eligible."""
    from ...services.judgment_service import validate_values
    base = resolve_source(db, settings, SourceRef(kind='dataset', id=dataset_id), verify=False)
    ids = {e['sample_id'] for e in base['entries']}
    candidates = db.scalars(select(Job).where(Job.dataset_id == dataset_id, Job.kind == 'features',
                                             Job.status == 'completed').order_by(Job.completed_at.desc())).all()
    versions = []
    parents = {}
    for job in candidates:
        try:
            workspace = safe_resolve(settings.data_dir, job.workspace_path)
            if not (workspace / 'handoff.json').is_file():
                continue
            bundle = resolve_source(db, settings, SourceRef(kind='job', id=job.id), verify=False)
            if bundle.get('dataset_id') != dataset_id or not bundle.get('has_features') or {e['sample_id'] for e in bundle['entries']} != ids:
                continue
            for entry in bundle['entries']:
                validate_values(entry['metadata'], entry['display_name'], features=True)
                mask = Path(entry.get('mask') or '')
                parent = str(mask.parent)
                if parent not in parents:
                    parents[parent] = safe_resolve(settings.data_dir, parent)
                if not entry.get('mask') or not (parents[parent] / mask.name).is_file():
                    raise ValueError('missing mask')
            versions.append({'id': job.id, 'name': (job.config_json or {}).get('name', job.id),
                             'completed_at': job.completed_at, 'image_count': len(ids)})
        except (AppError, OSError, ValueError, KeyError):
            continue
    return {'versions': versions, 'validation': 'inventory_only_execution_revalidated'}


@router.get('/workflow/judgment-source')
def judgment_source(kind: Literal['dataset', 'job'], id: str, db: Session = Depends(get_db), settings=Depends(get_settings)):
    bundle = resolve_source(db, settings, SourceRef(kind=kind, id=id), verify=False)
    return {'name': bundle['name'], 'items': [{'id': e['sample_id'], 'name': e['display_name'],
            'age': e.get('metadata', {}).get('age'), 'has_diabetes': e.get('metadata', {}).get('has_diabetes')}
            for e in bundle['entries']]}


class WorkflowJobRequest(BaseModel):
    kind: Literal["process", "masks", "features", "inference", "quick_analysis"]
    input_sources: InputSources
    config: dict = Field(default_factory=dict)
    name: str = Field(default="流程工作", min_length=1, max_length=200)


def create_source_job(db, settings, raw):
    try:
        payload = WorkflowJobRequest.model_validate(raw)
    except ValueError as exc:
        raise AppError(422, "INVALID_WORKFLOW_REQUEST", "來源或工作設定格式錯誤。") from exc
    config = dict(payload.config)
    _validate_client_config(config)
    _apply_runtime_defaults(db, config)
    _attach_registered_models(db, payload.kind, config)
    get_worker_manager()
    job_id = uuid_str()
    workspace = safe_resolve(settings.jobs_dir, job_id)
    workspace.mkdir(parents=True, exist_ok=False)
    try:
        bundle, managed = snapshot_inputs(db, settings, payload.input_sources, workspace, payload.kind)
        config.update(managed)
        if payload.kind == 'quick_analysis':
            if config.get('analysis_mode') not in {'mlp', 'image_only'}:
                raise AppError(422, 'INVALID_ANALYSIS_MODE', '請選擇 AI判斷模式。')
            from ...services.judgment_service import prepare_source
            source_job = db.get(Job, payload.input_sources.images.id) if payload.input_sources.images.kind == 'job' else None
            prepare_source(config, bundle, source_job, workspace, settings.data_dir)
        config.update(operation=payload.kind, name=payload.name, input_sources=payload.input_sources.model_dump(exclude_none=True))
        job = Job(id=job_id, dataset_id=bundle.get("dataset_id"), kind=payload.kind, status="queued", progress=0,
                  config_json=config, workspace_path=relative_path(workspace, settings.data_dir))
        db.add(job)
        add_event(db, job_id, "queued", {"status": "queued", "kind": payload.kind})
        db.commit()
    except Exception:
        db.rollback()
        remove_tree_contained(workspace, settings.jobs_dir)
        raise
    try:
        call_worker("submit_job", job_id)
    except Exception as exc:
        job.status = "failed"
        job.error_code = "WORKER_SUBMIT_FAILED"
        job.error_message = "工作排程失敗，請稍後重試。"
        job.completed_at = utc_now()
        db.commit()
        raise AppError(503, "WORKER_SUBMIT_FAILED", job.error_message) from exc
    db.refresh(job)
    return job_out(job)


@router.get("/workflow/source")
def preview_source(kind: Literal["dataset", "job"], id: str = Query(min_length=1, max_length=100),
                   db: Session = Depends(get_db), settings=Depends(get_settings)):
    try:
        ref = SourceRef(kind=kind, id=id)
    except ValueError as exc:
        raise AppError(422, "INVALID_SOURCE", "來源 ID 格式錯誤。") from exc
    return source_summary(db, settings, ref)


@router.post("/datasets/from-results", status_code=201)
def derive_dataset(payload: DerivedDatasetRequest, db: Session = Depends(get_db), settings=Depends(get_settings)):
    return create_derived_dataset(db, settings, payload)
