from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.config import AppSettings, get_settings
from ...core.errors import AppError
from ...core.security import (
    relative_path,
    remove_tree_contained,
    safe_resolve,
    sanitize_filename,
    sanitize_public_json,
)
from ...core.splitting import deterministic_stratified_split
from ...db.models import Dataset, DatasetSample, Job, JobEvent, TrainingJob, TrainingMetric, uuid_str
from ...db.session import get_db
from ...schemas.common import Page
from ...schemas.job import TrainingCreate
from ...schemas.job import TrainingMetricOut, TrainingOut
from ...services.settings_service import persisted_setting
from ..worker_bridge import call_worker, get_worker_manager
from .jobs import ACTIVE_STATUSES, _event_cursor, add_event, event_stream

router = APIRouter(prefix="/training/jobs", tags=["training"])

TRAINING_ARTIFACT_FILES = {
    "best": ("best_model.pth", "application/octet-stream"),
    "last": ("last_checkpoint.pth", "application/octet-stream"),
    "metadata": ("model_metadata.json", "application/json"),
    "config": ("training_config.json", "application/json"),
    "metrics": ("metrics.json", "application/json"),
    "history": ("history.csv", "text/csv"),
}
MAX_JSON_ARTIFACT_BYTES = 16 * 1024 * 1024


def _training_out(item: TrainingJob) -> dict:
    return {
        "id": item.id,
        "job_id": item.job_id,
        "dataset_id": item.dataset_id,
        "model_name": item.model_name,
        "architecture": item.architecture,
        "status": item.status,
        "config_json": item.config_json or {},
        "device": item.device,
        "current_epoch": item.current_epoch,
        "total_epochs": item.total_epochs,
        "current_batch": item.current_batch,
        "total_batches": item.total_batches,
        "best_metric": item.best_metric,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "started_at": item.started_at,
        "completed_at": item.completed_at,
    }


def _metric_out(item: TrainingMetric) -> dict:
    return {
        "id": item.id,
        "training_job_id": item.training_job_id,
        "epoch": item.epoch,
        "split": item.split,
        "loss": item.loss,
        "accuracy": item.accuracy,
        "precision": item.precision,
        "recall": item.recall,
        "f1": item.f1,
        "learning_rate": item.learning_rate,
        "confusion_matrix": item.confusion_matrix,
        "created_at": item.created_at,
    }


def _training_or_404(db: Session, training_job_id: str) -> TrainingJob:
    item = db.get(TrainingJob, training_job_id)
    if not item:
        raise AppError(404, "TRAINING_JOB_NOT_FOUND", "找不到指定訓練工作。")
    return item


