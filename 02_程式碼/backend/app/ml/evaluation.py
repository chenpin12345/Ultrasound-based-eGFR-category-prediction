"""評估：交叉驗證（out-of-fold）、固定測試集（只能一次）、兩個訓練的比較。

- 影像層級與病人層級（同一病人、同一側的影像機率平均）都報告。
- 信賴區間以病人為單位重抽 bootstrap。
- 固定測試集：依任務（分割、eGFR、回音分級）各自鎖定，評估一次後該任務不能再評估（M2.5，決策 D27）。
  分割：每個測試病人側至少 1 張人工確認的遮罩才能評估，只評估有確認遮罩的影像。
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_dated, now_iso
from ..data.versions import mask_verified
from ..db.models_research import Evaluation, Image, MaskAnnotation, ModelEntry, Split, SplitEntry, TrainingRun
from ..db.session import session_scope
from ..jobs.manager import JobContext, get_manager, register
from . import metrics
from .runs import oof_predictions


from .paths import eval_dir, new_eval_dir  # noqa: E402  03_評估/{任務}/{EVAL-ID}_{對象}


def _binary_report(rows: list[dict[str, Any]], prob_key: str) -> dict[str, Any]:
    y = np.array([r['target'] for r in rows])
    p = np.array([r[prob_key][1] for r in rows])
    image = metrics.binary_metrics(y, p)
    image['auc_ci'] = metrics.bootstrap_ci(rows, lambda rs: metrics.auc(np.array([r['target'] for r in rs]), np.array([r[prob_key][1] for r in rs])))
    # 病人層級：同一病人所有影像的機率平均
    by_patient: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_patient.setdefault(r['patient_id'], []).append(r)
    prow = [{'patient_id': pid, 'target': rs[0]['target'], 'p': float(np.mean([r[prob_key][1] for r in rs]))} for pid, rs in by_patient.items()]
    patient = metrics.binary_metrics(np.array([r['target'] for r in prow]), np.array([r['p'] for r in prow]))
    patient['auc_ci'] = metrics.bootstrap_ci(prow, lambda rs: metrics.auc(np.array([r['target'] for r in rs]), np.array([r['p'] for r in rs])))
    return {'image': image, 'patient': patient}


def patient_rows(rows: list[dict[str, Any]], prob_key: str) -> list[dict[str, Any]]:
    """同一位病人所有影像的類別機率取平均（左右合併）；eGFR 是病人層級的答案。"""
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r['patient_id'], []).append(r)
    return [{'patient_id': pid, 'target': rs[0]['target'], 'fold': rs[0].get('fold'), 'n_images': len(rs), prob_key: np.mean([r[prob_key] for r in rs], 0).tolist()} for pid, rs in by.items()]


def _egfr_level(rows: list[dict[str, Any]], prob_key: str, k: int) -> dict[str, Any]:
    from ..data import egfr as E

    y = np.array([r['target'] for r in rows])
    probs = np.array([r[prob_key] for r in rows])
    out = metrics.egfr_metrics(y, probs, k)

    def auc_at(cut):
        def f(rs):
            pr = np.array([r[prob_key] for r in rs])
            return metrics.fast_auc(E.y_lt(np.array([r['target'] for r in rs]), k, cut), E.p_lt(pr, k, cut))
        return f

    out['auc_lt60_ci'] = metrics.bootstrap_ci(rows, auc_at(60))
    if k >= 3:
        out['auc_lt30_ci'] = metrics.bootstrap_ci(rows, auc_at(30))
        out['qwk_ci'] = metrics.bootstrap_ci(rows, lambda rs: metrics.ordinal_metrics(np.array([r['target'] for r in rs]), np.array([r[prob_key] for r in rs]))['qwk'])
    if k == 2:
        out['auc_ci'] = out['auc_lt60_ci']  # 舊欄位名稱（評估報告表格用）
    collapsed = {}
    for to in (3, 2):
        if to < k:
            cp, cy = E.collapse_probs(probs, k, to), E.collapse_labels(y, k, to)
            collapsed[str(to)] = metrics.egfr_metrics(cy, cp, to)
    if collapsed:
        out['collapsed'] = collapsed
    out['classes'] = E.classes(k)
    return out


def _egfr_report(rows: list[dict[str, Any]], prob_key: str) -> dict[str, Any]:
    """eGFR 2／3／5 類：影像層級與病人層級（同一病人所有影像的機率平均）。共同的尺是 AUC(<60)。"""
    k = len(rows[0][prob_key])
    prow = patient_rows(rows, prob_key)
    return {'k': k, 'image': _egfr_level(rows, prob_key, k), 'patient': _egfr_level(prow, prob_key, k)}


def _ordinal_report(rows: list[dict[str, Any]], prob_key: str) -> dict[str, Any]:
    y = np.array([r['target'] for r in rows])
    probs = np.array([r[prob_key] for r in rows])
    image = metrics.ordinal_metrics(y, probs)

    def qwk(rs):
        return metrics.ordinal_metrics(np.array([r['target'] for r in rs]), np.array([r[prob_key] for r in rs]))['qwk']

    image['qwk_ci'] = metrics.bootstrap_ci(rows, qwk)
    # 病人＋側別層級：分級是每一側腎一個答案
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r['patient_id'], r['side']), []).append(r)
    srow = [{'patient_id': k[0], 'target': rs[0]['target'], prob_key: np.mean([r[prob_key] for r in rs], 0).tolist()} for k, rs in groups.items()]
    side = metrics.ordinal_metrics(np.array([r['target'] for r in srow]), np.array([r[prob_key] for r in srow]))
    side['qwk_ci'] = metrics.bootstrap_ci(srow, qwk)
    return {'image': image, 'patient_side': side}


def _seg_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {'n': len(rows)}
    for key in ('dice_mean', 'dice_parenchyma', 'dice_sinus', 'dice_liver', 'dice_spleen'):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if vals:
            sub = [r for r in rows if r.get(key) is not None]
            out[key] = {'mean': float(np.mean(vals)), 'n': len(vals), 'ci': metrics.bootstrap_ci(sub, lambda rs, k=key: float(np.mean([r[k] for r in rs])))}
    return out


def report(task: str, rows: list[dict[str, Any]], prob_key: str = 'calibrated') -> dict[str, Any]:
    if task == 'segmentation':
        return _seg_report(rows)
    if prob_key not in rows[0]:
        prob_key = 'probs'
    if task == 'grade':
        return _ordinal_report(rows, prob_key)
    return _egfr_report(rows, prob_key)


def _save(target: str, run_id: str | None, model_id: str | None, result: dict[str, Any], operator: str) -> str:
    subject = (model_id or '').replace('/', '-') or run_id or ''
    with session_scope('research') as db:
        eval_id = next_dated('EVAL-', [r[0] for r in db.query(Evaluation.id).all()], width=3)
        folder = new_eval_dir(eval_id, result.get('task', ''), subject)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        db.add(Evaluation(id=eval_id, model_id=model_id, run_id=run_id, target=target, metrics_json=json.dumps(result, ensure_ascii=False), relpath=folder.relative_to(get_settings().root).as_posix(), created_by=operator, created_at=now_iso()))
    return eval_id


def evaluate_oof(run_id: str, operator: str) -> dict[str, Any]:
    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        if run is None or run.status != 'completed':
            raise AppError(409, 'RUN_NOT_COMPLETED', '只能評估已完成的訓練。')
        task = run.task
    rows = oof_predictions(run_id)
    if not rows:
        raise AppError(409, 'NO_PREDICTIONS', '這個訓練沒有 out-of-fold 預測。')
    result = {'target': 'oof', 'task': task, 'run_id': run_id, **report(task, rows)}
    return {'id': _save('oof', run_id, None, result, operator), **result}


def compare(run_a: str, run_b: str) -> dict[str, Any]:
    """兩個用同一切分的訓練：逐折的最佳指標差，做 Nadeau-Bengio 校正 t 檢定。"""
    with session_scope('research') as db:
        a, b = db.get(TrainingRun, run_a), db.get(TrainingRun, run_b)
        if a is None or b is None or a.status != 'completed' or b.status != 'completed':
            raise AppError(409, 'RUN_NOT_COMPLETED', '兩個訓練都必須已完成。')
        if a.task != b.task:
            raise AppError(409, 'TASK_MISMATCH', '兩個訓練的任務不同，不能比較（eGFR、分割、回音分級各自比較）。')
        if a.split_id != b.split_id:
            raise AppError(409, 'SPLIT_MISMATCH', '兩個訓練用的切分不同，不能逐折比較。')
        sa, sb = json.loads(a.summary_json), json.loads(b.summary_json)
    fa = {f['fold']: f for f in sa['folds'] if 'best_score' in f}
    fb = {f['fold']: f for f in sb['folds'] if 'best_score' in f}
    common = sorted(set(fa) & set(fb))
    diffs = [fa[k]['best_score'] - fb[k]['best_score'] for k in common]
    n_train = int(np.mean([fa[k]['train_images'] for k in common])) if common else 0
    n_test = int(np.mean([fa[k]['val_images'] for k in common])) if common else 0
    return {'run_a': run_a, 'run_b': run_b, 'folds': common, 'diffs': diffs, **metrics.corrected_ttest(diffs, n_train, n_test)}


# ---------- 固定測試集（依任務只能一次）----------
def test_locks(split: Split) -> dict[str, Any]:
    locks = json.loads(split.test_locks_json or '{}')
    if split.test_locked and not locks:  # 舊版整個切分共用的鎖
        locks = {'*': {'note': '舊版整個切分共用的鎖'}}
    return locks


def is_locked(split: Split, scope: str) -> bool:
    locks = test_locks(split)
    return '*' in locks or scope in locks


def lock(split: Split, scope: str, info: dict[str, Any]) -> None:
    locks = test_locks(split)
    locks[scope] = {**info, 'at': now_iso()}
    split.test_locks_json = json.dumps(locks, ensure_ascii=False)


def latest_verified_masks(db, image_ids: list[str]) -> dict[str, MaskAnnotation]:
    """每張影像最新、未退回的遮罩；只有它是人工確認過的才算（測試答案必須是確認過的）。"""
    latest: dict[str, MaskAnnotation] = {}
    for mk in db.query(MaskAnnotation).filter(MaskAnnotation.image_id.in_(image_ids), MaskAnnotation.trashed_at.is_(None), MaskAnnotation.status != 'rejected').order_by(MaskAnnotation.version).all():
        latest[mk.image_id] = mk
    return {i: m for i, m in latest.items() if mask_verified(m)}


def missing_inputs(dataset_version_id: str, image_ids: list[str], feature_set_id: str | None, mask_set_id: str | None) -> dict[str, int]:
    """固定測試集影像缺少的模型輸入：⑤⑥ 的量測特徵、④ 的遮罩組遮罩。
    缺少時不能評估：否則量測會被默默補成平均值，或遮罩通道模型在測試集已鎖定後才失敗。"""
    from ..data.versions import load_manifest
    from ..features import service as features

    in_version = {i['id'] for i in load_manifest(dataset_version_id)['images']}
    ids = [i for i in image_ids if i in in_version]
    out = {'missing_features': 0, 'missing_masks': 0}
    if feature_set_id:
        have = {r['image_id'] for r in features.read_table(feature_set_id)}
        out['missing_features'] = sum(1 for i in ids if i not in have)
    if mask_set_id:
        from .masksets import mask_path

        out['missing_masks'] = sum(1 for i in ids if not mask_path(mask_set_id, i).exists())
    return out


def model_inputs(manifest: dict[str, Any]) -> tuple[str | None, str | None]:
    """模型需要的特徵集與遮罩組（沒有時為 None）。"""
    fspec = manifest.get('features') or {}
    return (fspec.get('measures') or {}).get('feature_set_id') or fspec.get('feature_set_id'), (manifest['input'].get('mask_source') or {}).get('mask_set_id')


def test_readiness(model_id: str) -> dict[str, Any]:
    with session_scope('research') as db:
        m = db.get(ModelEntry, model_id)
        if m is None or m.trashed_at:
            raise AppError(404, 'MODEL_NOT_FOUND', '找不到這個模型（或已在回收桶）。')
        run = db.get(TrainingRun, m.run_id)
        split = db.get(Split, run.split_id)
        patients = [r[0] for r in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == split.id, SplitEntry.group == 'test').all()]
        rows = db.query(Image).filter(Image.patient_id.in_(patients), Image.status == 'usable').all()
        images = [i.id for i in rows]
        locked = is_locked(split, m.task)
        missing: list[str] = []
        with_truth = len(images)
        if m.task == 'segmentation':
            # 每個測試病人側至少 1 張人工確認的遮罩（醫師只需圈約 72 張，不必全部 194 張）
            verified = latest_verified_masks(db, images)
            sides: dict[tuple[str, str], list[str]] = {}
            for i in rows:
                sides.setdefault((i.patient_id, i.side or '?'), []).append(i.id)
            missing = [f'{pid}／{side}' for (pid, side), ids in sorted(sides.items()) if not any(x in verified for x in ids)]
            with_truth = len(verified)
        manifest, version = json.loads(m.manifest_json), run.dataset_version_id
    gaps = missing_inputs(version, images, *model_inputs(manifest)) if m.task != 'segmentation' else {'missing_features': 0, 'missing_masks': 0}
    return {'model_id': model_id, 'task': m.task, 'split_id': split.id, 'locked': locked, 'locks': test_locks(split), 'patients': len(patients), 'images': len(images),
            'images_with_truth': with_truth, 'missing_sides': missing, 'unverified_masks': len(missing), **gaps,
            'ready': not locked and not missing and with_truth > 0 and not any(gaps.values())}


def start_test(model_id: str, confirm: str, operator: str) -> dict[str, Any]:
    state = test_readiness(model_id)
    if state['locked']:
        raise AppError(409, 'TEST_LOCKED', '這個任務的固定測試集已經評估過，不能再用（避免依測試結果反覆調整）。')
    if state['unverified_masks']:
        raise AppError(409, 'TEST_MASKS_UNVERIFIED', f'測試集還有 {state["unverified_masks"]} 個病人側沒有人工確認的遮罩（每側至少 1 張），不能做最後評估。')
    if not state['images']:
        raise AppError(409, 'TEST_EMPTY', '固定測試集沒有可用影像。')
    if state['missing_features'] or state['missing_masks']:
        raise AppError(409, 'TEST_INPUTS_MISSING', f'測試影像缺少模型需要的輸入（量測特徵 {state["missing_features"]} 張、遮罩 {state["missing_masks"]} 張），請先用同一個資料集版本產生遮罩組與特徵集。')
    if confirm.strip() != model_id:
        raise AppError(422, 'CONFIRM_MISMATCH', '請輸入完整的模型名稱確認：固定測試集只能評估一次。')
    job_id = get_manager().submit('evaluate_test', {'model_id': model_id, 'operator': operator}, target=model_id, created_by=operator)
    return {'job_id': job_id, **state}


@register('evaluate_test', exclusive=True, label='固定測試集評估')
def evaluate_test_job(ctx: JobContext) -> dict[str, Any]:
    from ..annotation.drafts import mask_label
    from ..features import service as features
    from . import data as mldata
    from . import registry

    model_id = ctx.config['model_id']
    state = test_readiness(model_id)
    if state['locked']:
        raise AppError(409, 'TEST_LOCKED', '這個任務的固定測試集已經評估過。')
    model = registry.load(model_id)
    with session_scope('research') as db:
        m = db.get(ModelEntry, model_id)
        run = db.get(TrainingRun, m.run_id)
        split_id = run.split_id
        split = db.get(Split, split_id)
        lock(split, m.task, {'model_id': model_id, 'by': ctx.config.get('operator', '')})  # 先鎖定：評估中途失敗也不能重來
        patients = [r[0] for r in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == split_id, SplitEntry.group == 'test').all()]
        images = [(i.id, i.patient_id, i.side, i.pixel_spacing_mm) for i in db.query(Image).filter(Image.patient_id.in_(patients), Image.status == 'usable').order_by(Image.id)]
        truths = latest_verified_masks(db, [i[0] for i in images]) if m.task == 'segmentation' else {}
        truth_flags = {i: json.loads(t.flags_json or '{}') for i, t in truths.items()}
        truth_paths = {i: t for i, t in truths.items()}
        if m.task == 'segmentation':
            images = [i for i in images if i[0] in truths]  # 只評估有確認遮罩的影像
    task = model.task
    egfr_k = (model.manifest.get('egfr') or {}).get('classes', 2)
    samples = {s.image_id: s for s in mldata.build(task, run.dataset_version_id, split_id, egfr_classes=egfr_k)} if task != 'segmentation' else {}
    fspec = model.manifest.get('features') or {}
    fs_id = (fspec.get('measures') or {}).get('feature_set_id') or fspec.get('feature_set_id')
    feature_rows = {r['image_id']: r for r in features.read_table(fs_id)} if fs_id else {}
    rows = []
    for index, (image_id, patient_id, side, spacing) in enumerate(images, 1):
        ctx.check_stop()
        ctx.progress(index / max(1, len(images)) * 100, f'{index}／{len(images)}')
        gray = mldata.load_image(image_id)
        if task == 'segmentation':
            truth = mask_label(truth_paths[image_id])
            states = truth_flags[image_id].get('structures') or {}
            pred = registry.predict_segmentation(model, gray)
            row = {'image_id': image_id, 'patient_id': patient_id, 'side': side}
            per = []
            for name, value, state_key in (('parenchyma', 1, 'kidney'), ('sinus', 2, 'sinus'), ('liver', 3, 'liver'), ('spleen', 4, 'spleen')):
                t, p = truth == value, pred == value
                if t.any():
                    d = float(2 * (t & p).sum() / (t.sum() + p.sum()))
                    row[f'dice_{name}'] = d
                    per.append(d)
                elif states.get(state_key) == 'absent':  # 確定不在影像中：報告模型多畫了多少（偽陽性比例）
                    row[f'false_positive_{name}'] = float(p.mean())
            row['dice_mean'] = float(np.mean(per)) if per else None
            rows.append(row)
        else:
            s = samples.get(image_id)
            if s is None:
                continue
            feats = registry.standardize(model, feature_rows.get(image_id, {}), s.extra.get('clinical')) if model.manifest.get('features') else None
            label = None
            if model.manifest['input'].get('mode') == 'mask_channels':  # 測試病人的遮罩來自遮罩組（各折模型平均）
                import cv2

                from .masksets import mask_path

                label = cv2.imdecode(np.fromfile(str(mask_path(model.manifest['input']['mask_source']['mask_set_id'], image_id)), np.uint8), cv2.IMREAD_GRAYSCALE)
            probs = registry.predict_classification(model, gray, feats, label, spacing)
            rows.append({'image_id': image_id, 'patient_id': patient_id, 'side': side, 'target': s.target, 'calibrated': probs})
    if not rows:
        raise AppError(409, 'TEST_EMPTY', '固定測試集沒有可評估的影像。')
    result = {'target': 'test', 'task': task, 'model_id': model_id, 'split_id': split_id, **report(task, rows)}
    eval_id = _save('test', run.id, model_id, result, ctx.config.get('operator', ''))
    (eval_dir(eval_id) / 'predictions.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    return {'evaluation_id': eval_id}


def list_evaluations(model_id: str | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
    with session_scope('research') as db:
        q = db.query(Evaluation)
        if model_id:
            q = q.filter(Evaluation.model_id == model_id)
        if run_id:
            q = q.filter(Evaluation.run_id == run_id)
        hidden_runs = {r for (r,) in db.query(TrainingRun.id).filter(TrainingRun.trashed_at.isnot(None)).all()}
        hidden_models = {m for (m,) in db.query(ModelEntry.id).filter(ModelEntry.trashed_at.isnot(None)).all()}
        return [{'id': e.id, 'target': e.target, 'model_id': e.model_id, 'run_id': e.run_id, 'metrics': json.loads(e.metrics_json or '{}'), 'created_by': e.created_by, 'created_at': e.created_at}
                for e in q.order_by(Evaluation.created_at.desc()).all() if e.run_id not in hidden_runs and e.model_id not in hidden_models]  # 回收桶裡的訓練、模型的評估不列出
