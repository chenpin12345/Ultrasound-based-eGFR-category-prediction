from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.config import AppSettings, get_settings
from ...core.errors import AppError
from ...core.security import (
    IMAGE_EXTENSIONS,
    ZipLimits,
    extract_zip_safe,
    relative_path,
    remove_tree_contained,
    safe_resolve,
    sanitize_filename,
    sanitize_public_json,
    sanitize_public_text,
    save_upload_file,
    validate_image,
)
from ...db.models import Dataset, DatasetSample, Job, JobEvent, ModelRecord, utc_now, uuid_str
from ...db.session import get_db, get_session_factory
from ...schemas.common import Page
from ...schemas.job import JobAction, JobCreate
from ...schemas.job import JobOut
from ...services.settings_service import persisted_setting
from ..worker_bridge import call_worker, get_worker_manager

router = APIRouter(prefix="/jobs", tags=["jobs"])
TERMINAL_STATUSES = {"completed", "failed", "stopped", "interrupted"}
ACTIVE_STATUSES = {"queued", "running", "stopping"}
MANAGED_CONFIG_KEYS = {
    "input_paths", "workspace_path", "model_path", "classifier_model_path",
    "unet_model_path", "segmentation_model_path", "mask_model_path",
    "output_path", "archive_path", "metadata_csv", "mask_dir", "feature_csv",
    "source_overrides", "dataset_id", "sample_ids", "operation",
    "selected_model", "selected_segmenter", "judgment_stage",
}


