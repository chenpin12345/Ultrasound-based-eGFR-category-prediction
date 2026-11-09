"""從右下角的體表示意圖判斷左右腎。

真實影像上沒有「LT／RT KIDNEY」文字（標頭的 KIDNEY 只是檢查項目名稱），側別只畫在體表示意圖：
白色身體輪廓，加上一條彩色探頭棒（青、淡青、黃、橘）。判斷規則（由專案負責人向技師確認）：
- 輪廓中有「×」＝肚臍 → 正面圖（病人仰躺）：探頭在畫面左邊＝病人右側
- 沒有「×」、中間是一條直線＝脊椎 → 背面圖（病人趴著）：探頭在畫面左邊＝病人左側
探頭太靠近中線、或認不出圖樣時回傳 None，留給人工設定。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# 探頭棒中心離中線至少要有軀幹寬度的這個比例，才判斷左右
MIN_OFFSET = 0.08


@dataclass
class BodyMark:
    side: str | None
    view: str | None  # 'front'（有肚臍）、'back'（有脊椎）
    reason: str = ''
    probe_x: float | None = None  # 以示意圖區域寬度為 1 的位置（除錯與介面顯示用）
    midline_x: float | None = None


def _masks(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """白色線條（輪廓、×、脊椎）與彩色探頭。Canon 的探頭是淡青色，飽和度只比白色高一些，所以門檻要分開。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    white = ((s < 35) & (v > 100)).astype(np.uint8)
    bright = ((s < 35) & (v > 170)).astype(np.uint8)
    color = ((s > 45) & (v > 120)).astype(np.uint8)
    return white, bright, color


