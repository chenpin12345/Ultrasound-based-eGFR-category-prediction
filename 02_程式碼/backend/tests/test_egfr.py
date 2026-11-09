"""M2.5 階段 C：eGFR 2／3／5 類、臨床資料、純臨床基準、勾選式比較組、多類評估、兩兩比較、三區分開。只用合成資料。"""

from __future__ import annotations

import csv
import json
import shutil

import numpy as np
import pytest

from tests.conftest import wait_job
from tests.test_training import TINY, FakeCtx

# 5 個 eGFR 分組各 4 位（≥90、60–89、30–59、15–29、<15）
EGFRS = [95, 100, 92, 120, 75, 65, 80, 88, 45, 31, 55, 59, 20, 16, 25, 29, 10, 5, 14, 12]


@pytest.fixture()
def cohort(imported_client, workspace):
    """20 位病人（每人左右各 1 張，從 8 張合成影像複製）；年齡、性別、糖尿病有幾筆缺值；凍結版本與切分。"""
    from app.core.ids import now_iso
    from app.data import storage
    from app.db.models_research import Image, Patient
    from app.db.session import session_scope

    client = imported_client
    with session_scope('research') as db:
        src = [(i.id, i.batch_id, i.machine, i.template_id, i.width, i.height, i.phash) for i in db.query(Image).order_by(Image.id).all()]
        for i in db.query(Image).all():
            i.status, i.exclude_reason = 'excluded', '測試：改用複製的影像'
    with session_scope('research') as db:
        for p, egfr in enumerate(EGFRS):
            pid = f'P-{p + 1:04d}'
            db.add(Patient(id=pid, egfr=float(egfr), age=None if p == 3 else 40 + p, sex=None if p == 7 else ['F', 'M'][p % 2],
                           has_diabetes=None if p == 11 else bool(p % 3 == 0), has_fatty_liver=False, created_at=now_iso()))
            db.flush()
            for j in range(2):
                sid, batch, machine, template, w, h, phash = src[(2 * p + j) % len(src)]
                new_id = f'IMG-E{p:02d}{j}00000000'
                for kind in ('model', 'calc', 'thumb'):
                    dst = storage.image_path(new_id, kind)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(storage.image_path(sid, kind), dst)
                db.add(Image(id=new_id, batch_id=batch, sha256=f'{p:032d}{j:032d}', phash=phash, patient_id=pid, machine=machine, template_id=template,
                             width=w, height=h, side=['right', 'left'][j], pixel_spacing_mm=0.3, status='usable', created_at=now_iso()))
    version = client.post('/api/dataset-versions', json={'note': 'eGFR 測試'}).json()['id']
    split = client.post('/api/splits', json={'seed': 3, 'folds': 2, 'test_ratio': 0.2}).json()['id']
    return {'client': client, 'version': version, 'split': split}


def _run(cohort, cfg, name='t'):
    """建立訓練並直接在測試程序裡跑（不開子程序）。"""
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope
    from app.ml import engine
    from app.ml.runs import create

    run = create('egfr', name, cohort['version'], cohort['split'], cfg, '測試', start=False)['id']
    if cfg.get('arch') == 'logreg':
        from app.ml.baseline import train_baseline

        summary = train_baseline(run, FakeCtx())
    else:
        summary = engine.train_run(run, 'egfr', cfg, cohort['version'], cohort['split'], FakeCtx())
    with session_scope('research') as db:
        r = db.get(TrainingRun, run)
        r.status, r.summary_json = 'completed', json.dumps(summary)
    return run, summary


