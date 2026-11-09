"""交叉預測遮罩組（M2.5，決策 D26）：用分割訓練替資料集版本的「每一張」影像預測遮罩。

- 病人在第 k 折 → 用第 k 折的模型（訓練時沒看過這位病人）；測試集、前瞻集與沒有分組的病人 → 各折模型的 softmax 平均。
- 這樣 975 張都有遮罩，醫師只需要圈一部分影像；也和日後實際使用時一樣，用的是模型畫的遮罩。
- 後處理只保留最大的腎臟區塊（腎實質 ∪ 腎竇），肝、脾各保留最大區塊。
- 產生後自動擷取回音與形態特徵（來源 mask_set），給 eGFR 的 ⑤ 影像＋遮罩量測、⑥ 純遮罩量測使用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_dated, now_iso, shard
from ..data import deid
from ..data.versions import load_manifest
from ..db.models_research import FeatureSet, MaskSet, SplitEntry, TrainingRun
from ..db.session import session_scope
from ..jobs.manager import JobContext, register
from . import data as mldata

KIDNEY_MIN_PX = 200


def folder(ms_id: str) -> Path:
    return get_settings().path('model_outputs') / '預測遮罩組' / ms_id


def mask_path(ms_id: str, image_id: str) -> Path:
    return folder(ms_id) / shard(image_id) / f'{image_id}.png'


def _dict(m: MaskSet) -> dict[str, Any]:
    return {'id': m.id, 'seg_run_id': m.seg_run_id, 'split_id': m.split_id, 'dataset_version_id': m.dataset_version_id, 'spec': json.loads(m.spec_json or '{}'),
            'rows': m.rows, 'status': m.status, 'relpath': m.relpath, 'job_id': m.job_id, 'created_by': m.created_by, 'created_at': m.created_at}


def list_sets() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        return [_dict(m) for m in db.query(MaskSet).filter(MaskSet.trashed_at.is_(None)).order_by(MaskSet.created_at.desc()).all()]


def get(ms_id: str) -> dict[str, Any]:
    with session_scope('research') as db:
        m = db.get(MaskSet, ms_id)
        if m is None or m.trashed_at:
            raise AppError(404, 'MASK_SET_NOT_FOUND', '找不到這個遮罩組。')
        return _dict(m)


def _fold_checkpoints(run: TrainingRun) -> dict[str, Path]:
    from .paths import run_dir

    with session_scope('research') as db:
        folds = sorted({g for (g,) in db.query(SplitEntry.group).filter(SplitEntry.split_id == run.split_id).all() if g.startswith('fold-')})
    base = run_dir(run.id)
    found = {f: base / f / 'best.pth' for f in folds if (base / f / 'best.pth').exists()}
    missing = [f for f in folds if f not in found]
    if missing:
        # 缺折時若改用集成，會用到看過那位病人的模型 → 交叉預測失效
        raise AppError(409, 'MASKSET_INCOMPLETE_FOLDS', f'這個分割訓練缺少 {"、".join(missing)} 的模型；交叉預測需要每一折都完成。')
    return found


def create(seg_run_id: str, note: str, operator: str) -> dict[str, Any]:
    from ..jobs.manager import get_manager

    with session_scope('research') as db:
        run = db.get(TrainingRun, seg_run_id)
        if run is None or run.trashed_at or run.task != 'segmentation' or run.status != 'completed':
            raise AppError(409, 'RUN_NOT_READY', '請選擇已完成的分割訓練。')
        if json.loads(run.config_json or '{}').get('framework'):
            raise AppError(409, 'RUN_NOT_SUPPORTED', 'nnU-Net 基準不能產生遮罩組，請用內建的分割訓練。')
        _fold_checkpoints(run)
        ms_id = next_dated('MS-', [r[0] for r in db.query(MaskSet.id).all()], width=3)
        spec = {'seg_run_id': seg_run_id, 'note': note, 'ensemble': 'mean_softmax', 'postprocess': 'largest_component', 'cross_fitted': True}
        db.add(MaskSet(id=ms_id, seg_run_id=seg_run_id, split_id=run.split_id, dataset_version_id=run.dataset_version_id, spec_json=json.dumps(spec, ensure_ascii=False),
                       relpath=folder(ms_id).relative_to(get_settings().root).as_posix(), status='queued', created_by=operator, created_at=now_iso()))
    job_id = get_manager().submit('mask_set', {'mask_set_id': ms_id, 'operator': operator}, target=ms_id, created_by=operator)
    with session_scope('research') as db:
        db.get(MaskSet, ms_id).job_id = job_id
    return {'id': ms_id, 'job_id': job_id}


def postprocess(label: np.ndarray) -> np.ndarray:
    """只保留最大的腎臟區塊（腎實質 ∪ 腎竇）；肝、脾各保留最大區塊。所有使用遮罩組、流程的地方都用這一份。"""
    out = np.zeros_like(label)
    kidney = (label == 1) | (label == 2)
    n, comp, stats, _ = cv2.connectedComponentsWithStats(kidney.astype(np.uint8), 8)
    if n > 1:
        keep = comp == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        out[keep & (label == 1)] = 1
        out[keep & (label == 2)] = 2
    for value in (3, 4):
        organ = label == value
        n, comp, stats, _ = cv2.connectedComponentsWithStats(organ.astype(np.uint8), 8)
        if n > 1:
            out[comp == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))] = value
    return out


def _load_nets(run_id: str, checkpoints: dict[str, Path], cfg: dict[str, Any]):
    import torch

    from .models import build_segmentation

    dev = torch.device('cuda' if torch.cuda.is_available() and cfg.get('device', 'auto') != 'cpu' else 'cpu')
    nets = {}
    for fold, path in checkpoints.items():
        net = build_segmentation(cfg['arch'], 'random', mldata.NUM_SEG_CLASSES)
        net.load_state_dict(torch.load(path, map_location=dev, weights_only=True)['model'])
        nets[fold] = net.to(dev).eval()
    return nets, dev


def _softmax(net, x):
    import torch

    with torch.no_grad():
        return torch.softmax(net(x).float(), 1)


@register('mask_set', exclusive=True, resumable=True, label='產生交叉預測遮罩組')
def mask_set_job(ctx: JobContext) -> dict[str, Any]:
    import torch

    from . import augment
    from .defaults import full_config

    ms_id = ctx.config['mask_set_id']
    with session_scope('research') as db:
        m = db.get(MaskSet, ms_id)
        m.status = 'running'
        run = db.get(TrainingRun, m.seg_run_id)
        cfg = full_config('segmentation', json.loads(run.config_json))
        version, split_id = m.dataset_version_id, m.split_id
        groups = dict(db.query(SplitEntry.patient_id, SplitEntry.group).filter(SplitEntry.split_id == split_id).all())
        checkpoints = _fold_checkpoints(run)
    nets, dev = _load_nets(run.id, checkpoints, cfg)
    images = load_manifest(version)['images']
    rows: dict[str, Any] = {}
    manifest_path = folder(ms_id) / 'manifest.json'
    if manifest_path.exists():  # 恢復：沿用已經做完的
        rows = json.loads(manifest_path.read_text(encoding='utf-8')).get('images', {})
    try:
        for n, img in enumerate(images, start=1):
            ctx.check_stop()
            image_id = img['id']
            out = mask_path(ms_id, image_id)
            if image_id in rows and out.exists():
                continue
            group = groups.get(img['patient_id'], 'unassigned')
            gray = mldata.load_image(image_id)
            boxed, box = augment.letterbox(gray, cfg['img_size'])
            x = torch.from_numpy(augment.to_tensor_array(boxed, cfg['init']))[None].to(dev)
            if group in nets:
                prob, source = _softmax(nets[group], x), group  # 這一折的模型沒看過這位病人
            else:
                prob, source = sum(_softmax(net, x) for net in nets.values()) / len(nets), 'ensemble'
            label = postprocess(augment.unletterbox(prob.argmax(1)[0].cpu().numpy().astype(np.uint8), box))
            deid.write_png(out, label)
            kidney = int(((label == 1) | (label == 2)).sum())
            rows[image_id] = {'group': group, 'source': source, 'kidney_px': kidney, 'sinus_px': int((label == 2).sum()),
                              'organ_px': int(((label == 3) | (label == 4)).sum()), 'no_kidney': kidney < KIDNEY_MIN_PX}
            if n % 25 == 0:
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(json.dumps({'id': ms_id, 'images': rows}, ensure_ascii=False), encoding='utf-8')
            ctx.progress(n / len(images) * 95, f'預測 {n}／{len(images)}')
    except Exception:
        with session_scope('research') as db:
            db.get(MaskSet, ms_id).status = 'failed'
        raise
    no_kidney = sum(1 for r in rows.values() if r['no_kidney'])
    manifest = {'id': ms_id, 'seg_run_id': run.id, 'dataset_version_id': version, 'split_id': split_id, 'created_at': now_iso(), 'postprocess': 'largest_component',
                'ensemble': 'mean_softmax', 'folds': sorted(nets), 'no_kidney': no_kidney, 'images': rows}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    with session_scope('research') as db:
        m = db.get(MaskSet, ms_id)
        spec = json.loads(m.spec_json or '{}')
        m.spec_json = json.dumps({**spec, 'no_kidney': no_kidney, 'folds': sorted(nets)}, ensure_ascii=False)
        m.rows, m.status = len(rows), 'completed'
    from ..features import service as features

    fs = features.create('mask_set', None, f'遮罩組 {ms_id} 自動擷取', ctx.config.get('operator', ''), mask_set_id=ms_id)
    return {'mask_set_id': ms_id, 'images': len(rows), 'no_kidney': no_kidney, 'feature_set_id': fs['id']}


def feature_set_for(ms_id: str) -> str:
    """這個遮罩組最新、已完成的特徵集（⑤⑥ 使用）。"""
    with session_scope('research') as db:
        for f in db.query(FeatureSet).filter(FeatureSet.status == 'completed', FeatureSet.trashed_at.is_(None)).order_by(FeatureSet.created_at.desc()).all():
            if json.loads(f.spec_json or '{}').get('mask_set_id') == ms_id:
                return f.id
    raise AppError(409, 'FEATURES_REQUIRED', '這個遮罩組還沒有特徵集（產生遮罩組後會自動擷取，請等它完成，或在「特徵擷取」用這個遮罩組擷取）。')


def overlay_png(ms_id: str, image_id: str) -> bytes:
    from ..data import storage
    from ..annotation.circling import OVERLAY_COLORS

    get(ms_id)
    base = cv2.imdecode(np.fromfile(str(storage.image_path(image_id, 'model')), np.uint8), cv2.IMREAD_GRAYSCALE)
    path = mask_path(ms_id, image_id)
    if base is None or not path.exists():
        raise AppError(404, 'NOT_FOUND', '這個遮罩組沒有這張影像。')
    label = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
    out = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    color = out.copy()
    for value, bgr in OVERLAY_COLORS.items():
        color[label == value] = bgr
    out = cv2.addWeighted(out, 0.55, color, 0.45, 0)
    scale = min(1.0, 900 / out.shape[1])
    if scale < 1:
        out = cv2.resize(out, (int(out.shape[1] * scale), int(out.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    return cv2.imencode('.png', out)[1].tobytes()


def coverage(ms_id: str) -> dict[str, Any]:
    info = get(ms_id)
    path = folder(ms_id) / 'manifest.json'
    rows = json.loads(path.read_text(encoding='utf-8')).get('images', {}) if path.exists() else {}
    by_source: dict[str, int] = {}
    for r in rows.values():
        by_source[r['source']] = by_source.get(r['source'], 0) + 1
    no_kidney = sorted(i for i, r in rows.items() if r['no_kidney'])
    return {**info, 'images': len(rows), 'by_source': by_source, 'no_kidney': no_kidney[:200], 'no_kidney_count': len(no_kidney), 'sample': sorted(rows)[:12]}
