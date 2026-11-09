"""工作事件的 SSE（改寫自訓練網站 routes/jobs.py 的 event_stream）。

改進：輪詢間隔與心跳分開。原本每 10 秒才查一次，進度最多延遲 10 秒；現在每 1 秒查一次，
沒有新事件時每 10 秒送一次心跳。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

from ..core.config import get_settings
from ..db.models_system import Job, JobEvent
from ..db.session import session_scope
from .manager import TERMINAL


def _fetch(job_id: str, cursor: int) -> tuple[list[tuple[int, str, str, str]], str | None]:
    with session_scope('system') as db:
        rows = (
            db.query(JobEvent.id, JobEvent.type, JobEvent.data_json, JobEvent.created_at)
            .filter(JobEvent.job_id == job_id, JobEvent.id > cursor)
            .order_by(JobEvent.id)
            .limit(200)
            .all()
        )
        job = db.get(Job, job_id)
        return [tuple(r) for r in rows], (job.status if job else None)


async def event_stream(job_id: str, cursor: int) -> AsyncIterator[str]:
    settings = get_settings()
    last_beat = time.monotonic()
    yield 'retry: 3000\n\n'
    while True:
        rows, status = await asyncio.to_thread(_fetch, job_id, cursor)
        for event_id, type_, data, created in rows:
            cursor = event_id
            payload = json.dumps({'id': event_id, 'type': type_, 'data': json.loads(data), 'created_at': created}, ensure_ascii=False)
            yield f'id: {event_id}\nevent: {type_}\ndata: {payload}\n\n'
        if not rows:
            if status is None or (status in TERMINAL):
                yield 'event: end\ndata: {}\n\n'
                return
            if time.monotonic() - last_beat >= settings.sse_heartbeat_seconds:
                last_beat = time.monotonic()
                yield ': heartbeat\n\n'
        await asyncio.sleep(settings.sse_poll_seconds)
