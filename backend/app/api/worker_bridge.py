from __future__ import annotations

import asyncio
import importlib
import inspect
from typing import Any

from ..core.errors import AppError


def get_worker_manager():
    """Load the worker subsystem only when a mutating job endpoint is used."""
    package_root = __package__.rsplit(".api", 1)[0]
    try:
        module = importlib.import_module(f"{package_root}.workers.manager")
        factory = getattr(module, "get_worker_manager")
        return factory()
    except (ImportError, AttributeError) as exc:
        raise AppError(503, "WORKER_UNAVAILABLE", "背景工作服務尚未就緒。") from exc


def call_worker(method_name: str, *args: Any, **kwargs: Any) -> Any:
    manager = get_worker_manager()
    method = getattr(manager, method_name, None)
    if method is None:
        raise AppError(503, "WORKER_UNAVAILABLE", f"背景工作服務不支援 {method_name}。")
    try:
        result = method(*args, **kwargs)
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result
    except AppError:
        raise
    except Exception as exc:
        raise AppError(503, "WORKER_SUBMIT_FAILED", "背景工作無法排入佇列。") from exc
