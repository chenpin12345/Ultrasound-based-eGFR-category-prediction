"""訓練紀錄：建立、在獨立程序執行、停止與恢復、查詢。

訓練在獨立的 Python 程序執行（app.ml.worker），網站本身不載入 PyTorch，訓練當掉也不會拖垮網站。
同一時間只跑一個訓練（工作佇列的「獨占」池），避免互相拖慢與顯示記憶體不足。
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_dated, now_iso
from ..core.security import sanitize_public_text
from ..db.models_research import DatasetVersion, Split, TrainingRun
from ..db.session import session_scope
from ..jobs.manager import JobContext, StopRequested, get_manager, register

TASKS = ('segmentation', 'egfr', 'grade')
ALLOWED = {
    'arch': str, 'init': str, 'head': str, 'img_size': int, 'epochs': int, 'batch_size': int, 'accum_steps': int, 'lr': float,
    'weight_decay': float, 'patience': int, 'seed': int, 'num_workers': int, 'amp': bool, 'max_images': int, 'folds': list, 'features': dict, 'device': str,
    'mask_policy': str, 'flip': bool, 'egfr_classes': int, 'inputs': list, 'mask_set_id': str, 'roi_mm': float,
}
EGFR_INPUTS = ('image', 'clinical', 'measures', 'mask_channels')  # 決策 D23
EXIT_STOPPED = 3
BACKEND = Path(__file__).resolve().parents[2]


from .paths import new_run_dir, run_dir, write_run_summary  # noqa: E402  run_dir 由這裡匯出給其他模組


def validate_config(task: str, config: dict[str, Any]) -> dict[str, Any]:
    if task not in TASKS:
        raise AppError(422, 'BAD_TASK', '不支援的訓練任務。')
    clean: dict[str, Any] = {}
    for key, value in (config or {}).items():
        if key not in ALLOWED:
            raise AppError(422, 'BAD_CONFIG', f'不認識的訓練設定：{key}')
        if value is None:
            continue
        kind = ALLOWED[key]
        if kind is float and isinstance(value, int):
            value = float(value)
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            raise AppError(422, 'BAD_CONFIG', f'訓練設定 {key} 的格式不正確。')
        clean[key] = value
    if clean.get('init', 'random') not in ('random', 'imagenet'):
        raise AppError(422, 'BAD_CONFIG', '初始化方式只能是 random 或 imagenet。')
    if task != 'egfr' and any(k in clean for k in ('egfr_classes', 'inputs', 'mask_set_id')):
        raise AppError(422, 'BAD_CONFIG', 'egfr_classes、inputs、mask_set_id 只用於 eGFR。')
    if task == 'egfr':
        _validate_egfr(clean)
    elif task != 'segmentation' and clean.get('head', 'corn') not in ('binary', 'ce', 'coral', 'corn', 'sord'):
        raise AppError(422, 'BAD_CONFIG', '不支援的輸出頭。')
    if task == 'grade' and clean.get('head') == 'binary':
        raise AppError(422, 'BAD_CONFIG', '回音分級是四類，不能用 binary 輸出頭。')
    for key in ('epochs', 'batch_size', 'img_size', 'accum_steps', 'patience'):
        if key in clean and clean[key] < 1:
            raise AppError(422, 'BAD_CONFIG', f'{key} 必須大於 0。')
    return clean


def _validate_egfr(clean: dict[str, Any]) -> None:
    """eGFR：類別數 2／3／5；2 類只能二元輸出頭，3、5 類用有序或多類輸出頭；輸入方式見決策 D23。"""
    k = clean.get('egfr_classes', 2)
    if k not in (2, 3, 5):
        raise AppError(422, 'BAD_CONFIG', 'eGFR 類別數只能是 2、3 或 5。')
    head = clean.get('head', 'binary' if k == 2 else 'corn')
    if k == 2 and head != 'binary':
        raise AppError(422, 'BAD_CONFIG', 'eGFR 2 類只能用 binary 輸出頭。')
    if k > 2 and head not in ('ce', 'coral', 'corn', 'sord'):
        raise AppError(422, 'BAD_CONFIG', 'eGFR 3、5 類請用 corn（建議）、ce、coral 或 sord 輸出頭。')
    inputs = clean.get('inputs') or (['image', 'measures'] if clean.get('features') else ['image'])
    if not inputs or len(set(inputs)) != len(inputs) or any(i not in EGFR_INPUTS for i in inputs):
        raise AppError(422, 'BAD_CONFIG', '輸入方式只能是 image、clinical、measures、mask_channels 的組合。')
    if clean.get('arch') == 'logreg':
        if 'image' in inputs or 'mask_channels' in inputs:
            raise AppError(422, 'BAD_CONFIG', '基準模型（logreg）只能用臨床資料或遮罩量測。')
    elif 'image' not in inputs:
        raise AppError(422, 'BAD_CONFIG', '影像模型的輸入必須包含 image；純臨床或純量測請用基準模型（arch=logreg）。')
    if 'measures' in inputs and not (clean.get('features') or {}).get('feature_set_id'):
        raise AppError(422, 'BAD_CONFIG', '遮罩量測需要特徵集（features.feature_set_id）。')
    if 'mask_channels' in inputs and not clean.get('mask_set_id'):
        raise AppError(422, 'BAD_CONFIG', '遮罩通道需要先選一個遮罩組（mask_set_id）。')


def check_weights(task: str, config: dict[str, Any]) -> None:
    """ImageNet 初始化要先下載權重（建立草稿時不檢查，開始訓練時才檢查）。"""
    if config.get('init') != 'imagenet':
        return
    from . import pretrained

    arch = config.get('arch', 'resnet34-unet' if task == 'segmentation' else 'resnet18')
    if arch == 'unet':
        raise AppError(422, 'BAD_CONFIG', '經典 UNet 沒有 ImageNet 權重，請改用 resnet34-unet。')
    name = 'resnet34-imagenet' if arch in ('resnet34-unet', 'resnet34') else f'{arch}-imagenet'
    if pretrained.info(name) is None:
        raise AppError(409, 'WEIGHTS_NOT_DOWNLOADED', f'選擇 ImageNet 初始化前，請先到「訓練 › 預訓練權重」下載 {name}。')


def create(task: str, name: str, dataset_version_id: str, split_id: str, config: dict[str, Any], operator: str, *, experiment_id: str | None = None, start: bool = True) -> dict[str, Any]:
    clean = validate_config(task, config)
    if (clean.get('features') or {}).get('feature_set_id'):
        from ..features.service import ensure_live

        ensure_live(clean['features']['feature_set_id'])  # 已移入回收桶的特徵集不能再拿來訓練
    if clean.get('mask_set_id'):
        from .masksets import get as get_mask_set

        ms = get_mask_set(clean['mask_set_id'])
        if ms['status'] != 'completed' or ms['split_id'] != split_id:
            raise AppError(409, 'MASK_SET_SPLIT', '遮罩組必須已完成，且和這個訓練用同一個切分（交叉預測）。')
    with session_scope('research') as db:
        version = db.get(DatasetVersion, dataset_version_id)
        if version is None or version.trashed_at:
            raise AppError(404, 'VERSION_NOT_FOUND', '找不到這個資料集版本。')
        split = db.get(Split, split_id)
        if split is None or split.trashed_at:
            raise AppError(404, 'SPLIT_NOT_FOUND', '找不到這個切分。')
        run_id = next_dated('RUN-', [r[0] for r in db.query(TrainingRun.id).all()], width=3)
        folder = new_run_dir(run_id, task, name)
        db.add(
            TrainingRun(
                id=run_id, task=task, name=name or run_id, experiment_id=experiment_id, split_id=split_id, dataset_version_id=dataset_version_id,
                config_json=json.dumps(clean, ensure_ascii=False), status='draft', relpath=folder.relative_to(get_settings().root).as_posix(),
                created_by=operator, created_at=now_iso(),
            )
        )
    folder.mkdir(parents=True, exist_ok=True)
    write_run_summary(run_id)
    job_id = start_run(run_id, operator) if start else None
    return {'id': run_id, 'job_id': job_id}


def start_run(run_id: str, operator: str) -> str:
    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        if run is None or run.trashed_at:
            raise AppError(404, 'RUN_NOT_FOUND', '找不到這個訓練。')
        if run.status not in ('draft', 'failed', 'stopped', 'interrupted'):
            raise AppError(409, 'RUN_ACTIVE', '這個訓練已經開始或已完成。')
        if json.loads(run.config_json).get('framework'):
            raise AppError(409, 'NOT_RESTARTABLE', 'nnU-Net 基準請從「訓練」頁重新建立。')
        config = json.loads(run.config_json)
        check_weights(run.task, config)
    kind = 'train_baseline' if config.get('arch') == 'logreg' else 'train'  # 基準模型在 CPU 上幾秒完成，不占用 GPU
    job_id = get_manager().submit(kind, {'run_id': run_id}, target=run_id, created_by=operator)
    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        run.status, run.job_id = 'queued', job_id
    return job_id


def _set(run_id: str, **values) -> None:
    with session_scope('research') as db:
        db.query(TrainingRun).filter(TrainingRun.id == run_id).update(values)


@register('train', exclusive=True, resumable=True, label='模型訓練')
def train_job(ctx: JobContext) -> dict[str, Any]:
    run_id = ctx.config['run_id']
    folder = run_dir(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    _set(run_id, status='running', job_id=ctx.job_id)
    env = {**os.environ, 'KIDNEY_WORKSPACE_ROOT': str(get_settings().root), 'PYTHONIOENCODING': 'utf-8'}
    log = folder / 'train.log'
    with log.open('a', encoding='utf-8') as fh:
        fh.write(f'\n==== {now_iso()} {"恢復" if ctx.resume else "開始"} {ctx.job_id} ====\n')
        fh.flush()
        code = subprocess.call([sys.executable, '-m', 'app.ml.worker', ctx.job_id, run_id], cwd=str(BACKEND), env=env, stdout=fh, stderr=subprocess.STDOUT)
    if code == EXIT_STOPPED:
        _set(run_id, status='stopped')
        write_run_summary(run_id)
        raise StopRequested()
    summary_path = folder / 'summary.json'
    if code != 0 or not summary_path.exists():
        _set(run_id, status='failed')
        write_run_summary(run_id)
        tail = log.read_text(encoding='utf-8', errors='replace').strip().splitlines()[-3:]
        raise AppError(500, 'TRAIN_FAILED', sanitize_public_text('訓練失敗：' + ' '.join(tail))[:400])
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    _set(run_id, status='completed', summary_json=json.dumps(summary, ensure_ascii=False), finished_at=now_iso())
    write_run_summary(run_id)
    return {'run_id': run_id, 'mean_best_score': summary.get('mean_best_score'), 'oof': summary.get('oof')}


def _run_dict(r: TrainingRun) -> dict[str, Any]:
    summary = json.loads(r.summary_json or '{}')
    return {
        'id': r.id, 'task': r.task, 'name': r.name, 'experiment_id': r.experiment_id, 'split_id': r.split_id,
        'dataset_version_id': r.dataset_version_id, 'config': json.loads(r.config_json), 'status': r.status, 'job_id': r.job_id,
        'mean_best_score': summary.get('mean_best_score'), 'oof': summary.get('oof'), 'created_by': r.created_by,
        'created_at': r.created_at, 'finished_at': r.finished_at,
    }


def list_runs(task: str | None = None, experiment_id: str | None = None) -> list[dict[str, Any]]:
    with session_scope('research') as db:
        q = db.query(TrainingRun).filter(TrainingRun.trashed_at.is_(None))
        if task:
            q = q.filter(TrainingRun.task == task)
        if experiment_id:
            q = q.filter(TrainingRun.experiment_id == experiment_id)
        return [_run_dict(r) for r in q.order_by(TrainingRun.created_at.desc()).all()]


def detail(run_id: str) -> dict[str, Any]:
    from .defaults import full_config

    with session_scope('research') as db:
        r = db.get(TrainingRun, run_id)
        if r is None or r.trashed_at:
            raise AppError(404, 'RUN_NOT_FOUND', '找不到這個訓練。')
        out = _run_dict(r)
        summary = json.loads(r.summary_json or '{}')
    folder = run_dir(run_id)
    out['effective_config'] = full_config(out['task'], out['config'])
    out['summary'] = summary
    histories: dict[str, list[dict[str, Any]]] = {}
    for fold_dir in sorted(p for p in folder.glob('fold-*') if p.is_dir()):
        h = fold_dir / 'history.csv'
        if h.exists():
            with h.open(encoding='utf-8') as fh:
                histories[fold_dir.name] = list(csv.DictReader(fh))
    out['history'] = histories
    # 最近一次交叉驗證評估：重新整理頁面後仍看得到
    from .evaluation import list_evaluations

    evaluations = list_evaluations(run_id=run_id)
    oof = [e for e in evaluations if e['target'] == 'oof']
    out['latest_evaluation'] = oof[0] if oof else None
    test = [e for e in evaluations if e['target'] == 'test']  # 固定測試集（模型或 eGFR 比較組評估的）
    out['latest_test'] = test[0] if test else None
    return out


def oof_predictions(run_id: str) -> list[dict[str, Any]]:
    path = run_dir(run_id) / 'oof_predictions.json'
    if not path.exists():
        raise AppError(404, 'OOF_NOT_FOUND', '這個訓練還沒有 out-of-fold 預測（尚未完成）。')
    return json.loads(path.read_text(encoding='utf-8'))


def learning_curve(split_id: str | None = None) -> dict[str, Any]:
    """分割的學習曲線（決策 D20）：每個完成的分割訓練＝一個點；橫軸是訓練用的遮罩張數，縱軸是交叉驗證 Dice。
    連續兩輪進步都小於 0.01 時提示可以停止請醫師圈選。不用測試集決定何時停止。"""
    from ..annotation.circling import primary_split_id

    split_id = split_id or primary_split_id()
    with session_scope('research') as db:
        rows = db.query(TrainingRun).filter(TrainingRun.task == 'segmentation', TrainingRun.status == 'completed', TrainingRun.split_id == split_id,
                                            TrainingRun.trashed_at.is_(None)).order_by(TrainingRun.finished_at).all()
        points = []
        for r in rows:
            cfg, summary = json.loads(r.config_json), json.loads(r.summary_json or '{}')
            if cfg.get('framework'):
                continue
            dice = (summary.get('oof') or {}).get('dice')
            n = (summary.get('data') or {}).get('samples')
            if dice is None or not n:
                continue
            points.append({'run_id': r.id, 'name': r.name, 'masks': int(n), 'dice': float(dice), 'finished_at': r.finished_at})
    points.sort(key=lambda p: (p['masks'], p['finished_at'] or ''))
    for prev, cur in zip(points, points[1:]):
        cur['gain'] = cur['dice'] - prev['dice']
    gains = [p['gain'] for p in points if 'gain' in p]
    plateau = len(gains) >= 2 and all(g < 0.01 for g in gains[-2:])
    return {'split_id': split_id, 'points': points, 'plateau': plateau, 'threshold': 0.01}
