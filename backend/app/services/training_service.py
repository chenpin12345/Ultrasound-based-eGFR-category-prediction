"""Route-callable facade for durable training operations."""

from __future__ import annotations

from typing import Any


def _manager(manager: Any = None):
    if manager is not None:
        return manager
    from ..workers import get_worker_manager

    return get_worker_manager()


def submit_training(training_job_id: str, *, manager: Any = None) -> str:
    _manager(manager).submit_training(training_job_id)
    return training_job_id


def stop_training(training_job_id: str, *, manager: Any = None) -> bool:
    return bool(_manager(manager).request_stop(training_job_id))


def resume_training(training_job_id: str, *, manager: Any = None) -> str:
    _manager(manager).resume_training(training_job_id)
    return training_job_id


__all__ = ["resume_training", "stop_training", "submit_training"]
