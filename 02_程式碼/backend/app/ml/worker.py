"""訓練子程序：python -m app.ml.worker <工作ID> <訓練ID>。

結束代碼：0 完成；3 安全停止；其他為失敗（錯誤訊息寫在 train.log）。
"""

from __future__ import annotations

import json
import sys
import time

from ..core.errors import AppError
from ..db.models_research import TrainingRun
from ..db.models_system import Job
from ..db.session import session_scope
from ..jobs.manager import JobContext, StopRequested
from .runs import EXIT_STOPPED


class WorkerContext(JobContext):
    """子程序用的工作狀態：除了停止要求，網站重啟（工作被標成中斷）時也要停下，避免留下孤兒程序。"""

    def __init__(self, job_id: str, run_id: str):
        super().__init__(job_id, {'run_id': run_id}, resume=True)
        self.run_id = run_id

    def should_stop(self) -> bool:
        now = time.monotonic()
        if now - self._last_stop_check >= 1.0:  # 最多每秒查一次資料庫
            self._last_stop_check = now
            with session_scope('system') as db:
                job = db.get(Job, self.job_id)
                self._stop_cached = job is None or bool(job.stop_requested) or job.status not in ('running', 'stopping')
        return self._stop_cached


def main(job_id: str, run_id: str) -> int:
    from .engine import train_run

    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        task, config, version, split = run.task, json.loads(run.config_json), run.dataset_version_id, run.split_id
    ctx = WorkerContext(job_id, run_id)
    try:
        summary = train_run(run_id, task, config, version, split, ctx)
    except StopRequested:
        print('已在安全的位置停止，可以恢復。', flush=True)
        return EXIT_STOPPED
    except AppError as exc:
        print(f'{exc.code}: {exc.message}', flush=True)
        return 2
    print(json.dumps({'mean_best_score': summary.get('mean_best_score')}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
