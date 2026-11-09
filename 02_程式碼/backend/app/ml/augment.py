"""前處理與任務專屬的資料增強。

- 影像等比例縮放後補邊成正方形（letterbox），預測可以準確換回原尺寸。
- 分類任務（分級、eGFR）不翻轉、不調亮度、不用 RandomErasing：回音分級的依據就是亮度與左右的解剖位置。
- 分割任務：影像與遮罩同步做幾何變換，影像可輕微調整 gamma。
- 每個樣本的隨機數由 (種子, epoch, 索引) 決定，停止後恢復的增強結果與不中斷時相同。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Letterbox:
    scale: float
    pad_x: int
    pad_y: int
    width: int
    height: int


def letterbox(img: np.ndarray, size: int, interpolation=cv2.INTER_AREA) -> tuple[np.ndarray, Letterbox]:
    h, w = img.shape[:2]
    scale = size / max(h, w)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=interpolation)
    out = np.zeros((size, size), img.dtype)
    px, py = (size - nw) // 2, (size - nh) // 2
    out[py:py + nh, px:px + nw] = resized
    return out, Letterbox(scale, px, py, w, h)


def unletterbox(arr: np.ndarray, box: Letterbox, interpolation=cv2.INTER_NEAREST) -> np.ndarray:
    nw, nh = max(1, round(box.width * box.scale)), max(1, round(box.height * box.scale))
    crop = arr[box.pad_y:box.pad_y + nh, box.pad_x:box.pad_x + nw]
    return cv2.resize(crop, (box.width, box.height), interpolation=interpolation)


def _affine(size: int, rng: np.random.Generator, rot: float, scale: float, shift: float, flip: bool) -> np.ndarray:
    angle = rng.uniform(-rot, rot)
    s = rng.uniform(1 - scale, 1 + scale)
    m = cv2.getRotationMatrix2D((size / 2, size / 2), angle, s)
    m[:, 2] += rng.uniform(-shift, shift, 2) * size
    if flip and rng.random() < 0.5:
        m = np.array([[-1, 0, size - 1], [0, 1, 0]], np.float64) @ np.vstack([m, [0, 0, 1]])
    return m


def augment_segmentation(img: np.ndarray, mask: np.ndarray, rng: np.random.Generator, flip: bool = False) -> tuple[np.ndarray, np.ndarray]:
    size = img.shape[0]
    m = _affine(size, rng, rot=10, scale=0.1, shift=0.05, flip=flip)  # 預設不翻轉：保留肝／脾和腎的相對位置（決策 D30）
    img = cv2.warpAffine(img, m, (size, size), flags=cv2.INTER_LINEAR, borderValue=0)
    mask = cv2.warpAffine(mask, m, (size, size), flags=cv2.INTER_NEAREST, borderValue=0)
    gamma = rng.uniform(0.85, 1.15)
    img = (np.clip((img / 255.0) ** gamma, 0, 1) * 255).astype(np.uint8)
    return img, mask


def augment_classification(img: np.ndarray, rng: np.random.Generator, extra: np.ndarray | None = None):
    """分類的輕微幾何增強。extra（遮罩通道，C×H×W）用同一個變換、最近鄰插值，維持 0／1；
    沒有 extra 時亂數的用法和以前完全相同，舊的訓練可以重現。"""
    size = img.shape[0]
    m = _affine(size, rng, rot=5, scale=0.05, shift=0.03, flip=False)
    out = cv2.warpAffine(img, m, (size, size), flags=cv2.INTER_LINEAR, borderValue=0)
    if extra is None:
        return out
    return out, np.stack([cv2.warpAffine(c, m, (size, size), flags=cv2.INTER_NEAREST, borderValue=0) for c in extra], 0)


def sample_rng(seed: int, epoch: int, index: int) -> np.random.Generator:
    return np.random.default_rng([seed, epoch, index])


# 正規化：隨機初始化用 0.5／0.25；ImageNet 初始化用 ImageNet 的灰階平均（三通道相同）
NORMALIZE = {'random': (0.5, 0.25), 'imagenet': (0.449, 0.226)}


def to_tensor_array(img: np.ndarray, init: str) -> np.ndarray:
    mean, std = NORMALIZE['imagenet' if init == 'imagenet' else 'random']
    return ((img.astype(np.float32) / 255.0 - mean) / std)[None]