def _resolve_device(requested: str, *, gpu_enabled: bool = True) -> str:
    if not gpu_enabled:
        if requested == "cuda":
            raise AppError(409, "GPU_DISABLED", "系統設定已停用 GPU。")
        return "cpu"
    if requested != "auto":
        if requested == "cuda":
            try:
                import torch
                if not torch.cuda.is_available():
                    raise AppError(409, "CUDA_UNAVAILABLE", "目前環境無可用 CUDA 裝置。")
            except ImportError as exc:
                raise AppError(503, "PYTORCH_UNAVAILABLE", "尚未安裝 PyTorch。") from exc
        return requested
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=TrainingOut)
def create_training(
    payload: TrainingCreate,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    effective_seed = payload.seed
    if "seed" not in payload.model_fields_set:
        effective_seed = int(persisted_setting(db, "default_seed", payload.seed))
    gpu_enabled = bool(persisted_setting(db, "gpu_enabled", True))
    dataset = db.get(Dataset, payload.dataset_id)
    if not dataset:
        raise AppError(404, "DATASET_NOT_FOUND", "找不到指定資料集。")
    if dataset.status != "ready" or dataset.sample_count == 0:
        raise AppError(409, "DATASET_NOT_READY", "資料集尚未就緒或沒有影像。")
    samples = db.scalars(select(DatasetSample).where(DatasetSample.dataset_id == payload.dataset_id)).all()
    labeled = [sample for sample in samples if sample.class_index is not None]
    if not labeled or len(labeled) != len(samples):
        raise AppError(422, "DATASET_UNLABELED", "分類訓練需要每張圖片都有可辨識的五級 eGFR 標籤。")
    if payload.architecture == "mlp-resnet18":
        required = {"age", "Length_px", "Contrast_Ratio", "has_diabetes"}
        missing = sum(not required.issubset(set(sample.metadata_json or {})) for sample in samples)
        if missing:
            raise AppError(
                422,
                "METADATA_INCOMPLETE",
                "MLP-ResNet18 需要完整的 age、Length_px、Contrast_Ratio、has_diabetes metadata。",
                {"missing_samples": missing, "required_fields": sorted(required)},
            )

    assignments = deterministic_stratified_split(
        ((sample.id, sample.class_index, sample.sha256) for sample in samples),
        train_ratio=payload.train_ratio,
        val_ratio=payload.val_ratio,
        test_ratio=payload.test_ratio,
        seed=effective_seed,
        k_folds=payload.k_fold or 0,
    )
    by_id = {assignment.sample_id: assignment for assignment in assignments}
    for sample in samples:
        sample.split = by_id[sample.id].split
        sample.fold = by_id[sample.id].fold
    split_counts = {
        split: sum(by_id[sample.id].split == split for sample in samples)
        for split in ("train", "validation", "test")
    }
    if split_counts["train"] < 2 or split_counts["validation"] < 1:
        raise AppError(
            422,
            "DATASET_SPLIT_TOO_SMALL",
            "資料切割後至少需要 2 張 training 與 1 張 validation 影像。",
            {"splits": split_counts},
        )
    if payload.k_fold:
        cross_validation_pool = [
            sample for sample in samples if by_id[sample.id].split != "test"
        ]
        fold_counts = {
            fold: sum(by_id[sample.id].fold == fold for sample in cross_validation_pool)
            for fold in range(payload.k_fold)
        }
        invalid_folds = [
            fold
            for fold, validation_count in fold_counts.items()
            if validation_count < 1 or len(cross_validation_pool) - validation_count < 2
        ]
        if invalid_folds:
            raise AppError(
                422,
                "K_FOLD_TOO_LARGE",
                "K-fold 資料不足；請降低 fold 數或增加各類別影像。",
                {
                    "fold_counts": fold_counts,
                    "invalid_folds": [fold + 1 for fold in invalid_folds],
                    "cross_validation_samples": len(cross_validation_pool),
                },
            )

    resume_checkpoint = payload.resume_checkpoint
    if resume_checkpoint:
        prior = db.get(TrainingJob, resume_checkpoint)
        if prior and prior.last_checkpoint_path:
            resume_checkpoint = prior.last_checkpoint_path
        checkpoint = Path(resume_checkpoint)
        if checkpoint.is_absolute() or ".." in checkpoint.parts:
            raise AppError(422, "UNSAFE_CHECKPOINT", "續訓 checkpoint 必須是模型庫內的相對路徑。")
        if not safe_resolve(settings.models_dir, checkpoint).is_file():
            raise AppError(422, "CHECKPOINT_MISSING", "指定的續訓 checkpoint 不存在。")

    free_bytes = shutil.disk_usage(settings.models_dir).free
    if free_bytes < max(256 * 1024 * 1024, dataset.total_bytes * 3):
        raise AppError(507, "DISK_SPACE_LOW", "磁碟空間不足，無法安全建立 checkpoint 與訓練產物。")

    device = _resolve_device(payload.device, gpu_enabled=gpu_enabled)
    get_worker_manager()
    training_id = uuid_str()
    job_id = uuid_str()
    workspace = safe_resolve(settings.training_dir, training_id)
    workspace.mkdir(parents=True, exist_ok=False)
    config = payload.model_dump()
    config["seed"] = effective_seed
    config["resume_checkpoint"] = resume_checkpoint
    config["coral"] = payload.classification_mode == "coral"
    config["random_seed"] = effective_seed
    config["split_counts"] = split_counts
    config["device"] = device
    serialized = json.dumps(config, ensure_ascii=False, sort_keys=True)
    for existing in db.scalars(
        select(TrainingJob).where(
            TrainingJob.dataset_id == payload.dataset_id,
            TrainingJob.status.in_(ACTIVE_STATUSES),
        )
    ).all():
        if json.dumps(existing.config_json or {}, ensure_ascii=False, sort_keys=True) == serialized:
            raise AppError(409, "DUPLICATE_TRAINING_JOB", "相同設定的訓練工作已在排隊或執行中。")
    job = Job(
        id=job_id,
        dataset_id=payload.dataset_id,
        kind="training",
        status="queued",
        progress=0,
        config_json=config,
        workspace_path=relative_path(workspace, settings.data_dir),
    )
    training = TrainingJob(
        id=training_id,
        job_id=job_id,
        dataset_id=payload.dataset_id,
        model_name=payload.model_name.strip(),
        architecture=payload.architecture,
        status="queued",
        config_json=config,
        device=device,
        current_epoch=0,
        total_epochs=payload.epochs * (payload.k_fold or 1),
    )
    db.add_all([job, training])
    add_event(db, job.id, "queued", {"status": "queued", "training_job_id": training.id})
    db.commit()
    db.refresh(training)
    try:
        call_worker("submit_training", training.id)
    except AppError as exc:
        job.status = training.status = "failed"
        job.error_code = exc.code
        job.error_message = exc.message
        add_event(db, job.id, "failed", {"status": "failed", "code": exc.code, "message": exc.message})
        db.commit()
        raise
    return _training_out(training)


@router.get("", response_model=Page[TrainingOut])
def list_training(
    status_filter: str | None = Query(default=None, alias="status"),
    dataset_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    query = select(TrainingJob)
    count_query = select(func.count()).select_from(TrainingJob)
    if status_filter:
        query, count_query = query.where(TrainingJob.status == status_filter), count_query.where(TrainingJob.status == status_filter)
    if dataset_id:
        query, count_query = query.where(TrainingJob.dataset_id == dataset_id), count_query.where(TrainingJob.dataset_id == dataset_id)
    total = db.scalar(count_query) or 0
    items = db.scalars(query.order_by(TrainingJob.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [_training_out(item) for item in items], "total": total, "offset": offset, "limit": limit}


@router.get("/{training_job_id}", response_model=TrainingOut)
def get_training(training_job_id: str, db: Session = Depends(get_db)) -> dict:
    return _training_out(_training_or_404(db, training_job_id))


@router.get("/{training_job_id}/events")
def training_events(
    training_job_id: str,
    after: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
):
    item = _training_or_404(db, training_job_id)
    cursor = _event_cursor(after, last_event_id)
    return StreamingResponse(
        event_stream(item.job_id, cursor, settings.sse_heartbeat_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{training_job_id}/stop", status_code=status.HTTP_202_ACCEPTED, response_model=TrainingOut)
def stop_training(training_job_id: str, db: Session = Depends(get_db)) -> dict:
    item = _training_or_404(db, training_job_id)
    if item.status not in ACTIVE_STATUSES:
        raise AppError(409, "TRAINING_NOT_ACTIVE", "訓練目前不在可停止狀態。")
    if not call_worker("request_stop", training_job_id):
        raise AppError(409, "STOP_REJECTED", "工作已結束，無法停止。")
    db.expire_all()
    return _training_out(_training_or_404(db, training_job_id))


@router.post("/{training_job_id}/resume", status_code=status.HTTP_202_ACCEPTED, response_model=TrainingOut)
def resume_training(training_job_id: str, db: Session = Depends(get_db)) -> dict:
    item = _training_or_404(db, training_job_id)
    if item.status not in {"stopped", "interrupted", "failed"}:
        raise AppError(409, "TRAINING_NOT_RESUMABLE", "只有已停止、中斷或失敗的訓練可續訓。")
    if not item.last_checkpoint_path:
        raise AppError(409, "CHECKPOINT_MISSING", "此訓練沒有可用 checkpoint。")
    call_worker("resume_training", training_job_id)
    db.expire_all()
    return _training_out(_training_or_404(db, training_job_id))


@router.get("/{training_job_id}/metrics", response_model=None)
def training_metrics(
    training_job_id: str,
    after_epoch: int = Query(default=-1, ge=-1),
    split: str | None = None,
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict | Response:
    _training_or_404(db, training_job_id)
    query = select(TrainingMetric).where(
        TrainingMetric.training_job_id == training_job_id,
        TrainingMetric.epoch > after_epoch,
    )
    if split:
        query = query.where(TrainingMetric.split == split)
    metrics = db.scalars(query.order_by(TrainingMetric.epoch, TrainingMetric.split)).all()
    items = [_metric_out(item) for item in metrics]
    if not download:
        return {"training_job_id": training_job_id, "items": items}

    output = io.StringIO(newline="")
    fieldnames = [
        "id", "training_job_id", "epoch", "split", "loss", "accuracy",
        "precision", "recall", "f1", "learning_rate", "confusion_matrix", "created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    for row in items:
        csv_row = dict(row)
        csv_row["confusion_matrix"] = (
            json.dumps(csv_row["confusion_matrix"], ensure_ascii=False, separators=(",", ":"))
            if csv_row["confusion_matrix"] is not None
            else ""
        )
        csv_row["created_at"] = csv_row["created_at"].isoformat()
        writer.writerow(csv_row)
    filename = sanitize_filename(f"training-{training_job_id}-metrics.csv")
    return Response(
        content=("\ufeff" + output.getvalue()).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{training_job_id}/artifacts")
def training_artifacts(
    training_job_id: str,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    item = _training_or_404(db, training_job_id)
    artifact_dir = safe_resolve(settings.models_dir, item.id)
    artifacts = []
    for kind, (filename, media_type) in TRAINING_ARTIFACT_FILES.items():
        path = safe_resolve(artifact_dir, filename)
        if path.is_file():
            artifacts.append({
                "kind": kind,
                "filename": filename,
                "media_type": media_type,
                "size_bytes": path.stat().st_size,
                "download_url": f"/api/training/jobs/{item.id}/artifacts/{kind}",
            })
    event_count = db.scalar(
        select(func.count()).select_from(JobEvent).where(JobEvent.job_id == item.job_id)
    ) or 0
    if event_count:
        artifacts.append({
            "kind": "events",
            "filename": "events.json",
            "media_type": "application/json",
            "event_count": event_count,
            "download_url": f"/api/training/jobs/{item.id}/artifacts/events",
        })
    return {"training_job_id": item.id, "items": artifacts}


@router.get("/{training_job_id}/artifacts/{kind}")
def download_training_artifact(
    training_job_id: str,
    kind: str,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
):
    item = _training_or_404(db, training_job_id)
    if kind == "events":
        events = db.scalars(
            select(JobEvent).where(JobEvent.job_id == item.job_id).order_by(JobEvent.id)
        ).all()
        if not events:
            raise AppError(404, "ARTIFACT_NOT_FOUND", "找不到指定訓練產物。")
        payload = sanitize_public_json({
            "training_job_id": item.id,
            "job_id": item.job_id,
            "events": [
                {
                    "id": event.id,
                    "event_type": event.event_type,
                    "data": event.data_json or {},
                    "created_at": event.created_at.isoformat(),
                }
                for event in events
            ],
        })
        filename = sanitize_filename(f"training-{item.id}-events.json")
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    specification = TRAINING_ARTIFACT_FILES.get(kind)
    if specification is None:
        raise AppError(404, "ARTIFACT_NOT_FOUND", "找不到指定訓練產物。")
    stored_filename, media_type = specification
    artifact_dir = safe_resolve(settings.models_dir, item.id)
    path = safe_resolve(artifact_dir, stored_filename)
    if not path.is_file():
        raise AppError(404, "ARTIFACT_NOT_FOUND", "訓練產物檔案不存在。")
    suffix = Path(stored_filename).suffix
    download_name = sanitize_filename(f"training-{item.id}-{kind}{suffix}")
    if media_type == "application/json":
        if path.stat().st_size > MAX_JSON_ARTIFACT_BYTES:
            raise AppError(413, "ARTIFACT_TOO_LARGE", "JSON 訓練產物超過安全下載限制。")
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                payload = sanitize_public_json(json.load(handle))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise AppError(409, "ARTIFACT_INVALID", "JSON 訓練產物格式無效。") from exc
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
        )
    return FileResponse(path, media_type=media_type, filename=download_name)


@router.delete("/{training_job_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_training(
    training_job_id: str,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
) -> Response:
    item = _training_or_404(db, training_job_id)
    if item.status in ACTIVE_STATUSES:
        raise AppError(409, "TRAINING_ACTIVE", "請先停止訓練，再進行刪除。")
    parent = db.get(Job, item.job_id)
    workspace = safe_resolve(settings.data_dir, parent.workspace_path) if parent else None
    trash = safe_resolve(settings.temp_dir, f"deleted-training-{training_job_id}-{uuid4().hex}")
    if workspace and workspace.exists():
        workspace.rename(trash)
    try:
        if parent:
            db.delete(parent)
        else:
            db.delete(item)
        db.commit()
    except Exception:
        db.rollback()
        if workspace and trash.exists() and not workspace.exists():
            trash.rename(workspace)
        raise
    remove_tree_contained(trash, settings.temp_dir)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
