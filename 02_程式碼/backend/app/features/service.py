"""回音與形態特徵（不需要 PyTorch）。

計算方式（依文獻與企劃 M2-1 第 5 項）：
- 皮質：腎實質中靠近腎包膜的外層帶（髓質錐體比較暗，不能用整個腎實質）。
- 參考組織：右腎用肝、左腎用脾，只取和皮質「相同深度」的像素（聲波衰減會讓深處變暗）。
- 排除 caliper 修補過的無效像素（計算用影像的透明度）與過曝像素。
- 平均值（文獻慣用）與中位數（較穩）都算。
- 右腎／肝、左腎／脾分開分析，不共用切點。
- 腎長由遮罩的最小外接矩形量出，和技師量的 Dist A 比較（Bland-Altman）。

來源：
- masks：每張影像最新的遮罩（人工或草稿）。用來探索，不能直接拿來訓練下游模型。
- run：某個分割訓練的 out-of-fold 預測遮罩（交叉擬合）。每張影像的遮罩都來自「沒看過這位病人」的模型，下游模型可以安全使用。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy import stats

from ..annotation.service import STRUCTURES
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_dated, now_iso, shard
from ..data import deid, storage
from ..db.models_research import FeatureSet, Image, MaskAnnotation, Patient, TrainingRun
from ..db.session import session_scope
from ..jobs.manager import JobContext, register

CORTEX_FRACTION = 0.35  # 皮質帶厚度上限：腎臟內部最大深度的 35%
CORTEX_MAX_MM = 10.0  # 且不超過 10 mm
CAPSULE_SKIP_MM = 1.0  # 腎臟外框沿被膜外緣畫（決策 D48），略過最外層，亮線才不會讓皮質偏亮
CAPSULE_SKIP_PX = 2  # 沒有像素間距時
DEPTH_TOLERANCE_MM = 5.0
MAX_DEPTH_DIFF_MM = 15.0
SATURATED = 250
COLUMNS = [
    'image_id', 'patient_id', 'side', 'ref_organ', 'mask_source', 'length_mm', 'width_mm', 'dist_a_mm', 'cortex_mean', 'cortex_median',
    'organ_mean', 'organ_median', 'sinus_mean', 'sinus_median', 'ratio_mean', 'ratio_median', 'p_index', 'depth_diff_mm', 'gain', 'reliable', 'reasons',
]
NUMERIC = {c for c in COLUMNS if c not in {'image_id', 'patient_id', 'side', 'ref_organ', 'mask_source', 'reasons', 'reliable'}}


def folder(feature_set_id: str) -> Path:
    return get_settings().path('model_outputs') / '特徵' / feature_set_id


def measure(label: np.ndarray, gray: np.ndarray, valid: np.ndarray, side: str | None, spacing_mm: float | None) -> dict[str, Any]:
    """單張影像的特徵。label：0 背景、1 腎實質、2 腎竇、3 肝、4 脾（原圖大小）。"""
    out: dict[str, Any] = {c: None for c in COLUMNS}
    reasons: list[str] = []
    kidney = (label == STRUCTURES['parenchyma']) | (label == STRUCTURES['sinus'])
    if kidney.sum() < 100:
        out.update(reliable=False, reasons='沒有腎臟遮罩')
        return out
    usable = valid & (gray < SATURATED)
    contours, _ = cv2.findContours(kidney.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    (_, _), (rw, rh), _ = cv2.minAreaRect(max(contours, key=cv2.contourArea))
    if spacing_mm:
        out['length_mm'] = round(max(rw, rh) * spacing_mm, 1)
        out['width_mm'] = round(min(rw, rh) * spacing_mm, 1)
    else:
        reasons.append('沒有像素間距，無法換算 mm')

    # 皮質：腎實質中、離腎包膜最近的一層
    dist = cv2.distanceTransform(kidney.astype(np.uint8), cv2.DIST_L2, 5)
    limit = CORTEX_FRACTION * float(dist.max())
    if spacing_mm:
        limit = min(limit, CORTEX_MAX_MM / spacing_mm)
    skip = CAPSULE_SKIP_MM / spacing_mm if spacing_mm else CAPSULE_SKIP_PX
    cortex = (label == STRUCTURES['parenchyma']) & (dist > skip) & (dist <= limit) & usable
    sinus = (label == STRUCTURES['sinus']) & usable
    if cortex.sum() < 50:
        reasons.append('皮質有效像素太少')
    else:
        out['cortex_mean'] = round(float(gray[cortex].mean()), 2)
        out['cortex_median'] = round(float(np.median(gray[cortex])), 2)
    if sinus.sum() >= 50:
        out['sinus_mean'] = round(float(gray[sinus].mean()), 2)
        out['sinus_median'] = round(float(np.median(gray[sinus])), 2)

    # 參考器官：右腎用肝、左腎用脾；只取和皮質相同深度的像素
    organ_name = {'right': 'liver', 'left': 'spleen'}.get(side or '')
    if organ_name is None:
        # 側別未知時，看遮罩裡畫的是哪一個器官
        organ_name = 'liver' if (label == STRUCTURES['liver']).any() else 'spleen' if (label == STRUCTURES['spleen']).any() else None
    out['ref_organ'] = organ_name
    if organ_name and cortex.any():
        organ = (label == STRUCTURES[organ_name]) & usable
        rows = np.nonzero(cortex.any(axis=1))[0]
        tol = int(DEPTH_TOLERANCE_MM / spacing_mm) if spacing_mm else int(0.03 * label.shape[0])
        band = np.zeros_like(organ)
        band[max(0, rows.min() - tol):rows.max() + tol + 1] = True
        roi = organ & band
        if roi.sum() < 200:
            reasons.append(f'和皮質同深度的{"肝" if organ_name == "liver" else "脾"}像素太少')
        else:
            out['organ_mean'] = round(float(gray[roi].mean()), 2)
            out['organ_median'] = round(float(np.median(gray[roi])), 2)
            diff_px = abs(float(np.median(np.nonzero(roi)[0])) - float(np.median(np.nonzero(cortex)[0])))
            out['depth_diff_mm'] = round(diff_px * spacing_mm, 1) if spacing_mm else None
            if spacing_mm and diff_px * spacing_mm > MAX_DEPTH_DIFF_MM:
                reasons.append('參考組織和皮質深度差超過 15 mm')
    elif not organ_name:
        reasons.append('沒有肝或脾遮罩')

    if out['cortex_mean'] and out['organ_mean']:
        out['ratio_mean'] = round(out['cortex_mean'] / out['organ_mean'], 4)
        out['ratio_median'] = round(out['cortex_median'] / max(out['organ_median'], 1e-6), 4)
    if out['cortex_median'] is not None and out['organ_median'] is not None and out['sinus_median'] is not None and out['sinus_median'] > out['organ_median']:
        out['p_index'] = round((out['cortex_median'] - out['organ_median']) / (out['sinus_median'] - out['organ_median']), 4)  # 探索性指標
    out['reliable'] = not reasons and out['ratio_mean'] is not None
    out['reasons'] = '；'.join(reasons)
    return out


def _mask_sources(source: str, run_id: str | None, image_ids: list[str], mask_set_id: str | None = None) -> dict[str, tuple[Path, str]]:
    found: dict[str, tuple[Path, str]] = {}
    if source == 'mask_set':  # 交叉預測遮罩組：全部影像都有（M2.5，決策 D26）
        from ..ml.masksets import mask_path

        for i in image_ids:
            p = mask_path(mask_set_id, i)
            if p.exists():
                found[i] = (p, f'mask_set:{mask_set_id}')
        return found
    if source == 'run':
        from ..ml.defaults import seg_output_dir

        base = seg_output_dir(run_id)
        for i in image_ids:
            p = base / shard(i) / f'{i}.png'
            if p.exists():
                found[i] = (p, f'run:{run_id}')
        return found
    with session_scope('research') as db:
        rows = (
            db.query(MaskAnnotation.image_id, MaskAnnotation.relpath, MaskAnnotation.source)
            .filter(MaskAnnotation.trashed_at.is_(None), MaskAnnotation.status != 'rejected')
            .order_by(MaskAnnotation.image_id, MaskAnnotation.version)
            .all()
        )
    for image_id, relpath, src in rows:
        found[image_id] = (storage.from_root(relpath), src)  # 依版本排序，最後一筆就是最新的
    return found


def create(source: str, run_id: str | None, note: str, operator: str, *, mask_set_id: str | None = None) -> dict[str, Any]:
    from ..jobs.manager import get_manager

    if source not in ('masks', 'run', 'mask_set'):
        raise AppError(422, 'BAD_SOURCE', '特徵來源只能是 masks、run 或 mask_set。')
    if source == 'mask_set':
        from ..ml.masksets import get

        if not mask_set_id or get(mask_set_id)['status'] != 'completed':
            raise AppError(409, 'MASK_SET_NOT_READY', '請選擇已完成的遮罩組。')
    with session_scope('research') as db:
        if source == 'run':
            run = db.get(TrainingRun, run_id or '')
            if run is None or run.task != 'segmentation' or run.status != 'completed':
                raise AppError(409, 'RUN_NOT_READY', '請選擇已完成的分割訓練（交叉擬合需要它的 out-of-fold 預測遮罩）。')
        fs_id = next_dated('FS-', [r[0] for r in db.query(FeatureSet.id).all()], width=3)
        spec = {'source': source, 'run_id': run_id if source == 'run' else None, 'mask_set_id': mask_set_id if source == 'mask_set' else None,
                'cross_fitted': source in ('run', 'mask_set'), 'note': note,
                'cortex_fraction': CORTEX_FRACTION, 'cortex_max_mm': CORTEX_MAX_MM, 'depth_tolerance_mm': DEPTH_TOLERANCE_MM}
        db.add(FeatureSet(id=fs_id, spec_json=json.dumps(spec, ensure_ascii=False), relpath=folder(fs_id).relative_to(get_settings().root).as_posix(), status='running', created_by=operator, created_at=now_iso()))
    job_id = get_manager().submit('extract_features', {'feature_set_id': fs_id}, target=fs_id, created_by=operator)
    with session_scope('research') as db:
        db.get(FeatureSet, fs_id).job_id = job_id
    return {'id': fs_id, 'job_id': job_id}


@register('extract_features', resumable=False, label='擷取回音特徵')
def extract_job(ctx: JobContext) -> dict[str, Any]:
    fs_id = ctx.config['feature_set_id']
    with session_scope('research') as db:
        fs = db.get(FeatureSet, fs_id)
        spec = json.loads(fs.spec_json)
        images = [(i.id, i.patient_id, i.side, i.pixel_spacing_mm, i.sonographer_length_mm, i.scan_params_json) for i in db.query(Image).filter(Image.status == 'usable').order_by(Image.id)]
    sources = _mask_sources(spec['source'], spec.get('run_id'), [i[0] for i in images], spec.get('mask_set_id'))
    out_dir = folder(fs_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    todo = [i for i in images if i[0] in sources]
    for index, (image_id, patient_id, side, spacing, dist_a, params) in enumerate(todo, 1):
        ctx.check_stop()
        ctx.progress(index / max(1, len(todo)) * 100, f'{index}／{len(todo)}')
        path, src = sources[image_id]
        label = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
        gray, valid = deid.read_gray_alpha(storage.image_path(image_id, 'calc'))
        row = measure(label, gray, valid > 0, side, spacing)
        row.update(image_id=image_id, patient_id=patient_id, side=side, mask_source=src, dist_a_mm=dist_a, gain=json.loads(params or '{}').get('gain'))
        rows.append(row)
    with (out_dir / 'features.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    (out_dir / 'spec.json').write_text(json.dumps({'id': fs_id, **spec, 'rows': len(rows), 'created_at': now_iso()}, ensure_ascii=False, indent=2), encoding='utf-8')
    with session_scope('research') as db:
        fs = db.get(FeatureSet, fs_id)
        fs.rows, fs.status = len(rows), 'completed'
    return {'feature_set_id': fs_id, 'rows': len(rows), 'reliable': sum(1 for r in rows if r['reliable'])}


def ensure_live(feature_set_id: str) -> None:
    """特徵集要存在、不在回收桶（頁面查看、匯出、建立新訓練時檢查）。"""
    with session_scope('research') as db:
        f = db.get(FeatureSet, feature_set_id)
        if f is None or f.trashed_at:
            raise AppError(404, 'FEATURES_NOT_FOUND', '找不到這個特徵集（可能已移入回收桶）。')


def read_table(feature_set_id: str) -> list[dict[str, Any]]:
    path = folder(feature_set_id) / 'features.csv'
    if not path.exists():
        raise AppError(404, 'FEATURES_NOT_FOUND', '找不到這個特徵集（可能還在計算）。')
    with path.open(encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for c in NUMERIC:
            r[c] = float(r[c]) if r.get(c) not in (None, '') else None
        r['reliable'] = r.get('reliable') == 'True'
    return rows


def analyze(feature_set_id: str) -> dict[str, Any]:
    """右腎／肝、左腎／脾分開：比值與 eGFR 的 Spearman 相關；自動腎長對技師 Dist A 的 Bland-Altman。"""
    ensure_live(feature_set_id)
    rows = read_table(feature_set_id)
    with session_scope('research') as db:
        egfr = {p.id: p.egfr for p in db.query(Patient).all()}
    by_side: dict[str, Any] = {}
    for side, organ in (('right', 'liver'), ('left', 'spleen')):
        sub = [r for r in rows if r['side'] == side and r['reliable'] and egfr.get(r['patient_id']) is not None]
        entry: dict[str, Any] = {'ref_organ': organ, 'n': len(sub)}
        for col in ('ratio_mean', 'ratio_median', 'p_index'):
            pairs = [(r[col], egfr[r['patient_id']]) for r in sub if r[col] is not None]
            if len(pairs) >= 5:
                rho, p = stats.spearmanr([a for a, _ in pairs], [b for _, b in pairs])
                entry[col] = {'n': len(pairs), 'rho': round(float(rho), 3), 'p': float(p), 'median': round(float(np.median([a for a, _ in pairs])), 3)}
        by_side[side] = entry
    pairs = [(r['length_mm'], r['dist_a_mm']) for r in rows if r['length_mm'] and r['dist_a_mm']]
    ba: dict[str, Any] = {'n': len(pairs)}
    if len(pairs) >= 3:
        d = np.array([a - b for a, b in pairs])
        ba.update(mean_diff_mm=round(float(d.mean()), 2), sd_mm=round(float(d.std(ddof=1)), 2), loa_low_mm=round(float(d.mean() - 1.96 * d.std(ddof=1)), 2), loa_high_mm=round(float(d.mean() + 1.96 * d.std(ddof=1)), 2))
    reasons: dict[str, int] = {}
    for r in rows:
        for reason in filter(None, (r['reasons'] or '').split('；')):
            reasons[reason] = reasons.get(reason, 0) + 1
    return {'feature_set_id': feature_set_id, 'rows': len(rows), 'reliable': sum(1 for r in rows if r['reliable']), 'by_side': by_side, 'length_vs_dist_a': ba, 'unreliable_reasons': reasons}


def export(feature_set_id: str) -> dict[str, Any]:
    """匯出到 08_匯出/{日期}_特徵_{FS-ID}/：逐張特徵、Spearman、Bland-Altman（Excel 可開；病人只用 P-編號，不含 eGFR 數值）。"""
    from ..services.workspace import new_export_dir

    ensure_live(feature_set_id)
    rows = read_table(feature_set_id)
    result = analyze(feature_set_id)
    out = new_export_dir(f'特徵_{feature_set_id}')
    with (folder(feature_set_id) / 'features.csv').open(encoding='utf-8') as src, (out / '特徵.csv').open('w', encoding='utf-8-sig', newline='') as dst:
        dst.write(src.read())
    with (out / 'Spearman.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['側別', '參考器官', '特徵', '影像數', 'Spearman rho', 'p 值', '中位數'])
        for side, entry in result['by_side'].items():
            for col in ('ratio_mean', 'ratio_median', 'p_index'):
                if col in entry:
                    e = entry[col]
                    w.writerow([side, entry['ref_organ'], col, e['n'], e['rho'], f"{e['p']:.4g}", e['median']])
    ba = result['length_vs_dist_a']
    with (out / '腎長BlandAltman.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['影像數', '平均差（mm）', '標準差（mm）', '一致性下限（mm）', '一致性上限（mm）'])
        w.writerow([ba['n'], ba.get('mean_diff_mm', ''), ba.get('sd_mm', ''), ba.get('loa_low_mm', ''), ba.get('loa_high_mm', '')])
    (out / '說明.txt').write_text(
        f'特徵集 {feature_set_id} 的匯出（{len(rows)} 張影像，可靠 {result["reliable"]} 張）。\n'
        '特徵.csv：逐張的腎長、皮質與參考器官亮度、比值、P 指數、深度差、是否可靠與原因；病人只用 P-編號。\n'
        'Spearman.csv：右腎（肝）、左腎（脾）分開，比值與 eGFR 的 Spearman 相關（只用可靠的影像）。\n'
        '腎長BlandAltman.csv：自動腎長和技師量的 Dist A 的一致性。\n',
        encoding='utf-8')
    return {'folder': out.relative_to(get_settings().root).as_posix()}


def list_sets() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        return [
            {'id': f.id, 'spec': json.loads(f.spec_json), 'rows': f.rows, 'status': f.status, 'job_id': f.job_id, 'relpath': f.relpath, 'created_by': f.created_by, 'created_at': f.created_at}
            for f in db.query(FeatureSet).filter(FeatureSet.trashed_at.is_(None)).order_by(FeatureSet.created_at.desc()).all()
        ]
