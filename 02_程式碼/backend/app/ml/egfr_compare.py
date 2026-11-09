"""eGFR 比較組（M2.5，決策 D22–D24、D33）：勾選輸入方式 ①–⑥ 與類別數 2／3／5，一次建立；比較格、兩兩比較、匯出。

- 一個比較組是一個實驗（template＝egfr_compare），成員記在 config_json 的 members：每格一個訓練。
- 設定相同（切分、資料集版本、類別數、輸入、架構、初始化、epoch、輸入大小、batch、學習率、種子、輸出頭、特徵、遮罩組）
  且已完成的訓練，預設直接沿用，不重新訓練。
- 所有成員都能用病人層級 AUC(<60) 比較；3、5 類另比 AUC(<30)、QWK；5 類可合併成 3 類。
- 預先指定的主要比較（D33）：② 影像＋臨床 vs ③ 純臨床（2 類 AUC(<60)）。
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any

import numpy as np

from ..core.errors import AppError
from ..core.ids import next_dated, now_iso
from ..data import egfr as E
from ..db.models_research import Experiment, TrainingRun
from ..db.session import session_scope
from . import evaluation, metrics, runs

INPUTS: dict[str, list[str]] = {
    'image': ['image'],
    'image_clinical': ['image', 'clinical'],
    'clinical': ['clinical'],
    'image_mask': ['image', 'mask_channels'],
    'image_measures': ['image', 'measures'],
    'measures': ['measures'],
}
LABELS = {
    'image': '① 影像', 'image_clinical': '② 影像＋臨床', 'clinical': '③ 純臨床',
    'image_mask': '④ 影像＋遮罩通道', 'image_measures': '⑤ 影像＋遮罩量測', 'measures': '⑥ 純遮罩量測',
}
NEEDS_MASK = ('image_mask', 'image_measures', 'measures')
CPU = ('clinical', 'measures')
PRESETS = {'無遮罩版': ['image', 'image_clinical', 'clinical'], '有遮罩版': ['image_mask', 'image_measures', 'measures']}
PRIMARY = [('image_clinical', 'clinical', 2, 'auc_lt60'), ('image', 'clinical', 2, 'auc_lt60'), ('image_mask', 'image', 2, 'auc_lt60'), ('image_measures', 'image', 2, 'auc_lt60')]
SIGNATURE_KEYS = ('egfr_classes', 'inputs', 'arch', 'init', 'epochs', 'img_size', 'batch_size', 'lr', 'seed', 'head', 'weight_decay', 'patience', 'mask_set_id')
MEASURE_COLUMNS = ['length_mm', 'ratio_mean', 'ratio_median', 'p_index']


def options() -> dict[str, Any]:
    return {
        'classes': {str(k): E.classes(k) for k in E.KS},
        'inputs': [{'code': c, 'label': LABELS[c], 'inputs': INPUTS[c], 'needs_mask': c in NEEDS_MASK, 'cpu': c in CPU} for c in INPUTS],
        'presets': PRESETS,
        'primary': [{'a': a, 'b': b, 'k': k, 'metric': m} for a, b, k, m in PRIMARY],
    }


def _signature(cfg: dict[str, Any], split_id: str, version: str) -> str:
    from .defaults import full_config
    from .tabular import input_list

    full = full_config('egfr', cfg)
    sig = {k: full.get(k) for k in SIGNATURE_KEYS}
    sig['inputs'] = sorted(input_list(full))  # 舊的訓練沒有 inputs：視為「只用影像」（或影像＋量測），才能被沿用
    feats = full.get('features') or {}
    sig['features'] = [feats.get('feature_set_id'), feats.get('columns')] if feats else None
    if full.get('arch') == 'logreg':  # 基準模型和影像設定無關
        sig = {k: sig[k] for k in ('egfr_classes', 'inputs', 'arch', 'features', 'seed')}
    return json.dumps({**sig, 'split': split_id, 'version': version}, sort_keys=True, ensure_ascii=False)


def _member_config(code: str, k: int, base: dict[str, Any], mask_set_id: str | None, feature_set_id: str | None) -> dict[str, Any]:
    cfg: dict[str, Any] = {'egfr_classes': k, 'inputs': INPUTS[code], 'seed': int(base.get('seed', 42))}
    if code in CPU:
        cfg['arch'] = 'logreg'
    else:
        for key in ('arch', 'init', 'epochs', 'img_size', 'batch_size', 'lr', 'max_images', 'device', 'num_workers', 'amp'):
            if base.get(key) is not None:
                cfg[key] = base[key]
        cfg['head'] = 'binary' if k == 2 else base.get('head', 'corn')
    if 'measures' in INPUTS[code]:
        cfg['features'] = {'feature_set_id': feature_set_id, 'columns': MEASURE_COLUMNS}
    if 'mask_channels' in INPUTS[code]:
        cfg['mask_set_id'] = mask_set_id
    return cfg


def _mask_inputs(mask_set_id: str | None, split_id: str, need_features: bool) -> str | None:
    """有遮罩的輸入需要一個完成的遮罩組；⑤⑥ 另外需要它的特徵集（④ 只用遮罩，不需要）。"""
    if not mask_set_id:
        raise AppError(409, 'MASK_SET_REQUIRED', '有遮罩的輸入（④⑤⑥）需要先產生遮罩組（分割 › 遮罩組）。')
    from . import masksets

    ms = masksets.get(mask_set_id)
    if ms['status'] != 'completed':
        raise AppError(409, 'MASK_SET_NOT_READY', '這個遮罩組還沒完成。')
    if ms['split_id'] != split_id:
        raise AppError(409, 'MASK_SET_SPLIT', '遮罩組的切分和比較組不同；交叉預測必須用同一個切分。')
    return masksets.feature_set_for(mask_set_id) if need_features else None


def create(name: str, dataset_version_id: str, split_id: str, codes: list[str], ks: list[int], base_config: dict[str, Any], mask_set_id: str | None,
           reuse: bool, start: bool, operator: str) -> dict[str, Any]:
    codes = [c for c in INPUTS if c in set(codes)]
    ks = sorted({int(k) for k in ks})
    if not codes or not ks:
        raise AppError(422, 'NOTHING_SELECTED', '請至少勾選一種輸入方式與一種類別數。')
    if any(k not in E.KS for k in ks):
        raise AppError(422, 'BAD_CLASSES', 'eGFR 類別數只能是 2、3 或 5。')
    feature_set_id = _mask_inputs(mask_set_id, split_id, any('measures' in INPUTS[c] for c in codes)) if any(c in NEEDS_MASK for c in codes) else None
    existing: dict[str, str] = {}
    if reuse:
        with session_scope('research') as db:
            for r in db.query(TrainingRun).filter(TrainingRun.task == 'egfr', TrainingRun.status == 'completed', TrainingRun.trashed_at.is_(None),
                                                    TrainingRun.split_id == split_id, TrainingRun.dataset_version_id == dataset_version_id).order_by(TrainingRun.created_at).all():
                existing.setdefault(_signature(json.loads(r.config_json), split_id, dataset_version_id), r.id)
    with session_scope('research') as db:
        exp_id = next_dated('EXP-', [r[0] for r in db.query(Experiment.id).all()], width=3)
        db.add(Experiment(id=exp_id, name=name or exp_id, template='egfr_compare', config_json='{}', note='', created_by=operator, created_at=now_iso()))
    members = []
    for code in codes:
        for k in ks:
            cfg = _member_config(code, k, base_config, mask_set_id, feature_set_id)
            runs.validate_config('egfr', cfg)
            sig = _signature(cfg, split_id, dataset_version_id)
            if sig in existing:
                members.append({'code': code, 'k': k, 'run_id': existing[sig], 'reused': True})
                continue
            run = runs.create('egfr', f'{LABELS[code]}・{k} 類', dataset_version_id, split_id, cfg, operator, experiment_id=exp_id, start=False)
            members.append({'code': code, 'k': k, 'run_id': run['id'], 'reused': False})
    config = {'task': 'egfr', 'dataset_version_id': dataset_version_id, 'split_id': split_id, 'base_config': base_config, 'codes': codes, 'ks': ks,
              'mask_set_id': mask_set_id, 'feature_set_id': feature_set_id, 'members': members}
    with session_scope('research') as db:
        db.get(Experiment, exp_id).config_json = json.dumps(config, ensure_ascii=False)
    jobs = start_group(exp_id, operator)['jobs'] if start else []
    return {'id': exp_id, 'members': members, 'jobs': jobs, 'reused': sum(m['reused'] for m in members)}


def _group(exp_id: str) -> tuple[Experiment, dict[str, Any]]:
    with session_scope('research') as db:
        e = db.get(Experiment, exp_id)
        if e is None or e.trashed_at or e.template != 'egfr_compare':
            raise AppError(404, 'COMPARISON_NOT_FOUND', '找不到這個 eGFR 比較組。')
        return e, json.loads(e.config_json)


def start_group(exp_id: str, operator: str) -> dict[str, Any]:
    """CPU 基準先跑（幾秒），GPU 模型依序排入獨占執行池。"""
    _, cfg = _group(exp_id)
    order = sorted(cfg['members'], key=lambda m: (m['code'] not in CPU, m['k']))
    jobs = []
    with session_scope('research') as db:
        status = {r.id: r.status for r in db.query(TrainingRun).filter(TrainingRun.id.in_([m['run_id'] for m in order])).all()}
    for m in order:
        if not m['reused'] and status.get(m['run_id']) in ('draft', 'failed', 'stopped', 'interrupted'):
            jobs.append(runs.start_run(m['run_id'], operator))
    return {'jobs': jobs}


def run_report(run_id: str) -> dict[str, Any] | None:
    """訓練的 OOF 報告（快取在訓練資料夾，OOF 檔更新後自動重算）。"""
    from .paths import run_dir

    folder = run_dir(run_id)
    oof = folder / 'oof_predictions.json'
    if not oof.exists():
        return None
    cache = folder / 'egfr_report.json'
    stamp = os.path.getmtime(oof)
    if cache.exists():
        data = json.loads(cache.read_text(encoding='utf-8'))
        if data.get('stamp') == stamp:
            return data['report']
    rows = json.loads(oof.read_text(encoding='utf-8'))
    if not rows:
        return None
    rep = evaluation.report('egfr', rows)
    cache.write_text(json.dumps({'stamp': stamp, 'report': rep}, ensure_ascii=False), encoding='utf-8')
    return rep


def _cell(rep: dict[str, Any] | None) -> dict[str, Any]:
    if not rep:
        return {}
    p = rep['patient']
    k = rep['k']
    qwk3 = p.get('qwk') if k == 3 else (p.get('collapsed', {}).get('3') or {}).get('qwk')
    return {
        'n_patients': p['n'], 'auc_lt60': p.get('auc_lt60'), 'auc_lt60_ci': p.get('auc_lt60_ci'), 'auc_lt30': p.get('auc_lt30'), 'auc_lt30_ci': p.get('auc_lt30_ci'),
        'qwk': p.get('qwk'), 'qwk3': qwk3, 'mae': p.get('mae'), 'accuracy': p.get('accuracy'), 'brier_lt60': p.get('brier_lt60'), 'ece_lt60': p.get('ece_lt60'),
        'sensitivity': p.get('sensitivity'), 'specificity': p.get('specificity'),
        'classes': p.get('classes'), 'confusion': p.get('confusion'), 'per_class_recall': p.get('per_class_recall'), 'class_counts': p.get('class_counts'),
        'confusion3': (p.get('collapsed', {}).get('3') or {}).get('confusion'),
    }


def detail(exp_id: str) -> dict[str, Any]:
    from ..db.models_research import Evaluation

    e, cfg = _group(exp_id)
    ids = [m['run_id'] for m in cfg['members']]
    with session_scope('research') as db:
        rows = {r.id: r for r in db.query(TrainingRun).filter(TrainingRun.id.in_(ids), TrainingRun.trashed_at.is_(None)).all()}  # 回收桶裡的成員顯示「找不到」
        info = {i: {'status': r.status, 'name': r.name, 'job_id': r.job_id, 'finished_at': r.finished_at} for i, r in rows.items()}
        tests: dict[str, dict[str, Any]] = {}  # 每個成員最近一次固定測試集評估（病人層級 AUC(<60)）
        for ev in db.query(Evaluation).filter(Evaluation.run_id.in_(ids), Evaluation.target == 'test').order_by(Evaluation.created_at).all():
            p = json.loads(ev.metrics_json).get('patient') or {}
            tests[ev.run_id] = {'evaluation_id': ev.id, 'auc_lt60': p.get('auc_lt60'), 'auc_lt60_ci': p.get('auc_lt60_ci'), 'created_at': ev.created_at}
    cells = []
    for m in cfg['members']:
        run = info.get(m['run_id'], {'status': 'missing'})
        rep = run_report(m['run_id']) if run['status'] == 'completed' else None
        cells.append({**m, 'label': LABELS[m['code']], **run, 'metrics': _cell(rep), 'test': tests.get(m['run_id'])})
    return {'id': e.id, 'name': e.name, 'created_by': e.created_by, 'created_at': e.created_at, 'config': {k: v for k, v in cfg.items() if k != 'members'},
            'cells': cells, 'labels': LABELS, 'primary': [{'a': a, 'b': b, 'k': k, 'metric': mt} for a, b, k, mt in PRIMARY]}


def list_groups() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        rows = db.query(Experiment).filter(Experiment.template == 'egfr_compare', Experiment.trashed_at.is_(None)).order_by(Experiment.created_at.desc()).all()
        groups = [(e, json.loads(e.config_json)) for e in rows]
        status = {r.id: r.status for r in db.query(TrainingRun).filter(TrainingRun.id.in_([m['run_id'] for _, c in groups for m in c.get('members', [])]), TrainingRun.trashed_at.is_(None)).all()}
    out = []
    for e, c in groups:
        members = c.get('members', [])
        out.append({'id': e.id, 'name': e.name, 'created_at': e.created_at, 'created_by': e.created_by, 'codes': c.get('codes', []), 'ks': c.get('ks', []),
                    'members': len(members), 'completed': sum(1 for m in members if status.get(m['run_id']) == 'completed'), 'split_id': c.get('split_id')})
    return out


# ---------- 兩兩比較 ----------
METRICS = ('auc_lt60', 'auc_lt30', 'qwk3', 'qwk')


def _patient_probs(run_id: str) -> tuple[int, dict[str, dict[str, Any]], dict[str, str]]:
    from .runs import oof_predictions

    rows = oof_predictions(run_id)
    if not rows:
        raise AppError(409, 'NO_PREDICTIONS', f'{run_id} 沒有 out-of-fold 預測。')
    key = 'calibrated' if 'calibrated' in rows[0] else 'probs'
    prow = evaluation.patient_rows(rows, key)
    return len(rows[0][key]), {r['patient_id']: {'y': r['target'], 'p': np.array(r[key])} for r in prow}, {r['patient_id']: r.get('fold') for r in prow}


def _metric_fn(metric: str, ka: int, kb: int):
    def value(rs: list[dict[str, Any]], side: str) -> float | None:
        k = ka if side == 'a' else kb
        y = np.array([r[side]['y'] for r in rs])
        p = np.array([r[side]['p'] for r in rs])
        if metric in ('auc_lt60', 'auc_lt30'):
            cut = 60 if metric == 'auc_lt60' else 30
            return metrics.fast_auc(E.y_lt(y, k, cut), E.p_lt(p, k, cut))
        if metric == 'qwk3':
            return metrics.ordinal_metrics(E.collapse_labels(y, k, 3), E.collapse_probs(p, k, 3))['qwk']
        return metrics.ordinal_metrics(y, p)['qwk']
    return value


def pairwise(run_a: str, run_b: str, metric: str = 'auc_lt60') -> dict[str, Any]:
    if metric not in METRICS:
        raise AppError(422, 'BAD_METRIC', '指標只能是 auc_lt60、auc_lt30、qwk3、qwk。')
    with session_scope('research') as db:
        a, b = db.get(TrainingRun, run_a), db.get(TrainingRun, run_b)
        if a is None or b is None or a.status != 'completed' or b.status != 'completed':
            raise AppError(409, 'RUN_NOT_COMPLETED', '兩個訓練都必須已完成。')
        if a.task != 'egfr' or b.task != 'egfr':
            raise AppError(409, 'TASK_MISMATCH', '兩兩比較只能比較 eGFR 的訓練。')
        if a.split_id != b.split_id:
            raise AppError(409, 'SPLIT_MISMATCH', '兩個訓練用的切分不同，不能配對比較。')
    ka, pa, fa = _patient_probs(run_a)
    kb, pb, _ = _patient_probs(run_b)
    if metric in ('auc_lt30', 'qwk3') and min(ka, kb) < 3:
        raise AppError(409, 'METRIC_UNAVAILABLE', '2 類模型沒有 AUC(<30) 與 3 類 QWK；請改用 AUC(<60)。')
    if metric == 'qwk' and ka != kb:
        raise AppError(409, 'METRIC_UNAVAILABLE', '類別數不同時不能直接比 QWK；請用 3 類合併後的 QWK（qwk3）。')
    common = sorted(set(pa) & set(pb))
    rows = [{'patient_id': p, 'a': pa[p], 'b': pb[p], 'fold': fa.get(p)} for p in common]
    fn = _metric_fn(metric, ka, kb)
    result = metrics.paired_bootstrap(rows, fn)
    folds = sorted({r['fold'] for r in rows if r['fold']})
    diffs = []
    for f in folds:
        sub = [r for r in rows if r['fold'] == f]
        va, vb = fn(sub, 'a'), fn(sub, 'b')
        if va is not None and vb is not None:
            diffs.append(va - vb)
    n = len(rows)
    ttest = metrics.corrected_ttest(diffs, n - n // max(1, len(folds)), n // max(1, len(folds))) if diffs else None
    return {'run_a': run_a, 'run_b': run_b, 'metric': metric, 'k_a': ka, 'k_b': kb, 'patients': n, **result, 'fold_ttest': ttest}


# ---------- 匯出 ----------
def oof_table(run_id: str) -> tuple[list[str], list[list[Any]]]:
    """每位病人（P-編號與類別，不含 eGFR 數值）的 OOF 機率。"""
    k, probs, folds = _patient_probs(run_id)
    header = ['病人', '折', '真實類別', *[f'P({c})' for c in E.classes(k)], 'P(eGFR<60)', *(['P(eGFR<30)'] if k >= 3 else []), '預測類別']
    rows = []
    for pid in sorted(probs):
        r = probs[pid]
        p = r['p']
        rows.append([pid, folds.get(pid) or '', E.classes(k)[r['y']], *[round(float(v), 4) for v in p], round(float(E.p_lt(p, k, 60)), 4),
                     *([round(float(E.p_lt(p, k, 30)), 4)] if k >= 3 else []), E.classes(k)[int(np.argmax(p))]])
    return header, rows


def export(exp_id: str) -> dict[str, Any]:
    from ..core.config import get_settings
    from ..services.workspace import new_export_dir

    info = detail(exp_id)
    folder = new_export_dir(f'eGFR比較_{exp_id}')
    fmt = lambda v: '' if v is None else round(v, 4) if isinstance(v, float) else v  # noqa: E731
    ci = lambda v: '' if not v or v[0] is None else f'{v[0]:.3f}–{v[1]:.3f}'  # noqa: E731
    with (folder / '比較表.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['輸入方式', '類別數', '訓練', '狀態', '沿用', '病人數', 'AUC(<60)', '95% CI', 'AUC(<30)', '95% CI', 'QWK', 'QWK（3 類）', 'MAE', '準確率', 'Brier(<60)', 'ECE(<60)'])
        for c in info['cells']:
            m = c['metrics']
            w.writerow([c['label'], c['k'], c['run_id'], c['status'], '是' if c['reused'] else '', m.get('n_patients', ''), fmt(m.get('auc_lt60')), ci(m.get('auc_lt60_ci')),
                        fmt(m.get('auc_lt30')), ci(m.get('auc_lt30_ci')), fmt(m.get('qwk')), fmt(m.get('qwk3')), fmt(m.get('mae')), fmt(m.get('accuracy')), fmt(m.get('brier_lt60')), fmt(m.get('ece_lt60'))])
    done = [c for c in info['cells'] if c['status'] == 'completed']
    for c in done:
        header, rows = oof_table(c['run_id'])
        with (folder / f'每位病人機率_{c["code"]}_{c["k"]}類_{c["run_id"]}.csv').open('w', encoding='utf-8-sig', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
    (folder / '說明.txt').write_text(
        f'eGFR 比較組 {exp_id}（{info["name"]}）的匯出，{now_iso()[:16]}。\n'
        '比較表.csv：每一格（輸入方式 × 類別數）的病人層級交叉驗證成績；AUC(<60) 是所有模型共同的尺。\n'
        '每位病人機率_*.csv：每位病人（P-編號）在該模型的各類機率、P(eGFR<60)、P(eGFR<30)、預測類別；真實類別只寫類別，不含 eGFR 數值。\n'
        '預先指定的主要比較：② 影像＋臨床 vs ③ 純臨床（2 類 AUC(<60)，決策 D33）。\n', encoding='utf-8')
    return {'folder': folder.relative_to(get_settings().root).as_posix(), 'files': len(done) + 2}


# ---------- 固定測試集：勾選的比較組一起評估，一次鎖定（決策 D27）----------
def _members(exp_ids: list[str]) -> tuple[list[dict[str, Any]], str]:
    members, splits = [], set()
    for exp_id in exp_ids:
        _, cfg = _group(exp_id)
        splits.add(cfg['split_id'])
        for m in cfg['members']:
            if m['run_id'] not in {x['run_id'] for x in members}:
                members.append({**m, 'experiment_id': exp_id})
    if len(splits) != 1:
        raise AppError(409, 'SPLIT_MISMATCH', '要一起評估的比較組必須用同一個切分。')
    return members, splits.pop()


def test_readiness(exp_ids: list[str]) -> dict[str, Any]:
    from ..db.models_research import Split

    if not exp_ids:
        raise AppError(422, 'NOTHING_SELECTED', '請至少勾選一個比較組。')
    from ..db.models_research import Image as ImageRow
    from ..db.models_research import SplitEntry

    members, split_id = _members(exp_ids)
    with session_scope('research') as db:
        split = db.get(Split, split_id)
        locked = evaluation.is_locked(split, 'egfr')
        rows = {r.id: r for r in db.query(TrainingRun).filter(TrainingRun.id.in_([m['run_id'] for m in members]), TrainingRun.trashed_at.is_(None)).all()}
        status = {i: r.status for i, r in rows.items()}
        configs = {i: (json.loads(r.config_json), r.dataset_version_id) for i, r in rows.items()}
        patients = [p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == split_id, SplitEntry.group == 'test').all()]
        test_ids = [i for (i,) in db.query(ImageRow.id).filter(ImageRow.patient_id.in_(patients), ImageRow.status == 'usable').all()]
    others = [g['id'] for g in list_groups() if g['split_id'] == split_id and g['id'] not in exp_ids and g['completed'] < g['members']]
    unfinished = [m['run_id'] for m in members if status.get(m['run_id']) != 'completed']
    gaps = {}
    for m in members:  # ④ 需要遮罩組的遮罩、⑤⑥ 需要量測特徵；缺少時先擋下，不要鎖定後才失敗
        if m['run_id'] in configs:
            cfg, version = configs[m['run_id']]
            g = evaluation.missing_inputs(version, test_ids, (cfg.get('features') or {}).get('feature_set_id'), cfg.get('mask_set_id'))
            if any(g.values()):
                gaps[m['run_id']] = g
    return {'split_id': split_id, 'locked': locked, 'members': len(members), 'unfinished': unfinished, 'missing_inputs': gaps,
            'other_unfinished_groups': others, 'ready': not locked and not unfinished and not gaps and bool(members)}


def start_test(exp_ids: list[str], confirm: str, operator: str) -> dict[str, Any]:
    from ..jobs.manager import get_manager

    state = test_readiness(exp_ids)
    if state['locked']:
        raise AppError(409, 'TEST_LOCKED', '這個切分的 eGFR 固定測試集已經評估過，不能再用。')
    if state['unfinished']:
        raise AppError(409, 'RUNS_UNFINISHED', f'還有 {len(state["unfinished"])} 個訓練沒完成，請等全部完成後再評估。')
    if state['missing_inputs']:
        raise AppError(409, 'TEST_INPUTS_MISSING', f'有 {len(state["missing_inputs"])} 個模型的測試影像缺少遮罩或量測特徵，請先用同一個資料集版本產生遮罩組與特徵集。')
    if confirm.strip() != state['split_id']:
        raise AppError(422, 'CONFIRM_MISMATCH', f'請輸入切分編號 {state["split_id"]} 確認：eGFR 的固定測試集只能評估一次。')
    job_id = get_manager().submit('evaluate_egfr_test', {'experiment_ids': exp_ids, 'operator': operator}, target='、'.join(exp_ids), created_by=operator)
    return {'job_id': job_id, **state}


def _member_test_rows(run_id: str, test_ids: set[str]) -> list[dict[str, Any]]:
    """一個成員在測試影像上的預測（CNN 用各折最佳模型平均；基準用各折係數的預測平均）。"""
    import cv2

    from ..features import service as features
    from . import data as mldata
    from . import registry
    from .baseline import predict_ordinal_logit
    from .defaults import full_config
    from .paths import run_dir
    from .tabular import tabular_features

    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        cfg, version, split = full_config('egfr', json.loads(run.config_json)), run.dataset_version_id, run.split_id
    k = int(cfg.get('egfr_classes', 2))
    samples = mldata.build('egfr', version, split, egfr_classes=k)
    tests = [s for s in samples if s.image_id in test_ids]
    rows = []
    if cfg.get('arch') == 'logreg':
        feats, _ = tabular_features(cfg, samples)  # 統計值只用開發集，和訓練時相同
        folder = run_dir(run_id)
        models = [json.loads((folder / f / 'model.json').read_text(encoding='utf-8')) for f in sorted(p.name for p in folder.glob('fold-*')) if (folder / f / 'model.json').exists()]
        for s in tests:
            if s.image_id in feats:
                probs = np.mean([predict_ordinal_logit(m, np.array([feats[s.image_id]]))[0] for m in models], 0)
                rows.append({'image_id': s.image_id, 'patient_id': s.patient_id, 'side': s.side, 'target': s.target, 'calibrated': [round(float(v), 5) for v in probs]})
        return rows
    model = registry.load_run(run_id)
    fspec = model.manifest.get('features') or {}
    fs_id = (fspec.get('measures') or {}).get('feature_set_id') or fspec.get('feature_set_id')
    feature_rows = {r['image_id']: r for r in features.read_table(fs_id)} if fs_id else {}
    for s in tests:
        gray = mldata.load_image(s.image_id)
        x = registry.standardize(model, feature_rows.get(s.image_id, {}), s.extra.get('clinical')) if model.manifest.get('features') else None
        label = None
        if model.manifest['input'].get('mode') == 'mask_channels':
            from .masksets import mask_path

            label = cv2.imdecode(np.fromfile(str(mask_path(model.manifest['input']['mask_source']['mask_set_id'], s.image_id)), np.uint8), cv2.IMREAD_GRAYSCALE)
        probs = registry.predict_classification(model, gray, x, label, s.extra.get('spacing'))
        rows.append({'image_id': s.image_id, 'patient_id': s.patient_id, 'side': s.side, 'target': s.target, 'calibrated': probs})
    return rows


from ..jobs.manager import JobContext, register  # noqa: E402


@register('evaluate_egfr_test', exclusive=True, label='eGFR 比較組一起評估固定測試集')
def evaluate_test_job(ctx: JobContext) -> dict[str, Any]:
    from ..db.models_research import Split, SplitEntry
    from ..db.models_research import Image as ImageRow

    exp_ids = ctx.config['experiment_ids']
    state = test_readiness(exp_ids)
    if not state['ready']:
        raise AppError(409, 'TEST_NOT_READY', '比較組還不能評估（已鎖定、有訓練沒完成，或測試影像缺少遮罩或量測特徵）。')
    members, split_id = _members(exp_ids)
    with session_scope('research') as db:
        evaluation.lock(db.get(Split, split_id), 'egfr', {'experiments': exp_ids, 'by': ctx.config.get('operator', '')})  # 先鎖定：中途失敗也不能重來
        patients = [p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == split_id, SplitEntry.group == 'test').all()]
        test_ids = {i for (i,) in db.query(ImageRow.id).filter(ImageRow.patient_id.in_(patients), ImageRow.status == 'usable').all()}
    results = []
    for n, m in enumerate(members, start=1):
        ctx.check_stop()
        rows = _member_test_rows(m['run_id'], test_ids)
        if rows:
            rep = {'target': 'test', 'task': 'egfr', 'run_id': m['run_id'], 'split_id': split_id, 'experiments': exp_ids, 'code': m['code'], **evaluation.report('egfr', rows)}
            eval_id = evaluation._save('test', m['run_id'], None, rep, ctx.config.get('operator', ''))
            (evaluation.eval_dir(eval_id) / 'predictions.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            results.append({'run_id': m['run_id'], 'code': m['code'], 'k': m['k'], 'evaluation_id': eval_id,
                            'auc_lt60': rep['patient'].get('auc_lt60'), 'auc_lt60_ci': rep['patient'].get('auc_lt60_ci')})
        ctx.progress(n / len(members) * 100, f'{n}／{len(members)}')
    return {'split_id': split_id, 'evaluations': results}
