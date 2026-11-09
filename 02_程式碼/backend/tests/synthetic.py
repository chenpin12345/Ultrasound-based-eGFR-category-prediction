"""產生假的超音波截圖（不含任何真實病人資料），版面模仿 Toshiba 與 Canon 兩種機型。

每張圖都有：上方標頭（假病歷號、假姓名、年齡性別）、右側參數、左側深度尺刻度點、
扇形掃描區、青色 caliper 十字與虛線、左下 Dist A／B 量測框、側別文字。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX


@dataclass
class Truth:
    age: int
    sex: str
    dist_a: float
    dist_b: float
    side: str
    px_per_cm: float
    gain: int | None
    kidney_center: tuple[int, int] | None = None  # 腎臟橢圓中心；長短軸見 kidney_mask()


def _text(img, text, x, y, scale, color=(235, 235, 235), thick=None):
    cv2.putText(img, text, (int(x), int(y)), FONT, scale, color, thick or max(1, int(scale * 2)), cv2.LINE_AA)


def _sector(img, top_y, bottom_y, apex_half, base_left, base_right, rng):
    h, w = img.shape[:2]
    cx = (base_left + base_right) / 2
    poly = np.array([[cx - apex_half, top_y], [cx + apex_half, top_y], [base_right, bottom_y], [base_left, bottom_y]], np.int32)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [poly], 255)
    noise = rng.normal(70, 25, (h, w)).clip(10, 200).astype(np.uint8)
    noise = cv2.GaussianBlur(noise, (5, 5), 0)
    # 一個像腎臟的橢圓：較暗的皮質＋較亮的腎竇
    kidney = np.zeros((h, w), np.uint8)
    kc = (int(cx), int((top_y + bottom_y) / 2))
    cv2.ellipse(kidney, kc, (int(w * 0.17), int(h * 0.09)), -12, 0, 360, 1, -1)
    noise[kidney == 1] = (noise[kidney == 1] * 0.7).astype(np.uint8)
    cv2.ellipse(noise, kc, (int(w * 0.08), int(h * 0.025)), -12, 0, 360, 170, -1)
    for c in range(3):
        img[:, :, c][mask > 0] = noise[mask > 0]
    return mask, kc


def kidney_mask(width: int, height: int, center: tuple[int, int], sinus: bool = False) -> np.ndarray:
    """_sector 畫的腎臟（或腎竇）橢圓，當作測試的正確答案。"""
    m = np.zeros((height, width), np.uint8)
    axes = (int(width * 0.08), int(height * 0.025)) if sinus else (int(width * 0.17), int(height * 0.09))
    cv2.ellipse(m, center, axes, -12, 0, 360, 1, -1)
    return m > 0


def _ruler(img, x, top, px_per_cm, count, size):
    for i in range(count + 1):
        y = int(top + i * px_per_cm)
        cv2.circle(img, (int(x), y), size, (230, 230, 230), -1)
        if i in (0, 5, 10):
            _text(img, str(i), x - size * 9, y + size * 2, size * 0.35 + 0.25)


def _caliper(img, p1, p2, size):
    cyan = (230, 220, 40)  # BGR：藍綠高、紅低
    for p in (p1, p2):
        cv2.drawMarker(img, (int(p[0]), int(p[1])), cyan, cv2.MARKER_CROSS, size * 4, max(1, size // 2))
    steps = 18
    for i in range(1, steps):
        x = p1[0] + (p2[0] - p1[0]) * i / steps
        y = p1[1] + (p2[1] - p1[1]) * i / steps
        cv2.circle(img, (int(x), int(y)), max(1, size // 2), cyan, -1)
    _text(img, 'A', p1[0] - size * 5, p1[1] + size * 2, size * 0.25 + 0.3, cyan)


def toshiba(width: int, height: int, seed: int = 0, side: str = 'left') -> tuple[np.ndarray, Truth]:
    rng = np.random.default_rng(seed)
    s = width / 622
    img = np.zeros((height, width, 3), np.uint8)
    img[: int(0.09 * height)] = (55, 45, 45)
    _text(img, 'TOSHIBA', 6 * s, 30 * s, 0.45 * s)
    _text(img, '0012345:TEST PATIENT:66:F', 120 * s, 25 * s, 0.5 * s)
    _text(img, 'KIDNEY', 380 * s, 40 * s, 0.45 * s)
    for i, t in enumerate(['P100', '6C3', '4.2', '21fps', 'DR70', '2DG', '78']):
        _text(img, t, 560 * s, (75 + i * 20) * s, 0.42 * s)
    mask, kc = _sector(img, int(55 * s), int(380 * s), 80 * s, 95 * s, 525 * s, rng)
    px_per_cm = 26.0 * s
    _ruler(img, 96 * s, 70 * s, px_per_cm, 11, max(2, int(2 * s)))
    _caliper(img, (kc[0] - 120 * s, kc[1] + 15 * s), (kc[0] + 120 * s, kc[1] - 30 * s), max(2, int(2 * s)))
    _text(img, f'{"L" if side == "left" else "R"}-Kidney', 275 * s, 418 * s, 0.6 * s)
    cv2.rectangle(img, (int(32 * s), int(445 * s)), (int(320 * s), int(468 * s)), (200, 200, 200), 1)
    _text(img, 'Dist A 102.2mm', 36 * s, 462 * s, 0.5 * s)
    _text(img, 'Dist B 44.2mm', 185 * s, 462 * s, 0.5 * s)
    return img, Truth(66, 'F', 102.2, 44.2, side, px_per_cm, None, kc)


def canon(width: int, height: int, seed: int = 0) -> tuple[np.ndarray, Truth]:
    rng = np.random.default_rng(seed)
    s = width / 1600
    img = np.zeros((height, width, 3), np.uint8)
    img[: int(0.08 * height)] = (90, 50, 35)
    _text(img, 'Canon', 10 * s, 40 * s, 1.0 * s)
    _text(img, '0099999:SAMPLE NAME', 185 * s, 45 * s, 1.1 * s)
    _text(img, 'TEST HOSPITAL', 185 * s, 85 * s, 0.8 * s)
    _text(img, 'F 67', 1085 * s, 45 * s, 1.0 * s)
    for i, t in enumerate(['6C1', 'diffT5.0', '20 fps', 'Qscan', 'G:83', 'DR:70']):
        _text(img, t, 1460 * s, (300 + i * 45) * s, 0.8 * s)
    mask, kc = _sector(img, int(150 * s), int(965 * s), 190 * s, 190 * s, 1410 * s, rng)
    px_per_cm = 59.0 * s
    _ruler(img, 135 * s, 205 * s, px_per_cm, 12, max(2, int(4 * s)))
    _caliper(img, (kc[0] - 320 * s, kc[1] + 90 * s), (kc[0] + 290 * s, kc[1] - 80 * s), max(2, int(4 * s)))
    cv2.rectangle(img, (int(50 * s), int(1090 * s)), (int(410 * s), int(1185 * s)), (220, 220, 220), 2)
    _text(img, 'Dist A 108.3mm', 65 * s, 1125 * s, 0.9 * s)
    _text(img, 'Dist B 58.1mm', 65 * s, 1170 * s, 0.9 * s)
    return img, Truth(67, 'F', 108.3, 58.1, 'unknown', px_per_cm, 83, kc)


def bodymark(img: np.ndarray, rect: dict[str, float], view: str, probe: str) -> None:
    """在體表示意圖區域畫身體輪廓：view='front' 畫肚臍「×」，'back' 畫脊椎直線；
    probe='viewer_left'／'viewer_right' 是探頭棒在畫面上的位置。"""
    h, w = img.shape[:2]
    x0, y0 = int(rect['x'] / 100 * w), int(rect['y'] / 100 * h)
    rw, rh = int(rect['w'] / 100 * w), int(rect['h'] / 100 * h)
    img[y0:y0 + rh, x0:x0 + rw] = 0
    def pt(fx, fy):
        return int(x0 + fx * rw), int(y0 + fy * rh)
    white, t = (235, 235, 235), max(1, rw // 90)
    for side in (0.3, 0.7):  # 軀幹兩側
        cv2.polylines(img, [np.array([pt(side, .25), pt(side + (.04 if side < .5 else -.04), .5), pt(side, .78)], np.int32)], False, white, t)
    cv2.polylines(img, [np.array([pt(.36, .3), pt(.45, .26), pt(.5, .3), pt(.55, .26), pt(.64, .3)], np.int32)], False, white, t)  # 肋骨弧線
    if view == 'front':
        d = max(3, rw // 30)
        cx, cy = pt(.5, .55)
        cv2.line(img, (cx - d, cy - d), (cx + d, cy + d), white, t)
        cv2.line(img, (cx - d, cy + d), (cx + d, cy - d), white, t)
    else:
        cv2.line(img, pt(.5, .36), pt(.5, .64), white, t)  # 脊椎（真實示意圖中不和肋骨弧線相連）
    px = .4 if probe == 'viewer_left' else .6
    cv2.rectangle(img, pt(px - .012, .4), pt(px + .012, .56), (230, 220, 40), -1)  # 青色探頭棒（BGR）


def write(path: Path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    buf.tofile(str(path))


def make_dataset(folder: Path) -> list[tuple[str, Truth]]:
    """四種尺寸各 2 張。檔名模仿真實資料的「eGFR_序號」格式（數值是假的）。"""
    out = []
    specs = [
        ('30.5', lambda i: toshiba(622, 500, i, 'left')),
        ('30.5', lambda i: toshiba(1493, 1200, i + 10, 'right')),
        ('72.1', lambda i: canon(1600, 1200, i)),
        ('72.1', lambda i: canon(666, 500, i + 20)),
    ]
    n = 1
    for prefix, make in specs:
        for i in range(2):
            img, truth = make(i)
            name = f'{prefix}_{n}.jpg'
            write(folder / name, img)
            out.append((name, truth))
            n += 1
    return out
