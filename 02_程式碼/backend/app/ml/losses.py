"""損失函數與輸出解碼。

- 分割：部分標註的交叉熵（同一群組的類別機率相加）＋只對單獨標註類別計算的 Dice。
- 分類：二元（pos_weight）、加權 CE、正確版 CORAL、CORN、SORD 軟標籤。
"""

from __future__ import annotations

import torch
import torch.nn.functional as F


def merge_matrix(groups_batch: list[list[list[int]]], num_classes: int, device) -> torch.Tensor:
    """(B, C, C)：M[b, t, c] = 1 表示第 b 張的標籤 t 與類別 c 在這份遮罩中無法區分。"""
    m = torch.zeros(len(groups_batch), num_classes, num_classes, device=device)
    for b, groups in enumerate(groups_batch):
        for g in groups:
            for t in g:
                m[b, t, g] = 1.0
    return m


def partial_ce(logits: torch.Tensor, target: torch.Tensor, merge: torch.Tensor) -> torch.Tensor:
    """-log Σ_{c ∈ group(target)} p_c。完整標註時等於一般的交叉熵。"""
    logp = F.log_softmax(logits.float(), 1)  # B,C,H,W
    b = torch.arange(target.shape[0], device=target.device)[:, None, None]
    allowed = merge[b, target].permute(0, 3, 1, 2)  # B,C,H,W
    masked = logp.masked_fill(allowed == 0, float('-inf'))
    return -torch.logsumexp(masked, 1).mean()


def partial_dice(logits: torch.Tensor, target: torch.Tensor, singles: torch.Tensor) -> torch.Tensor:
    """singles (B, C)：這張影像單獨標註的類別（不含背景）。只在這些類別上計算 soft Dice。"""
    probs = F.softmax(logits.float(), 1)
    onehot = F.one_hot(target, probs.shape[1]).permute(0, 3, 1, 2).float()
    inter = (probs * onehot).sum((2, 3))
    denom = probs.sum((2, 3)) + onehot.sum((2, 3))
    dice = (2 * inter + 1) / (denom + 1)
    w = singles.float()
    w[:, 0] = 0
    if w.sum() == 0:
        return logits.sum() * 0
    return 1 - (dice * w).sum() / w.sum()


def dice_per_class(pred: torch.Tensor, target: torch.Tensor, cls: int) -> float | None:
    p, t = pred == cls, target == cls
    denom = p.sum() + t.sum()
    return None if denom == 0 else float(2 * (p & t).sum() / denom)


# ---- 分類 ----
def coral_loss(logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    levels = (y[:, None] > torch.arange(logits.shape[1], device=y.device)[None]).float()
    return F.binary_cross_entropy_with_logits(logits.float(), levels)


def corn_loss(logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """CORN：第 k 個子任務只用 y ≥ k 的樣本，學 P(y > k | y ≥ k)。"""
    losses = []
    for k in range(logits.shape[1]):
        mask = y >= k
        if mask.any():
            losses.append(F.binary_cross_entropy_with_logits(logits[mask, k].float(), (y[mask] > k).float(), reduction='sum'))
    return torch.stack(losses).sum() / max(1, y.numel())


def sord_loss(logits: torch.Tensor, y: torch.Tensor, alpha: float = 2.0) -> torch.Tensor:
    classes = torch.arange(logits.shape[1], device=y.device)[None].float()
    soft = F.softmax(-alpha * (classes - y[:, None].float()).abs(), 1)
    return -(soft * F.log_softmax(logits.float(), 1)).sum(1).mean()


def classification_loss(head: str, logits: torch.Tensor, y: torch.Tensor, class_weights: torch.Tensor | None) -> torch.Tensor:
    if head == 'binary':
        pos_weight = class_weights[1:2] / class_weights[0:1] if class_weights is not None else None
        return F.binary_cross_entropy_with_logits(logits[:, 0].float(), y.float(), pos_weight=pos_weight)
    if head == 'ce':
        return F.cross_entropy(logits.float(), y, weight=class_weights)
    if head == 'coral':
        return coral_loss(logits, y)
    if head == 'corn':
        return corn_loss(logits, y)
    if head == 'sord':
        return sord_loss(logits, y)
    raise ValueError(head)


def class_probs(head: str, logits: torch.Tensor, temperature: float = 1.0) -> torch.Tensor:
    """各類別機率（B, K）。有序頭由累積機率 P(y > k) 換算。"""
    z = logits.float() / temperature
    if head == 'binary':
        p1 = torch.sigmoid(z[:, 0])
        return torch.stack([1 - p1, p1], 1)
    if head in ('ce', 'sord'):
        return F.softmax(z, 1)
    gt = torch.sigmoid(z)
    if head == 'corn':
        gt = torch.cumprod(gt, 1)
    gt = torch.minimum(gt, torch.cummin(gt, 1).values)  # 確保 P(y>k) 遞減
    ones, zeros = torch.ones_like(gt[:, :1]), torch.zeros_like(gt[:, :1])
    cum = torch.cat([ones, gt, zeros], 1)
    probs = (cum[:, :-1] - cum[:, 1:]).clamp_min(0)
    return probs / probs.sum(1, keepdim=True).clamp_min(1e-8)
