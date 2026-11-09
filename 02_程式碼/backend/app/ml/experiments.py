"""實驗：一組用同一資料集版本與切分、可以互相比較的訓練。

範本：
- init：同一設定，隨機初始化 vs ImageNet 初始化（D2）。
- ablation：消融實驗 A0–A5（eGFR 或回音分級）：
  A0 只用影像（隨機初始化）、A1 只用影像（ImageNet）、A2 影像＋腎長、A3 影像＋腎長＋回音比值、
  A4 同 A3 但打亂特徵（負對照：成績沒有下降代表特徵沒有幫助）、A5 同 A3 用 ImageNet。
  A2–A5 需要交叉擬合的特徵集（來自分割訓練的 out-of-fold 遮罩）。
建立實驗只會建立「草稿」訓練，由你按開始。
"""

from __future__ import annotations

import json
from typing import Any

from ..core.errors import AppError
from ..core.ids import next_dated, now_iso
from ..db.models_research import Experiment, FeatureSet
from ..db.session import session_scope
from . import evaluation, runs

LENGTH = ['length_mm']
ECHO = ['length_mm', 'ratio_mean', 'ratio_median']


def _variants(template: str, task: str, feature_set_id: str | None) -> list[tuple[str, dict[str, Any]]]:
    if template == 'init':
        return [('隨機初始化', {'init': 'random'}), ('ImageNet 初始化', {'init': 'imagenet'})]
    if template == 'ablation':
        if task not in ('egfr', 'grade'):
            raise AppError(422, 'BAD_TEMPLATE', '消融實驗範本只適用於 eGFR 或回音分級。')
        if not feature_set_id:
            raise AppError(422, 'FEATURES_REQUIRED', '消融實驗需要交叉擬合的特徵集。')
        f = lambda cols, shuffle=False: {'feature_set_id': feature_set_id, 'columns': cols, 'shuffle': shuffle}  # noqa: E731
        return [
            ('A0 只用影像', {'init': 'random'}),
            ('A1 只用影像（ImageNet）', {'init': 'imagenet'}),
            ('A2 影像＋腎長', {'init': 'random', 'features': f(LENGTH)}),
            ('A3 影像＋腎長＋回音比值', {'init': 'random', 'features': f(ECHO)}),
            ('A4 負對照：打亂特徵', {'init': 'random', 'features': f(ECHO, True)}),
            ('A5 同 A3（ImageNet）', {'init': 'imagenet', 'features': f(ECHO)}),
        ]
    if template == 'custom':
        return []
    raise AppError(422, 'BAD_TEMPLATE', '不支援的實驗範本。')


def create(name: str, template: str, task: str, dataset_version_id: str, split_id: str, base_config: dict[str, Any], feature_set_id: str | None, note: str, operator: str) -> dict[str, Any]:
    if feature_set_id:
        with session_scope('research') as db:
            fs = db.get(FeatureSet, feature_set_id)
            if fs is None or fs.status != 'completed':
                raise AppError(404, 'FEATURES_NOT_FOUND', '找不到這個特徵集，或還在計算。')
            if not json.loads(fs.spec_json).get('cross_fitted'):
                raise AppError(409, 'FEATURES_NOT_CROSS_FITTED', '下游模型只能用交叉擬合的特徵集（來自分割訓練的 out-of-fold 遮罩），避免標籤洩漏。')
    variants = _variants(template, task, feature_set_id)
    with session_scope('research') as db:
        exp_id = next_dated('EXP-', [r[0] for r in db.query(Experiment.id).all()], width=3)
        db.add(Experiment(id=exp_id, name=name or exp_id, template=template, config_json=json.dumps({'task': task, 'dataset_version_id': dataset_version_id, 'split_id': split_id, 'base_config': base_config, 'feature_set_id': feature_set_id}, ensure_ascii=False), note=note, created_by=operator, created_at=now_iso()))
    created = []
    for label, overrides in variants:
        created.append(runs.create(task, f'{label}', dataset_version_id, split_id, {**base_config, **overrides}, operator, experiment_id=exp_id, start=False)['id'])
    return {'id': exp_id, 'runs': created}


def start_all(exp_id: str, operator: str) -> dict[str, Any]:
    started = []
    for r in runs.list_runs(experiment_id=exp_id):
        if r['status'] in ('draft', 'failed', 'stopped', 'interrupted'):
            started.append(runs.start_run(r['id'], operator))
    return {'jobs': started}


def detail(exp_id: str) -> dict[str, Any]:
    with session_scope('research') as db:
        e = db.get(Experiment, exp_id)
        if e is None or e.trashed_at:
            raise AppError(404, 'EXPERIMENT_NOT_FOUND', '找不到這個實驗。')
        out = {'id': e.id, 'name': e.name, 'template': e.template, 'config': json.loads(e.config_json), 'note': e.note, 'created_by': e.created_by, 'created_at': e.created_at}
    members = sorted(runs.list_runs(experiment_id=exp_id), key=lambda r: r['created_at'])
    out['runs'] = members
    done = [r for r in members if r['status'] == 'completed']
    out['comparisons'] = [evaluation.compare(r['id'], done[0]['id']) for r in done[1:]] if len(done) > 1 else []
    return out


def list_experiments() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        rows = db.query(Experiment).filter(Experiment.trashed_at.is_(None)).order_by(Experiment.created_at.desc()).all()
        items = [{'id': e.id, 'name': e.name, 'template': e.template, 'config': json.loads(e.config_json), 'created_by': e.created_by, 'created_at': e.created_at} for e in rows]
    for item in items:
        members = runs.list_runs(experiment_id=item['id'])
        item['runs'] = len(members)
        item['completed'] = sum(1 for r in members if r['status'] == 'completed')
    return items