def job_out(job: Job) -> dict:
    return {
        "id": job.id,
        "dataset_id": job.dataset_id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "config_json": sanitize_public_json(job.config_json or {}),
        "result_json": sanitize_public_json(job.result_json),
        "error_code": job.error_code,
        "error_message": sanitize_public_text(job.error_message) if job.error_message else None,
        "stop_requested": job.stop_requested,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def add_event(db: Session, job_id: str, event_type: str, data: dict) -> JobEvent:
    event = JobEvent(job_id=job_id, event_type=event_type, data_json=data)
    db.add(event)
    db.flush()
    return event


def _job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppError(404, "JOB_NOT_FOUND", "找不到指定工作。")
    return job


def _validate_client_config(config: dict) -> None:
    serialized_config = json.dumps(config, ensure_ascii=False)
    if len(serialized_config.encode("utf-8")) > 256 * 1024:
        raise AppError(413, "JOB_CONFIG_TOO_LARGE", "工作設定內容超過限制。")
    for key, value in config.items():
        if isinstance(value, str) and any(token in key.lower() for token in ("path", "dir", "csv", "excel", "checkpoint")):
            candidate = Path(value)
            if candidate.is_absolute() or ".." in candidate.parts or bool(candidate.drive):
                raise AppError(422, "ABSOLUTE_PATH_FORBIDDEN", "瀏覽器設定不可包含絕對或越界路徑。")
    for forbidden in MANAGED_CONFIG_KEYS:
        if forbidden in config:
            raise AppError(422, "MANAGED_PATH_REQUIRED", f"{forbidden} 必須由伺服器管理，不接受瀏覽器路徑。")


def _apply_runtime_defaults(db: Session, config: dict) -> None:
    config.setdefault("random_seed", int(persisted_setting(db, "default_seed", 42)))
    if bool(persisted_setting(db, "gpu_enabled", True)):
        return
    requested_device = str(config.get("device") or "auto").lower()
    if requested_device.startswith("cuda"):
        raise AppError(409, "GPU_DISABLED", "系統設定已停用 GPU。")
    config["device"] = "cpu"


def _attach_registered_models(db: Session, kind: str, config: dict) -> None:
    def snapshot(model: ModelRecord) -> dict:
        metadata_file = safe_resolve(get_settings().models_dir, model.metadata_path)
        manifest = json.loads(metadata_file.read_text(encoding="utf-8-sig"))
        return {"id": model.id, "name": model.name, "sha256": model.sha256, "class_count": model.class_count,
                "class_names": model.class_names, "manifest": manifest}

    def selected(task: str, supplied_id: str | None) -> ModelRecord | None:
        model = db.get(ModelRecord, supplied_id) if supplied_id else db.scalar(
            select(ModelRecord).where(ModelRecord.task == task, ModelRecord.active.is_(True))
        )
        if model and (model.task != task or model.status not in {"ready", "completed"}):
            return None
        return model

    if kind in {"masks", "inference"}:
        model_id = config.pop("model_id", None)
        task = "segmentation" if kind == "masks" else "classification"
        model = selected(task, model_id)
        if not model:
            raise AppError(422, "MODEL_REQUIRED", "請選擇與工作類型相容的模型。")
        config["model_path"] = model.weights_path
        config["architecture"] = model.architecture
        config["coral"] = "coral" in model.architecture.lower()
        config["selected_model"] = snapshot(model)
    elif kind == "quick_analysis":
        mode = config.get('analysis_mode')
        if mode is not None and mode not in {'mlp', 'image_only'}:
            raise AppError(422, 'INVALID_ANALYSIS_MODE', '不支援的分析模式。')
        if mode and not config.get('classifier_model_id'):
            raise AppError(422, 'MODEL_REQUIRED', 'AI判斷需要明確選擇分類模型。')
        classifier = selected("classification", config.pop("classifier_model_id", None))
        segmenter = selected("segmentation", config.pop("unet_model_id", None))
        if not classifier or (mode != 'image_only' and not segmenter):
            raise AppError(422, "MODEL_REQUIRED", "快速分析需要預設 UNet 與分類模型。")
        if mode and (('mlp' in classifier.architecture.lower()) != (mode == 'mlp')):
            raise AppError(422, 'MODEL_MODE_MISMATCH', '模型與分析模式不一致。')
        config["classifier_model_path"] = classifier.weights_path
        config["architecture"] = classifier.architecture
        config["coral"] = "coral" in classifier.architecture.lower()
        config["selected_model"] = snapshot(classifier)
        if segmenter and mode != 'image_only':
            config["unet_model_path"] = segmenter.weights_path
            config["selected_segmenter"] = snapshot(segmenter)


def _create_job(db: Session, payload: JobCreate, settings: AppSettings) -> Job:
    dataset = db.get(Dataset, payload.dataset_id)
    if not dataset:
        raise AppError(404, "DATASET_NOT_FOUND", "找不到指定資料集。")
    if dataset.status != "ready":
        raise AppError(409, "DATASET_NOT_READY", "資料集尚未就緒。")
    get_worker_manager()  # Fail before persistence when the worker subsystem is unavailable.
    config = dict(payload.config)
    _validate_client_config(config)
    _apply_runtime_defaults(db, config)
    requested_ids = config.get("sample_ids")
    sample_query = select(DatasetSample.id).where(DatasetSample.dataset_id == payload.dataset_id)
    if requested_ids:
        sample_query = sample_query.where(DatasetSample.id.in_(list(requested_ids)))
    sample_ids = list(db.scalars(sample_query).all())
    if not sample_ids:
        raise AppError(422, "NO_JOB_SAMPLES", "工作沒有可處理的影像。")
    if requested_ids and len(sample_ids) != len(set(requested_ids)):
        raise AppError(422, "INVALID_SAMPLE_SELECTION", "部分影像不屬於指定資料集。")
    config.update({"dataset_id": payload.dataset_id, "sample_ids": sample_ids, "operation": payload.kind})
    _attach_registered_models(db, payload.kind, config)
    job_id = uuid_str()
    workspace = safe_resolve(settings.jobs_dir, job_id)
    workspace.mkdir(parents=True, exist_ok=False)
    job = Job(
        id=job_id,
        dataset_id=payload.dataset_id,
        kind=payload.kind,
        status="queued",
        progress=0,
        config_json=config,
        workspace_path=relative_path(workspace, settings.data_dir),
    )
    db.add(job)
    add_event(db, job.id, "queued", {"status": "queued", "kind": job.kind})
    db.commit()
    db.refresh(job)
    try:
        call_worker("submit_job", job.id)
    except AppError as exc:
        job.status = "failed"
        job.error_code = exc.code
        job.error_message = exc.message
        job.completed_at = utc_now()
        add_event(db, job.id, "failed", {"status": "failed", "code": exc.code, "message": exc.message})
        db.commit()
        raise
    return job


async def _create_uploaded_job(request: Request, db: Session, settings: AppSettings) -> Job:
    form = await request.form()
    kind = str(form.get("kind") or "").strip().lower()
    if kind == "mask":
        kind = "masks"
    if kind not in {"process", "masks", "features", "inference", "quick_analysis"}:
        raise AppError(422, "INVALID_JOB_KIND", "不支援的工作類型。")
    try:
        raw_config = json.loads(str(form.get("config") or "{}"))
    except (TypeError, ValueError) as exc:
        raise AppError(422, "INVALID_JOB_CONFIG", "工作設定 JSON 格式錯誤。") from exc
    if not isinstance(raw_config, dict):
        raise AppError(422, "INVALID_JOB_CONFIG", "工作設定必須是 JSON object。")
    config = dict(raw_config)
    _validate_client_config(config)
    _apply_runtime_defaults(db, config)
    get_worker_manager()

    job_id = uuid_str()
    workspace = safe_resolve(settings.jobs_dir, job_id)
    input_dir = safe_resolve(workspace, "input")
    workspace.mkdir(parents=True, exist_ok=False)
    input_paths: list[str] = []
    uploaded_total = 0
    original_names: list[str] = []

    async def save_images(field: str, folder: str) -> list[str]:
        nonlocal uploaded_total
        saved: list[str] = []
        uploads = [item for item in form.getlist(field) if getattr(item, "filename", None)]
        if len(uploads) > settings.max_zip_entries:
            raise AppError(413, "UPLOAD_TOO_MANY_FILES", "上傳檔案數量超過限制。")
        for index, upload in enumerate(uploads):
            clean = sanitize_filename(str(upload.filename), f"image-{index}.jpg")
            suffix = Path(clean).suffix.lower()
            if kind == 'quick_analysis' and config.get('analysis_mode') and field == 'files':
                if suffix not in {'.jpg', '.jpeg', '.png', '.jfif'}:
                    raise AppError(422, 'UNSUPPORTED_IMAGE', 'AI判斷僅接受 JPEG、PNG、JFIF 圖片。')
            target = safe_resolve(input_dir, folder, f"{index:06d}-{clean}")
            if suffix == ".zip" and field == "files":
                size, _ = await save_upload_file(upload, target, settings.max_upload_bytes)
                uploaded_total += size
                extracted = extract_zip_safe(
                    target,
                    safe_resolve(input_dir, folder, f"archive-{index:06d}"),
                    ZipLimits(
                        max_entries=settings.max_zip_entries,
                        max_total_bytes=settings.max_zip_uncompressed_bytes,
                        max_entry_bytes=settings.max_zip_entry_bytes,
                        max_ratio=settings.max_zip_compression_ratio,
                    ),
                    IMAGE_EXTENSIONS,
                )
                target.unlink(missing_ok=True)
                for path in extracted:
                    validate_image(path, settings.max_image_pixels)
                    saved.append(relative_path(path, settings.data_dir))
                    original_names.append(path.name)
                continue
            if suffix not in IMAGE_EXTENSIONS:
                await upload.close()
                raise AppError(422, "UNSUPPORTED_IMAGE", "僅接受 JPEG、JFIF、PNG 或 ZIP。")
            size, _ = await save_upload_file(upload, target, settings.max_upload_bytes)
            uploaded_total += size
            validate_image(target, settings.max_image_pixels)
            saved.append(relative_path(target, settings.data_dir))
            if field == 'files':
                original_names.append(clean)
        return saved

    async def save_auxiliary(field: str, filename: str) -> str | None:
        nonlocal uploaded_total
        upload = form.get(field)
        if not getattr(upload, "filename", None):
            return None
        clean = sanitize_filename(str(upload.filename), filename)
        if Path(clean).suffix.lower() != ".csv":
            await upload.close()
            raise AppError(422, "UNSUPPORTED_METADATA", "Metadata／Feature 檔必須是 CSV。")
        target = safe_resolve(input_dir, filename)
        size, _ = await save_upload_file(upload, target, settings.max_metadata_bytes)
        uploaded_total += size
        return relative_path(target, settings.data_dir)

    try:
        input_paths = await save_images("files", "images")
        if not input_paths:
            raise AppError(422, "NO_JOB_IMAGES", "請上傳至少一張有效影像。")
        mask_paths = await save_images("mask_files", "masks")
        metadata_csv = await save_auxiliary("metadata_file", "metadata.csv")
        feature_csv = await save_auxiliary("feature_csv", "features.csv")
        if uploaded_total > settings.max_zip_uncompressed_bytes:
            raise AppError(413, "UPLOAD_TOTAL_TOO_LARGE", "本次上傳總大小超過限制。")
        if mask_paths:
            config["mask_dir"] = relative_path(safe_resolve(input_dir, "masks"), settings.data_dir)
        if metadata_csv:
            config["metadata_csv"] = metadata_csv
        if feature_csv:
            config["metadata_csv"] = feature_csv
            config["feature_csv"] = feature_csv
        overrides: dict[str, list[str]] = {}
        for step in ("convert", "crop", "rb", "assort"):
            values = await save_images(f"override_{step}", f"overrides/{step}")
            if values:
                overrides[step] = values
        if overrides:
            config["source_overrides"] = overrides
        config.update({
            "input_paths": input_paths,
            "operation": kind,
            "name": sanitize_filename(str(form.get("name") or kind), kind),
        })
        _attach_registered_models(db, kind, config)
        if kind == 'inference':
            from ...services.judgment_service import prepare_inference_upload
            prepare_inference_upload(config, input_paths, original_names, workspace, settings.data_dir)
        if kind == 'quick_analysis' and config.get('analysis_mode'):
            if overrides or mask_paths or metadata_csv or feature_csv:
                raise AppError(422, 'JUDGMENT_INPUT_CONFLICT', 'AI判斷使用逐張基本資料，不接受混合其他輸入產物。')
            from ...services.judgment_service import prepare_upload
            prepare_upload(config, input_paths, original_names, workspace, settings.data_dir)
        job = Job(
            id=job_id,
            dataset_id=None,
            kind=kind,
            status="queued",
            progress=0,
            config_json=config,
            workspace_path=relative_path(workspace, settings.data_dir),
        )
        db.add(job)
        add_event(db, job.id, "queued", {"status": "queued", "kind": kind})
        db.commit()
        db.refresh(job)
        try:
            call_worker("submit_job", job.id)
        except Exception as exc:
            job.status = "failed"
            job.error_code = "WORKER_UNAVAILABLE"
            job.error_message = "背景工作無法啟動。"
            add_event(db, job.id, "failed", {"status": "failed", "code": job.error_code, "message": job.error_message})
            db.commit()
            raise AppError(503, "WORKER_UNAVAILABLE", "背景工作無法啟動。") from exc
        return job
    except Exception:
        db.rollback()
        remove_tree_contained(workspace, settings.jobs_dir)
        raise


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
async def create_job(request: Request, db: Session = Depends(get_db), settings: AppSettings = Depends(get_settings)) -> dict:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        return job_out(await _create_uploaded_job(request, db, settings))
    try:
        raw = await request.json()
    except ValueError as exc:
        raise AppError(422, "INVALID_JOB_REQUEST", "工作請求格式錯誤。") from exc
    if isinstance(raw, dict) and "input_sources" in raw:
        from .workflow import create_source_job
        return create_source_job(db, settings, raw)
    try:
        payload = JobCreate.model_validate(raw)
    except Exception as exc:
        raise AppError(422, "INVALID_JOB_REQUEST", "工作請求格式錯誤。") from exc
    return job_out(_create_job(db, payload, settings))


@router.get("")
def list_jobs(
    kind: str | None = None,
    dataset_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    view: str = Query(default='full', pattern='^(full|summary)$'),
    db: Session = Depends(get_db),
) -> dict:
    query = select(Job).where(Job.kind != "training")
    count_query = select(func.count()).select_from(Job).where(Job.kind != "training")
    if kind:
        query, count_query = query.where(Job.kind == kind), count_query.where(Job.kind == kind)
    if dataset_id:
        query, count_query = query.where(Job.dataset_id == dataset_id), count_query.where(Job.dataset_id == dataset_id)
    if status_filter:
        query, count_query = query.where(Job.status == status_filter), count_query.where(Job.status == status_filter)
    total = db.scalar(count_query) or 0
    if view == 'summary':
        # SQLite extracts just the small listing fields; never hydrate all predictions.
        columns = [Job.id, Job.dataset_id, Job.kind, Job.status, Job.progress,
                   Job.created_at, Job.updated_at, Job.started_at, Job.completed_at,
                   Job.error_code, Job.error_message, Job.stop_requested,
                   func.json_extract(Job.config_json, '$.name').label('name'),
                   func.coalesce(func.json_array_length(Job.result_json, '$.items'),
                                 func.json_array_length(Job.result_json, '$.inference.items'),
                                 func.json_extract(Job.result_json, '$.rows'), 0).label('result_count')]
        rows = db.execute(query.with_only_columns(*columns).order_by(Job.created_at.desc()).offset(offset).limit(limit)).mappings()
        return {'items': [sanitize_public_json(dict(row)) for row in rows], 'total': total, 'offset': offset, 'limit': limit}
    items = db.scalars(query.order_by(Job.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [job_out(item) for item in items], "total": total, "offset": offset, "limit": limit}


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), view: str = Query(default='full', pattern='^(full|summary)$')) -> dict:
    job = _job_or_404(db, job_id)
    if view == 'full':
        return job_out(job)
    output = {field: getattr(job, field) for field in ('id','dataset_id','kind','status','progress','error_code','error_message','stop_requested','created_at','updated_at','started_at','completed_at')}
    output['config_json'] = {key:value for key,value in (job.config_json or {}).items() if key not in ('input_paths','basic_metadata','source_overrides')}
    output['result_json'] = None
    return sanitize_public_json(output)


