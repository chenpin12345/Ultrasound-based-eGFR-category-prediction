"""Database-backed worker entry points.

All database objects are loaded inside worker threads. Heavy ML modules are also
imported only by the selected operation, keeping normal API startup light.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


LOGGER = logging.getLogger(__name__)
TERMINAL_STATES = frozenset({"completed", "failed", "stopped", "interrupted", "cancelled"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_resolve(root: Path, relative: str | Path) -> Path:
    value = Path(relative)
    if value.is_absolute():
        raise ValueError("Absolute paths are not accepted in persisted job configuration.")
    target = (root / value).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Persisted job path leaves its managed root.")
    return target


def _relative(root: Path, path: str | Path) -> str:
    return str(Path(path).resolve().relative_to(root.resolve())).replace("\\", "/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_event(session: Any, job_id: str, event_type: str, data: Mapping[str, Any]) -> None:
    from ..db.models import JobEvent

    payload = dict(data)
    status_by_event = {
        "queued": "queued",
        "started": "running",
        "training_started": "running",
        "progress": "running",
        "training_progress": "running",
        "epoch_completed": "running",
        "completed": "completed",
        "failed": "failed",
        "stopping": "stopping",
        "stopped": "stopped",
        "interrupted": "interrupted",
        "cancelled": "cancelled",
    }
    if status := status_by_event.get(event_type):
        payload.setdefault("status", status)
    session.add(JobEvent(job_id=job_id, event_type=event_type, data_json=payload))


def _set_job_running(manager: Any, job_id: str) -> tuple[dict[str, Any], Path]:
    from ..db.models import Job

    with manager.session_factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status not in {"queued", "interrupted"}:
            raise RuntimeError(f"Job cannot start from status {job.status!r}.")
        workspace_relative = job.workspace_path or f"jobs/{job.id}"
        workspace = _safe_resolve(manager.data_root, workspace_relative)
        workspace.mkdir(parents=True, exist_ok=True)
        job.workspace_path = _relative(manager.data_root, workspace)
        job.status = "running"
        job.progress = 0.0
        job.started_at = _now()
        job.error_code = None
        job.error_message = None
        _append_event(session, job.id, "started", {"kind": job.kind})
        config = dict(job.config_json or {})
        config.setdefault("operation", job.kind)
        session.commit()
        return config, workspace


def _job_progress(manager: Any, job_id: str, current: int, total: int, message: str) -> None:
    from ..db.models import Job

    with manager.session_factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.progress = min(99.9, max(0.0, current / max(1, total) * 100.0))
        _append_event(
            session,
            job_id,
            "progress",
            {"current": current, "total": total, "progress": job.progress, "message": message},
        )
        session.commit()


def _resolve_inputs(manager: Any, config: Mapping[str, Any]) -> list[Path]:
    relative_paths = list(config.get("input_paths") or [])
    if relative_paths:
        paths = [_safe_resolve(manager.data_root, path) for path in relative_paths]
        return [path for path in paths if path.is_file()]
    sample_ids = list(config.get("sample_ids") or [])
    dataset_id = config.get("dataset_id")
    if not sample_ids and not dataset_id:
        return []
    from sqlalchemy import select
    from ..db.models import Dataset, DatasetSample

    with manager.session_factory() as session:
        query = select(DatasetSample)
        if sample_ids:
            query = query.where(DatasetSample.id.in_(sample_ids))
        if dataset_id:
            query = query.where(DatasetSample.dataset_id == str(dataset_id))
        samples = session.scalars(query.order_by(DatasetSample.relative_path)).all()
        datasets: dict[str, Any] = {}
        result: list[Path] = []
        for sample in samples:
            dataset = datasets.get(sample.dataset_id)
            if dataset is None:
                dataset = session.get(Dataset, sample.dataset_id)
                datasets[sample.dataset_id] = dataset
            if dataset is None:
                continue
            dataset_root = _safe_resolve(manager.data_root, dataset.root_path)
            path = _safe_resolve(dataset_root, sample.relative_path)
            if path.is_file():
                result.append(path)
        return result


def _resolve_optional(manager: Any, value: Any, *, model: bool = False, feature: bool = False):
    if not value:
        return None
    root = manager.models_root if model else manager.features_root if feature else manager.data_root
    return _safe_resolve(root, value)


def _resolve_source_overrides(manager: Any, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for step, source in value.items():
        if isinstance(source, (list, tuple)):
            result[str(step)] = [_safe_resolve(manager.data_root, item) for item in source]
        elif source:
            result[str(step)] = _safe_resolve(manager.data_root, source)
    return result


def _result_archive(manager: Any, workspace: Path, *sources: Path) -> str:
    from ..services.artifact_service import create_result_archive

    archive = create_result_archive(workspace, sources)
    return _relative(manager.data_root, archive)


def _dispatch_general(manager: Any, job_id: str, config: Mapping[str, Any], workspace: Path):
    operation = str(config.get("operation") or config.get("kind") or "").lower()
    inputs = _resolve_inputs(manager, config)
    if not inputs:
        raise ValueError("Job has no managed input images.")

    if operation in {"process", "processing"}:
        from ..ml.processing import run_processing_pipeline

        result = run_processing_pipeline(
            inputs,
            workspace / "processing",
            config.get("steps") or ("convert", "crop", "rb", "assort"),
            source_overrides=_resolve_source_overrides(manager, config.get("source_overrides")),
            seed=int(config.get("random_seed", 32008)),
            progress=lambda current, total, message: _job_progress(
                manager, job_id, current, total, message
            ),
        )
        return {
            "operation": "process",
            "output_dir": _relative(manager.data_root, result.output_dir),
            "steps": [
                {
                    **step,
                    "output": _relative(manager.data_root, step["output"]),
                }
                for step in result.steps
            ],
            "warnings": result.warnings,
            "archive_path": _result_archive(manager, workspace, result.output_dir),
        }

    if operation in {"masks", "mask"}:
        from ..ml.segmentation import generate_masks

        model_path = _resolve_optional(manager, config.get("model_path"), model=True)
        if model_path is None or not model_path.is_file():
            raise FileNotFoundError("尚未安裝 UNet 模型。")
        output = workspace / "masks"
        generated = generate_masks(
            inputs,
            source_root=manager.data_root,
            output_root=output,
            model_path=model_path,
            device=config.get("device"),
            refine=bool(config.get("refine", True)),
            progress=lambda current, total, message: _job_progress(
                manager, job_id, current, total, message
            ),
        )
        previews: list[dict[str, str]] = []
        preview_sources = workspace / "previews" / "sources"
        for index, (source, mask) in enumerate(zip(inputs, generated, strict=True), 1):
            try:
                source.relative_to(workspace)
                managed_source = source
            except ValueError:
                # Dataset-backed jobs read outside the job workspace. Keep the
                # preview endpoint workspace-scoped by copying only the source
                # image needed for the result pair.
                preview_sources.mkdir(parents=True, exist_ok=True)
                suffix = source.suffix.lower() if source.suffix else ".jpg"
                managed_source = preview_sources / f"{index:06d}{suffix}"
                shutil.copy2(source, managed_source)
            previews.append(
                {
                    "name": source.name,
                    "source_file": _relative(workspace, managed_source),
                    "mask_file": _relative(workspace, mask),
                }
            )
        return {
            "operation": "masks",
            "output_dir": _relative(manager.data_root, output),
            "files": [_relative(manager.data_root, path) for path in generated],
            "previews": previews,
            "archive_path": _result_archive(manager, workspace, output),
        }

    if operation in {"features", "feature"}:
        from ..ml.features import generate_feature_csv

        output = workspace / "features" / "features.csv"
        report = generate_feature_csv(
            inputs,
            output,
            mask_dir=_resolve_optional(manager, config.get("mask_dir")),
            metadata_csv=_resolve_optional(manager, config.get("metadata_csv")),
            diabetes_excel=_resolve_optional(
                manager,
                config.get("diabetes_excel", "add_HbA1C.xlsx"),
                feature=True,
            ),
            progress=lambda current, total, message: _job_progress(
                manager, job_id, current, total, message
            ),
        )
        payload = report.to_dict()
        payload["output_csv"] = _relative(manager.data_root, report.output_csv)
        archive_path = _result_archive(manager, workspace, report.output_csv)
        return {
            "operation": "features",
            **payload,
            "archive_path": archive_path,
            "download": archive_path,
        }

    if operation in {"inference", "infer"}:
        from ..ml.inference import run_batch_inference

        model_path = _resolve_optional(manager, config.get("model_path"), model=True)
        if model_path is None or not model_path.is_file():
            raise FileNotFoundError("尚未安裝分類模型。")
        report = run_batch_inference(
            inputs,
            model_path=model_path,
            output_dir=workspace / "inference",
            architecture=config.get("architecture"),
            coral=bool(config.get("coral", False)),
            metadata_csv=_resolve_optional(manager, config.get("metadata_csv")),
            device=config.get("device"),
            progress=lambda current, total, message: _job_progress(
                manager, job_id, current, total, message
            ),
        )
        payload = report.to_dict()
        payload["csv"] = _relative(manager.data_root, report.csv_path)
        payload["zip"] = _relative(manager.data_root, report.zip_path)
        return {
            "operation": "inference",
            **payload,
            "archive_path": payload["zip"],
            "download": payload["zip"],
        }

    if operation in {"quick", "quick_analysis", "analysis"}:
        from ..services.analysis_service import run_quick_analysis

        return run_quick_analysis(
            inputs,
            workspace=workspace,
            data_root=manager.data_root,
            models_root=manager.models_root,
            features_root=manager.features_root,
            config=config,
            progress=lambda current, total, message: _job_progress(
                manager, job_id, current, total, message
            ),
        )
    raise ValueError(f"Unsupported job operation: {operation!r}")


def run_persisted_job(manager: Any, job_id: str) -> None:
    from ..db.models import Job

    with manager.session_factory() as session:
        candidate = session.get(Job, job_id)
        evaluation = candidate is not None and candidate.kind == 'evaluation'
    if evaluation:
        from .evaluation_runner import run_evaluation
        run_evaluation(manager, job_id)
        return

    try:
        config, workspace = _set_job_running(manager, job_id)
        result = _dispatch_general(manager, job_id, config, workspace)
        with manager.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = "completed"
            job.progress = 100.0
            job.result_json = result
            job.completed_at = _now()
            _append_event(session, job_id, "completed", result)
            session.commit()
    except Exception as exc:
        LOGGER.exception("Background job %s failed", job_id)
        try:
            with manager.session_factory() as session:
                job = session.get(Job, job_id)
                if job is not None:
                    job.status = "failed"
                    job.error_code = type(exc).__name__.upper()
                    job.error_message = str(exc).replace(str(manager.data_root), "<data>")[:500]
                    job.completed_at = _now()
                    _append_event(
                        session,
                        job_id,
                        "failed",
                        {"code": job.error_code, "message": job.error_message},
                    )
                    session.commit()
        except Exception:
            LOGGER.exception("Could not persist failure for job %s", job_id)


def _training_samples(manager: Any, dataset_id: str):
    from sqlalchemy import select
    from ..db.models import Dataset, DatasetSample
    from ..ml.training import TrainingSample

    with manager.session_factory() as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise KeyError(dataset_id)
        root = _safe_resolve(manager.data_root, dataset.root_path)
        rows = session.scalars(
            select(DatasetSample).where(DatasetSample.dataset_id == dataset_id)
        ).all()
        samples = []
        for row in rows:
            if row.class_index is None or not row.split:
                continue
            split = "val" if str(row.split).lower() in {"validation", "valid"} else str(row.split).lower()
            path = _safe_resolve(root, row.relative_path)
            samples.append(
                TrainingSample(
                    image_path=path,
                    class_index=int(row.class_index),
                    split=split,
                    metadata=dict(row.metadata_json or {}),
                    fold=row.fold,
                    group_id=row.sha256,
                )
            )
        return samples


def _training_event(manager: Any, job_id: str, event_type: str, data: Mapping[str, Any]) -> None:
    with manager.session_factory() as session:
        _append_event(session, job_id, event_type, data)
        session.commit()


def _training_progress(
    manager: Any,
    training_id: str,
    job_id: str,
    epoch: int,
    epochs: int,
    batch: int,
    batches: int,
) -> None:
    from ..db.models import Job, TrainingJob

    with manager.session_factory() as session:
        training = session.get(TrainingJob, training_id)
        job = session.get(Job, job_id)
        if training is None or job is None:
            return
        training.current_epoch = epoch
        training.total_epochs = epochs
        training.current_batch = batch
        training.total_batches = batches
        job.progress = min(99.9, ((epoch - 1) + batch / max(1, batches)) / max(1, epochs) * 100)
        _append_event(
            session,
            job_id,
            "training_progress",
            {
                "epoch": epoch,
                "total_epochs": epochs,
                "batch": batch,
                "total_batches": batches,
                "progress": job.progress,
            },
        )
        session.commit()


def _training_metric(manager: Any, training_id: str, row: Mapping[str, Any]) -> None:
    from sqlalchemy import select
    from ..db.models import TrainingMetric

    with manager.session_factory() as session:
        for split, prefix in (("train", "train"), ("val", "val")):
            metric = session.scalar(
                select(TrainingMetric).where(
                    TrainingMetric.training_job_id == training_id,
                    TrainingMetric.epoch == int(row["epoch"]),
                    TrainingMetric.split == split,
                )
            ) or TrainingMetric(
                training_job_id=training_id,
                epoch=int(row["epoch"]),
                split=split,
            )
            metric.loss = float(row[f"{prefix}_loss"])
            metric.accuracy = float(row[f"{prefix}_accuracy"])
            metric.precision = float(row[f"{prefix}_precision"])
            metric.recall = float(row[f"{prefix}_recall"])
            metric.f1 = float(row[f"{prefix}_f1"])
            metric.learning_rate = float(row["learning_rate"])
            metric.confusion_matrix = row[f"{prefix}_confusion_matrix"]
            session.add(metric)
        session.commit()


def _stop_requested(manager: Any, job_id: str) -> bool:
    from ..db.models import Job

    with manager.session_factory() as session:
        job = session.get(Job, job_id)
        return bool(job is None or job.stop_requested)


def _register_model(manager: Any, training: Any, outcome: Any) -> None:
    from sqlalchemy import select
    from ..db.models import ModelRecord
    from ..ml.contracts import CLASS_COUNT, CLASS_NAMES, IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD, METADATA_FIELDS

    best = outcome.artifact_dir / "best_model.pth"
    metadata = outcome.artifact_dir / "model_metadata.json"
    with manager.session_factory() as session:
        record = session.scalar(
            select(ModelRecord).where(ModelRecord.source_training_job_id == training.id)
        )
        training_config = dict(training.config_json or {})
        registered_architecture = (
            f"coral-{training.architecture}"
            if training_config.get("coral")
            else training.architecture
        )
        values = {
            "name": training.model_name,
            "version": str(training.id),
            "task": "classification",
            "architecture": registered_architecture,
            "class_count": CLASS_COUNT,
            "class_names": [CLASS_NAMES[index] for index in range(CLASS_COUNT)],
            "metadata_columns": list(METADATA_FIELDS),
            "preprocessing": {
                "mode": "RGB",
                "size": list(IMAGE_SIZE),
                "mean": list(IMAGENET_MEAN),
                "std": list(IMAGENET_STD),
            },
            "weights_path": _relative(manager.models_root, best),
            "metadata_path": _relative(manager.models_root, metadata),
            "sha256": _sha256(best),
            "size_bytes": best.stat().st_size,
            "status": "completed",
            "active": False,
            "source_training_job_id": training.id,
        }
        if record is None:
            record = ModelRecord(**values)
            session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
        session.commit()


def run_persisted_training(manager: Any, training_job_id: str) -> None:
    from ..db.models import Job, TrainingJob
    from ..ml.training import TrainingCallbacks, TrainingConfig, TrainingError, train_classifier

    job_id: str | None = None
    try:
        with manager.session_factory() as session:
            training = session.get(TrainingJob, training_job_id)
            if training is None:
                raise KeyError(training_job_id)
            job = session.get(Job, training.job_id)
            if job is None:
                raise KeyError(training.job_id)
            if training.status == "stopped" and job.status == "stopped":
                # A queued future may begin just as request_stop() cancels it.
                # Treat the durable stopped state as authoritative.
                return
            if training.status not in {"queued", "interrupted"}:
                raise RuntimeError(f"Training cannot start from {training.status!r}.")
            job_id = job.id
            job.status = training.status = "running"
            job.started_at = training.started_at = _now()
            job.stop_requested = False
            job.error_code = job.error_message = None
            _append_event(session, job.id, "training_started", {"training_job_id": training.id})
            config_payload = dict(training.config_json or {})
            config_payload.update(
                {
                    "architecture": training.architecture,
                    "device": training.device,
                    # In K-fold mode TrainingJob.total_epochs represents overall
                    # work (folds × epochs), while the persisted config keeps the
                    # per-fold epoch count used by the ML loop.
                    "epochs": config_payload.get("epochs") or training.total_epochs or 10,
                }
            )
            dataset_id = training.dataset_id
            session.commit()
        if str(config_payload.get("architecture", "")).lower() == "unet":
            raise TrainingError(
                "UNet training needs paired segmentation masks, which this classification dataset does not provide."
            )
        samples = _training_samples(manager, dataset_id)
        extra = config_payload.get("extra")
        if isinstance(extra, Mapping):
            for key, value in extra.items():
                config_payload.setdefault(key, value)
        config_payload["random_seed"] = int(
            config_payload.get("random_seed", config_payload.get("seed", 32008))
        )
        scheduler = config_payload.get("scheduler")
        if scheduler in (None, "", "off"):
            config_payload["scheduler"] = "none"
        elif str(scheduler).lower() in {"reduce_on_plateau", "reducelronplateau"}:
            config_payload["scheduler"] = "plateau"
        if config_payload.get("resume_checkpoint"):
            config_payload["resume_checkpoint"] = str(
                _safe_resolve(manager.models_root, config_payload["resume_checkpoint"])
            )
        config = TrainingConfig(
            **{
                key: value
                for key, value in config_payload.items()
                if key in TrainingConfig.__dataclass_fields__
            }
        )
        artifact_dir = manager.models_root / training_job_id
        callbacks = TrainingCallbacks(
            event=lambda event_type, data: _training_event(manager, job_id, event_type, data),
            progress=lambda epoch, epochs, batch, batches: _training_progress(
                manager, training_job_id, job_id, epoch, epochs, batch, batches
            ),
            metric=lambda row: _training_metric(manager, training_job_id, row),
            resource=lambda data: _training_event(manager, job_id, "resource_sample", data),
            should_stop=lambda: _stop_requested(manager, job_id),
        )
        from ..services import checkpoint_provenance
        try:
            provenance_inputs=checkpoint_provenance.capture_inputs(samples)
            provenance_error=None
        except (OSError,ValueError,TypeError):
            provenance_inputs=None
            provenance_error='訓練輸入來源無法完整核實；不宣稱 checkpoint 評估已驗證。'
        outcome = train_classifier(
            config,
            samples,
            artifact_dir,
            dataset_id=dataset_id,
            callbacks=callbacks,
        )
        provenance={'status':'unverified','reason':provenance_error or '工作尚未完成，未建立 checkpoint 來源證據。'}
        if outcome.status=='completed' and provenance_inputs is not None:
            try:
                provenance=checkpoint_provenance.record(outcome,training_job_id,dataset_id,provenance_inputs,checkpoint_provenance.capture_inputs(samples))
            except (OSError,ValueError,TypeError,KeyError):
                provenance={'status':'unverified','reason':'checkpoint 或输入／epoch／fold 來源未通過核對；既有訓練產物保留，不能視為已核實評估。'}
        with manager.session_factory() as session:
            training = session.get(TrainingJob, training_job_id)
            job = session.get(Job, job_id)
            if training is None or job is None:
                return
            training.status = job.status = outcome.status
            training.best_metric = (
                outcome.best_validation_loss if math_is_finite(outcome.best_validation_loss) else None
            )
            training.best_checkpoint_path = (
                _relative(manager.models_root, artifact_dir / "best_model.pth")
                if (artifact_dir / "best_model.pth").exists()
                else None
            )
            training.last_checkpoint_path = (
                _relative(manager.models_root, artifact_dir / "last_checkpoint.pth")
                if (artifact_dir / "last_checkpoint.pth").exists()
                else None
            )
            job.progress = 100.0 if outcome.status == "completed" else job.progress
            job.result_json = {
                "training_job_id": training_job_id,
                "status": outcome.status,
                "metrics": outcome.metrics,
                "artifact_dir": _relative(manager.models_root, artifact_dir),
                "checkpoint_provenance": provenance,
            }
            job.completed_at = training.completed_at = _now()
            _append_event(session, job.id, outcome.status, job.result_json)
            session.commit()
            detached = training
        if outcome.status == "completed":
            _register_model(manager, detached, outcome)
    except Exception as exc:
        LOGGER.exception("Training job %s failed", training_job_id)
        if job_id is None:
            try:
                with manager.session_factory() as session:
                    training = session.get(TrainingJob, training_job_id)
                    job_id = training.job_id if training else None
            except Exception:
                pass
        try:
            with manager.session_factory() as session:
                training = session.get(TrainingJob, training_job_id)
                job = session.get(Job, job_id) if job_id else None
                message = str(exc).replace(str(manager.data_root), "<data>").replace(
                    str(manager.models_root), "<models>"
                )[:500]
                if training is not None:
                    training.status = "failed"
                    training.completed_at = _now()
                if job is not None:
                    job.status = "failed"
                    job.error_code = type(exc).__name__.upper()
                    job.error_message = message
                    job.completed_at = _now()
                    _append_event(
                        session, job.id, "failed", {"code": job.error_code, "message": message}
                    )
                session.commit()
        except Exception:
            LOGGER.exception("Could not persist training failure %s", training_job_id)


def math_is_finite(value: float) -> bool:
    try:
        return value not in (float("inf"), float("-inf")) and value == value
    except TypeError:
        return False
