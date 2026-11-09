"""M2.5 階段 D：交叉預測遮罩組、遮罩組特徵、學習曲線。只用合成資料。"""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.conftest import wait_job
from tests.test_training import TINY, FakeCtx, research  # noqa: F401  共用 research 資料（6 位病人、已確認的遮罩）


def _seg_run(research, folds=None):  # noqa: F811
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope
    from app.ml import engine
    from app.ml.runs import create

    cfg = {**TINY, 'epochs': 1, 'arch': 'unet', **({'folds': folds} if folds else {})}
    run = create('segmentation', 's', research['version'], research['split'], cfg, '測試', start=False)['id']
    summary = engine.train_run(run, 'segmentation', cfg, research['version'], research['split'], FakeCtx())
    with session_scope('research') as db:
        r = db.get(TrainingRun, run)
        r.status, r.summary_json, r.finished_at = 'completed', json.dumps(summary), '2026-10-29T10:00:00'
    return run


def test_mask_set_cross_fitted_for_all_images(research):  # noqa: F811
    from app.data.versions import load_manifest
    from app.db.models_research import SplitEntry
    from app.db.session import session_scope
    from app.ml import masksets

    client = research['client']
    run = _seg_run(research)
    created = client.post('/api/mask-sets', json={'seg_run_id': run}).json()
    wait_job(created['job_id'])
    job = client.get(f"/api/jobs/{created['job_id']}").json()
    assert job['status'] == 'completed', job
    info = client.get(f"/api/mask-sets/{created['id']}").json()
    manifest_images = load_manifest(research['version'])['images']
    assert info['images'] == len(manifest_images) and info['status'] == 'completed'
    with session_scope('research') as db:
        groups = dict(db.query(SplitEntry.patient_id, SplitEntry.group).filter(SplitEntry.split_id == research['split']).all())
    rows = json.loads((masksets.folder(created['id']) / 'manifest.json').read_text(encoding='utf-8'))['images']
    for img in manifest_images:
        row = rows[img['id']]
        group = groups.get(img['patient_id'])
        assert row['source'] == (group if group and group.startswith('fold-') else 'ensemble')  # 每位病人只用沒看過他的折
        assert masksets.mask_path(created['id'], img['id']).exists()
    assert 'test' in set(groups.values()) and 'ensemble' in info['by_source']
    # 自動擷取特徵：全部影像都有（不再只有有遮罩的驗證影像）
    from app.db.models_research import FeatureSet

    with session_scope('research') as db:
        extract_job = db.get(FeatureSet, job['result']['feature_set_id']).job_id
    wait_job(extract_job)
    feature_set = masksets.feature_set_for(created['id'])
    assert feature_set == job['result']['feature_set_id']
    fs = client.get(f'/api/features/{feature_set}').json()
    assert fs['total'] == len(manifest_images)
    png = client.get(f"/api/mask-sets/{created['id']}/overlay/{manifest_images[0]['id']}")
    assert png.status_code == 200 and png.content[:4] == b'\x89PNG'
    # 特徵集匯出到 08_匯出（Excel 可開；不含 eGFR 數值）；清單標出來源遮罩組
    listed = next(f for f in client.get('/api/features').json()['feature_sets'] if f['id'] == feature_set)
    assert listed['spec']['mask_set_id'] == created['id'] and listed['relpath']
    from app.core.config import get_settings

    out = get_settings().root / client.post(f'/api/features/{feature_set}/export').json()['folder']
    assert {'特徵.csv', 'Spearman.csv', '腎長BlandAltman.csv', '說明.txt'} <= {p.name for p in out.iterdir()}
    header = (out / '特徵.csv').read_text(encoding='utf-8-sig').splitlines()[0]
    assert 'image_id' in header and 'egfr' not in header.lower()


def test_mask_set_rejects_incomplete_folds_and_nnunet(research):  # noqa: F811
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope

    client = research['client']
    partial = _seg_run(research, folds=['fold-1'])
    r = client.post('/api/mask-sets', json={'seg_run_id': partial})
    assert r.status_code == 409 and r.json()['error']['code'] == 'MASKSET_INCOMPLETE_FOLDS'
    with session_scope('research') as db:
        db.get(TrainingRun, partial).config_json = json.dumps({'framework': 'nnunetv2'})
    assert client.post('/api/mask-sets', json={'seg_run_id': partial}).json()['error']['code'] == 'RUN_NOT_SUPPORTED'


def test_postprocess_keeps_largest_kidney():
    from app.ml.masksets import postprocess

    label = np.zeros((40, 40), np.uint8)
    label[5:20, 5:20] = 1
    label[10:14, 10:14] = 2
    label[30:33, 30:33] = 1  # 小雜點
    label[25:28, 2:5] = 3
    out = postprocess(label)
    assert out[31, 31] == 0 and out[12, 12] == 2 and out[6, 6] == 1 and out[26, 3] == 3


def test_learning_curve_and_plateau(research):  # noqa: F811
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope

    client = research['client']
    client.put('/api/settings', json={'primary_split_id': research['split']})
    with session_scope('research') as db:
        for n, (masks, dice) in enumerate([(100, 0.80), (200, 0.85), (300, 0.855), (400, 0.857)]):
            db.add(TrainingRun(id=f'RUN-20261101-{n + 1:03d}', task='segmentation', name=f'第 {n + 1} 輪', split_id=research['split'], dataset_version_id=research['version'],
                               config_json='{}', status='completed', summary_json=json.dumps({'oof': {'dice': dice}, 'data': {'samples': masks}}),
                               relpath=f'04_模型/x{n}', created_at='2026-11-01', finished_at=f'2026-11-0{n + 1}'))
    curve = client.get('/api/training/learning-curve').json()
    assert [p['masks'] for p in curve['points']] == [100, 200, 300, 400]
    assert curve['points'][1]['gain'] == pytest.approx(0.05) and curve['plateau'] is True
