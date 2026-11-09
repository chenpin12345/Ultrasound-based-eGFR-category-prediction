"""評估指標（純 numpy／scipy，不需要 PyTorch）。

- 二元：AUC、準確率、敏感度、特異度、Brier、ECE。
- 有序分級：QWK（quadratic weighted kappa）、準確率、MAE。
- 校準：temperature scaling（在 out-of-fold logits 上擬合）。
- 不確定性：以「病人」為單位重抽的 bootstrap 信賴區間（同一病人的影像一起抽，避免低估）。
- 比較兩個模型：Nadeau-Bengio 校正的重複交叉驗證 t 檢定。
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable

import numpy as np
from scipy import optimize, stats

from ..annotation.agreement import weighted_kappa


def auc(y: np.ndarray, p: np.ndarray) -> float | None:
    from sklearn.metrics import roc_auc_score

    if len(set(np.asarray(y).tolist())) < 2:
        return None
    return float(roc_auc_score(y, p))


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """二元的 expected calibration error：每個機率區間的 |平均預測 − 實際比例|，依樣本數加權。"""
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(total)


def binary_metrics(y: np.ndarray, p: np.ndarray, threshold: float = 0.5) -> dict[str, Any]:
    y, p = np.asarray(y, int), np.asarray(p, float)
    pred = (p >= threshold).astype(int)
    tp, tn = int(((pred == 1) & (y == 1)).sum()), int(((pred == 0) & (y == 0)).sum())
    fp, fn = int(((pred == 1) & (y == 0)).sum()), int(((pred == 0) & (y == 1)).sum())
    return {
        'n': int(len(y)),
        'auc': auc(y, p),
        'accuracy': (tp + tn) / len(y) if len(y) else None,
        'sensitivity': tp / (tp + fn) if tp + fn else None,
        'specificity': tn / (tn + fp) if tn + fp else None,
        'brier': float(np.mean((p - y) ** 2)) if len(y) else None,
        'ece': ece(y, p) if len(y) else None,
    }


def ordinal_metrics(y: np.ndarray, probs: np.ndarray) -> dict[str, Any]:
    y = np.asarray(y, int)
    pred = probs.argmax(1)
    expected = probs @ np.arange(probs.shape[1])
    return {
        'n': int(len(y)),
        'qwk': weighted_kappa(y.tolist(), pred.tolist(), k=probs.shape[1]),
        'accuracy': float((pred == y).mean()) if len(y) else None,
        'mae': float(np.abs(expected - y).mean()) if len(y) else None,
    }


def fit_temperature(logits: np.ndarray, y: np.ndarray, to_probs: Callable[[np.ndarray, float], np.ndarray]) -> float:
    """找出讓 out-of-fold 負對數概似最小的溫度 T（> 0）。"""
    y = np.asarray(y, int)

    def nll(log_t: float) -> float:
        probs = to_probs(logits, float(np.exp(log_t)))
        return float(-np.log(np.clip(probs[np.arange(len(y)), y], 1e-8, 1)).mean())

    res = optimize.minimize_scalar(nll, bounds=(-3, 3), method='bounded')
    return float(np.exp(res.x))


def aggregate(rows: list[dict[str, Any]], key: Callable[[dict[str, Any]], Any], value: str) -> dict[Any, float]:
    """把影像層級的機率平均成病人（或病人＋側別）層級。"""
    groups: dict[Any, list[float]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(float(r[value]))
    return {k: float(np.mean(v)) for k, v in groups.items()}


def bootstrap_ci(
    rows: list[dict[str, Any]], metric: Callable[[list[dict[str, Any]]], float | None], *, n: int = 1000, seed: int = 0, cluster: str = 'patient_id'
) -> tuple[float | None, float | None]:
    """以病人為單位重抽，回傳 95% 信賴區間。"""
    by: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[r[cluster]].append(r)
    keys = list(by)
    if len(keys) < 3:
        return None, None
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n):
        pick = rng.choice(len(keys), len(keys), replace=True)
        v = metric([r for i in pick for r in by[keys[i]]])
        if v is not None and not math.isnan(v):
            values.append(v)
    if len(values) < n * 0.5:
        return None, None
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def corrected_ttest(diffs: list[float], n_train: int, n_test: int) -> dict[str, Any]:
    """Nadeau & Bengio（2003）：交叉驗證各折的指標差，變異數乘上 (1/J + n_test/n_train) 校正折與折之間的相關。"""
    d = np.asarray(diffs, float)
    j = len(d)
    if j < 2:
        return {'mean_diff': float(d.mean()) if j else None, 't': None, 'p': None, 'folds': j}
    var = d.var(ddof=1)
    denom = math.sqrt((1 / j + n_test / max(1, n_train)) * var) if var > 0 else 0.0
    if denom == 0:
        return {'mean_diff': float(d.mean()), 't': None, 'p': None, 'folds': j}
    t = float(d.mean() / denom)
    p = float(2 * stats.t.sf(abs(t), df=j - 1))
    return {'mean_diff': float(d.mean()), 't': t, 'p': p, 'folds': j}


# ---------- eGFR 2／3／5 類（M2.5，決策 D22）----------
def fast_auc(y: np.ndarray, p: np.ndarray) -> float | None:
    """排名法 AUC（給 bootstrap 用，比 sklearn 快）；同分取平均名次，結果和 roc_auc_score 相同。"""
    y, p = np.asarray(y, int), np.asarray(p, float)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return None
    ranks = stats.rankdata(p)
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def confusion(y: np.ndarray, pred: np.ndarray, k: int) -> list[list[int]]:
    m = np.zeros((k, k), int)
    for t, q in zip(np.asarray(y, int), np.asarray(pred, int)):
        m[t, q] += 1
    return m.tolist()


def egfr_metrics(y: np.ndarray, probs: np.ndarray, k: int) -> dict[str, Any]:
    """eGFR 的指標：共同的尺 AUC(<60)（以及類別數允許時的 AUC(<30)、AUC(<90)、AUC(<15)）；
    2 類另有敏感度、特異度等二元指標；3、5 類另有 QWK、MAE、準確率、各類敏感度、混淆矩陣。"""
    from ..data import egfr as E

    y, probs = np.asarray(y, int), np.asarray(probs, float)
    out: dict[str, Any] = {'n': int(len(y)), 'k': k}
    for cut in (90, 60, 30, 15):
        p, t = E.p_lt(probs, k, cut), E.y_lt(y, k, cut)
        if p is not None:
            out[f'auc_lt{cut}'] = fast_auc(t, p)
    p60 = E.p_lt(probs, k, 60)
    y60 = E.y_lt(y, k, 60)
    out['brier_lt60'] = float(np.mean((p60 - y60) ** 2)) if len(y) else None
    out['ece_lt60'] = ece(y60, p60) if len(y) else None
    if k == 2:
        out.update({key: v for key, v in binary_metrics(y, probs[:, 1]).items() if key != 'n'})
    else:
        pred = probs.argmax(1)
        out.update({key: v for key, v in ordinal_metrics(y, probs).items() if key != 'n'})
        out['confusion'] = confusion(y, pred, k)
        out['per_class_recall'] = [float((pred[y == c] == c).mean()) if (y == c).any() else None for c in range(k)]
        out['class_counts'] = np.bincount(y, minlength=k).tolist()
    return out


def paired_bootstrap(
    rows: list[dict[str, Any]], metric: Callable[[list[dict[str, Any]]], float | None], *, n: int = 2000, seed: int = 0
) -> dict[str, Any]:
    """配對 bootstrap：rows 是同一批病人，每列有 a、b 兩個模型的資料；metric(rows, side) 算出單邊的值。
    回傳差異（a − b）、95% 信賴區間與雙尾 p 值（重抽差異跨過 0 的比例 × 2）。"""
    if len(rows) < 3:
        return {'diff': None, 'ci': [None, None], 'p': None, 'n': len(rows)}
    a = metric(rows, 'a')
    b = metric(rows, 'b')
    if a is None or b is None:
        return {'a': a, 'b': b, 'diff': None, 'ci': [None, None], 'p': None, 'n': len(rows)}
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n):
        pick = [rows[i] for i in rng.choice(len(rows), len(rows), replace=True)]
        va, vb = metric(pick, 'a'), metric(pick, 'b')
        if va is not None and vb is not None:
            diffs.append(va - vb)
    if len(diffs) < n * 0.5:
        return {'a': a, 'b': b, 'diff': a - b, 'ci': [None, None], 'p': None, 'n': len(rows)}
    d = np.asarray(diffs)
    p = float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())))
    return {'a': a, 'b': b, 'diff': float(a - b), 'ci': [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))], 'p': p, 'n': len(rows), 'boot': len(d)}
