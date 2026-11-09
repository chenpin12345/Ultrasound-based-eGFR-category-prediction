"""單張影像的去識別化與資訊擷取。

流程：讀取原圖 → OCR 讀出需要的欄位（標頭原文立即丟棄）→ 依範本遮蓋文字區 →
找出掃描扇形區 → 偵測 caliper → 產生兩種輸出：
- 模型輸入用：灰階、文字區清空、caliper 用 inpainting 修補、扇形區外清空。
- 灰階計算用：灰階＋alpha，caliper 與扇形區外的 alpha 為 0（無效），不修補，避免用推算的像素算比值。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from . import bodymark, ocr
from .templates import to_pixels


@dataclass
class DeidResult:
    model_image: np.ndarray  # uint8 灰階
    calc_gray: np.ndarray  # uint8 灰階
    calc_valid: np.ndarray  # uint8 0/255
    age: int | None = None
    sex: str | None = None
    side: str | None = None
    side_source: str = ''  # 'bodymark'（體表示意圖）或 'ocr'（側別文字）
    dist_a_mm: float | None = None
    dist_b_mm: float | None = None
    pixel_spacing_mm: float | None = None
    spacing_check: str = 'missing'
    scan_params: dict[str, Any] = field(default_factory=dict)
    caliper_pixels: int = 0
    review_reasons: list[str] = field(default_factory=list)


def read_image(path: Path) -> np.ndarray:
    """支援中文路徑的讀檔（cv2.imread 不支援非 ASCII 路徑）。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('無法解碼影像')
    return image


def write_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode('.png', image)
    if not ok:
        raise ValueError('無法編碼 PNG')
    tmp = path.with_suffix('.part')
    buf.tofile(str(tmp))
    tmp.replace(path)


def write_gray_alpha(path: Path, gray: np.ndarray, valid: np.ndarray) -> None:
    """灰階＋alpha 的 PNG（LA 模式）。alpha=0 代表這個像素不能用來計算灰階。"""
    from PIL import Image as PILImage

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.part')
    PILImage.fromarray(np.dstack([gray, valid]), 'LA').save(tmp, format='PNG')
    tmp.replace(path)


def read_gray_alpha(path: Path) -> tuple[np.ndarray, np.ndarray]:
    from PIL import Image as PILImage

    with PILImage.open(path) as im:
        arr = np.array(im.convert('LA'))
    return arr[:, :, 0], arr[:, :, 1]


def write_jpeg(path: Path, image: np.ndarray, quality: int = 85) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError('無法編碼 JPEG')
    tmp = path.with_suffix('.part')
    buf.tofile(str(tmp))
    tmp.replace(path)


def crop(image: np.ndarray, rect: dict[str, float]) -> tuple[np.ndarray, int, int]:
    h, w = image.shape[:2]
    x0, y0, x1, y1 = to_pixels(rect, w, h)
    return image[y0:y1, x0:x1], x0, y0


def ruler_spacing(gray: np.ndarray, rect: dict[str, float], *, cross_check: bool = True) -> tuple[float | None, str]:
    """深度尺：刻度點每 1 cm 一個，取相鄰刻度間距的中位數 → 每像素 mm。
    cross_check=True 時再用 OCR 讀到的「0」「5」數字位置交叉確認（比較慢，匯入時只抽前幾張做）。"""
    region, _, _ = crop(gray, rect)
    if region.size == 0:
        return None, 'missing'
    h, w = gray.shape[:2]
    _, binary = cv2.threshold(region, 120, 255, cv2.THRESH_BINARY)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    max_side = max(3, int(0.02 * w))
    points = [
        (centroids[i][0], centroids[i][1])
        for i in range(1, count)
        if stats[i, cv2.CC_STAT_AREA] >= 1 and stats[i, cv2.CC_STAT_WIDTH] <= max_side and stats[i, cv2.CC_STAT_HEIGHT] <= max_side
    ]
    tick_px = None
    if len(points) >= 4:
        xs = np.array([p[0] for p in points])
        # 取點最多的那一欄（數字筆畫也會被抓到，但通常分散在別的 x）
        bins = np.round(xs / max(2.0, 0.006 * w)).astype(int)
        values, counts = np.unique(bins, return_counts=True)
        column = values[np.argmax(counts)]
        ys = np.sort(np.array([p[1] for p, b in zip(points, bins) if b == column]))
        diffs = np.diff(ys)
        diffs = diffs[diffs > 0.01 * h]
        if len(diffs) >= 3:
            tick_px = float(np.median(diffs))
    ocr_px = None
    if not cross_check and tick_px:
        return 10.0 / tick_px, 'ticks_only'
    tokens = ocr.read_tokens(region, min_confidence=0.6)
    marks = {t.text.strip(): t.cy for t in tokens if t.text.strip() in {'0', '5', '10'}}
    if '0' in marks and '5' in marks and marks['5'] > marks['0']:
        ocr_px = (marks['5'] - marks['0']) / 5
    elif '5' in marks and '10' in marks and marks['10'] > marks['5']:
        ocr_px = (marks['10'] - marks['5']) / 5
    if tick_px and ocr_px:
        if abs(tick_px - ocr_px) / ocr_px <= 0.05:
            return 10.0 / tick_px, 'ok'
        return 10.0 / ocr_px, 'mismatch'
    if tick_px:
        return 10.0 / tick_px, 'ticks_only'
    if ocr_px:
        return 10.0 / ocr_px, 'ocr_only'
    return None, 'missing'


