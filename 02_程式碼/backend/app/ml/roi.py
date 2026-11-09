"""④ 影像＋遮罩通道的輸入（M2.5，決策 D23、D35）。

- 裁切：以預測的腎臟（腎實質 ∪ 腎竇）外接框中心為中心，切固定實際大小（預設 160 mm）的正方形，超出影像的部分補 0。
  固定 mm 而不是「外接框加邊距」：後者會把每顆腎放大成差不多大，模型就看不到腎臟大小（腎長是 eGFR 的強預測因子）。
  160 mm 通常包含相鄰的肝或脾。
- 沒有像素間距時：腎臟外接框加 10% 邊距、補成正方形。找不到腎臟時：用整張影像（roi_fallback）。
- 4 個通道：灰階影像、腎實質、腎竇、肝或脾（0／1）。
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

ROI_MM = 160.0
KIDNEY_MIN_PX = 200
MARGIN = 0.10


def crop_box(label: np.ndarray, spacing_mm: float | None, roi_mm: float = ROI_MM) -> tuple[tuple[int, int, int, int], str]:
    """回傳 (x0, y0, x1, y1)（可以超出影像範圍）與方式：fixed_mm、bbox、whole。"""
    h, w = label.shape
    kidney = (label == 1) | (label == 2)
    if int(kidney.sum()) < KIDNEY_MIN_PX:
        return (0, 0, w, h), 'whole'
    ys, xs = np.nonzero(kidney)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    if spacing_mm and spacing_mm > 0:
        side = roi_mm / spacing_mm
        how = 'fixed_mm'
    else:
        side = max(xs.max() - xs.min(), ys.max() - ys.min()) * (1 + 2 * MARGIN)
        how = 'bbox'
    half = side / 2
    return (int(round(cx - half)), int(round(cy - half)), int(round(cx + half)), int(round(cy + half))), how


def crop(arr: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """裁切，超出影像的部分補 0。"""
    x0, y0, x1, y1 = box
    h, w = arr.shape[:2]
    out = np.zeros((y1 - y0, x1 - x0) + arr.shape[2:], arr.dtype)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = arr[sy0:sy1, sx0:sx1]
    return out


def mask_channels(label: np.ndarray) -> np.ndarray:
    """標籤圖 → 3 個 0／1 通道：腎實質、腎竇、肝或脾。"""
    return np.stack([(label == 1), (label == 2), (label == 3) | (label == 4)], 0).astype(np.uint8)


def prepare(gray: np.ndarray, label: np.ndarray, spacing_mm: float | None, size: int, roi_mm: float = ROI_MM) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """灰階影像與遮罩 → 同一個裁切後縮成 size × size：影像用 AREA、遮罩用最近鄰（保持 0／1）。"""
    box, how = crop_box(label, spacing_mm, roi_mm)
    img = crop(gray, box)
    channels = mask_channels(crop(label, box))
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    channels = np.stack([cv2.resize(c, (size, size), interpolation=cv2.INTER_NEAREST) for c in channels], 0)
    return img, channels, {'roi': how, 'box': list(box)}
