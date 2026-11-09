"""表格特徵（不需要 PyTorch）：臨床資料與遮罩量測，給影像模型做 late fusion，也給 CPU 上的基準模型使用。

標準化與補值只用開發集（各折）計算，不用測試集（決策 D23）。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import data as mldata


def input_list(cfg: dict[str, Any]) -> list[str]:
    """舊的設定沒有 inputs：有特徵集就是「影像＋量測」，否則只用影像。"""
    if cfg.get('inputs'):
        return list(cfg['inputs'])
    return ['image', 'measures'] if cfg.get('features') else ['image']


def tabular_features(cfg: dict[str, Any], samples: list[mldata.Sample]) -> tuple[dict[str, list[float]] | None, dict[str, Any] | None]:
    """late fusion 的表格特徵：臨床資料（inputs 含 clinical）與遮罩量測（inputs 含 measures，來自特徵集），依序串接。
    標準化與補值只用各折（開發集）的資料計算，不用測試集（決策 D23）。"""
    inputs = input_list(cfg) if cfg['task'] != 'segmentation' else []
    dev = {s.image_id for s in samples if s.group.startswith('fold-')}
    parts: list[tuple[dict[str, list[float]], dict[str, Any]]] = []
    if 'clinical' in inputs:
        parts.append(clinical_features(samples, dev))
    if 'measures' in inputs and cfg.get('features'):
        parts.append(load_features(cfg['features'], [s.image_id for s in samples], dev))
    if not parts:
        return None, None
    ids = set.intersection(*(set(p[0]) for p in parts))
    merged = {i: [v for p in parts for v in p[0][i]] for i in ids}
    stats: dict[str, Any] = {'columns': [c for p in parts for c in p[1]['columns']]}
    for p in parts:
        stats[p[1]['kind']] = p[1]
    if 'measures' in stats:  # 舊合約相容：量測特徵的平均與標準差也放在最上層
        stats.update({k: stats['measures'][k] for k in ('mean', 'std')})
    return merged, stats


def clinical_features(samples: list[mldata.Sample], dev: set[str]) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """臨床資料 → 6 個欄位：年齡（標準化）、女性、糖尿病，各加一個缺值標記。缺值用開發集的平均（年齡）或眾數補上。"""
    def raw(s):
        c = s.extra.get('clinical') or {}
        sex = {'F': 1.0, 'M': 0.0}.get(str(c.get('sex') or '').upper())
        dm = None if c.get('has_diabetes') is None else float(bool(c.get('has_diabetes')))
        age = None if c.get('age') is None else float(c['age'])
        return age, sex, dm
    rows = {s.image_id: raw(s) for s in samples}
    dev_rows = [rows[i] for i in rows if i in dev] or list(rows.values())
    ages = [r[0] for r in dev_rows if r[0] is not None]
    age_mean = float(np.mean(ages)) if ages else 0.0
    age_std = float(np.std(ages)) if len(ages) > 1 and np.std(ages) > 0 else 1.0
    def mode(values):
        values = [v for v in values if v is not None]
        return float(round(np.mean(values))) if values else 0.0
    sex_mode, dm_mode = mode([r[1] for r in dev_rows]), mode([r[2] for r in dev_rows])
    out = {}
    for i, (age, sex, dm) in rows.items():
        out[i] = [((age if age is not None else age_mean) - age_mean) / age_std, sex if sex is not None else sex_mode, dm if dm is not None else dm_mode,
                  float(age is None), float(sex is None), float(dm is None)]
    stats = {'kind': 'clinical', 'columns': ['age_z', 'female', 'diabetes', 'age_missing', 'sex_missing', 'diabetes_missing'],
             'age_mean': age_mean, 'age_std': age_std, 'sex_mode': sex_mode, 'diabetes_mode': dm_mode}
    return out, stats


def load_features(spec: dict[str, Any], image_ids: list[str], dev: set[str] | None = None) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """遮罩量測的表格特徵：從特徵集 CSV 讀指定欄位，以開發集（各折）的平均與標準差標準化，缺值補 0（＝平均）。"""
    from ..features import service as features_service

    table = features_service.read_table(spec['feature_set_id'])
    cols = spec['columns']
    rows = {r['image_id']: r for r in table}
    values = np.array([[float(rows[i][c]) if i in rows and rows[i].get(c) not in (None, '') else np.nan for c in cols] for i in image_ids], float)
    fit = values[[k for k, i in enumerate(image_ids) if dev is None or i in dev]] if dev else values  # 只用開發集算平均與標準差
    if len(fit) == 0:
        fit = values
    with np.errstate(all='ignore'):
        mean, std = np.nanmean(fit, 0), np.nanstd(fit, 0)
    std[~np.isfinite(std) | (std == 0)] = 1.0
    mean[~np.isfinite(mean)] = 0.0
    z = (values - mean) / std
    if spec.get('shuffle'):  # 負對照：打亂特徵，若成績沒下降，代表特徵沒有幫助
        rng = np.random.default_rng(0)
        z = z[rng.permutation(len(z))]
    z = np.nan_to_num(z, nan=0.0)
    stats = {'kind': 'measures', 'columns': cols, 'mean': mean.tolist(), 'std': std.tolist(), 'feature_set_id': spec['feature_set_id']}
    return {i: z[k].tolist() for k, i in enumerate(image_ids) if i in rows}, stats
