"""背景工作（改寫自訓練網站 workers/manager.py）。

- 一般工作走 CPU 工作池；需要獨占的工作（訓練、GPU）走單一執行緒，同一時間只跑一個。
- 醫師端的工作（預熱、分析）走自己的單一執行緒佇列，不排在幾小時的訓練後面（M3，D44）。
- 工作與事件先寫進資料庫，網頁重新整理或服務重啟都不會遺失。
- 服務重啟時，執行中的工作標記為「中斷」，排隊中的工作重新排入。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import now_iso, short_uid
from ..core.security import sanitize_public_text
from ..db.models_system import Job, JobEvent
from ..db.session import session_scope

logger = logging.getLogger(__name__)

ACTIVE = {'queued', 'running', 'stopping'}
TERMINAL = {'completed', 'failed', 'stopped', 'interrupted'}


class StopRequested(Exception):
    """工作在安全的位置停止。"""


@dataclass
class HandlerSpec:
    func: Callable[['JobContext'], dict[str, Any]]
    exclusive: bool = False
    resumable: bool = False
    label: str = ''
    pool: str = ''  # 'clinical'＝醫師端佇列；空白依 exclusive 決定


HANDLERS: dict[str, HandlerSpec] = {}
# 工作結束（不論成功與否）後呼叫，例如更新索引；失敗不影響工作本身
FINISH_HOOKS: list[Callable[[str], None]] = []


def register(kind: str, *, exclusive: bool = False, resumable: bool = False, label: str = '', pool: str = ''):
    def wrap(func):
        HANDLERS[kind] = HandlerSpec(func, exclusive, resumable, label or kind, pool)
        return func

    return wrap


def add_event(job_id: str, type_: str, data: dict[str, Any] | None = None) -> None:
    with session_scope('system') as db:
        db.add(JobEvent(job_id=job_id, type=type_, data_json=json.dumps(data or {}, ensure_ascii=False), created_at=now_iso()))


class JobContext:
    def __init__(self, job_id: str, config: dict[str, Any], resume: bool):
        self.job_id = job_id
        self.config = config
        self.resume = resume
        self._last_progress_write = 0.0
        self._last_progress = -1.0
        self._last_stop_check = 0.0
        self._stop_cached = False

    def progress(self, value: float, message: str = '') -> None:
        """寫入進度。節流：最多每 0.5 秒或進度變化 1% 才寫一次，避免資料庫膨脹。"""
        now = time.monotonic()
        value = max(0.0, min(100.0, value))
        if value < 100 and now - self._last_progress_write < 0.5 and abs(value - self._last_progress) < 1:
            return
        self._last_progress_write, self._last_progress = now, value
        with session_scope('system') as db:
            db.query(Job).filter(Job.id == self.job_id).update({'progress': value, 'message': message[:200]})
        add_event(self.job_id, 'progress', {'progress': round(value, 1), 'message': message})

    def event(self, type_: str, data: dict[str, Any] | None = None) -> None:
        add_event(self.job_id, type_, data)

    def should_stop(self) -> bool:
        now = time.monotonic()
        if now - self._last_stop_check >= 1.0:
            self._last_stop_check = now
            with session_scope('system') as db:
                job = db.get(Job, self.job_id)
                self._stop_cached = bool(job and job.stop_requested)
        return self._stop_cached

    def check_stop(self) -> None:
        if self.should_stop():
            raise StopRequested()


class JobManager:
    def __init__(self) -> None:
        settings = get_settings()
        self.cpu = ThreadPoolExecutor(max_workers=max(1, min(settings.cpu_workers, 4)), thread_name_prefix='job-cpu')
        self.exclusive = ThreadPoolExecutor(max_workers=1, thread_name_prefix='job-exclusive')
        self.clinical = ThreadPoolExecutor(max_workers=1, thread_name_prefix='job-clinical')
        self.futures: dict[str, Future] = {}
        self.lock = threading.RLock()

    # ---- 建立與執行 ----
    def submit(self, kind: str, config: dict[str, Any] | None = None, *, target: str = '', created_by: str = '', retry_of: str | None = None) -> str:
        if kind not in HANDLERS:
            raise AppError(400, 'UNKNOWN_JOB_KIND', f'不支援的工作類型：{kind}')
        job_id = f'JOB-{short_uid()}'
        with session_scope('system') as db:
            db.add(
                Job(
                    id=job_id,
                    kind=kind,
                    target=target,
                    status='queued',
                    config_json=json.dumps(config or {}, ensure_ascii=False),
                    created_by=created_by,
                    created_at=now_iso(),
                    retry_of=retry_of,
                )
            )
        add_event(job_id, 'queued', {'kind': kind})
        self._schedule(job_id, kind, resume=False)
        return job_id

    def _schedule(self, job_id: str, kind: str, *, resume: bool) -> None:
        spec = HANDLERS[kind]
        pool = self.clinical if spec.pool == 'clinical' else self.exclusive if spec.exclusive else self.cpu
        with self.lock:
            self.futures[job_id] = pool.submit(self._run, job_id, resume)

    def _run(self, job_id: str, resume: bool) -> None:
        with session_scope('system') as db:
            job = db.get(Job, job_id)
            if job is None or job.status not in {'queued'}:
                return
            if job.stop_requested:
                job.status, job.finished_at = 'stopped', now_iso()
                return
            job.status, job.started_at = 'running', now_iso()
            kind, config = job.kind, json.loads(job.config_json or '{}')
        add_event(job_id, 'started', {'resume': resume})
        ctx = JobContext(job_id, config, resume)
        try:
            result = HANDLERS[kind].func(ctx) or {}
        except StopRequested:
            self._finish(job_id, 'stopped')
            add_event(job_id, 'stopped', {'safe': True})
        except AppError as exc:
            self._finish(job_id, 'failed', code=exc.code, message=exc.message)
            add_event(job_id, 'failed', {'code': exc.code, 'message': exc.message})
        except Exception as exc:  # noqa: BLE001
            logger.exception('job %s failed', job_id)
            message = sanitize_public_text(f'{type(exc).__name__}: {exc}')[:500]
            self._finish(job_id, 'failed', code='JOB_FAILED', message=message)
            add_event(job_id, 'failed', {'code': 'JOB_FAILED', 'message': message})
        else:
            self._finish(job_id, 'completed', result=result)
            add_event(job_id, 'completed', result if isinstance(result, dict) else {})
        finally:
            with self.lock:
                self.futures.pop(job_id, None)
            for hook in FINISH_HOOKS:
                try:
                    hook(job_id)
                except Exception:  # noqa: BLE001
                    logger.warning('工作結束後的處理失敗', exc_info=True)

    def _finish(self, job_id: str, status: str, *, code: str | None = None, message: str | None = None, result: dict | None = None) -> None:
        with session_scope('system') as db:
            job = db.get(Job, job_id)
            if job is None:
                return
            job.status, job.finished_at = status, now_iso()
            job.error_code, job.error_message = code, message
            if result is not None:
                job.result_json = json.dumps(result, ensure_ascii=False)
                job.progress = 100.0

    # ---- 控制 ----
    def stop(self, job_id: str) -> str:
        with session_scope('system') as db:
            job = db.get(Job, job_id)
            if job is None:
                raise AppError(404, 'JOB_NOT_FOUND', '找不到這個工作。')
            if job.status == 'queued':
                job.status, job.stop_requested, job.finished_at = 'stopped', True, now_iso()
                with self.lock:
                    fut = self.futures.pop(job_id, None)
                if fut:
                    fut.cancel()
                result = 'stopped'
            elif job.status == 'running':
                job.status, job.stop_requested = 'stopping', True
                result = 'stopping'
            else:
                raise AppError(409, 'JOB_NOT_ACTIVE', '這個工作沒有在執行。')
        add_event(job_id, 'stop_requested', {'safe': True})
        return result

    def resume(self, job_id: str) -> None:
        with session_scope('system') as db:
            job = db.get(Job, job_id)
            if job is None:
                raise AppError(404, 'JOB_NOT_FOUND', '找不到這個工作。')
            if job.status not in {'stopped', 'interrupted', 'failed'}:
                raise AppError(409, 'JOB_NOT_RESUMABLE', '只有已停止、中斷或失敗的工作可以恢復。')
            if not HANDLERS.get(job.kind, HandlerSpec(lambda c: {})).resumable:
                raise AppError(409, 'JOB_NOT_RESUMABLE', '這類工作不能恢復，請改用重試。')
            job.status, job.stop_requested, job.error_code, job.error_message = 'queued', False, None, None
            kind = job.kind
        add_event(job_id, 'resumed', {})
        self._schedule(job_id, kind, resume=True)

    def retry(self, job_id: str, created_by: str = '') -> str:
        with session_scope('system') as db:
            job = db.get(Job, job_id)
            if job is None:
                raise AppError(404, 'JOB_NOT_FOUND', '找不到這個工作。')
            if job.status in ACTIVE:
                raise AppError(409, 'JOB_ACTIVE', '工作還在執行中。')
            kind, config, target = job.kind, json.loads(job.config_json or '{}'), job.target
        return self.submit(kind, config, target=target, created_by=created_by, retry_of=job_id)

    def recover(self) -> None:
        """服務啟動時：執行中 → 中斷；排隊中 → 重新排入。"""
        requeue: list[tuple[str, str]] = []
        interrupted: list[str] = []
        with session_scope('system') as db:
            for job in db.query(Job).filter(Job.status.in_(ACTIVE)).all():
                if job.status == 'queued' and not job.stop_requested:
                    requeue.append((job.id, job.kind))
                else:
                    job.status, job.finished_at = 'interrupted', now_iso()
                    interrupted.append(job.id)
        for job_id in interrupted:
            add_event(job_id, 'interrupted', {'reason': 'service_restart'})
        for job_id, kind in requeue:
            if kind in HANDLERS:
                self._schedule(job_id, kind, resume=False)

    def wait(self, job_id: str, timeout: float = 120) -> None:
        """測試用：等工作結束。"""
        with self.lock:
            fut = self.futures.get(job_id)
        if fut:
            fut.result(timeout=timeout)

    def shutdown(self, wait: bool = False) -> None:
        self.cpu.shutdown(wait=wait, cancel_futures=True)
        self.exclusive.shutdown(wait=wait, cancel_futures=True)
        self.clinical.shutdown(wait=wait, cancel_futures=True)


_manager: JobManager | None = None


def get_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


def reset_manager(wait: bool = False) -> None:
    """wait=True：等執行中的工作結束（測試用，避免工作在下一個測試的工作區繼續寫入）。"""
    global _manager
    if _manager is not None:
        _manager.shutdown(wait=wait)
    _manager = None
