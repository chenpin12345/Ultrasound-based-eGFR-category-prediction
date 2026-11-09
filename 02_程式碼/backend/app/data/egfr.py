"""eGFR 類別的唯一定義（M2.5，決策 D22）。不依賴 PyTorch，切分、訓練、評估、報告都從這裡取。

第 0 類為腎功能最好：
- 2 類：≥60／<60
- 3 類：≥60／30–59／<30
- 5 類（KDIGO，G3a、G3b 合併）：≥90／60–89／30–59／15–29／<15

模型輸出各類機率後，P(eGFR < 切點) = 嚴重那一側的類別機率加總；所以 2、3、5 類的模型都能用 AUC(<60) 這把共同的尺比較。
"""

from __future__ import annotations

from typing import Any

import numpy as np

SCHEMES: dict[int, dict[str, Any]] = {
    2: {'cuts': (60,), 'classes': ('eGFR ≥ 60', 'eGFR < 60')},
    3: {'cuts': (60, 30), 'classes': ('eGFR ≥ 60', 'eGFR 30–59', 'eGFR < 30')},
    5: {'cuts': (90, 60, 30, 15), 'classes': ('eGFR ≥ 90', 'eGFR 60–89', 'eGFR 30–59', 'eGFR 15–29', 'eGFR < 15')},
}
KS = tuple(SCHEMES)
# 合併規則：原本的類別 → 合併後的類別
COLLAPSE: dict[tuple[int, int], tuple[int, ...]] = {(5, 3): (0, 0, 1, 2, 2), (5, 2): (0, 0, 1, 1, 1), (3, 2): (0, 1, 1)}


def check_k(k: int) -> int:
    if k not in SCHEMES:
        raise ValueError(f'eGFR 類別數只能是 {KS}')
    return k


def classes(k: int) -> list[str]:
    return list(SCHEMES[check_k(k)]['classes'])


def egfr_class(egfr: float, k: int) -> int:
    """eGFR 數值 → 類別（0 為腎功能最好）。邊界值屬於較好的一類，例如 60 → ≥60。"""
    return int(sum(egfr < c for c in SCHEMES[check_k(k)]['cuts']))


def lt_index(k: int, cut: int) -> int | None:
    """「eGFR < cut」從第幾類開始；這個切點不在此分類中時回傳 None。"""
    cuts = SCHEMES[check_k(k)]['cuts']
    return cuts.index(cut) + 1 if cut in cuts else None


def p_lt(probs: np.ndarray, k: int, cut: int) -> np.ndarray | None:
    """各類機率 → P(eGFR < cut)。"""
    i = lt_index(k, cut)
    if i is None:
        return None
    return np.asarray(probs, float)[..., i:].sum(-1)


def y_lt(y: np.ndarray, k: int, cut: int) -> np.ndarray | None:
    i = lt_index(k, cut)
    return None if i is None else (np.asarray(y) >= i).astype(int)


def collapse_probs(probs: np.ndarray, k: int, to: int) -> np.ndarray:
    if k == to:
        return np.asarray(probs, float)
    mapping = COLLAPSE[(k, to)]
    probs = np.asarray(probs, float)
    out = np.zeros(probs.shape[:-1] + (to,))
    for src, dst in enumerate(mapping):
        out[..., dst] += probs[..., src]
    return out


def collapse_labels(y: np.ndarray, k: int, to: int) -> np.ndarray:
    if k == to:
        return np.asarray(y, int)
    return np.asarray(COLLAPSE[(k, to)])[np.asarray(y, int)]


def groups_upper_bounds() -> list[float]:
    """依 5 類切點產生 patients.EGFR_GROUPS 的上界（由低到高，最後是無限大）。"""
    return [*sorted(SCHEMES[5]['cuts']), float('inf')]