def sector_mask(gray: np.ndarray) -> np.ndarray:
    """掃描扇形區：遮蓋文字後，最大的非黑色連通區，再取凸包填滿。"""
    h, w = gray.shape[:2]
    _, binary = cv2.threshold(gray, 6, 255, cv2.THRESH_BINARY)
    k = max(3, int(0.01 * w)) | 1
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros((h, w), np.uint8)
    if not contours:
        return mask
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 0.05 * h * w:
        return mask
    cv2.fillPoly(mask, [cv2.convexHull(largest)], 255)
    return mask


def caliper_mask(bgr: np.ndarray, within: np.ndarray) -> np.ndarray:
    """caliper 十字、虛線與 A／B 字母是青色（藍綠高、紅低）。"""
    b, g, r = (bgr[:, :, i].astype(np.int16) for i in range(3))
    cyan = (b > 110) & (g > 110) & (b - r > 50) & (g - r > 50)
    mask = (cyan & (within > 0)).astype(np.uint8) * 255
    if mask.any():
        size = max(3, int(0.004 * bgr.shape[1]) * 2 + 1)
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    return mask


def process(
    bgr: np.ndarray,
    regions: list[dict[str, float]],
    readers: dict[str, dict[str, float]],
    *,
    read_text: bool = True,
    ruler_cross_check: bool = True,
) -> DeidResult:
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    reasons: list[str] = []
    fields: dict[str, Any] = {}

    if read_text:
        # 小尺寸影像（寬度 < 1000）的文字很小，放大 2 倍再辨識；大尺寸影像的文字夠大，縮小以加快速度
        zoom = 2.0 if w < 1000 else 0.6

        def read(rect_key: str):
            region = crop(bgr, readers[rect_key])[0]
            if zoom != 1.0 and region.size:
                region = cv2.resize(region, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
            return ocr.read_tokens(region)

        header_tokens = read('header')
        header = ocr.parse_header(ocr.joined(header_tokens))
        del header_tokens  # 標頭原文含個資，立即丟棄
        fields['age'], fields['sex'] = header.age, header.sex
        measure = ocr.parse_measure(ocr.joined(read('measure')))
        fields['dist_a_mm'], fields['dist_b_mm'] = measure.dist_a_mm, measure.dist_b_mm
        # 真實影像的側別畫在體表示意圖上；讀不到時才用側別文字（舊格式或測試影像）
        if 'bodymark' in readers:
            mark = bodymark.detect(crop(bgr, readers['bodymark'])[0])
            if mark.side:
                fields['side'], fields['side_source'] = mark.side, 'bodymark'
        if not fields.get('side'):
            side = ocr.parse_side(ocr.joined(read('side')))
            if side:
                fields['side'], fields['side_source'] = side, 'ocr'
        params = ocr.parse_params(read('params'))
        fields['scan_params'] = {'gain': params.gain, 'tokens': params.tokens}
        spacing, check = ruler_spacing(gray, readers['ruler'], cross_check=ruler_cross_check)
        fields['pixel_spacing_mm'], fields['spacing_check'] = spacing, check
        if spacing is None:
            reasons.append('讀不到深度尺')
        elif check == 'mismatch':
            reasons.append('深度尺刻度與數字不一致')
        if header.age is None:
            reasons.append('讀不到年齡性別')

    masked = gray.copy()
    for rect in regions:
        x0, y0, x1, y1 = to_pixels(rect, w, h)
        masked[y0:y1, x0:x1] = 0

    sector = sector_mask(masked)
    if not sector.any():
        reasons.append('找不到掃描扇形區')
        sector = np.full((h, w), 255, np.uint8)
        for rect in regions:
            x0, y0, x1, y1 = to_pixels(rect, w, h)
            sector[y0:y1, x0:x1] = 0

    calipers = caliper_mask(bgr, sector)
    caliper_count = int((calipers > 0).sum())

    model = cv2.inpaint(masked, calipers, 3, cv2.INPAINT_TELEA) if caliper_count else masked
    model = cv2.bitwise_and(model, model, mask=sector)
    valid = cv2.bitwise_and(sector, cv2.bitwise_not(calipers))
    calc = cv2.bitwise_and(masked, masked, mask=valid)

    return DeidResult(
        model_image=model,
        calc_gray=calc,
        calc_valid=valid,
        age=fields.get('age'),
        sex=fields.get('sex'),
        side=fields.get('side'),
        side_source=fields.get('side_source', ''),
        dist_a_mm=fields.get('dist_a_mm'),
        dist_b_mm=fields.get('dist_b_mm'),
        pixel_spacing_mm=fields.get('pixel_spacing_mm'),
        spacing_check=fields.get('spacing_check', 'missing'),
        scan_params=fields.get('scan_params', {}),
        caliper_pixels=caliper_count,
        review_reasons=reasons,
    )


def residual_check(model_image: np.ndarray) -> list[str]:
    """在去識別化後的影像上再跑一次 OCR，找個資殘留。只回傳類型。
    大影像先縮到最長邊 1000 px（標頭文字在原圖約 40 px 高，縮小後仍可辨識），速度約快 3 倍。"""
    h, w = model_image.shape[:2]
    if max(h, w) > 1000:
        scale = 1000 / max(h, w)
        model_image = cv2.resize(model_image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return ocr.looks_like_phi(ocr.read_tokens(model_image, min_confidence=0.6))


def phash(gray: np.ndarray) -> str:
    """64 位元感知雜湊，用來找近似重複影像（例如同一段影片的相鄰影格）。"""
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(small)[:8, :8]
    bits = (dct > np.median(dct[1:, 1:])).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f'{value:016x}'


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count('1')


def thumbnail(gray: np.ndarray, max_side: int = 384) -> np.ndarray:
    h, w = gray.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return gray
    return cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def blurred_preview(bgr: np.ndarray, regions: list[dict[str, float]], readers: dict[str, dict[str, float]]) -> np.ndarray:
    """範本編輯用的預覽：整張強烈模糊（文字無法辨識），再畫出遮蓋區與讀取區，讓人確認位置。"""
    h, w = bgr.shape[:2]
    # 馬賽克：每格約為影像寬度的 1/60（1600 寬約 26 px、622 寬約 10 px），大於標頭文字的筆畫與字高的一半，
    # 文字無法辨識；扇形區與版面輪廓仍看得出來。高斯模糊或平滑放大都會讓大字隱約可辨，所以不採用。
    block = max(8, w // 60)
    small = cv2.resize(bgr, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    out = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    overlay = out.copy()
    for rect in regions:
        x0, y0, x1, y1 = to_pixels(rect, w, h)
        cv2.rectangle(overlay, (x0, y0), (x1, y1), (60, 60, 200), -1)
    out = cv2.addWeighted(overlay, 0.45, out, 0.55, 0)
    for name, rect in readers.items():
        x0, y0, x1, y1 = to_pixels(rect, w, h)
        cv2.rectangle(out, (x0, y0), (x1, y1), (85, 180, 224), max(1, w // 400))
    return out


def scan_params_json(result: DeidResult) -> str:
    return json.dumps(result.scan_params, ensure_ascii=False)