def _pictogram(white: np.ndarray, color: np.ndarray) -> tuple[int, int, int, int] | None:
    """示意圖的範圍 (左, 上, 右, 下)。
    先去掉碰到裁切邊緣的東西（超音波影像的角落、下方工具列、量測文字框、分隔線），
    再用橫向較寬的核把輪廓兩側、肋骨弧線、探頭連成一塊（側別示意圖的左右輪廓相距較遠），取最大的一塊。"""
    h, w = white.shape
    lines = white | color
    n, labels, stats, _ = cv2.connectedComponentsWithStats(lines, 8)
    keep = np.zeros_like(lines)
    for i in range(1, n):
        x, y, bw, bh, _ = stats[i]
        if x <= 0 or y <= 0 or x + bw >= w or y + bh >= h:
            continue
        keep[labels == i] = 1
    kx, ky = max(3, int(0.16 * w)) | 1, max(3, int(0.05 * w)) | 1
    joined = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky)))
    n, blobs, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
    best = None
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bh < 0.25 * h or bw < 0.2 * w:
            continue
        if best is None or area > stats[best][4]:
            best = i
    if best is None:
        return None
    # 左右邊界用輪廓兩側的高線條決定：連在一起的畫格編號（例如「#110」）不會撐大範圍
    inside = keep & (blobs == best)
    n2, _, st2, _ = cv2.connectedComponentsWithStats(inside, 8)
    blob_h = stats[best][3]
    tall = [st2[i] for i in range(1, n2) if st2[i][3] >= 0.3 * blob_h]
    if len(tall) >= 2:
        left = min(int(t[0]) for t in tall)
        right = max(int(t[0] + t[2]) for t in tall)
        top = min(int(t[1]) for t in tall)
        bottom = max(int(t[1] + t[3]) for t in tall)
        if right - left >= 0.2 * w:
            return left, top, right, bottom
    x, y, bw, bh, _ = stats[best]
    return int(x + kx // 2), int(y + ky // 2), int(x + bw - kx // 2), int(y + bh - ky // 2)


def _probe(color: np.ndarray, box: tuple[int, int, int, int]) -> float | None:
    x0, y0, x1, y1 = box
    sub = color[y0:y1, x0:x1]
    n, _, stats, centroids = cv2.connectedComponentsWithStats(sub, 8)
    best = None
    for i in range(1, n):
        if stats[i][4] < 6:
            continue
        if best is None or stats[i][4] > stats[best][4]:
            best = i
    return float(x0 + centroids[best][0]) if best is not None else None


def _navel(bright: np.ndarray, box: tuple[int, int, int, int]) -> float | None:
    """在軀幹中段找「×」：小、接近正方形、四個角都有像素、像素集中在兩條對角線上。
    bright 用較高的亮度門檻：小圖的「×」只有約 5 像素，邊緣的灰色像素會讓它糊成一塊。"""
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    sub = bright[y0:y1, x0:x1]
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(sub, 8)
    best, best_score = None, 0.0
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        size = max(bw, bh)
        if not (3 <= size <= 0.25 * tw) or min(bw, bh) < 0.6 * size or area < 4:
            continue
        cy = (y + bh / 2) / th
        if not (0.25 <= cy <= 0.85):  # 上方是肋骨弧線，最下方是骨盆／臀部記號
            continue
        if not (0.15 <= (x + bw / 2) / tw <= 0.85):
            continue
        comp = labels[y:y + bh, x:x + bw] == i
        if not (0.15 <= comp.mean() <= 0.8):
            continue
        a, b = max(1, bh // 3), max(1, bw // 3)
        corners = (comp[:a, :b].any(), comp[:a, -b:].any(), comp[-a:, :b].any(), comp[-a:, -b:].any())
        if not all(corners):  # 「Y」「⊥」等記號缺角
            continue
        yy, xx = np.nonzero(comp)
        u, v = xx / max(bw - 1, 1), yy / max(bh - 1, 1)
        score = min((np.abs(u - v) < 0.25).mean(), (np.abs(u + v - 1) < 0.25).mean())
        if score > 0.25 and score > best_score:
            best, best_score = i, score
    return float(x0 + centroids[best][0]) if best is not None else None


def _spine(white: np.ndarray, box: tuple[int, int, int, int]) -> float | None:
    """在軀幹中間找脊椎：細長的垂直白線（不碰到兩側輪廓）。"""
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    sub = white[y0:y1, x0:x1]
    n, _, stats, centroids = cv2.connectedComponentsWithStats(sub, 8)
    best, best_len = None, 0
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bh < 0.18 * th or bw > max(3, 0.1 * tw):
            continue
        if not (0.25 <= centroids[i][0] / tw <= 0.75):
            continue
        if bh > best_len:
            best, best_len = i, bh
    return float(x0 + centroids[best][0]) if best is not None else None


def _hide_measure_box(bgr: np.ndarray) -> np.ndarray:
    """Toshiba 的量測框（深青底、白字，例如「D 9.9mm」）常蓋在示意圖下方，邊框會和身體輪廓連在一起；
    先把它整塊塗黑，避免輪廓被當成碰到邊緣的雜訊刪掉。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    teal = ((h >= 80) & (h <= 105) & (s > 100) & (v >= 40) & (v <= 130)).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(teal, 8)
    out = bgr
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bw >= 0.3 * bgr.shape[1] and area >= 0.4 * bw * bh:  # 寬而實心的長方形
            if out is bgr:
                out = bgr.copy()
            pad = max(2, bh // 4)
            out[max(0, y - pad):y + bh + pad, max(0, x - pad):x + bw + pad] = 0
    return out


def detect(bgr: np.ndarray) -> BodyMark:
    """bgr：體表示意圖所在的區域（原圖裁切）。"""
    if bgr.size == 0:
        return BodyMark(None, None, '沒有示意圖區域')
    if bgr.shape[1] < 200:  # 小圖放大，「×」才有足夠像素
        # 用整數倍放大：非整數倍（例如 124→200）時，裁切差 1 像素就會讓約 5 像素的「×」變形而認不出來
        f = int(np.ceil(200 / bgr.shape[1]))
        bgr = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)
    bgr = _hide_measure_box(bgr)
    w = bgr.shape[1]
    white, bright, color = _masks(bgr)
    box = _pictogram(white, color)
    if box is None:
        return BodyMark(None, None, '找不到體表示意圖')
    probe = _probe(color, box)
    if probe is None:
        return BodyMark(None, None, '找不到探頭標記')
    navel = _navel(bright, box)
    if navel is None:  # 大圖的「×」是淡灰色，達不到較高的亮度門檻
        navel = _navel(white, box)
    if navel is not None:
        view, mid = 'front', navel
    else:
        spine = _spine(white, box)
        if spine is None:
            return BodyMark(None, None, '認不出示意圖樣式', probe_x=probe / w)
        view, mid = 'back', spine
    offset = (probe - mid) / (box[2] - box[0])
    if abs(offset) < MIN_OFFSET:
        return BodyMark(None, view, '探頭太靠近中線', probe / w, mid / w)
    probe_on_viewer_left = offset < 0
    if view == 'front':
        side = 'right' if probe_on_viewer_left else 'left'
    else:
        side = 'left' if probe_on_viewer_left else 'right'
    return BodyMark(side, view, '', probe / w, mid / w)