def _action(job_id: str, expected_kind: str, payload: JobAction, db: Session) -> dict:
    job = _job_or_404(db, job_id)
    if job.kind != expected_kind:
        raise AppError(409, "JOB_KIND_MISMATCH", f"此工作不是 {expected_kind} 類型。")
    if job.status not in {"queued", "failed", "stopped", "interrupted"}:
        raise AppError(409, "JOB_NOT_ACTIONABLE", "目前工作狀態無法執行此動作。")
    _validate_client_config(payload.config)
    job.config_json = {**(job.config_json or {}), **payload.config}
    job.status = "queued"
    job.progress = 0
    job.stop_requested = False
    job.error_code = None
    job.error_message = None
    job.completed_at = None
    add_event(db, job.id, "queued", {"status": "queued", "kind": expected_kind})
    db.commit()
    call_worker("submit_job", job.id)
    db.refresh(job)
    return job_out(job)


@router.post("/{job_id}/process", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
def run_process(job_id: str, payload: JobAction, db: Session = Depends(get_db)) -> dict:
    return _action(job_id, "process", payload, db)


@router.post("/{job_id}/masks", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
def run_masks(job_id: str, payload: JobAction, db: Session = Depends(get_db)) -> dict:
    return _action(job_id, "masks", payload, db)


@router.post("/{job_id}/features", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
def run_features(job_id: str, payload: JobAction, db: Session = Depends(get_db)) -> dict:
    return _action(job_id, "features", payload, db)


@router.post("/{job_id}/inference", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
def run_inference(job_id: str, payload: JobAction, db: Session = Depends(get_db)) -> dict:
    return _action(job_id, "inference", payload, db)


def _event_cursor(after: int | None, last_event_id: str | None) -> int:
    if after is not None:
        return after
    if last_event_id:
        try:
            return max(0, int(last_event_id))
        except ValueError as exc:
            raise AppError(422, "INVALID_EVENT_CURSOR", "Last-Event-ID 必須是整數。") from exc
    return 0


async def event_stream(job_id: str, cursor: int, heartbeat: float):
    factory = get_session_factory()
    while True:
        with factory() as db:
            job = db.get(Job, job_id)
            if not job:
                payload = json.dumps({"code": "JOB_NOT_FOUND", "message": "工作已刪除。"}, ensure_ascii=False)
                yield f"event: error\ndata: {payload}\n\n"
                return
            events = db.scalars(
                select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.id > cursor).order_by(JobEvent.id).limit(200)
            ).all()
            terminal = job.status in TERMINAL_STATUSES
        if events:
            for item in events:
                cursor = item.id
                payload = json.dumps(
                    {"id": item.id, "type": item.event_type, "data": sanitize_public_json(item.data_json), "created_at": item.created_at.isoformat()},
                    ensure_ascii=False,
                )
                yield f"id: {item.id}\nevent: {item.event_type}\ndata: {payload}\n\n"
            if terminal:
                return
        elif terminal:
            return
        else:
            yield ": heartbeat\n\n"
        await asyncio.sleep(heartbeat)


@router.get("/{job_id}/events")
def job_events(
    job_id: str,
    after: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
):
    _job_or_404(db, job_id)
    cursor = _event_cursor(after, last_event_id)
    return StreamingResponse(
        event_stream(job_id, cursor, settings.sse_heartbeat_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _preview_file_url(job_id: str, relative_file: object, workspace: Path) -> str | None:
    if not isinstance(relative_file, str) or not relative_file or Path(relative_file).is_absolute():
        return None
    try:
        target = safe_resolve(workspace, relative_file)
    except AppError:
        return None
    if not target.is_file() or target.suffix.lower() not in IMAGE_EXTENSIONS:
        return None
    encoded = "/".join(quote(part, safe="") for part in Path(relative_file).as_posix().split("/"))
    return f"/api/jobs/{quote(job_id, safe='')}/files/{encoded}"


@router.get("/{job_id}/results")
def job_results(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1, le=200),
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    job = _job_or_404(db, job_id)
    if job.status not in TERMINAL_STATUSES:
        raise AppError(409, "JOB_NOT_FINISHED", "工作尚未完成。")
    payload = dict(job.result_json or {})
    if limit is not None:
        nested = 'inference' in payload
        target = dict(payload['inference']) if nested else payload
        all_items = target.get('items', [])
        if isinstance(all_items, list):
            workspace = safe_resolve(settings.data_dir, job.workspace_path)
            manifest = workspace / ('judgment-results.json' if job.kind == 'quick_analysis' else 'handoff.json')
            if manifest.is_file() and job.kind in ('inference','quick_analysis'):
                from ...services.display_cache import display_json
                entries = {Path(e['image']).name:e for e in display_json(manifest).get('entries',[])}
                if any(e.get('class_index') is not None for e in entries.values()):
                    target['evaluation'] = _inference_evaluation(target, entries, job.dataset_id)
            target.update(items=all_items[offset:offset+limit], total=len(all_items), offset=offset, limit=limit)
        if nested:
            payload['inference'] = target
        if isinstance(payload.get('previews'), list):
            previews = payload['previews']
            payload.update(previews=previews[offset:offset+limit], total=len(previews), offset=offset, limit=limit)
    results = sanitize_public_json(payload)
    raw_previews = results.pop("previews", []) if isinstance(results, dict) else []
    workspace = safe_resolve(settings.data_dir, job.workspace_path)
    mask_previews: list[dict[str, str]] = []
    if isinstance(raw_previews, list):
        for item in raw_previews:
            if not isinstance(item, dict):
                continue
            source_url = _preview_file_url(job.id, item.get("source_file"), workspace)
            mask_url = _preview_file_url(job.id, item.get("mask_file"), workspace)
            if source_url and mask_url:
                mask_previews.append(
                    {
                        "name": sanitize_filename(str(item.get("name") or "image")),
                        "source_url": source_url,
                        "mask_url": mask_url,
                    }
                )
    if isinstance(results, dict) and mask_previews:
        results["mask_previews"] = mask_previews
    if job.kind == 'quick_analysis' and (workspace / 'judgment-results.json').is_file():
        bundle = json.loads((workspace / 'judgment-results.json').read_text(encoding='utf-8'))
        entries = {Path(e['image']).name: e for e in bundle['entries']}
        for item in results.get('inference', {}).get('items', []):
            entry = entries.get(item.get('file'))
            if not entry:
                continue
            item['file_name'] = entry['display_name']
            item['metadata'] = entry.get('metadata', {})
            for role, key in [('thumbnail_url', 'original_image'), ('processed_url', 'image'),
                              ('mask_url', 'mask'), ('overlay_url', 'overlay_image')]:
                if entry.get(key):
                    path = safe_resolve(settings.data_dir, entry[key])
                    if path.is_relative_to(workspace):
                        item[role] = _preview_file_url(job.id, path.relative_to(workspace).as_posix(), workspace)
        if limit is None and any(e.get('class_index') is not None for e in entries.values()):
            results['inference']['evaluation'] = _inference_evaluation(results['inference'], entries, job.dataset_id)
    if job.kind == "inference" and isinstance(results, dict) and results.get("items"):
        manifest_path = workspace / "handoff.json"
        if manifest_path.is_file():
            bundle = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = {Path(e["image"]).name: e for e in bundle.get("entries", [])}
            for item in results["items"]:
                entry = entries.get(item.get("file"))
                if not entry:
                    continue
                item["file_name"] = entry.get("display_name") or item["file"]
                path = safe_resolve(settings.data_dir, entry["image"])
                if path.is_relative_to(workspace):
                    item["thumbnail_url"] = _preview_file_url(job.id, path.relative_to(workspace).as_posix(), workspace)
            if limit is None and any(e.get('class_index') is not None for e in entries.values()):
                results["evaluation"] = _inference_evaluation(results, entries, job.dataset_id)
    return {"job_id": job.id, "status": job.status, "results": results}


def _inference_evaluation(results: dict, entries: dict, dataset_id: str | None) -> dict:
    """Display-only aggregation of stored predictions; original labels stay intact."""
    from ...ml.contracts import classification_labels, remap_five_class
    count = int(results.get("class_count", 5))
    labels = results.get("class_names") or list(classification_labels(count).values())
    matrix = [[0] * count for _ in range(count)]
    matched = 0
    for item in results.get("items", []):
        original = entries.get(item.get("file"), {}).get("class_index")
        predicted = item.get("predicted_index")
        if original not in range(5) or predicted not in range(count):
            continue
        truth = remap_five_class(original, count)
        item["evaluation_class_index"] = truth
        item["original_five_class_index"] = original
        matrix[truth][predicted] += 1
        matched += 1
    return {"class_count": count, "class_names": labels, "confusion_matrix": matrix,
            "sample_count": matched, "dataset_id": dataset_id,
            "scope": "本批已標記資料；可能含訓練資料，不是獨立測試，也不是海報重現成績。"}


@router.get("/{job_id}/files/{file_path:path}")
def job_image_file(
    job_id: str,
    file_path: str,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
):
    job = _job_or_404(db, job_id)
    if job.status not in TERMINAL_STATUSES:
        raise AppError(409, "JOB_NOT_FINISHED", "工作尚未完成。")
    if not file_path or Path(file_path).is_absolute():
        raise AppError(400, "UNSAFE_PATH", "檔案路徑超出允許範圍。")
    workspace = safe_resolve(settings.data_dir, job.workspace_path)
    path = safe_resolve(workspace, file_path)
    if path.suffix.lower() not in IMAGE_EXTENSIONS or not path.is_file():
        raise AppError(404, "JOB_IMAGE_MISSING", "找不到指定的工作預覽影像。")
    info = validate_image(path, settings.max_image_pixels)
    return FileResponse(
        path,
        media_type=info.mime_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/{job_id}/download")
def download_job(
    job_id: str,
    format: str | None = Query(default=None, pattern="^(csv|zip)$"),
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
):
    job = _job_or_404(db, job_id)
    result = job.result_json or {}
    archive_path = (
        (result.get("csv") or result.get("output_csv") or result.get('inference', {}).get('csv'))
        if format == "csv"
        else (result.get("archive_path") or result.get("zip") or result.get("download"))
    )
    if not archive_path or Path(str(archive_path)).is_absolute():
        raise AppError(404, "JOB_ARCHIVE_MISSING", "此工作沒有可下載的結果。")
    path = safe_resolve(settings.data_dir, str(archive_path))
    if not path.is_file():
        raise AppError(404, "JOB_ARCHIVE_MISSING", "結果壓縮檔不存在。")
    media_type = "application/zip" if path.suffix.lower() == ".zip" else "text/csv" if path.suffix.lower() == ".csv" else "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=f"job-{job.id}{path.suffix}")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_job(job_id: str, db: Session = Depends(get_db), settings: AppSettings = Depends(get_settings)) -> Response:
    job = _job_or_404(db, job_id)
    if job.status in ACTIVE_STATUSES:
        raise AppError(409, "JOB_ACTIVE", "請先停止工作，再進行刪除。")
    workspace = safe_resolve(settings.data_dir, job.workspace_path)
    trash = safe_resolve(settings.temp_dir, f"deleted-job-{job_id}-{uuid4().hex}")
    if workspace.exists():
        workspace.rename(trash)
    try:
        db.delete(job)
        db.commit()
    except Exception:
        db.rollback()
        if trash.exists() and not workspace.exists():
            trash.rename(workspace)
        raise
    remove_tree_contained(trash, settings.temp_dir)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
