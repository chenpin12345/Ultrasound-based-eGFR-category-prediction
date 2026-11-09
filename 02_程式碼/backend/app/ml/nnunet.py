"""nnU-Net v2 基準：把資料轉成 nnU-Net 格式，用同一個病人層級切分訓練，結果和內建 UNet 比較。

- 只匯出腎實質、腎竇都分得出來的遮罩（標籤：0 背景、1 腎實質、2 腎竇；肝、脾在這裡算背景，所以不受部分標註影響）。
- 固定測試集的病人不匯出。
- 折的分法寫進 splits_final.json，和系統的切分完全一致，因此可以逐折比較。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..annotation.service import STRUCTURES
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_dated, now_iso
from ..data import deid
from ..db.models_research import TrainingRun
from ..db.session import session_scope
from ..jobs.manager import JobContext, StopRequested, register
from . import data as mldata

DATASET_ID = 501
DATASET_NAME = f'Dataset{DATASET_ID}_KidneyUS'
TRAINERS = {'100': 'nnUNetTrainer_100epochs', '250': 'nnUNetTrainer_250epochs', '1000': 'nnUNetTrainer'}


def roots() -> dict[str, Path]:
    base = get_settings().path('models') / 'nnUNet'
    return {'nnUNet_raw': base / 'nnUNet_raw', 'nnUNet_preprocessed': base / 'nnUNet_preprocessed', 'nnUNet_results': base / 'nnUNet_results'}


def export(dataset_version_id: str, split_id: str) -> dict[str, Any]:
    samples = mldata.build('segmentation', dataset_version_id, split_id)
    usable = [s for s in samples if s.group.startswith('fold-') and [STRUCTURES['parenchyma']] in s.groups and [STRUCTURES['sinus']] in s.groups]
    if not usable:
        raise AppError(409, 'NO_FULL_MASKS', '沒有腎實質與腎竇都分得出來的遮罩，無法建立 nnU-Net 資料。')
    r = roots()
    raw = r['nnUNet_raw'] / DATASET_NAME
    if raw.exists():
        shutil.rmtree(raw)
    (raw / 'imagesTr').mkdir(parents=True)
    (raw / 'labelsTr').mkdir()
    folds = sorted({s.group for s in usable})
    for s in usable:
        case = s.image_id.replace('-', '_')
        deid.write_png(raw / 'imagesTr' / f'{case}_0000.png', mldata.load_image(s.image_id))
        label = cv2.imdecode(np.fromfile(s.target, np.uint8), cv2.IMREAD_GRAYSCALE)
        kidney_only = np.where(np.isin(label, [STRUCTURES['parenchyma'], STRUCTURES['sinus']]), label, 0).astype(np.uint8)
        deid.write_png(raw / 'labelsTr' / f'{case}.png', kidney_only)
    dataset = {'channel_names': {'0': 'US'}, 'labels': {'background': 0, 'parenchyma': 1, 'sinus': 2}, 'numTraining': len(usable), 'file_ending': '.png', 'name': 'Kidney ultrasound (腎超修改版)'}
    (raw / 'dataset.json').write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding='utf-8')
    splits = [
        {'train': [s.image_id.replace('-', '_') for s in usable if s.group != f], 'val': [s.image_id.replace('-', '_') for s in usable if s.group == f]}
        for f in folds
    ]
    pre = r['nnUNet_preprocessed'] / DATASET_NAME
    pre.mkdir(parents=True, exist_ok=True)
    (pre / 'splits_final.json').write_text(json.dumps(splits, indent=2), encoding='utf-8')
    info = {'dataset_version_id': dataset_version_id, 'split_id': split_id, 'cases': len(usable), 'folds': folds, 'exported_at': now_iso()}
    (raw / 'export.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    return info


def _tool(name: str) -> str:
    exe = Path(sys.executable).parent / (name + ('.exe' if os.name == 'nt' else ''))
    if not exe.exists():
        raise AppError(409, 'NNUNET_NOT_INSTALLED', '找不到 nnU-Net v2，請重新執行 setup.bat 安裝。')
    return str(exe)


def _run(cmd: list[str], env: dict[str, str], log: Path, ctx: JobContext) -> None:
    with log.open('a', encoding='utf-8') as fh:
        fh.write(f'\n$ {" ".join(cmd)}\n')
        fh.flush()
        proc = subprocess.Popen(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            if ctx.should_stop():
                proc.terminate()
                proc.wait(timeout=60)
                raise StopRequested()
            time.sleep(2)
    if proc.returncode != 0:
        raise AppError(500, 'NNUNET_FAILED', f'nnU-Net 指令失敗（{Path(cmd[0]).name}），詳見 {log.name}。')


def start(dataset_version_id: str, split_id: str, epochs: str, operator: str) -> dict[str, Any]:
    from ..jobs.manager import get_manager
    from .paths import new_run_dir

    if epochs not in TRAINERS:
        raise AppError(422, 'BAD_EPOCHS', 'epoch 數只能選 100、250 或 1000。')
    with session_scope('research') as db:
        run_id = next_dated('RUN-', [r[0] for r in db.query(TrainingRun.id).all()], width=3)
        name = f'nnU-Net v2 基準（{epochs} epochs）'
        folder = new_run_dir(run_id, 'segmentation', f'nnU-Net-{epochs}')
        db.add(TrainingRun(id=run_id, task='segmentation', name=name, split_id=split_id, dataset_version_id=dataset_version_id,
                           config_json=json.dumps({'framework': 'nnunetv2', 'trainer': TRAINERS[epochs]}, ensure_ascii=False), status='queued',
                           relpath=folder.relative_to(get_settings().root).as_posix(), created_by=operator, created_at=now_iso()))
    folder.mkdir(parents=True, exist_ok=True)
    job_id = get_manager().submit('nnunet_train', {'run_id': run_id}, target=run_id, created_by=operator)
    with session_scope('research') as db:
        db.get(TrainingRun, run_id).job_id = job_id
    return {'id': run_id, 'job_id': job_id}


@register('nnunet_train', exclusive=True, resumable=True, label='nnU-Net v2 基準訓練')
def train_job(ctx: JobContext) -> dict[str, Any]:
    from .runs import _set, run_dir

    run_id = ctx.config['run_id']
    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        version, split, trainer = run.dataset_version_id, run.split_id, json.loads(run.config_json)['trainer']
    _set(run_id, status='running')
    folder = run_dir(run_id)
    log = folder / 'nnunet.log'
    info = export(version, split)
    ctx.progress(5, f'已匯出 {info["cases"]} 張')
    env = {**os.environ, **{k: str(v) for k, v in roots().items()}, 'nnUNet_n_proc_DA': '2', 'PYTHONIOENCODING': 'utf-8'}
    try:
        _run([_tool('nnUNetv2_plan_and_preprocess'), '-d', str(DATASET_ID), '-c', '2d', '--verify_dataset_integrity'], env, log, ctx)
        folds = []
        for k, fold in enumerate(info['folds']):
            ctx.progress(10 + 85 * k / len(info['folds']), f'{fold}（nnU-Net fold {k}）')
            _run([_tool('nnUNetv2_train'), str(DATASET_ID), '2d', str(k), '-tr', trainer, '--npz'], env, log, ctx)
            summary = roots()['nnUNet_results'] / DATASET_NAME / f'{trainer}__nnUNetPlans__2d' / f'fold_{k}' / 'validation' / 'summary.json'
            data = json.loads(summary.read_text(encoding='utf-8'))
            dice = float(data['foreground_mean']['Dice'])
            per = {data_key: float(v['Dice']) for data_key, v in data.get('mean', {}).items()}
            n_val = len(json.loads((roots()['nnUNet_preprocessed'] / DATASET_NAME / 'splits_final.json').read_text())[k]['val'])
            folds.append({'fold': fold, 'best_score': dice, 'metrics': {'dice': dice, 'per_label': per}, 'train_images': info['cases'] - n_val, 'val_images': n_val})
    except StopRequested:
        _set(run_id, status='stopped')
        raise
    except AppError:
        _set(run_id, status='failed')
        raise
    result = {'task': 'segmentation', 'framework': 'nnunetv2', 'folds': folds, 'mean_best_score': float(np.mean([f['best_score'] for f in folds])), 'oof': {'dice': float(np.mean([f['best_score'] for f in folds]))}, 'export': info}
    (folder / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    _set(run_id, status='completed', summary_json=json.dumps(result, ensure_ascii=False), finished_at=now_iso())
    return {'run_id': run_id, 'mean_dice': result['mean_best_score']}