def test_egfr_class_boundaries_match_split_groups():
    from app.data import egfr as E
    from app.data.patients import EGFR_GROUPS, egfr_group

    for value, k5, k3, k2 in [(89.9, 1, 0, 0), (90, 0, 0, 0), (59.9, 2, 1, 1), (60, 1, 0, 0), (29.9, 3, 2, 1), (30, 2, 1, 1), (14.9, 4, 2, 1), (15, 3, 2, 1)]:
        assert (E.egfr_class(value, 5), E.egfr_class(value, 3), E.egfr_class(value, 2)) == (k5, k3, k2)
        labels = [g[1] for g in EGFR_GROUPS]
        assert 4 - labels.index(egfr_group(value)) == E.egfr_class(value, 5)  # 和切分用的分組一致
    assert [g[1] for g in EGFR_GROUPS] == ['eGFR <15', 'eGFR 15–29', 'eGFR 30–59', 'eGFR 60–89', 'eGFR ≥90']  # 標籤文字一字不改
    probs = np.array([[0.1, 0.2, 0.3, 0.25, 0.15]])
    assert E.p_lt(probs, 5, 60)[0] == pytest.approx(0.7) and E.p_lt(probs, 5, 30)[0] == pytest.approx(0.4)
    assert E.collapse_probs(probs, 5, 3)[0].tolist() == pytest.approx([0.3, 0.3, 0.4])
    assert E.collapse_labels(np.array([0, 1, 2, 3, 4]), 5, 3).tolist() == [0, 0, 1, 2, 2]


def test_metrics_cumulative_auc_and_paired_bootstrap():
    from app.ml import metrics

    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 60)
    p = np.clip(y * 0.4 + rng.random(60) * 0.6, 0, 1)
    assert metrics.fast_auc(y, p) == pytest.approx(metrics.auc(y, p))
    two = metrics.egfr_metrics(y, np.stack([1 - p, p], 1), 2)
    assert two['auc_lt60'] == pytest.approx(two['auc'])  # 2 類時累積 AUC＝二元 AUC
    rows = [{'a': {'y': int(t), 'p': float(q)}, 'b': {'y': int(t), 'p': float(q)}} for t, q in zip(y, p)]
    fn = lambda rs, side: metrics.fast_auc(np.array([r[side]['y'] for r in rs]), np.array([r[side]['p'] for r in rs]))  # noqa: E731
    same = metrics.paired_bootstrap(rows, fn, n=200)
    assert same['diff'] == 0 and same['ci'] == [0.0, 0.0]
    better = [{'a': {'y': int(t), 'p': float(t)}, 'b': {'y': int(t), 'p': float(q)}} for t, q in zip(y, rng.random(60))]
    res = metrics.paired_bootstrap(better, fn, n=300)
    assert res['diff'] > 0 and res['ci'][0] > 0 and res['p'] < 0.05


def test_ordinal_logit_ranks_separable_data():
    from app.ml.baseline import fit_ordinal_logit, predict_ordinal_logit

    rng = np.random.default_rng(1)
    x = rng.normal(size=(150, 2))
    y = np.digitize(x[:, 0] * 2 + rng.normal(scale=0.3, size=150), [-1, 1])
    model = fit_ordinal_logit(x, y, 3)
    probs = predict_ordinal_logit(model, x)
    assert np.allclose(probs.sum(1), 1) and (np.diff(model['theta']) > 0).all()
    assert (probs.argmax(1) == y).mean() > 0.8


def test_validate_egfr_config():
    from app.core.errors import AppError
    from app.ml.runs import validate_config

    assert validate_config('egfr', {'egfr_classes': 5})['egfr_classes'] == 5
    for bad in ({'egfr_classes': 4}, {'egfr_classes': 2, 'head': 'corn'}, {'egfr_classes': 3, 'head': 'binary'}, {'inputs': ['clinical']},
                {'arch': 'logreg', 'inputs': ['image', 'clinical']}, {'inputs': ['image', 'measures']}, {'inputs': ['image', 'mask_channels']}):
        with pytest.raises(AppError):
            validate_config('egfr', bad)
    with pytest.raises(AppError):
        validate_config('segmentation', {'egfr_classes': 3})


