"""醫師端自動分析（M3-3）。

- 走醫師端佇列（不排在訓練後面）；模型來自分析方案，用快取（預熱過就不用再載入）。
- 每個步驟各自成功或失敗：分割、eGFR、回音分級；失敗的步驟不影響其他步驟，可以重新分析。
- eGFR 以整次檢查（同一位病人兩側所有影像）整合，和訓練、評估的病人層級一致（D44）；左右側只分開顯示腎長、回音比、P 指數。
- 缺像素間距：腎長不可用，回音比照樣計算；每項結果標示缺了什麼。
- 合約：④ 遮罩通道、⑤ 遮罩量測都要搭配訓練時用的分割訓練註冊的分割模型；② 缺臨床資料時略過並標示。
- 每次分析一筆不可修改的紀錄（B8）；重新分析是新增一筆。
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from ..core.errors import AppError
from ..core.ids import next_dated, now_iso
from ..db.models_clinical import ClinicalAnalysis, ClinicalExam, ClinicalImage
from ..db.session import session_scope
from ..jobs.manager import JobContext, get_manager, register
from . import exams, plan

STEP_LABELS = {'segmentation': '分割', 'egfr': 'eGFR', 'grade': '回音分級'}


def start(exam_id: str, operator: str, retry_of: str | None = None) -> dict[str, str]:
    with session_scope('clinical') as db:
        exam = db.get(ClinicalExam, exam_id)
        if exam is None or exam.trashed_at:
            raise AppError(404, 'EXAM_NOT_FOUND', '找不到這筆檢查。')
        if not db.query(ClinicalImage).filter(ClinicalImage.exam_id == exam_id, ClinicalImage.status == 'ok').count():
            raise AppError(409, 'NO_USABLE_IMAGES', '這筆檢查沒有可分析的影像（可能版面不符、去識別化有殘留，或全部被排除）。')
        analysis_id = next_dated('AN-', [a for (a,) in db.query(ClinicalAnalysis.id).all()], width=3)
        db.add(ClinicalAnalysis(id=analysis_id, exam_id=exam_id, status='queued', retry_of=retry_of, created_by=operator, created_at=now_iso()))
        exam.status = 'analyzing'
    job_id = get_manager().submit('clinical_analysis', {'analysis_id': analysis_id}, target=exam_id, created_by=operator)
    with session_scope('clinical') as db:
        db.get(ClinicalAnalysis, analysis_id).job_id = job_id
    return {'analysis_id': analysis_id, 'job_id': job_id}


def _snapshot() -> tuple[dict[str, Any], bool]:
    """分析當下的方案：每區的模型 ID、階段、合約版本、檔案雜湊（記進分析紀錄）。"""
    current = plan.current()
    from ..db.models_research import ModelEntry

    out: dict[str, Any] = {}
    with session_scope('research') as db:
        for zone, info in current['zones'].items():
            if not info['model_id']:
                continue
            m = db.get(ModelEntry, info['model_id'])
            manifest = json.loads(m.manifest_json)
            out[zone] = {'model_id': m.id, 'stage': m.stage, 'run_id': m.run_id, 'contract_version': manifest.get('contract_version'),
                         'hashes': manifest.get('ensemble'), 'inputs': manifest.get('inputs'), 'classes': manifest.get('classes')}
    return out, current['candidate']


def _read(exam_id: str, image_id: str):
    import cv2

    from ..data import deid

    gray = cv2.imdecode(np.fromfile(str(exams.image_file(exam_id, image_id, 'model')), np.uint8), cv2.IMREAD_GRAYSCALE)
    calc, valid = deid.read_gray_alpha(exams.image_file(exam_id, image_id, 'calc'))
    return gray, calc, valid > 0


@register('clinical_analysis', pool='clinical', label='醫師端自動分析')
def analysis_job(ctx: JobContext) -> dict[str, Any]:
    from ..data import deid
    from ..data import egfr as E
    from ..features.service import measure
    from ..ml import registry
    from ..ml.masksets import postprocess
    from ..services import backups
    from . import models_cache

    analysis_id = ctx.config['analysis_id']
    try:  # 系統一直開著時，每天第一次分析前補做每日快照（M3-8）
        backups.daily_snapshot()
    except Exception:  # noqa: BLE001
        pass
    with session_scope('clinical') as db:
        a = db.get(ClinicalAnalysis, analysis_id)
        a.status = 'running'
        exam = db.get(ClinicalExam, a.exam_id)
        exam_id = exam.id
        clinical = exams.clinical_for_model(exam)
        missing_clinical = exams.missing_clinical(exam)
        images = [(i.id, i.side, i.pixel_spacing_mm, json.loads(i.deid_json or '{}')) for i in
                  db.query(ClinicalImage).filter(ClinicalImage.exam_id == exam_id, ClinicalImage.status == 'ok').order_by(ClinicalImage.seq).all()]
    models_info, candidate = _snapshot()
    _, device_note = models_cache.device_choice()
    steps: dict[str, Any] = {zone: {'status': 'not_configured', 'message': f'分析方案沒有選{STEP_LABELS[zone]}模型'} for zone in STEP_LABELS}
    per_image: dict[str, dict[str, Any]] = {i[0]: {'image_id': i[0], 'side': i[1], 'pixel_spacing_mm': i[2], 'missing': list(i[3].get('missing') or []),
                                                   'sonographer_length_mm': i[3].get('sonographer_length_mm')} for i in images}
    labels: dict[str, Any] = {}
    out_dir = exams.analysis_dir(exam_id, analysis_id)
    loaded: dict[str, Any] = {}
    device = ''
    for zone in ('segmentation', 'egfr', 'grade'):
        if zone in models_info:
            try:
                loaded[zone] = models_cache.get(models_info[zone]['model_id'], zone)
                device = device or str(loaded[zone].device)
            except AppError as exc:
                steps[zone] = {'status': 'failed', 'message': exc.message}
    seg = loaded.get('segmentation')

    # 1. 分割與量測
    if seg is not None:
        try:
            for n, (image_id, side, spacing, _) in enumerate(images, start=1):
                ctx.check_stop()
                gray, calc, valid = _read(exam_id, image_id)
                label = postprocess(registry.predict_segmentation(seg, gray))
                deid.write_png(out_dir / f'{image_id}_mask.png', label)
                labels[image_id] = label
                feats = measure(label, calc, valid, side, spacing)
                per_image[image_id].update({k: feats.get(k) for k in ('length_mm', 'width_mm', 'ratio_mean', 'ratio_median', 'p_index', 'ref_organ', 'reliable', 'reasons')})
                per_image[image_id]['mask'] = exams.rel(out_dir / f'{image_id}_mask.png')
                ctx.progress(n / max(1, len(images)) * 50, f'分割 {n}／{len(images)}')
            steps['segmentation'] = {'status': 'done', 'message': ''}
        except Exception as exc:  # noqa: BLE001  一步失敗不影響其他步驟
            if isinstance(exc, AppError):
                msg = exc.message
            else:
                msg = f'分割失敗：{type(exc).__name__}'
            steps['segmentation'] = {'status': 'failed', 'message': msg}
            labels.clear()

    # 2、3. 分類（eGFR、回音分級）
    def classify(zone: str) -> dict[str, list[float]] | None:
        model = loaded[zone]
        manifest = model.manifest
        inputs = manifest.get('inputs') or ['image']
        need_labels = 'mask_channels' in inputs or 'measures' in inputs
        if 'clinical' in inputs and missing_clinical:
            steps[zone] = {'status': 'skipped', 'message': f'缺臨床資料（{"、".join(missing_clinical)}），這個模型（影像＋臨床）不執行；補填後重新分析', 'missing': missing_clinical}
            return None
        if need_labels:
            needed = (manifest['input'].get('mask_source') or {}).get('seg_run_id') or (manifest['input'].get('measures_source') or {}).get('seg_run_id')
            if seg is None or not labels:
                steps[zone] = {'status': 'failed', 'message': '這個模型需要分割遮罩，但分割步驟沒有完成'}
                return None
            if needed and seg.manifest['training']['run_id'] != needed:
                steps[zone] = {'status': 'failed', 'message': f'這個模型需要分割訓練 {needed} 註冊的分割模型，請在「設定 › 醫師端」更換分割模型'}
                return None
        probs: dict[str, list[float]] = {}
        for image_id, side, spacing, _ in images:
            ctx.check_stop()
            gray, _, _ = _read(exam_id, image_id)
            feats = None
            if manifest.get('features'):
                raw = {k: per_image[image_id].get(k) for k in ('length_mm', 'ratio_mean', 'ratio_median', 'p_index')}
                feats = registry.standardize(model, raw, clinical)
                if 'measures' in inputs and per_image[image_id].get('length_mm') is None:
                    per_image[image_id]['missing'].append(f'{STEP_LABELS[zone]}模型的腎長是缺值（以平均補上）')
            label = labels.get(image_id) if 'mask_channels' in inputs else None
            if label is not None and not spacing:
                per_image[image_id]['missing'].append('沒有像素間距，遮罩通道改用腎臟外接框裁切')
            probs[image_id] = registry.predict_classification(model, gray, feats, label, spacing)
        steps[zone] = {'status': 'done', 'message': ''}
        return probs

    egfr_result = grade_result = None
    if 'egfr' in loaded:
        try:
            probs = classify('egfr')
            if probs:
                k = len(loaded['egfr'].manifest['classes'])
                mean = np.mean(list(probs.values()), 0)  # 整次檢查整合（D44）
                egfr_result = {'k': k, 'classes': loaded['egfr'].manifest['classes'], 'probs': [round(float(v), 4) for v in mean],
                               'p_lt60': round(float(E.p_lt(mean[None], k, 60)[0]), 4), 'p_lt30': round(float(E.p_lt(mean[None], k, 30)[0]), 4) if k >= 3 else None,
                               'predicted': loaded['egfr'].manifest['classes'][int(np.argmax(mean))], 'images': len(probs)}
                for image_id, p in probs.items():
                    per_image[image_id]['egfr_probs'] = [round(float(v), 4) for v in p]
        except Exception as exc:  # noqa: BLE001
            steps['egfr'] = {'status': 'failed', 'message': exc.message if isinstance(exc, AppError) else f'eGFR 失敗：{type(exc).__name__}'}
        ctx.progress(80, 'eGFR')
    if 'grade' in loaded:
        try:
            probs = classify('grade')
            if probs:
                classes = loaded['grade'].manifest['classes']
                grade_result = {}
                for side in ('right', 'left'):
                    ps = [p for image_id, p in probs.items() if per_image[image_id]['side'] == side]
                    if ps:
                        mean = np.mean(ps, 0)
                        grade_result[side] = {'probs': [round(float(v), 4) for v in mean], 'predicted': classes[int(np.argmax(mean))], 'classes': classes}
        except Exception as exc:  # noqa: BLE001
            steps['grade'] = {'status': 'failed', 'message': exc.message if isinstance(exc, AppError) else f'回音分級失敗：{type(exc).__name__}'}

    # 左右側：影像量測（腎長取最長、回音比與 P 指數取中位數）
    sides: dict[str, Any] = {}
    for side in ('right', 'left'):
        rows = [r for r in per_image.values() if r['side'] == side]
        if not rows:
            continue
        lengths = [r for r in rows if r.get('length_mm')]
        longest = max(lengths, key=lambda r: r['length_mm']) if lengths else None
        ratios = [r['ratio_mean'] for r in rows if r.get('ratio_mean') is not None]
        pidx = [r['p_index'] for r in rows if r.get('p_index') is not None]
        sono = [r['sonographer_length_mm'] for r in rows if r.get('sonographer_length_mm')]
        sides[side] = {'images': len(rows), 'length_mm': longest['length_mm'] if longest else None, 'longest_image_id': longest['image_id'] if longest else None,
                       'ratio_mean': round(float(np.median(ratios)), 4) if ratios else None, 'p_index': round(float(np.median(pidx)), 4) if pidx else None,
                       'sonographer_length_mm': max(sono) if sono else None, 'grade': (grade_result or {}).get(side),
                       'missing': sorted({m for r in rows for m in r['missing']})}
    unassigned = [r['image_id'] for r in per_image.values() if r['side'] not in ('right', 'left')]

    configured = [s for s in steps.values() if s['status'] != 'not_configured']
    done = [s for s in configured if s['status'] == 'done']
    status = 'failed' if configured and not done else 'completed' if len(done) == len(configured) else 'partial'
    if not configured:
        status = 'partial'
    results = {'images': list(per_image.values()), 'sides': sides, 'unassigned': unassigned, 'egfr': egfr_result}
    with session_scope('clinical') as db:
        a = db.get(ClinicalAnalysis, analysis_id)
        a.status, a.finished_at = status, now_iso()
        a.models_json = json.dumps(models_info, ensure_ascii=False)
        a.inputs_json = json.dumps({'clinical': clinical, 'missing_clinical': missing_clinical, 'device_note': device_note}, ensure_ascii=False)
        a.steps_json = json.dumps(steps, ensure_ascii=False)
        a.results_json = json.dumps(results, ensure_ascii=False)
        a.candidate, a.device = bool(candidate and done), device
        exam = db.get(ClinicalExam, exam_id)
        exam.latest_analysis_id = analysis_id
        if exam.status not in ('signed',):
            exam.status = ('needs_data' if any(s['status'] == 'skipped' for s in steps.values()) else
                           'ready' if status == 'completed' else 'partial' if status == 'partial' else 'failed')
    ctx.progress(100, '完成')
    return {'analysis_id': analysis_id, 'status': status, 'steps': {k: v['status'] for k, v in steps.items()}}


def analysis_dict(a: ClinicalAnalysis) -> dict[str, Any]:
    return {'id': a.id, 'status': a.status, 'models': json.loads(a.models_json or '{}'), 'inputs': json.loads(a.inputs_json or '{}'),
            'steps': json.loads(a.steps_json or '{}'), 'results': json.loads(a.results_json or '{}'), 'candidate': a.candidate,
            'candidate_label': plan.CANDIDATE_LABEL if a.candidate else '', 'device': a.device, 'retry_of': a.retry_of, 'job_id': a.job_id,
            'created_by': a.created_by, 'created_at': a.created_at, 'finished_at': a.finished_at}


def overlay_png(analysis_id: str, image_id: str) -> bytes:
    """預測遮罩轉成半透明彩色 PNG（和一鍵流程的顏色一致），疊在去識別化影像上。"""
    import cv2

    from ..ml.pipeline import OVERLAY

    with session_scope('clinical') as db:
        a = db.get(ClinicalAnalysis, analysis_id)
        if a is None:
            raise AppError(404, 'ANALYSIS_NOT_FOUND', '找不到這次分析。')
        path = exams.analysis_dir(a.exam_id, analysis_id) / f'{image_id}_mask.png'
    if not path.exists():
        raise AppError(404, 'MASK_NOT_FOUND', '這張影像沒有預測遮罩。')
    label = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
    rgba = np.zeros((*label.shape, 4), np.uint8)
    for value, color in OVERLAY.items():
        rgba[label == value] = color
    return cv2.imencode('.png', rgba)[1].tobytes()
