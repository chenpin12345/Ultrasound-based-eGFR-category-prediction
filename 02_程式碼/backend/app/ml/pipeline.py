"""一鍵流程與 AI 分析：分割 → 回音特徵 → 分類（eGFR、回音分級），結果存成 CSV。

用註冊過的模型；每個步驟先檢查模型合約，不符就拒絕。結果放在 03_資料/04_模型產出/預測結果/{工作ID}/。
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from typing import Any

import numpy as np

from ..core.config import get_settings
from ..core.errors import AppError
from ..data import deid, storage
from ..db.models_research import Image, Patient
from ..db.session import session_scope
from ..features.service import measure
from ..jobs.manager import JobContext, get_manager, register
from . import data as mldata
from . import registry


def out_dir(job_id: str):
    return get_settings().path('model_outputs') / '預測結果' / job_id


def start(seg_model_id: str, classifier_ids: list[str], image_ids: list[str] | None, operator: str) -> dict[str, Any]:
    if not seg_model_id and not classifier_ids:
        raise AppError(422, 'NO_MODELS', '請至少選一個模型。')
    for mid in [seg_model_id] + classifier_ids if seg_model_id else classifier_ids:
        registry.detail(mid)  # 不存在就拒絕
    config = {'seg_model_id': seg_model_id, 'classifier_ids': classifier_ids, 'image_ids': image_ids}
    target = f'{len(image_ids)} 張影像' if image_ids else '全部可用影像'
    return {'job_id': get_manager().submit('pipeline', config, target=target, created_by=operator)}


@register('pipeline', exclusive=True, label='一鍵流程／AI 分析')
def pipeline_job(ctx: JobContext) -> dict[str, Any]:
    cfg = ctx.config
    seg = registry.load(cfg['seg_model_id'], 'segmentation') if cfg.get('seg_model_id') else None
    classifiers = [registry.load(m) for m in cfg.get('classifier_ids') or []]
    for c in classifiers:
        if c.task == 'segmentation':
            raise AppError(409, 'CONTRACT_MISMATCH', '分類步驟不能選分割模型。')
        needs_measures = 'measures' in (c.manifest.get('inputs') or (['measures'] if c.manifest.get('features') else []))
        if (needs_measures or c.manifest['input'].get('mode') == 'mask_channels') and seg is None:
            raise AppError(409, 'CONTRACT_MISMATCH', f'{c.manifest["id"]} 需要分割遮罩（回音特徵或遮罩通道），請同時選一個分割模型。')
        source = (c.manifest['input'].get('mask_source') or {}).get('seg_run_id')
        if source and seg is not None and seg.manifest['training']['run_id'] != source:
            raise AppError(409, 'CONTRACT_MISMATCH', f'{c.manifest["id"]} 是用分割訓練 {source} 的遮罩訓練的，請選用同一個訓練註冊的分割模型。')
    with session_scope('research') as db:
        q = db.query(Image).filter(Image.status == 'usable')
        if cfg.get('image_ids'):
            q = q.filter(Image.id.in_(cfg['image_ids']))
        images = [(i.id, i.patient_id, i.side, i.pixel_spacing_mm) for i in q.order_by(Image.id)]
        patients = {p.id: p for p in db.query(Patient).filter(Patient.id.in_({i[1] for i in images if i[1]})).all()}
        clinical = {i[0]: ({'age': patients[i[1]].age, 'sex': patients[i[1]].sex, 'has_diabetes': patients[i[1]].has_diabetes} if i[1] in patients else {}) for i in images}
    if not images:
        raise AppError(409, 'NO_IMAGES', '沒有可分析的影像。')
    folder = out_dir(ctx.job_id)
    rows = []
    for index, (image_id, patient_id, side, spacing) in enumerate(images, 1):
        ctx.check_stop()
        ctx.progress(index / len(images) * 100, f'{index}／{len(images)}')
        gray = mldata.load_image(image_id)
        row: dict[str, Any] = {'image_id': image_id, 'patient_id': patient_id, 'side': side}
        feats: dict[str, Any] = {}
        label = None
        if seg:
            from .masksets import postprocess

            label = postprocess(registry.predict_segmentation(seg, gray))
            deid.write_png(folder / '遮罩' / f'{image_id}.png', label)
            calc, valid = deid.read_gray_alpha(storage.image_path(image_id, 'calc'))
            feats = measure(label, calc, valid > 0, side, spacing)
            for key in ('length_mm', 'width_mm', 'ratio_mean', 'ratio_median', 'p_index', 'ref_organ', 'reliable', 'reasons'):
                row[key] = feats.get(key)
        for c in classifiers:
            x = registry.standardize(c, feats, clinical.get(image_id)) if c.manifest.get('features') else None
            probs = registry.predict_classification(c, gray, x, label, spacing)
            row[f'{c.manifest["id"]}'] = probs
        rows.append(row)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'results.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    with (folder / 'results.csv').open('w', newline='', encoding='utf-8') as fh:
        keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in ('image_id', 'patient_id', 'side'), k))
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows([{k: json.dumps(v) if isinstance(v, list) else v for k, v in r.items()} for r in rows])
    return {'images': len(rows), 'output': str(folder.relative_to(get_settings().root).as_posix())}


# 疊圖顏色（BGRA），和標註編輯器一致：腎實質青、腎竇紫、肝黃、脾綠
OVERLAY = {1: (0xD6, 0xC4, 0x5E, 140), 2: (0xEA, 0x92, 0xC7, 160), 3: (0x55, 0xB4, 0xE0, 120), 4: (0x6B, 0xCB, 0x9C, 120)}


def mask_overlay(job_id: str, image_id: str) -> bytes:
    """預測遮罩轉成半透明彩色 PNG，疊在去識別化影像上顯示。"""
    import cv2

    path = out_dir(job_id) / '遮罩' / f'{image_id}.png'
    if not path.exists():
        raise AppError(404, 'MASK_NOT_FOUND', '這張影像沒有預測遮罩。')
    label = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
    rgba = np.zeros((*label.shape, 4), np.uint8)
    for value, color in OVERLAY.items():
        rgba[label == value] = color
    return cv2.imencode('.png', rgba)[1].tobytes()


def results(job_id: str) -> dict[str, Any]:
    path = out_dir(job_id) / 'results.json'
    if not path.exists():
        raise AppError(404, 'RESULTS_NOT_FOUND', '找不到這個流程的結果（可能還在執行）。')
    rows = json.loads(path.read_text(encoding='utf-8'))
    # 病人＋側別層級：同一側的影像機率平均
    model_keys = [k for k in (rows[0] if rows else {}) if '@' in k]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r['patient_id'], r['side'])].append(r)
    by_side = []
    for (pid, side), rs in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        entry = {'patient_id': pid, 'side': side, 'images': len(rs)}
        for k in model_keys:
            entry[k] = np.mean([r[k] for r in rs], 0).round(4).tolist()
        ratios = [r['ratio_mean'] for r in rs if r.get('ratio_mean') is not None and r.get('reliable')]
        entry['ratio_mean'] = round(float(np.median(ratios)), 4) if ratios else None
        by_side.append(entry)
    return {'job_id': job_id, 'images': rows, 'by_patient_side': by_side, 'models': model_keys}