def test_train_three_and_five_classes_with_clinical(cohort):
    run3, s3 = _run(cohort, {**TINY, 'epochs': 1, 'egfr_classes': 3})
    assert s3['egfr_classes'] == 3 and s3['oof']['k'] == 3
    assert 'auc_lt60' in s3['oof'] and 'qwk' in s3['oof'] and len(s3['oof']['confusion']) == 3
    run5, s5 = _run(cohort, {**TINY, 'epochs': 1, 'egfr_classes': 5, 'head': 'ce', 'inputs': ['image', 'clinical']})
    assert s5['oof']['k'] == 5 and s5['temperature'] > 0
    stats = s5['feature_stats']
    assert stats['columns'][:3] == ['age_z', 'female', 'diabetes'] and 'clinical' in stats
    # 補值只用開發集（各折）：缺值的病人得到眾數或平均，並有缺值標記
    from app.ml import data as mldata
    from app.ml.tabular import clinical_features

    samples = mldata.build('egfr', cohort['version'], cohort['split'], egfr_classes=5)
    dev = {s.image_id for s in samples if s.group.startswith('fold-')}
    feats, cs = clinical_features(samples, dev)
    missing_age = next(s.image_id for s in samples if s.patient_id == 'P-0004')
    assert feats[missing_age][0] == 0.0 and feats[missing_age][3] == 1.0
    dev_ages = [s.extra['clinical']['age'] for s in samples if s.image_id in dev and s.extra['clinical']['age'] is not None]
    assert cs['age_mean'] == pytest.approx(float(np.mean(dev_ages)))
    rep = cohort['client'].post(f'/api/training/runs/{run5}/evaluate').json()
    assert rep['k'] == 5 and rep['patient']['collapsed']['3']['k'] == 3 and rep['patient']['auc_lt60_ci'] is not None


def test_comparison_group_reuse_pairwise_and_export(cohort, workspace):
    client = cohort['client']
    base = {'dataset_version_id': cohort['version'], 'split_id': cohort['split'], 'base_config': {**TINY, 'epochs': 1}, 'start': False}
    # 只勾 ③：只建立 CPU 基準；有遮罩的輸入沒有遮罩組時拒絕
    only3 = client.post('/api/egfr/comparisons', json={**base, 'inputs': ['clinical'], 'classes': [2, 5]}).json()
    assert len(only3['members']) == 2
    assert client.post('/api/egfr/comparisons', json={**base, 'inputs': ['image_mask'], 'classes': [2]}).json()['error']['code'] == 'MASK_SET_REQUIRED'
    assert client.post('/api/egfr/comparisons', json={**base, 'inputs': [], 'classes': [2]}).status_code == 422
    from app.ml.baseline import train_baseline

    for m in only3['members']:
        summary = train_baseline(m['run_id'], FakeCtx())
        from app.db.models_research import TrainingRun
        from app.db.session import session_scope

        with session_scope('research') as db:
            r = db.get(TrainingRun, m['run_id'])
            r.status, r.summary_json = 'completed', json.dumps(summary)
    # ②③ 都勾：③ 沿用已完成的同設定訓練，② 新建
    both = client.post('/api/egfr/comparisons', json={**base, 'inputs': ['image_clinical', 'clinical'], 'classes': [2]}).json()
    reused = {m['code']: m['reused'] for m in both['members']}
    assert reused == {'image_clinical': False, 'clinical': True} and both['reused'] == 1
    no_reuse = client.post('/api/egfr/comparisons', json={**base, 'inputs': ['clinical'], 'classes': [2], 'reuse': False}).json()
    assert not no_reuse['members'][0]['reused']
    # M2.5 以前的訓練（設定沒有 inputs、egfr_classes）視為「2 類、只用影像」，① 2 類可以沿用
    old, _ = _run(cohort, {**{k: v for k, v in TINY.items() if k != 'patience'}, 'epochs': 1}, name='舊的二元訓練')  # 比較組不帶 patience，用預設值
    image = client.post('/api/egfr/comparisons', json={**base, 'inputs': ['image'], 'classes': [2]}).json()
    assert image['members'][0]['run_id'] == old and image['members'][0]['reused']
    detail = client.get(f"/api/egfr/comparisons/{only3['id']}").json()
    cells = {(c['code'], c['k']): c for c in detail['cells']}
    assert cells[('clinical', 5)]['metrics']['auc_lt60'] is not None and cells[('clinical', 5)]['metrics']['n_patients'] > 0
    a, b = cells[('clinical', 2)]['run_id'], cells[('clinical', 5)]['run_id']
    pw = client.get(f'/api/egfr/pairwise?a={a}&b={b}&metric=auc_lt60').json()
    assert pw['patients'] > 0 and 'ci' in pw
    assert client.get(f'/api/egfr/pairwise?a={a}&b={b}&metric=auc_lt30').json()['error']['code'] == 'METRIC_UNAVAILABLE'
    out = client.post(f"/api/egfr/comparisons/{only3['id']}/export").json()
    folder = workspace / out['folder']
    table = list(csv.reader((folder / '比較表.csv').open(encoding='utf-8-sig')))
    assert table[0][0] == '輸入方式' and len(table) == 3
    per = next(folder.glob('每位病人機率_clinical_5類_*.csv'))
    text = per.read_text(encoding='utf-8-sig')
    assert 'P(eGFR<60)' in text and 'P-0001' in text and '95.0' not in text and ',95,' not in text  # 不含 eGFR 數值
    csv_resp = client.get(f'/api/training/runs/{b}/oof.csv')
    assert csv_resp.status_code == 200 and 'P(eGFR<30)' in csv_resp.content.decode('utf-8-sig')


