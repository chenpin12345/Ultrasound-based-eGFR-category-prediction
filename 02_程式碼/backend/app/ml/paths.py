"""訓練、模型庫、評估的資料夾位置（決策 D29）。

依任務分資料夾，並在 ID 後面加上名稱，在檔案總管裡不用打開就知道是什麼：
04_模型/01_訓練紀錄/{eGFR|分割|回音分級}/{RUN-ID}_{名稱}/
04_模型/02_模型庫/{eGFR|分割|回音分級}/{名稱}@{版本}/
04_模型/03_評估/{eGFR|分割|回音分級}/{EVAL-ID}_{對象}/

已存在的資料夾一律以資料庫的 relpath 為準，所以搬移資料夾後只要更新 relpath。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..data.storage import slug
from ..db.models_research import Evaluation, TrainingRun
from ..db.session import session_scope

TASK_FOLDERS = {'egfr': 'eGFR', 'segmentation': '分割', 'grade': '回音分級'}


def task_folder(task: str) -> str:
    return TASK_FOLDERS.get(task, task)


def _labelled(identifier: str, label: str) -> str:
    text = slug(label) if label and label != identifier else ''
    return f'{identifier}_{text}' if text else identifier


def new_run_dir(run_id: str, task: str, name: str) -> Path:
    return get_settings().path('models') / '01_訓練紀錄' / task_folder(task) / _labelled(run_id, name)


def run_dir(run_id: str) -> Path:
    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        relpath = run.relpath if run else None
    if relpath:
        return get_settings().root / relpath
    return get_settings().path('models') / '01_訓練紀錄' / run_id


def model_dir(task: str, name: str, version: str) -> Path:
    return get_settings().path('models') / '02_模型庫' / task_folder(task) / f'{name}@{version}'


def new_eval_dir(eval_id: str, task: str, subject: str) -> Path:
    return get_settings().path('models') / '03_評估' / task_folder(task) / _labelled(eval_id, subject)


def eval_dir(eval_id: str) -> Path:
    with session_scope('research') as db:
        row = db.get(Evaluation, eval_id)
        relpath = row.relpath if row else None
    if relpath:
        return get_settings().root / relpath
    return get_settings().path('models') / '03_評估' / eval_id


def write_run_summary(run_id: str) -> None:
    """在訓練資料夾寫一份人看得懂的 摘要.txt（建立、開始、結束時更新）。"""
    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        if run is None or not run.relpath:
            return
        info: dict[str, Any] = {
            'id': run.id, 'task': run.task, 'name': run.name, 'status': run.status, 'split': run.split_id,
            'version': run.dataset_version_id, 'experiment': run.experiment_id, 'created_by': run.created_by,
            'created_at': run.created_at, 'finished_at': run.finished_at,
            'config': json.loads(run.config_json or '{}'), 'summary': json.loads(run.summary_json or '{}'),
        }
        folder = get_settings().root / run.relpath
    cfg, summary = info['config'], info['summary']
    lines = [
        f'訓練：{info["id"]}',
        f'名稱：{info["name"]}',
        f'任務：{task_folder(info["task"])}',
        f'狀態：{info["status"]}',
        f'資料集版本：{info["version"]}　切分：{info["split"]}',
        f'比較組／實驗：{info["experiment"] or "—"}',
        f'建立：{info["created_at"]}（{info["created_by"]}）　結束：{info["finished_at"] or "—"}',
        '',
        '設定：',
        *[f'  {k}: {v}' for k, v in sorted(cfg.items())],
    ]
    if summary:
        lines += ['', '結果：']
        if summary.get('mean_best_score') is not None:
            lines.append(f'  各折最佳分數平均：{summary["mean_best_score"]:.4f}（標準差 {summary.get("std_best_score") or 0:.4f}）')
        for key, value in sorted((summary.get('oof') or {}).items()):
            if isinstance(value, (int, float)):
                lines.append(f'  OOF {key}: {value:.4f}')
    lines += ['', '本檔由系統自動產生；詳細內容見 config.json、summary.json、oof_predictions.json。']
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / '摘要.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except OSError:
        pass
