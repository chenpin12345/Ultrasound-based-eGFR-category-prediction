"""遮罩草稿：舊程式遮罩、MedSAM 重畫的腎臟、規則產生的肝／脾。

草稿存成 status='draft' 的遮罩版本（source 記錄來源），可以在標註編輯器裡直接修改。
人工「接受」後記下確認者；人工修改後存成新的 manual 版本。測試集只接受經人工確認的遮罩。

flags_json 的欄位：
- labeled：這個版本確實標了哪些結構（parenchyma／sinus／kidney／liver／spleen）。訓練時沒標的類別不算錯。
- review：'needed'（需要人工確認）或 'ok'；reasons：原因。
- 其他數值：iou_vs_legacy、edge_score、kidney（凸性、腎長 mm）、sinus（三群中心、皮質／腎竇亮度比、
  腎竇比例、是否疑似腎盂擴張）、organ（肝脾品質檢查）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from ..core.errors import AppError
from ..core.ids import now_iso, shard
from ..data import deid, storage
from ..db.models_research import Image, MaskAnnotation
from ..db.session import session_scope
from ..jobs.manager import JobContext, register
from .service import STRUCTURES, rasterize

# 舊程式（batch_crop.py）的作法：原圖縮放成 1600×1200，再從 (235, 90) 裁出 1024×1024
LEGACY_CANVAS = (1600, 1200)
LEGACY_OFFSET = (235, 90)
LEGACY_SIZE = 1024

ANNOTATORS = {'legacy': '舊程式草稿', 'medsam': 'MedSAM 草稿', 'rule': '規則草稿', 'model': '模型預測'}
IOU_OK = 0.8
EDGE_OK = 1.1
# 繪製順序：肝脾 → 整顆腎（當作腎實質）→ 腎竇蓋在上面
DRAW_ORDER = ('liver', 'spleen', 'parenchyma', 'sinus')


# ---------- 幾何 ----------
def legacy_to_original(mask: np.ndarray, width: int, height: int) -> np.ndarray:
    """1024×1024 的舊遮罩換回原圖座標（bool）。"""
    cw, ch = LEGACY_CANVAS
    x0, y0 = LEGACY_OFFSET
    canvas = np.zeros((ch, cw), np.uint8)
    canvas[y0:y0 + LEGACY_SIZE, x0:x0 + LEGACY_SIZE] = (mask > 127).astype(np.uint8)[:LEGACY_SIZE, :LEGACY_SIZE]
    return cv2.resize(canvas, (width, height), interpolation=cv2.INTER_NEAREST) > 0


def largest_component(mask: np.ndarray) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    if n <= 1:
        return np.zeros(mask.shape, bool)
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return labels == best


def fill_holes(mask: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = np.zeros(mask.shape, np.uint8)
    cv2.drawContours(out, contours, -1, 1, -1)
    return out > 0


def iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def edge_score(gray: np.ndarray, mask: np.ndarray) -> float:
    """遮罩邊界上的影像梯度 ÷ 整張影像的平均梯度。邊界貼在真正的邊緣上時明顯大於 1。"""
    g = cv2.GaussianBlur(gray, (5, 5), 0).astype(np.float32)
    grad = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    edge = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    if not edge.any():
        return 0.0
    return float(grad[edge].mean() / (grad.mean() + 1e-6))


def raster_to_shapes(label: np.ndarray) -> list[dict[str, Any]]:
    """標籤圖 → 標註編輯器的多邊形。腎實質用整顆腎的外框（腎竇畫在上面覆蓋），所以兩者都能各自拖動。"""
    shapes: list[dict[str, Any]] = []
    h, w = label.shape
    min_area = max(20, int(0.0005 * h * w))
    for name in DRAW_ORDER:
        value = STRUCTURES[name]
        region = (label == value) | (label == STRUCTURES['sinus']) if name == 'parenchyma' else label == value
        if not region.any():
            continue
        contours, _ = cv2.findContours(region.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue
            approx = cv2.approxPolyDP(c, max(1.0, 0.003 * cv2.arcLength(c, True)), True)
            if len(approx) >= 3:
                shapes.append({'structure': name, 'kind': 'polygon', 'points': [[float(x), float(y)] for x, y in approx[:, 0, :]]})
    return shapes


# ---------- 讀寫 ----------
def load_gray(image_id: str) -> tuple[np.ndarray, np.ndarray]:
    """計算用影像：灰階與有效像素（扇形內、不含 caliper）。"""
    gray, valid = deid.read_gray_alpha(storage.image_path(image_id, 'calc'))
    return gray, valid > 0


def load_model_gray(image_id: str) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(storage.image_path(image_id, 'model')), np.uint8), cv2.IMREAD_GRAYSCALE)


def mask_label(record: MaskAnnotation) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(storage.from_root(record.relpath)), np.uint8), cv2.IMREAD_GRAYSCALE)


def save_draft(image_id: str, label: np.ndarray, source: str, flags: dict[str, Any]) -> dict[str, Any]:
    from .circling import protected_test_image_ids

    if image_id in protected_test_image_ids():  # 主切分測試集的影像不產生任何草稿（決策 D20）
        return {'id': None, 'skipped': 'protected_test'}
    shapes = raster_to_shapes(label)
    annotator = ANNOTATORS[source]
    with session_scope('research') as db:
        image = db.get(Image, image_id)
        if image is None:
            raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像。')
        final = rasterize(shapes, image.width, image.height)
        last = db.query(MaskAnnotation.version).filter(MaskAnnotation.image_id == image_id).order_by(MaskAnnotation.version.desc()).first()
        version = (last[0] + 1) if last else 1
        path = storage.mask_path(image_id, version, source)
        deid.write_png(path, final)
        record = MaskAnnotation(
            image_id=image_id,
            version=version,
            annotator=annotator,
            relpath=storage.relative_to_root(path),
            shapes_json=json.dumps(shapes, ensure_ascii=False),
            flags_json=json.dumps(flags, ensure_ascii=False),
            status='draft',
            source=source,
            created_at=now_iso(),
        )
        db.add(record)
        db.flush()
        return {'id': record.id, 'version': version}


def latest(db, image_id: str, sources: set[str] | None = None) -> MaskAnnotation | None:
    q = db.query(MaskAnnotation).filter(MaskAnnotation.image_id == image_id, MaskAnnotation.trashed_at.is_(None), MaskAnnotation.status != 'rejected')
    if sources:
        q = q.filter(MaskAnnotation.source.in_(sources))
    return q.order_by(MaskAnnotation.version.desc()).first()


def _has_human(db, image_id: str) -> bool:
    """已經有人工版本（人畫的或人確認過的）就不再產生新草稿，避免蓋掉人工結果。"""
    return (
        db.query(MaskAnnotation.id)
        .filter(MaskAnnotation.image_id == image_id, MaskAnnotation.trashed_at.is_(None))
        .filter((MaskAnnotation.source == 'manual') | MaskAnnotation.verified_by.isnot(None))
        .first()
        is not None
    )


# ---------- 1. 舊程式遮罩 ----------
@register('legacy_masks', resumable=True, label='匯入舊程式遮罩')
def import_legacy(ctx: JobContext) -> dict[str, Any]:
    from ..data import importer

    root = Path(ctx.config['folder'])
    if not root.is_dir():
        raise AppError(404, 'FOLDER_NOT_FOUND', '找不到舊遮罩資料夾。')
    pairs = importer.legacy_mask_pairs(root)
    counts = {'pairs': len(pairs), 'imported': 0, 'skipped': 0, 'needs_redraw': 0}
    total = max(1, len(pairs))
    for index, (image_id, path) in enumerate(pairs, 1):
        ctx.check_stop()
        ctx.progress(index / total * 100, f'{index}／{len(pairs)}')
        with session_scope('research') as db:
            image = db.get(Image, image_id)
            if image is None or latest(db, image_id, {'legacy'}) is not None or _has_human(db, image_id):
                counts['skipped'] += 1
                continue
            width, height, spacing = image.width, image.height, image.pixel_spacing_mm
        old = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
        if old is None or old.shape != (LEGACY_SIZE, LEGACY_SIZE):
            counts['skipped'] += 1
            continue
        kidney = largest_component(legacy_to_original(old, width, height))
        reasons = []
        if (old[0] > 127).any() or (old[-1] > 127).any() or (old[:, 0] > 127).any() or (old[:, -1] > 127).any():
            reasons.append('舊遮罩碰到裁切邊緣，腎臟可能被切掉一部分')
        score = edge_score(load_model_gray(image_id), kidney)
        if score < EDGE_OK:
            reasons.append('舊遮罩邊界和影像邊緣對不上')
        gray, valid = load_gray(image_id)
        checks, metrics = kidney_checks(gray, kidney, spacing)
        reasons += checks
        # 腎竇：腎臟內中央最亮的區域（分不出來時只標整顆腎）
        sinus, sinfo = split_sinus(gray, valid, kidney)
        reasons += sinus_reasons(sinus, sinfo)
        label = kidney.astype(np.uint8) * STRUCTURES['parenchyma']
        if sinus is not None:
            label[sinus] = STRUCTURES['sinus']
            labeled = ['parenchyma', 'sinus']
        else:
            labeled = ['kidney']
        save_draft(
            image_id,
            label,
            'legacy',
            {'labeled': labeled, 'review': 'needed' if reasons else 'ok', 'reasons': reasons, 'edge_score': round(score, 3), 'kidney': metrics, 'sinus': sinfo},
        )
        counts['imported'] += 1
        counts['needs_redraw'] += bool(reasons)
    return counts


# ---------- 2. MedSAM 重畫腎臟（選用的比較工具）----------
# 2026-10-24 在 60 張真實影像上的唯讀評估：MedSAM（零樣本、以舊遮罩為框）圈出的面積中位數只有舊遮罩的 53%，
# 區域明顯比被排除的外圈亮（44.5 vs 32.7），邊界落在較弱的邊緣上（2.98 vs 舊遮罩 3.23）。
# 因此腎臟草稿以舊遮罩為主，MedSAM 只當比較；之後用自己訓練的分割模型做「模型預測 → 人工修正」。
Segmenter = Callable[[np.ndarray, list[tuple[int, int, int, int]]], np.ndarray]


def jitter_boxes(mask: np.ndarray, margin: float = 0.075, shift: float = 0.03) -> list[tuple[int, int, int, int]]:
    """舊遮罩外接框加邊距，再加上 4 個輕微平移的框（平均後較不受框誤差影響）。"""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    bw, bh = x1 - x0, y1 - y0
    base = (x0 - margin * bw, y0 - margin * bh, x1 + margin * bw, y1 + margin * bh)
    boxes = []
    for dx, dy in ((0, 0), (shift, 0), (-shift, 0), (0, shift), (0, -shift)):
        bx0, by0, bx1, by1 = base[0] + dx * bw, base[1] + dy * bh, base[2] + dx * bw, base[3] + dy * bh
        boxes.append((int(max(0, bx0)), int(max(0, by0)), int(min(w - 1, bx1)), int(min(h - 1, by1))))
    return boxes


# 腎內分層的依據（文獻整理見 01_計畫與文件/Deep_research/reports/腎超器官辨識與分割規則.md）：
# - 腎竇是腎內最亮、位於中央的區域；腎盂擴張時中央會有無回音區，仍屬於腎竇（Open Kidney 的 CEC 定義）。
# - 髓質錐體比皮質暗，排在皮質內側、腎竇外圍，屬於腎實質。
# - 慢性腎病時皮質變亮，皮質與腎竇分不清時不硬切，交給人工。
# 門檻是依文獻推論的起始值，之後用人工確認的遮罩校準。
CMD_LOST = 0.85  # 皮質外圈平均 ÷ 腎竇平均 > 0.85：皮質和腎竇一樣亮
ANECHOIC = 0.6  # 平均 < 0.6 × 皮質：明顯比皮質暗（錐體、積水），分亮區時先排除
# 併入腎竇的積水：比皮質暗很多（< 0.3 ×）且夠大（≥ 腎臟 8%）。
# 2026-10-25 真實 975 張唯讀檢查：用 0.6 × 與 2% 時有 181 張（19%）被判為積水，多半是錐體（本院影像皮質偏暗，
# 皮質亮度中位數約 27），改為 0.3 × 與 8% 後約 31 張（3%）。
PELVIS_DARK = 0.3
PELVIS_AREA = 0.08
SINUS_RATIO = (0.08, 0.6)


def split_sinus(gray: np.ndarray, valid: np.ndarray, kidney: np.ndarray) -> tuple[np.ndarray | None, dict[str, Any]]:
    """把整顆腎分成腎實質與腎竇。回傳 (腎竇遮罩或 None, 資訊)；分不出來時 info['reasons'] 說明原因。

    1. 以腎臟外圈（皮質）為亮度基準，先排除明顯比皮質暗的像素（錐體、積水），再用 Otsu 分「皮質 vs 腎竇」。
       原本直接對整顆腎做 Otsu：錐體或積水很暗時，閾值會落在「暗區 vs 皮質＋腎竇」之間，把皮質切進腎竇。
    2. 腎竇不碰腎包膜：只在內縮後的範圍找，取最大的一塊並補洞。
    3. 皮質外圈和腎竇一樣亮（皮髓質分界消失，常見於慢性腎病）→ 不切，交給人工。
    4. 位在腎竇凸包內、明顯比皮質暗的大區塊（腎盂擴張）→ 併入腎竇；錐體在腎竇外圍，不會被併入。
    """
    h, w = gray.shape
    info: dict[str, Any] = {'reasons': [], 'hydronephrosis': False}
    inside = kidney & valid
    if inside.sum() < 200:
        info['reasons'].append('腎臟範圍太小')
        return None, info
    smooth = cv2.GaussianBlur(gray, (0, 0), max(1.5, 0.01 * w)).astype(np.float32)
    raw = gray.astype(np.float32)
    rim_px = max(2, int(0.01 * w))
    inner = cv2.erode(kidney.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=rim_px) > 0
    # 皮質外圈用未平滑的影像：平滑會把腎外的組織混進外圈，讓皮質看起來比較暗
    rim = (cv2.erode(kidney.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2) > 0) & ~inner & valid
    cortex_ref = float(np.median(raw[rim])) if rim.any() else float(np.median(raw[inside]))
    info['cortex_ref'] = round(cortex_ref, 1)
    usable = inside & (smooth >= ANECHOIC * cortex_ref)
    values = smooth[usable if usable.sum() >= 200 else inside]
    thr, _ = cv2.threshold(values.astype(np.uint8).reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    info['threshold'] = round(float(thr), 1)
    k = max(3, int(0.008 * w)) | 1
    bright = cv2.morphologyEx((inner & valid & (smooth > thr)).astype(np.uint8), cv2.MORPH_OPEN, np.ones((k, k), np.uint8)) > 0
    sinus = fill_holes(largest_component(bright))
    if not sinus.any():
        info['reasons'].append('腎臟內沒有明顯較亮的中央區域')
        return None, info
    rim_mean = float(raw[rim].mean()) if rim.any() else cortex_ref
    contrast = rim_mean / max(float(raw[sinus].mean()), 1.0)
    info['cortex_sinus_contrast'] = round(contrast, 3)
    if contrast > CMD_LOST:
        info['reasons'].append(f'皮質和腎竇一樣亮（比值 {contrast:.2f}，可能是皮髓質分界消失），不自動切分')
        info['cmd_lost'] = True
        return None, info
    # 積水會把亮的腎竇撐開成好幾片：凸包用所有夠大的亮區（不只最大的一片）
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bright.astype(np.uint8), 8)
    pieces = np.isin(labels, [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 0.01 * kidney.sum()]) | sinus
    hull = np.zeros((h, w), np.uint8)
    cv2.fillPoly(hull, [cv2.convexHull(cv2.findNonZero(pieces.astype(np.uint8)))], 1)
    touching = cv2.dilate(pieces.astype(np.uint8), np.ones((k, k), np.uint8), iterations=2) > 0
    # 腎臟的長軸（主成分）：積水在長軸附近（中央），錐體偏離長軸、夾在腎竇和皮質之間
    ys, xs = np.nonzero(kidney)
    center = np.array([xs.mean(), ys.mean()])
    evals, evecs = np.linalg.eigh(np.cov(np.stack([xs, ys])))
    minor, half_minor = evecs[:, 0], 2 * np.sqrt(max(evals[0], 1e-6))
    # 暗區用較輕的平滑：強平滑會把旁邊亮的腎竇混進積水，讓它看起來不夠暗
    light = cv2.GaussianBlur(gray, (0, 0), max(1.5, 0.004 * w)).astype(np.float32)
    dark = inner & valid & ~pieces & (light < ANECHOIC * cortex_ref)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(dark.astype(np.uint8), 8)
    for i in range(1, n):
        cx, cy = int(round(centroids[i][0])), int(round(centroids[i][1]))
        region = labels == i
        central = abs(float((centroids[i] - center) @ minor)) < 0.35 * half_minor
        anechoic = float(raw[region].mean()) < PELVIS_DARK * cortex_ref
        if stats[i, cv2.CC_STAT_AREA] >= PELVIS_AREA * kidney.sum() and anechoic and (hull[cy, cx] or (central and (region & touching).any())):
            sinus |= labels == i
            info['hydronephrosis'] = True
    if info['hydronephrosis']:
        sinus |= pieces
    sinus = fill_holes(sinus) & kidney
    ratio = sinus.sum() / max(1, kidney.sum())
    info['sinus_ratio'] = round(float(ratio), 3)
    if not (SINUS_RATIO[0] <= ratio <= SINUS_RATIO[1]):
        info['reasons'].append(f'腎竇佔整顆腎 {ratio:.0%}，不在常見範圍（8–60%）')
        return None, info
    return sinus, info


def sinus_reasons(sinus: np.ndarray | None, info: dict[str, Any]) -> list[str]:
    """切分腎竇的結果轉成「需要確認」的原因。"""
    if sinus is None:
        return [f'無法自動分出腎竇：{"；".join(info["reasons"]) or "原因不明"}']
    if info.get('hydronephrosis'):
        return ['腎竇中央有大片無回音區（可能是腎盂擴張），已併入腎竇，請確認']
    return []


def kidney_checks(gray: np.ndarray, kidney: np.ndarray, spacing_mm: float | None) -> tuple[list[str], dict[str, Any]]:
    """整顆腎的合理性檢查：只產生提醒，不改遮罩。"""
    reasons: list[str] = []
    metrics: dict[str, Any] = {}
    contour = cv2.findNonZero(kidney.astype(np.uint8))
    if contour is None or len(contour) < 5:
        return ['沒有腎臟範圍'], metrics
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    convexity = float(kidney.sum() / max(hull_area, 1.0))
    metrics['convexity'] = round(convexity, 3)
    if convexity < 0.85:
        reasons.append(f'腎臟形狀不規則（凸性 {convexity:.2f}），可能圈到腎外的組織')
    if spacing_mm:
        (_, _), (a, b), _ = cv2.minAreaRect(contour)
        length = max(a, b) * spacing_mm
        metrics['length_mm'] = round(float(length), 1)
        # 台灣成人腎長約 10.6–10.8 cm（Su 2019）；慢性腎病會縮小，部分切面也會變短
        if not 60 <= length <= 140:
            reasons.append(f'腎長約 {length / 10:.1f} cm，超出常見範圍（6–14 cm）')
    return reasons, metrics


@register('medsam_kidney', exclusive=True, resumable=True, label='MedSAM 重畫腎臟')
def medsam_kidney(ctx: JobContext) -> dict[str, Any]:
    from ..ml import medsam

    segment: Segmenter = medsam.get_segmenter()
    with session_scope('research') as db:
        image_ids = [r[0] for r in db.query(MaskAnnotation.image_id).filter(MaskAnnotation.source == 'legacy', MaskAnnotation.trashed_at.is_(None)).distinct().order_by(MaskAnnotation.image_id)]
    counts = {'images': len(image_ids), 'drafted': 0, 'needs_review': 0, 'skipped': 0}
    out_dir = medsam.output_dir()
    total = max(1, len(image_ids))
    for index, image_id in enumerate(image_ids, 1):
        ctx.check_stop()
        ctx.progress(index / total * 100, f'{index}／{len(image_ids)}')
        with session_scope('research') as db:
            if _has_human(db, image_id) or latest(db, image_id, {'medsam'}) is not None:
                counts['skipped'] += 1
                continue
            legacy = latest(db, image_id, {'legacy'})
            legacy_flags = json.loads(legacy.flags_json)
            old = mask_label(legacy) > 0
        model_gray = load_model_gray(image_id)
        prob = segment(model_gray, jitter_boxes(old))
        kidney = fill_holes(largest_component(prob > 0.5))
        reasons = list(legacy_flags.get('reasons', []))
        overlap = iou(kidney, old)
        area_ratio = kidney.sum() / max(1, old.sum())
        if kidney.sum() == 0:
            reasons.append('MedSAM 沒有圈出腎臟')
        elif overlap < IOU_OK:
            reasons.append(f'和舊遮罩差異大（IoU {overlap:.2f}）')
        if 0 < area_ratio < 0.7:
            reasons.append(f'只圈到舊遮罩面積的 {area_ratio:.0%}，可能漏掉較暗的皮質')
        gray, valid = load_gray(image_id)
        sinus, sinfo = split_sinus(gray, valid, kidney) if kidney.any() else (None, {'reasons': ['沒有腎臟範圍']})
        reasons += sinus_reasons(sinus, sinfo)
        label = kidney.astype(np.uint8) * STRUCTURES['parenchyma']
        if sinus is not None:
            label[sinus] = STRUCTURES['sinus']
            labeled = ['parenchyma', 'sinus']
        else:
            labeled = ['kidney']
        deid.write_png(out_dir / shard(image_id) / f'{image_id}.png', label)
        save_draft(
            image_id,
            label,
            'medsam',
            {'labeled': labeled, 'review': 'needed' if reasons else 'ok', 'reasons': reasons, 'iou_vs_legacy': round(overlap, 3), 'edge_score': round(edge_score(model_gray, kidney), 3)},
        )
        counts['drafted'] += 1
        counts['needs_review'] += bool(reasons)
    return counts


# ---------- 3. 規則產生肝／脾 ----------
def shadow_mask(gray: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """聲影：強反射（肋骨、腸氣、結石）正下方一路延伸的暗帶。

    由上往下逐列掃描：遇到很亮的像素就「開始」，之後只要一直是暗的就延續（亮暗交界的幾列過渡可以跳過）；
    只保留縱向長度 ≥ 影像高度 10% 的暗帶，避免把一般的暗組織當成陰影。"""
    h, w = gray.shape
    sector = valid & (gray > 0)
    if sector.sum() < 1000:
        return np.zeros((h, w), bool)
    smooth = cv2.GaussianBlur(gray, (0, 0), max(1.5, 0.006 * w)).astype(np.float32)
    median = float(np.median(smooth[sector]))
    bright = sector & (smooth > max(float(np.percentile(smooth[sector], 98)), 1.8 * median))
    dark = sector & (smooth < 0.5 * median)
    max_gap = max(3, int(0.02 * h))
    armed = np.zeros(w, bool)
    gap = np.zeros(w, np.int32)
    shadow = np.zeros((h, w), bool)
    for y in range(h):
        b, d = bright[y], dark[y]
        gap = np.where(armed & ~d & ~b, gap + 1, 0)
        armed = b | (armed & (d | (gap <= max_gap)))
        shadow[y] = armed & d
    n, labels, stats, _ = cv2.connectedComponentsWithStats(shadow.astype(np.uint8), 8)
    keep = np.zeros(n, bool)
    keep[1:] = (stats[1:, cv2.CC_STAT_HEIGHT] >= 0.1 * h) & (stats[1:, cv2.CC_STAT_WIDTH] >= 3)
    return keep[labels]


# 位置規則：文獻上肝脾在腎臟的近場／頭側，腎臟深側是腰大肌、腸道或背部肌肉。
# 2026-10-25 真實影像唯讀檢查：舊規則的肝脾草稿面積中位數有 62%（前方切面）／66%（後方切面）在腎臟深側，
# 幾乎沒有在腎臟上方的。數字無法分辨是舊草稿圈錯，還是本院影像的切面讓肝脾落在腎臟旁邊或深側，
# 所以先不開啟；人工確認一批肝脾草稿後再決定。開啟時：排除比腎臟最深處更深的區域，並偏好近場或頭側的一塊。
DEEP_SIDE_RULE = False


def organ_draft(gray: np.ndarray, valid: np.ndarray, kidney: np.ndarray, spacing_mm: float | None) -> tuple[np.ndarray | None, dict[str, Any]]:
    """右腎旁邊找肝、左腎旁邊找脾：緊貼腎臟、紋理均勻、亮度適中的區域。回傳 (遮罩, 品質資訊)。

    依文獻加上的規則（門檻是起始值，之後用人工確認結果校準）：
    - 肝脾和腎之間以腎周的亮線（包膜＋腎周脂肪）為界：亮線本身不算器官。
    - 聲影（強反射下方的暗帶）不算器官。
    - 位置規則（DEEP_SIDE_RULE）預設關閉，見常數說明。"""
    h, w = gray.shape
    info: dict[str, Any] = {'ok': False, 'reasons': []}
    if not kidney.any():
        info['reasons'].append('沒有腎臟範圍')
        return None, info
    sector = valid & (gray > 0)
    if sector.sum() < 1000:
        info['reasons'].append('有效影像區域太小')
        return None, info
    win = max(5, int(0.02 * w)) | 1
    g = gray.astype(np.float32)
    mean = cv2.blur(g, (win, win))
    sq = cv2.blur(g * g, (win, win))
    cv = np.sqrt(np.maximum(sq - mean * mean, 0)) / (mean + 1.0)
    gap = max(2, int(0.01 * w))
    reach = max(10, int(0.25 * w))
    kid = kidney.astype(np.uint8)
    # 到腎臟的距離（距離轉換）：等同用圓形核膨脹，但大範圍時快很多
    dist = cv2.distanceTransform((kid == 0).astype(np.uint8), cv2.DIST_L2, 5)
    near = dist <= reach
    away = dist <= gap
    ring = near & ~away & sector
    if ring.sum() < 500:
        info['reasons'].append('腎臟周圍沒有足夠的影像')
        return None, info
    lo, hi = np.percentile(g[sector], [25, 92])
    # 腎周亮線：腎臟外圍 4% 寬度內的亮像素，當作肝脾和腎的分界，不算器官
    band = dist <= int(0.04 * w)
    away |= band & ~kidney & (mean > np.percentile(g[sector], 85))
    ky = np.nonzero(kidney.any(axis=1))[0]
    kx = np.nonzero(kidney.any(axis=0))[0]
    not_deep = np.ones((h, w), bool)
    if DEEP_SIDE_RULE:
        not_deep[min(h, int(ky.max() + 0.03 * h)) + 1:] = False
    shadow = shadow_mask(gray, valid)
    info['shadow_px'] = int((shadow & ring).sum())
    candidate = ring & ~away & not_deep & ~shadow & (mean >= lo) & (mean <= hi) & (cv <= np.percentile(cv[ring], 50))
    k = max(3, int(0.012 * w)) | 1
    candidate = cv2.morphologyEx(candidate.astype(np.uint8), cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8)) > 0
    # 只保留緊貼腎臟的區塊（和腎臟外圍一圈有接觸）；開啟位置規則時，近場或頭側的區塊加權
    touch = cv2.dilate(away.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(candidate.astype(np.uint8), 8)
    kcx, kcy = float(kx.mean()), float(ky.mean())
    best, best_score = 0, 0.0
    for i in range(1, n):
        if not (touch & (labels == i)).any():
            continue
        cx, cy = centroids[i]
        score = stats[i, cv2.CC_STAT_AREA] * (1.0 if (not DEEP_SIDE_RULE or cy < kcy or cx < kcx) else 0.5)
        if score > best_score:
            best, best_score = i, score
    if not best:
        info['reasons'].append('找不到緊貼腎臟、紋理均勻的區域')
        return None, info
    organ = fill_holes(labels == best) & sector & ~shadow & ~kidney
    values = g[organ]
    info.update(area_px=int(organ.sum()), mean=round(float(values.mean()), 1), cv=round(float(cv[organ].mean()), 3))
    # 品質檢查
    if organ.sum() < 0.02 * sector.sum():
        info['reasons'].append('區域太小')
    if values.mean() < 20:
        info['reasons'].append('太暗（可能是陰影）')
    if values.mean() > 200:
        info['reasons'].append('太亮（可能是腸氣或骨頭）')
    ky = np.nonzero(kidney.any(axis=1))[0]
    oy = np.nonzero(organ.any(axis=1))[0]
    overlap = max(0, min(ky.max(), oy.max()) - max(ky.min(), oy.min())) / max(1, ky.max() - ky.min())
    info['depth_overlap'] = round(float(overlap), 2)
    if overlap < 0.2:
        far = (min(abs(oy.mean() - ky.mean()), h) * spacing_mm) if spacing_mm else None
        info['reasons'].append('和腎皮質深度差太多' + (f'（約 {far:.0f} mm）' if far else ''))
    info['ok'] = not info['reasons']
    return organ, info


@register('organ_drafts', resumable=True, label='產生肝／脾草稿')
def organ_drafts(ctx: JobContext) -> dict[str, Any]:
    with session_scope('research') as db:
        rows = [
            (i.id, i.side, i.pixel_spacing_mm)
            for i in db.query(Image).filter(Image.status == 'usable').order_by(Image.id)
        ]
    counts = {'images': len(rows), 'drafted': 0, 'unreliable': 0, 'no_side': 0, 'no_kidney': 0, 'skipped': 0}
    total = max(1, len(rows))
    for index, (image_id, side, spacing) in enumerate(rows, 1):
        ctx.check_stop()
        ctx.progress(index / total * 100, f'{index}／{len(rows)}')
        if side not in ('right', 'left'):
            counts['no_side'] += 1
            continue
        with session_scope('research') as db:
            if _has_human(db, image_id) or latest(db, image_id, {'rule'}) is not None:
                counts['skipped'] += 1
                continue
            # 腎臟以舊遮罩為主：真實影像上 MedSAM 常只圈到中央較亮的部分（約一半面積），漏掉皮質
            base = latest(db, image_id, {'legacy'}) or latest(db, image_id, {'medsam'})
            if base is None:
                counts['no_kidney'] += 1
                continue
            base_flags = json.loads(base.flags_json)
            label = mask_label(base)
        organ_name = 'liver' if side == 'right' else 'spleen'
        gray, valid = load_gray(image_id)
        organ, info = organ_draft(gray, valid, label > 0, spacing)
        reasons = list(base_flags.get('reasons', []))
        labeled = list(base_flags.get('labeled', ['kidney']))
        if organ is not None and info['ok']:
            label = label.copy()
            label[organ & (label == 0)] = STRUCTURES[organ_name]
            labeled += ['liver', 'spleen']  # 一側只會有其中一個器官，另一個確定不存在
        else:
            reasons += [f'{"肝" if organ_name == "liver" else "脾"}：{r}' for r in info['reasons']]
            counts['unreliable'] += 1
        save_draft(image_id, label, 'rule', {**base_flags, 'labeled': labeled, 'review': 'needed' if reasons else 'ok', 'reasons': reasons, 'organ': {organ_name: info}})
        counts['drafted'] += 1
    return counts


# ---------- 3b. 用新規則重新產生 ----------
# 匯入與產生草稿都會跳過「已經有草稿」的影像，規則改進後舊草稿不會自動更新。
# 這裡把還沒有人工結果的舊草稿整批移入回收桶（可以一次還原），再依序重跑兩個步驟。
REGENERATE_SOURCES = ('legacy', 'rule')


def regenerable_drafts(max_id: int | None = None) -> list[int]:
    """可以重新產生的草稿：舊程式與肝脾草稿、還沒確認，而且那張影像沒有任何人工版本。退回的草稿保留當紀錄。"""
    with session_scope('research') as db:
        human = {
            r[0]
            for r in db.query(MaskAnnotation.image_id)
            .filter(MaskAnnotation.trashed_at.is_(None))
            .filter((MaskAnnotation.source == 'manual') | MaskAnnotation.verified_by.isnot(None))
            .all()
        }
        q = db.query(MaskAnnotation.id, MaskAnnotation.image_id).filter(
            MaskAnnotation.source.in_(REGENERATE_SOURCES),
            MaskAnnotation.status == 'draft',
            MaskAnnotation.verified_by.is_(None),
            MaskAnnotation.trashed_at.is_(None),
        )
        if max_id is not None:
            q = q.filter(MaskAnnotation.id <= max_id)
        return [mask_id for mask_id, image_id in q.all() if image_id not in human]


class _Stage:
    """把子工作 0–100% 的進度對應到整體進度的一段；其他屬性（config、check_stop）照原本的工作。"""

    def __init__(self, ctx: JobContext, start: float, end: float, label: str):
        self._ctx, self._start, self._end, self._label = ctx, start, end, label

    def progress(self, value: float, message: str = '') -> None:
        self._ctx.progress(self._start + (self._end - self._start) * value / 100, f'{self._label}：{message}')

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ctx, name)


@register('regenerate_drafts', resumable=True, label='用新規則重新產生草稿')
def regenerate_drafts(ctx: JobContext) -> dict[str, Any]:
    from ..trash import service as trash

    # 只處理按下按鈕時就存在的草稿（編號 ≤ max_id）：中斷後恢復時，不會把這次新產生的草稿又移入回收桶
    ids = regenerable_drafts(ctx.config['max_id'])
    moved = trash.move_many_to_trash('mask', [str(i) for i in ids], f'舊規則產生的遮罩草稿 {len(ids)} 份', '改用新規則重新產生', ctx.config.get('operator', ''))
    legacy = import_legacy(_Stage(ctx, 0, 60, '舊程式遮罩'))  # type: ignore[arg-type]
    organs = organ_drafts(_Stage(ctx, 60, 100, '肝／脾'))  # type: ignore[arg-type]
    return {'trashed': moved['moved'], 'trash_group': moved['group_id'], 'legacy': legacy, 'organs': organs}


# ---------- 4. 人工確認 ----------
def review_queue(only_needed: bool = False, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """每張影像最新的草稿（還沒有人工版本、沒被確認或退回），需要確認的排前面、IoU 低的排前面。"""
    with session_scope('research') as db:
        rows = db.query(MaskAnnotation).filter(MaskAnnotation.trashed_at.is_(None)).order_by(MaskAnnotation.image_id, MaskAnnotation.version.desc()).all()
        latest_by_image: dict[str, MaskAnnotation] = {}
        for m in rows:
            latest_by_image.setdefault(m.image_id, m)
        items = []
        for m in latest_by_image.values():
            if m.status != 'draft' or m.verified_by:
                continue
            flags = json.loads(m.flags_json)
            if only_needed and flags.get('review') != 'needed':
                continue
            items.append(
                {
                    'mask_id': m.id,
                    'image_id': m.image_id,
                    'version': m.version,
                    'source': m.source,
                    'review': flags.get('review', 'needed'),
                    'reasons': flags.get('reasons', []),
                    'labeled': flags.get('labeled', []),
                    'iou_vs_legacy': flags.get('iou_vs_legacy'),
                }
            )
    # 需要確認的排前面；同樣需要確認時，問題越多的越前面，再依和舊遮罩的差異
    items.sort(key=lambda x: (x['review'] != 'needed', -len(x['reasons']), x['iou_vs_legacy'] if x['iou_vs_legacy'] is not None else 1.0, x['image_id']))
    return {'total': len(items), 'items': items[offset:offset + limit]}


def decide(mask_id: int, decision: str, operator: str, reason: str = '') -> dict[str, Any]:
    if decision not in {'accept', 'reject'}:
        raise AppError(422, 'BAD_DECISION', '只能接受或退回。')
    if not operator or operator == '本機':
        raise AppError(422, 'OPERATOR_REQUIRED', '請先在右上角選擇操作者，確認紀錄才知道是誰確認的。')
    with session_scope('research') as db:
        m = db.get(MaskAnnotation, mask_id)
        if m is None or m.trashed_at:
            raise AppError(404, 'MASK_NOT_FOUND', '找不到這份遮罩。')
        if m.status != 'draft':
            raise AppError(409, 'NOT_DRAFT', '這份遮罩不是草稿，不需要確認。')
        flags = json.loads(m.flags_json)
        if decision == 'accept':
            m.verified_by, m.verified_at, m.status = operator, now_iso(), 'reviewed'
        else:
            m.status = 'rejected'
            flags['rejected_reason'] = reason
            m.flags_json = json.dumps(flags, ensure_ascii=False)
        return {'mask_id': m.id, 'status': m.status}


def delete_drafts(sources: list[str], operator: str) -> dict[str, Any]:
    """把指定來源的草稿（待確認與被退回的）移入回收桶，每個來源一組，可以一次還原。
    已經接受的（成為人工確認的遮罩）與人工畫的版本不受影響。"""
    from ..trash import service as trash

    unknown = [s for s in sources if s not in ANNOTATORS]
    if unknown:
        raise AppError(422, 'BAD_SOURCE', '不認識的草稿來源：' + '、'.join(unknown))
    out: dict[str, Any] = {'moved': 0, 'groups': []}
    for source in sources:
        with session_scope('research') as db:
            ids = [
                r[0]
                for r in db.query(MaskAnnotation.id).filter(
                    MaskAnnotation.source == source,
                    MaskAnnotation.status.in_(('draft', 'rejected')),
                    MaskAnnotation.verified_by.is_(None),
                    MaskAnnotation.trashed_at.is_(None),
                )
            ]
        moved = trash.move_many_to_trash('mask', [str(i) for i in ids], f'{ANNOTATORS[source]} {len(ids)} 份', '刪除草稿', operator)
        out['moved'] += moved['moved']
        if moved['group_id']:
            out['groups'].append(moved['group_id'])
    return out


def max_mask_id() -> int:
    with session_scope('research') as db:
        return int(db.query(MaskAnnotation.id).order_by(MaskAnnotation.id.desc()).limit(1).scalar() or 0)


def draft_stats() -> dict[str, Any]:
    """各來源的草稿數、接受、修改、退回與接受率。修改＝草稿之後同一張影像出現人工版本。"""
    with session_scope('research') as db:
        rows = db.query(MaskAnnotation.image_id, MaskAnnotation.version, MaskAnnotation.source, MaskAnnotation.status, MaskAnnotation.verified_by).filter(MaskAnnotation.trashed_at.is_(None)).all()
    manual_after: dict[str, int] = {}
    for image_id, version, source, status, _ in rows:
        if source == 'manual':
            manual_after[image_id] = max(manual_after.get(image_id, 0), version)
    out: dict[str, dict[str, Any]] = {}
    for image_id, version, source, status, verified in rows:
        if source == 'manual':
            continue
        s = out.setdefault(source, {'drafts': 0, 'accepted': 0, 'edited': 0, 'rejected': 0, 'pending': 0})
        s['drafts'] += 1
        if verified:
            s['accepted'] += 1
        elif status == 'rejected':
            s['rejected'] += 1
        elif manual_after.get(image_id, 0) > version:
            s['edited'] += 1
        else:
            s['pending'] += 1
    for s in out.values():
        decided = s['accepted'] + s['edited'] + s['rejected']
        s['acceptance_rate'] = round(s['accepted'] / decided, 3) if decided else None
    return {'by_source': out, 'regenerable': len(regenerable_drafts())}