def test_zones_lists_require_task_and_cross_task_compare(cohort):
    client = cohort['client']
    assert client.get('/api/training/runs').status_code == 422
    assert client.get('/api/training/runs?task=egfr').status_code == 200
    assert client.get('/api/models').status_code == 422
    assert client.get('/api/experiments').status_code == 422
    run, _ = _run(cohort, {'arch': 'logreg', 'inputs': ['clinical'], 'egfr_classes': 2})
    from app.core.errors import AppError
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope
    from app.ml import evaluation

    with session_scope('research') as db:
        other = TrainingRun(id='RUN-20991231-001', task='grade', name='g', split_id=cohort['split'], dataset_version_id=cohort['version'],
                            config_json='{}', status='completed', summary_json=json.dumps({'folds': []}), relpath='04_模型/x', created_at='2099')
        db.add(other)
    with pytest.raises(AppError) as err:
        evaluation.compare(run, 'RUN-20991231-001')
    assert err.value.code == 'TASK_MISMATCH'
    assert client.post('/api/models', json={'run_id': run, 'name': 'baseline-x'}).json()['error']['code'] == 'BASELINE_NOT_REGISTRABLE'
    jobs = client.get('/api/jobs?zone=egfr').json()['jobs']
    assert all(j['zone'] == 'egfr' for j in jobs)


def test_baseline_job_via_api(cohort):
    client = cohort['client']
    run = client.post('/api/training/runs', json={'task': 'egfr', 'dataset_version_id': cohort['version'], 'split_id': cohort['split'],
                                                   'config': {'arch': 'logreg', 'inputs': ['clinical'], 'egfr_classes': 3}, 'start': True}).json()
    job = client.get(f"/api/jobs/{run['job_id']}").json()
    assert job['kind'] == 'train_baseline'
    wait_job(run['job_id'])
    detail = client.get(f"/api/training/runs/{run['id']}").json()
    assert detail['status'] == 'completed' and detail['summary']['oof']['k'] == 3
    assert client.get(f"/api/jobs/{run['job_id']}").json()['zone'] == 'egfr'
