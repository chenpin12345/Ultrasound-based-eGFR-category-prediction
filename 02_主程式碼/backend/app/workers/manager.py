"""Bounded durable background execution for API-created database jobs."""

from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable


class WorkerConfigurationError(RuntimeError):
    pass


def _default_session_factory():
    try:
        from ..db.session import get_session_factory
    except ImportError as exc:
        raise WorkerConfigurationError("Database session factory is unavailable.") from exc
    return get_session_factory()


class WorkerManager:
    """Runs a small CPU pool and a serialized GPU pool.

    HTTP routes persist the Job/TrainingJob first and then call one of the public
    submit methods. Worker state is therefore recoverable from SQLite rather
    than being authoritative in this object.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any] | None = None,
        data_root: str | Path = "data",
        models_root: str | Path = "models",
        features_root: str | Path = "features",
        cpu_workers: int = 2,
    ) -> None:
        self.session_factory = session_factory or _default_session_factory()
        self.data_root = Path(data_root).resolve()
        self.models_root = Path(models_root).resolve()
        self.features_root = Path(features_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.models_root.mkdir(parents=True, exist_ok=True)
        self.features_root.mkdir(parents=True, exist_ok=True)
        self._cpu = ThreadPoolExecutor(max_workers=max(1, min(int(cpu_workers), 4)), thread_name_prefix="isu-cpu")
        self._gpu = ThreadPoolExecutor(max_workers=1, thread_name_prefix="isu-gpu")
        from ..clinical.resources import gpu_lock
        self._gpu_lock = gpu_lock
        self._lock = threading.RLock()
        self._futures: dict[str, Future[Any]] = {}
        self._closed = False
        queued_jobs, queued_training = self._recover_interrupted()
        # Durable queued work survived a clean or unclean service restart and
        # is safe to enqueue again because it never entered the running state.
        for job_id in queued_jobs:
            self.submit_job(job_id)
        for training_id in queued_training:
            self.submit_training(training_id)

    def _recover_interrupted(self) -> tuple[list[str], list[str]]:
        """Mark work abandoned by an earlier process as interrupted."""

        try:
            from sqlalchemy import select
            from ..db.models import Job, JobEvent, TrainingJob
        except ImportError:
            return [], []
        with self.session_factory() as session:
            changed: list[Any] = []
            jobs = session.scalars(
                select(Job).where(Job.status.in_(("running", "stopping")))
            ).all()
            for job in jobs:
                job.status = "interrupted"
                if job.kind == 'evaluation':
                    from ..db.models import EvaluationRecord, utc_now
                    evaluation = session.scalar(select(EvaluationRecord).where(EvaluationRecord.job_id == job.id))
                    if evaluation and evaluation.status in {'queued', 'running'}:
                        evaluation.status = 'interrupted'
                        evaluation.completed_at = utc_now()
                        evaluation.result_json = {'complete_cohort': False, 'reason': '主程式中斷；既有逐筆結果保留，重試建立新評估。'}
                event = JobEvent(job_id=job.id, event_type="interrupted", data_json={"reason": "service_restart"})
                session.add(event)
                changed.append(job)
            training = session.scalars(
                select(TrainingJob).where(TrainingJob.status.in_(("running", "stopping")))
            ).all()
            for item in training:
                item.status = "interrupted"
                artifact_root = (self.models_root / item.id).resolve()
                if artifact_root.is_relative_to(self.models_root):
                    candidates: list[Path] = []
                    state_path = artifact_root / "kfold_state.json"
                    if state_path.is_file():
                        try:
                            state = json.loads(state_path.read_text(encoding="utf-8"))
                            active_fold = int(state.get("active_fold", -1))
                            if active_fold >= 0:
                                candidates.append(
                                    artifact_root
                                    / "folds"
                                    / f"fold-{active_fold + 1}"
                                    / "last_checkpoint.pth"
                                )
                        except (OSError, TypeError, ValueError):
                            pass
                    candidates.append(artifact_root / "last_checkpoint.pth")
                    candidates.extend(
                        sorted(
                            (artifact_root / "folds").glob("fold-*/last_checkpoint.pth")
                            if (artifact_root / "folds").is_dir()
                            else (),
                            key=lambda path: path.stat().st_mtime,
                            reverse=True,
                        )
                    )
                    checkpoint = next(
                        (
                            path.resolve()
                            for path in candidates
                            if path.is_file() and path.resolve().is_relative_to(self.models_root)
                        ),
                        None,
                    )
                    if checkpoint is not None:
                        item.last_checkpoint_path = checkpoint.relative_to(self.models_root).as_posix()
                    best = (artifact_root / "best_model.pth").resolve()
                    if best.is_file() and best.is_relative_to(self.models_root):
                        item.best_checkpoint_path = best.relative_to(self.models_root).as_posix()
                changed.append(item)
            queued_jobs = list(session.scalars(
                select(Job.id).where(Job.status == "queued", Job.kind != "training")
            ).all())
            queued_training = list(session.scalars(
                select(TrainingJob.id).where(TrainingJob.status == "queued")
            ).all())
            if changed:
                session.commit()
            return queued_jobs, queued_training

    def _track(self, key: str, future: Future[Any]) -> None:
        with self._lock:
            if key in self._futures and not self._futures[key].done():
                raise RuntimeError(f"Job is already enqueued: {key}")
            self._futures[key] = future

        def remove(_future: Future[Any]) -> None:
            with self._lock:
                if self._futures.get(key) is _future:
                    self._futures.pop(key, None)

        future.add_done_callback(remove)

    def _uses_gpu_for_job(self, job_id: str) -> bool:
        try:
            from ..db.models import Job
            with self.session_factory() as session:
                job = session.get(Job, job_id)
                config = dict(job.config_json or {}) if job else {}
                from ..clinical.resources import resolve_device
                return resolve_device(config.get("device", "auto")).startswith("cuda")
        except Exception:
            return False

    def _uses_gpu_for_training(self, training_job_id: str) -> bool:
        try:
            from ..db.models import TrainingJob
            with self.session_factory() as session:
                job = session.get(TrainingJob, training_job_id)
                from ..clinical.resources import resolve_device
                return bool(job and resolve_device(job.device).startswith("cuda"))
        except Exception:
            return False

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Worker manager is shut down.")

    def submit_job(self, job_id: str) -> None:
        self._ensure_open()
        from .runner import run_persisted_job

        use_gpu = self._uses_gpu_for_job(job_id)

        def execute() -> None:
            if use_gpu:
                with self._gpu_lock:
                    run_persisted_job(self, job_id)
            else:
                run_persisted_job(self, job_id)

        executor = self._gpu if use_gpu else self._cpu
        future = executor.submit(execute)
        try:
            self._track(f"job:{job_id}", future)
        except Exception:
            future.cancel()
            raise

    def submit_training(self, training_job_id: str) -> None:
        self._ensure_open()
        from .runner import run_persisted_training

        use_gpu = self._uses_gpu_for_training(training_job_id)

        def execute() -> None:
            if use_gpu:
                with self._gpu_lock:
                    run_persisted_training(self, training_job_id)
            else:
                run_persisted_training(self, training_job_id)

        executor = self._gpu if use_gpu else self._cpu
        future = executor.submit(execute)
        try:
            self._track(f"training:{training_job_id}", future)
        except Exception:
            future.cancel()
            raise

    def request_stop(self, training_job_id: str) -> bool:
        from ..db.models import Job, JobEvent, TrainingJob

        with self.session_factory() as session:
            training = session.get(TrainingJob, training_job_id)
            if training is None:
                return False
            job = session.get(Job, training.job_id)
            if job is None or job.status not in {"queued", "running", "stopping"}:
                return False
            job.stop_requested = True
            job.status = "stopping" if job.status == "running" else "stopped"
            training.status = job.status
            session.add(
                JobEvent(job_id=job.id, event_type="stop_requested", data_json={"safe": True})
            )
            session.commit()
            if job.status == "stopped":
                with self._lock:
                    future = self._futures.get(f"training:{training_job_id}")
                if future is not None:
                    future.cancel()
            return True

    def resume_training(self, training_job_id: str) -> None:
        from ..db.models import Job, JobEvent, TrainingJob

        with self.session_factory() as session:
            training = session.get(TrainingJob, training_job_id)
            if training is None:
                raise KeyError(training_job_id)
            job = session.get(Job, training.job_id)
            if job is None:
                raise KeyError(training.job_id)
            if training.status not in {"stopped", "interrupted", "failed"}:
                raise RuntimeError("Only stopped, interrupted or failed training can resume.")
            checkpoint = training.last_checkpoint_path
            if not checkpoint:
                raise RuntimeError("No checkpoint is available for resume.")
            resolved = (self.models_root / checkpoint).resolve()
            if not resolved.is_relative_to(self.models_root) or not resolved.is_file():
                raise RuntimeError("The recorded checkpoint is unavailable.")
            config = dict(training.config_json or {})
            # Persist only a managed-root-relative value.  The worker resolves it
            # immediately before use, so browser-controlled JSON can never smuggle
            # an arbitrary host path into torch.load().
            config["resume_checkpoint"] = str(Path(checkpoint)).replace("\\", "/")
            training.config_json = config
            training.status = "queued"
            job.status = "queued"
            job.stop_requested = False
            job.error_code = None
            job.error_message = None
            session.add(JobEvent(job_id=job.id, event_type="resumed", data_json={}))
            session.commit()
        self.submit_training(training_job_id)

    def shutdown(self, wait: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._cpu.shutdown(wait=wait, cancel_futures=True)
        self._gpu.shutdown(wait=wait, cancel_futures=True)


_manager: WorkerManager | None = None
_manager_lock = threading.Lock()


def configure_worker_manager(**kwargs: Any) -> WorkerManager:
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.shutdown(wait=False)
        _manager = WorkerManager(**kwargs)
        return _manager


def get_worker_manager() -> WorkerManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = WorkerManager()
        return _manager


def worker_startup(**kwargs: Any) -> WorkerManager:
    return configure_worker_manager(**kwargs) if kwargs else get_worker_manager()


def worker_shutdown() -> None:
    global _manager
    with _manager_lock:
        manager, _manager = _manager, None
    if manager is not None:
        manager.shutdown(wait=False)
