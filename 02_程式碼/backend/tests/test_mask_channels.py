"""M2.5 階段 E：④ 影像＋遮罩通道（160 mm 裁切、同步增強、4 通道模型）、eGFR 比較組一起評估固定測試集。只用合成資料。"""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from tests.conftest import wait_job
from tests.test_egfr import _run, cohort  # noqa: F401  共用 20 位合成病人
from tests.test_training import TINY, FakeCtx


def _label(h=200, w=240, cx=120, cy=100, sinus=True):
    label = np.zeros((h, w), np.uint8)
    label[10:40, 10:60] = 3
    cv2.ellipse(label, (cx, cy), (40, 25), 0, 0, 360, 1, -1)
    if sinus:
        cv2.ellipse(label, (cx, cy), (15, 8), 0, 0, 360, 2, -1)
    return label


def _mask_set(cohort):  # noqa: F811
    """直接寫一個合成遮罩組（不經分割訓練）：每張影像中央一顆腎。"""
    from app.core.ids import now_iso
    from app.db.models_research import Image, MaskSet, TrainingRun
    from app.db.session import session_scope
    from app.ml import data as mldata
    from app.ml import masksets

    ms_id, seg_run = 'MS-20261029-001', 'RUN-20261029-901'
    with session_scope('research') as db:
        db.add(TrainingRun(id=seg_run, task='segmentation', name='合成分割', split_id=cohort['split'], dataset_version_id=cohort['version'],
                           config_json='{}', status='completed', summary_json='{}', relpath='04_模型/01_訓練紀錄/分割/x', created_at=now_iso()))
    with session_scope('research') as db:
        images = [i.id for i in db.query(Image).filter(Image.status == 'usable').all()]
        db.add(MaskSet(id=ms_id, seg_run_id=seg_run, split_id=cohort['split'], dataset_version_id=cohort['version'], spec_json='{}', rows=len(images),
                       status='completed', relpath=f'03_資料/04_模型產出/預測遮罩組/{ms_id}', created_at=now_iso()))
    for image_id in images:
        h, w = mldata.load_image(image_id).shape
        path = masksets.mask_path(ms_id, image_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imencode('.png', _label(h, w, w // 2, h // 2))[1].tofile(str(path))
    return ms_id, seg_run


def _train(cohort, run_id):  # noqa: F811
    """比較組的成員直接在測試程序裡訓練。"""
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope
    from app.ml import engine
    from app.ml.baseline import train_baseline

    with session_scope('research') as db:
        cfg = json.loads(db.get(TrainingRun, run_id).config_json)
    summary = train_baseline(run_id, FakeCtx()) if cfg.get('arch') == 'logreg' else engine.train_run(run_id, 'egfr', cfg, cohort['version'], cohort['split'], FakeCtx())
    with session_scope('research') as db:
        r = db.get(TrainingRun, run_id)
        r.status, r.summary_json = 'completed', json.dumps(summary)


def test_roi_crop_fixed_mm_and_fallbacks():
    from app.ml import roi

    label = _label()
    box, how = roi.crop_box(label, 0.5)  # 160 mm ÷ 0.5 mm/px = 320 px，以腎臟為中心
    assert how == 'fixed_mm' and box[2] - box[0] == 320 and box[3] - box[1] == 320
    assert ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2) == pytest.approx((120, 100), abs=1)
    box, how = roi.crop_box(label, None)  # 沒有像素間距：腎臟外接框加 10% 邊距
    assert how == 'bbox' and box[2] - box[0] == pytest.approx(96, abs=2)
    assert roi.crop_box(np.zeros((50, 50), np.uint8), 0.5)[1] == 'whole'  # 找不到腎臟：整張影像
    img, ch, info = roi.prepare(np.full(label.shape, 100, np.uint8), label, 0.5, 64)
    assert img.shape == (64, 64) and ch.shape == (3, 64, 64) and set(np.unique(ch)) <= {0, 1}
    assert img[0, 0] == 0 and info['roi'] == 'fixed_mm'  # 超出影像的部分補 0
    # 固定 mm：大腎在裁切後仍比小腎大（外接框裁切會把兩者放大成一樣）
    big = _label(sinus=False)
    small = np.zeros_like(big)
    cv2.ellipse(small, (120, 100), (25, 15), 0, 0, 360, 1, -1)
    gray = np.zeros(big.shape, np.uint8)
    assert roi.prepare(gray, big, 0.5, 64)[1][0].sum() > 2 * roi.prepare(gray, small, 0.5, 64)[1][0].sum()


def test_mask_channels_follow_the_same_augmentation():
    from app.ml import augment, roi

    label = _label(sinus=False)
    gray = np.where(label == 1, 200, 0).astype(np.uint8)  # 影像的亮區＝腎實質
    img, ch, _ = roi.prepare(gray, label, 0.5, 128)
    for seed in range(6):
        a_img, a_ch = augment.augment_classification(img, augment.sample_rng(seed, 1, 0), ch)
        assert set(np.unique(a_ch)) <= {0, 1}  # 最近鄰插值，仍是 0／1
        bright, mask = a_img > 100, a_ch[0] == 1
        assert (bright & mask).sum() / (bright | mask).sum() > 0.75  # 影像和遮罩一起移動
    plain = augment.augment_classification(img, augment.sample_rng(0, 1, 0))
    assert np.array_equal(plain, augment.augment_classification(img, augment.sample_rng(0, 1, 0), ch)[0])  # 亂數用法和只用影像時相同


def test_mask_channel_model_starts_identical_to_image_model():
    import torch

    from app.ml.models import build_classifier

    torch.manual_seed(0)
    one = build_classifier('resnet18', 'random', 'corn', 3, 6, 1).eval()
    torch.manual_seed(0)
    four = build_classifier('resnet18', 'random', 'corn', 3, 6, 4).eval()
    x, feats = torch.randn(2, 1, 64, 64), torch.randn(2, 6)
    masks = torch.randint(0, 2, (2, 3, 64, 64)).float()
    with torch.no_grad():
        assert torch.allclose(one(x, feats), four(torch.cat([x, masks], 1), feats), atol=1e-5)  # 遮罩通道從 0 開始，輸出層初始值也相同


def test_four_channel_run_register_predict_and_contract(cohort):  # noqa: F811
    from app.core.errors import AppError
    from app.ml import data as mldata
    from app.ml import registry
    from app.ml.masksets import mask_path

    client = cohort['client']
    ms, seg_run = _mask_set(cohort)
    run, summary = _run(cohort, {**TINY, 'epochs': 1, 'inputs': ['image', 'mask_channels'], 'mask_set_id': ms})
    assert summary['oof']['n'] > 0
    model = client.post('/api/models', json={'run_id': run, 'name': 'mask-channels', 'version': '1.0.0'}).json()['id']
    spec = client.get(f'/api/models/{model}').json()['manifest']['input']
    assert spec['mode'] == 'mask_channels' and spec['channels'] == 4 and spec['mask_source'] == {'mask_set_id': ms, 'seg_run_id': seg_run, 'postprocess': 'largest_component'}
    ready = client.get(f'/api/models/{model}/test-readiness').json()
    assert ready['missing_masks'] == 0 and ready['missing_features'] == 0 and ready['ready']
    loaded = registry.load(model)
    image_id = mldata.build('egfr', cohort['version'], cohort['split'])[0].image_id
    gray = mldata.load_image(image_id)
    label = cv2.imdecode(np.fromfile(str(mask_path(ms, image_id)), np.uint8), cv2.IMREAD_GRAYSCALE)
    probs = registry.predict_classification(loaded, gray, None, label, 0.3)
    assert len(probs) == 2 and sum(probs) == pytest.approx(1, abs=1e-3)
    with pytest.raises(AppError) as err:
        registry.predict_classification(loaded, gray)  # 沒有遮罩
    assert err.value.code == 'CONTRACT_MISMATCH'
    job = client.post('/api/pipelines', json={'classifier_ids': [model], 'image_ids': [image_id]}).json()['job_id']
    wait_job(job)
    info = client.get(f'/api/jobs/{job}').json()
    assert info['status'] == 'failed' and 'CONTRACT_MISMATCH' in json.dumps(info)  # 流程沒選分割模型時拒絕
    # 遮罩組必須和訓練同一個切分
    from app.ml.runs import create

    other = client.post('/api/splits', json={'seed': 9, 'folds': 2, 'test_ratio': 0.2}).json()['id']
    with pytest.raises(AppError) as err:
        create('egfr', 'x', cohort['version'], other, {**TINY, 'inputs': ['image', 'mask_channels'], 'mask_set_id': ms}, '測試', start=False)
    assert err.value.code == 'MASK_SET_SPLIT'


def test_egfr_group_test_evaluation_locks_only_egfr(cohort, workspace):  # noqa: F811
    from app.db.models_research import Split, SplitEntry
    from app.db.session import session_scope
    from app.ml import evaluation

    client = cohort['client']
    ms, _ = _mask_set(cohort)
    group = client.post('/api/egfr/comparisons', json={'dataset_version_id': cohort['version'], 'split_id': cohort['split'], 'base_config': {**TINY, 'epochs': 1},
                                                       'inputs': ['image_mask', 'clinical'], 'classes': [2], 'mask_set_id': ms, 'start': False}).json()
    gid = group['id']  # ④ 只用遮罩，遮罩組還沒有特徵集也能建立
    measures = client.post('/api/egfr/comparisons', json={'dataset_version_id': cohort['version'], 'split_id': cohort['split'], 'inputs': ['image_measures'],
                                                          'classes': [2], 'mask_set_id': ms, 'start': False}).json()
    assert measures['error']['code'] == 'FEATURES_REQUIRED'  # ⑤⑥ 需要量測數值
    ready =client.get(f'/api/egfr/test-readiness?experiment_ids={gid}').json()
    assert not ready['ready'] and len(ready['unfinished']) == 2 and ready['split_id'] == cohort['split']
    body = {'experiment_ids': [gid], 'confirm': cohort['split']}
    assert client.post('/api/egfr/test', json=body).json()['error']['code'] == 'RUNS_UNFINISHED'
    for m in group['members']:
        _train(cohort, m['run_id'])
    # 測試影像缺少遮罩組的遮罩時先擋下（不要鎖定後才失敗）
    from app.db.models_research import Image
    from app.ml.masksets import mask_path

    with session_scope('research') as db:
        patients = [p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == cohort['split'], SplitEntry.group == 'test').all()]
        test_image = db.query(Image).filter(Image.patient_id.in_(patients), Image.status == 'usable').first().id
    path = mask_path(ms, test_image)
    hidden = path.with_suffix('.bak')
    path.rename(hidden)
    gap = client.get(f'/api/egfr/test-readiness?experiment_ids={gid}').json()
    assert not gap['ready'] and list(gap['missing_inputs'].values()) == [{'missing_features': 0, 'missing_masks': 1}]
    assert client.post('/api/egfr/test', json=body).json()['error']['code'] == 'TEST_INPUTS_MISSING'
    hidden.rename(path)
    assert client.get(f'/api/egfr/test-readiness?experiment_ids={gid}').json()['ready']
    assert client.post('/api/egfr/test', json={**body, 'confirm': 'split-x'}).json()['error']['code'] == 'CONFIRM_MISMATCH'
    started = client.post('/api/egfr/test', json=body)
    assert started.status_code == 202
    wait_job(started.json()['job_id'])
    job = client.get(f"/api/jobs/{started.json()['job_id']}").json()
    assert job['status'] == 'completed', job
    assert job['zone'] == 'egfr' and len(job['result']['evaluations']) == 2
    with session_scope('research') as db:
        test_patients = {p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == cohort['split'], SplitEntry.group == 'test').all()}
        split = db.get(Split, cohort['split'])
        assert evaluation.is_locked(split, 'egfr') and not evaluation.is_locked(split, 'segmentation')  # 只鎖 eGFR
    cells = {c['run_id']: c for c in client.get(f'/api/egfr/comparisons/{gid}').json()['cells']}
    for ev in job['result']['evaluations']:
        rows = json.loads((evaluation.eval_dir(ev['evaluation_id']) / 'predictions.json').read_text(encoding='utf-8'))
        assert rows and {r['patient_id'] for r in rows} <= test_patients  # 只用測試病人
        # 重新整理後仍看得到：比較格與訓練詳細都帶著測試集結果
        assert cells[ev['run_id']]['test']['evaluation_id'] == ev['evaluation_id']
        assert client.get(f"/api/training/runs/{ev['run_id']}").json()['latest_test']['id'] == ev['evaluation_id']
    again = client.get(f'/api/egfr/test-readiness?experiment_ids={gid}').json()
    assert again['locked'] and not again['ready']
    assert client.post('/api/egfr/test', json=body).json()['error']['code'] == 'TEST_LOCKED'
