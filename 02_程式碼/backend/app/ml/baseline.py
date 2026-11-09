"""eGFR 基準模型（M2.5，決策 D23）：③ 純臨床、⑥ 純遮罩量測的有序邏輯迴歸，在 CPU 上幾秒完成。

比例勝算（proportional odds）模型：P(y ≥ j) = σ(x·β − θ_j)，θ_1 < θ_2 < …；2 類時就是一般的邏輯迴歸。
和影像模型用同一個切分、同樣的病人層級評估，輸出格式也和訓練引擎相同（oof_predictions.json、summary.json），
所以比較頁、兩兩比較、匯出都能直接使用。只用來比較，不能註冊成模型。
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
from scipy import optimize

from ..core.errors import AppError
from ..core.ids import now_iso
from ..db.models_research import TrainingRun
from ..db.session import session_scope
from ..jobs.manager import JobContext, register
from . import data as mldata
from . import metrics
from .tabular import tabular_features

L2 = 1.0  # 係數的 L2 懲罰（特徵都已標準化）


def _cum_probs(x: np.ndarray, beta: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """回傳各類機率（n × K）。"""
    z = x @ beta
    ge = 1.0 / (1.0 + np.exp(-(z[:, None] - theta[None, :])))  # P(y ≥ j), j = 1..K-1
    upper = np.hstack([np.ones((len(x), 1)), ge])
    lower = np.hstack([ge, np.zeros((len(x), 1))])
    return np.clip(upper - lower, 1e-9, 1.0)


def _unpack(params: np.ndarray, d: int, k: int) -> tuple[np.ndarray, np.ndarray]:
    beta = params[:d]
    theta = np.cumsum(np.concatenate([[params[d]], np.exp(params[d + 1:])]))  # 確保 θ 遞增
    return beta, theta[: k - 1]


def fit_ordinal_logit(x: np.ndarray, y: np.ndarray, k: int, l2: float = L2) -> dict[str, Any]:
    x, y = np.asarray(x, float), np.asarray(y, int)
    d = x.shape[1]
    counts = np.bincount(y, minlength=k).astype(float) + 0.5
    cum = np.cumsum(counts[::-1])[::-1][1:] / counts.sum()  # 起始的 P(y ≥ j)
    theta0 = -np.log(cum / (1 - cum))
    start = np.concatenate([np.zeros(d), [theta0[0]], np.log(np.maximum(np.diff(theta0), 1e-3))])

    def nll(params: np.ndarray) -> float:
        beta, theta = _unpack(params, d, k)
        p = _cum_probs(x, beta, theta)
        return float(-np.log(p[np.arange(len(y)), y]).mean() + l2 * (beta @ beta) / len(y))

    res = optimize.minimize(nll, start, method='L-BFGS-B')
    beta, theta = _unpack(res.x, d, k)
    return {'beta': beta.tolist(), 'theta': theta.tolist(), 'converged': bool(res.success), 'nll': float(res.fun)}


def predict_ordinal_logit(model: dict[str, Any], x: np.ndarray) -> np.ndarray:
    return _cum_probs(np.asarray(x, float), np.asarray(model['beta'], float), np.asarray(model['theta'], float))


def train_baseline(run_id: str, ctx) -> dict[str, Any]:
    from .defaults import full_config
    from .paths import run_dir

    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        task, overrides, version, split = run.task, json.loads(run.config_json), run.dataset_version_id, run.split_id
    cfg = full_config(task, overrides)
    k = int(cfg.get('egfr_classes', 2))
    folder = run_dir(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'config.json').write_text(json.dumps({**cfg, 'dataset_version_id': version, 'split_id': split}, ensure_ascii=False, indent=2), encoding='utf-8')
    samples = mldata.build(task, version, split, egfr_classes=k)
    check = mldata.check_classes(task, samples, mldata.task_classes(task, cfg))
    ctx.event('data', check)
    features, stats = tabular_features(cfg, samples)
    if not features:
        raise AppError(409, 'NO_FEATURES', '基準模型需要臨床資料或遮罩量測，但沒有可用的特徵。')
    samples = [s for s in samples if s.image_id in features]
    folds = sorted({s.group for s in samples if s.group.startswith('fold-')})
    results, oof = [], []
    for n, fold in enumerate(folds, start=1):
        ctx.check_stop()
        train = [s for s in samples if s.group.startswith('fold-') and s.group != fold]
        val = [s for s in samples if s.group == fold]
        if not train or not val:
            results.append({'fold': fold, 'skipped': '這一折沒有訓練或驗證資料'})
            continue
        model = fit_ordinal_logit(np.array([features[s.image_id] for s in train]), np.array([s.target for s in train]), k)
        probs = predict_ordinal_logit(model, np.array([features[s.image_id] for s in val]))
        rows = [{'image_id': s.image_id, 'patient_id': s.patient_id, 'side': s.side, 'target': int(s.target), 'fold': fold,
                 'logits': [], 'probs': [round(float(v), 5) for v in p], 'calibrated': [round(float(v), 5) for v in p]} for s, p in zip(val, probs)]
        m = metrics.egfr_metrics(np.array([r['target'] for r in rows]), probs, k)
        fold_dir = folder / fold
        fold_dir.mkdir(exist_ok=True)
        (fold_dir / 'model.json').write_text(json.dumps({**model, 'columns': stats['columns']}, ensure_ascii=False, indent=2), encoding='utf-8')
        (fold_dir / 'oof.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        result = {'fold': fold, 'best_epoch': None, 'best_score': m['auc_lt60'] if m['auc_lt60'] is not None else 0.0, 'metrics': m,
                  'train_images': len(train), 'val_images': len(val), 'converged': model['converged']}
        (fold_dir / 'done.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        results.append(result)
        oof += rows
        ctx.progress(n / len(folds) * 95, f'{fold} 完成')
    done = [r for r in results if 'best_score' in r]
    y = np.array([r['target'] for r in oof], int)
    probs = np.array([r['calibrated'] for r in oof], float)
    summary = {
        'task': task, 'folds': results, 'data': check, 'temperature': 1.0, 'egfr_classes': k, 'baseline': True,
        'mean_best_score': float(np.mean([r['best_score'] for r in done])) if done else None,
        'std_best_score': float(np.std([r['best_score'] for r in done])) if done else None,
        'oof': metrics.egfr_metrics(y, probs, k) if len(oof) else {}, 'feature_stats': stats,
    }
    (folder / 'oof_predictions.json').write_text(json.dumps(oof, ensure_ascii=False), encoding='utf-8')
    (folder / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


@register('train_baseline', label='eGFR 基準模型（有序邏輯迴歸）')
def baseline_job(ctx: JobContext) -> dict[str, Any]:
    from .paths import write_run_summary
    from .runs import _set

    run_id = ctx.config['run_id']
    _set(run_id, status='running', job_id=ctx.job_id)
    try:
        summary = train_baseline(run_id, ctx)
    except Exception:
        _set(run_id, status='failed')
        write_run_summary(run_id)
        raise
    _set(run_id, status='completed', summary_json=json.dumps(summary, ensure_ascii=False), finished_at=now_iso())
    write_run_summary(run_id)
    return {'run_id': run_id, 'mean_best_score': summary.get('mean_best_score'), 'oof': summary.get('oof')}
