"""M2 訓練：損失函數、指標、回音特徵、訓練引擎（停止恢復一致）、子程序訓練、模型庫合約、評估、實驗、nnU-Net 匯出。

全部在 CPU 上用極小的設定（64 px、1–2 epoch），只驗證流程與數值，不代表真正的模型表現。
"""

from __future__ import annotations

import json
import shutil

import cv2
import numpy as np
import pytest
import torch

from tests import synthetic
from tests.conftest import wait_job

TINY = {'img_size': 64, 'epochs': 2, 'batch_size': 2, 'device': 'cpu', 'amp': False, 'patience': 5}


class FakeCtx:
    """在測試程序裡直接呼叫訓練引擎用的工作狀態；stop_after_epochs：完成幾個 epoch 後要求停止。"""

    def __init__(self, stop_after_epochs: int | None = None):
        self.stop_after, self.events = stop_after_epochs, []

    def should_stop(self):
        done = sum(1 for t, _ in self.events if t == 'epoch')
        return self.stop_after is not None and done >= self.stop_after

    def check_stop(self):
        from app.jobs.manager import StopRequested

        if self.should_stop():
            raise StopRequested()

    def progress(self, value, message=''):
        pass

    def event(self, type_, data=None):
        self.events.append((type_, data))


# ---------- 純函式 ----------
def test_partial_ce_equals_ce_when_fully_labeled_and_merges_groups():
    import torch.nn.functional as F

    from app.ml import losses

    torch.manual_seed(0)
    logits = torch.randn(2, 5, 4, 4)
    target = torch.randint(0, 5, (2, 4, 4))
    full = losses.merge_matrix([[[0], [1], [2], [3], [4]]] * 2, 5, 'cpu')
    assert torch.allclose(losses.partial_ce(logits, target, full), F.cross_entropy(logits, target), atol=1e-5)
    # 只有整顆腎、沒有肝脾：背景與肝脾合併、腎實質與腎竇合併，loss 一定不大於完整標註
    kidney_only = losses.merge_matrix([[[0, 3, 4], [1, 2]]] * 2, 5, 'cpu')
    t = target.clone()
    t[t == 2] = 1
    t[(t == 3) | (t == 4)] = 0
    assert losses.partial_ce(logits, t, kidney_only) <= F.cross_entropy(logits, t) + 1e-6


@pytest.mark.parametrize('head', ['binary', 'ce', 'coral', 'corn', 'sord'])
def test_heads_give_valid_probabilities(head):
    from app.ml import losses
    from app.ml.models import build_classifier

    k = 2 if head == 'binary' else 4
    model = build_classifier('resnet18', 'random', head, k)
    x = torch.randn(3, 1, 64, 64)
    logits = model(x)
    probs = losses.class_probs(head, logits)
    assert probs.shape == (3, k) and torch.all(probs >= 0) and torch.allclose(probs.sum(1), torch.ones(3), atol=1e-5)
    y = torch.tensor([0, 1, 1]) if k == 2 else torch.tensor([0, 2, 3])
    assert torch.isfinite(losses.classification_loss(head, logits, y, None))


def test_coral_shares_weights():
    from app.ml.models import OrdinalCoral

    head = OrdinalCoral(8, 4)
    assert head.fc.weight.shape == (1, 8) and head.biases.shape == (3,)  # 所有門檻共用一組權重


def test_metrics_helpers():
    from app.ml import metrics

    assert metrics.ece(np.array([0, 1, 1, 0]), np.array([0.0, 1.0, 1.0, 0.0])) == pytest.approx(0.0)
    res = metrics.corrected_ttest([0.05, 0.04, 0.06, 0.05, 0.05], n_train=400, n_test=100)
    assert res['p'] is not None and res['p'] < 0.05
    rows = [{'patient_id': f'P{i // 2}', 'v': float(i % 2)} for i in range(40)]
    lo, hi = metrics.bootstrap_ci(rows, lambda rs: float(np.mean([r['v'] for r in rs])), n=200)
    assert lo <= 0.5 <= hi


def test_feature_measure_cortex_liver_ratio():
    from app.annotation.service import STRUCTURES
    from app.features.service import measure

    h, w = 400, 500
    label = np.zeros((h, w), np.uint8)
    gray = np.full((h, w), 30, np.uint8)
    cv2.ellipse(label, (300, 200), (120, 60), 0, 0, 360, STRUCTURES['parenchyma'], -1)
    cv2.ellipse(label, (300, 200), (60, 20), 0, 0, 360, STRUCTURES['sinus'], -1)
    label[100:300, 20:150] = STRUCTURES['liver']
    gray[label == STRUCTURES['parenchyma']] = 60
    gray[label == STRUCTURES['sinus']] = 150
    gray[label == STRUCTURES['liver']] = 50
    valid = np.ones((h, w), bool)
    valid[195:205, 180:420] = False  # caliper 修補過的像素
    gray[195:205, 180:420] = 255
    out = measure(label, gray, valid, 'right', 0.2)
    assert out['ref_organ'] == 'liver' and out['reliable'], out['reasons']
    assert out['ratio_mean'] == pytest.approx(1.2, abs=1e-3)
    assert out['p_index'] == pytest.approx(0.1, abs=1e-3)
    assert out['length_mm'] == pytest.approx(48, abs=1.5)


# ---------- 研究資料 ----------
@pytest.fixture()
def research(imported_client, imported_template, workspace):
    """8 張假影像複製成 6 位病人（eGFR 交替 30／80、各一張左右腎），遮罩用已知答案，兩位醫師分級，再凍結版本與切分。"""
    from app.annotation import drafts
    from app.annotation.service import STRUCTURES
    from app.core.ids import now_iso
    from app.data import storage
    from app.db.models_research import Image, Patient, SourceMap
    from app.db.session import session_scope

    client = imported_client
    _, names = imported_template
    truth = dict(names)
    with session_scope('research') as db:
        rows = db.query(Image, SourceMap.original_relpath).join(SourceMap, SourceMap.image_id == Image.id).order_by(Image.id).all()
        sources = [(i.id, i.batch_id, i.machine, i.template_id, i.width, i.height, i.phash, truth[rel.rsplit('/', 1)[-1]].kidney_center) for i, rel in rows]
        for i, _ in rows:
            i.status = 'excluded'
            i.exclude_reason = '測試：改用複製的影像'
    created = []
    with session_scope('research') as db:
        for p in range(6):
            pid = f'P-{p + 1:04d}'
            db.add(Patient(id=pid, egfr=[30.0, 80.0][p % 2], age=60 + p, sex='F', has_fatty_liver=False, created_at=now_iso()))
            db.flush()
            for j in range(2):
                src_id, batch, machine, template, w, h, phash, center = sources[(2 * p + j) % len(sources)]
                new_id = f'IMG-T{p}{j}000000000'
                for kind in ('model', 'calc', 'thumb'):
                    dst = storage.image_path(new_id, kind)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(storage.image_path(src_id, kind), dst)
                db.add(Image(id=new_id, batch_id=batch, sha256=f'{p:032d}{j:032d}', phash=phash, patient_id=pid, machine=machine, template_id=template, width=w, height=h,
                             side=['right', 'left'][j], pixel_spacing_mm=0.3, status='usable', created_at=now_iso()))
                created.append((new_id, w, h, center, j))
    for new_id, w, h, center, j in created:
        label = np.zeros((h, w), np.uint8)
        label[synthetic.kidney_mask(w, h, center)] = STRUCTURES['parenchyma']
        label[synthetic.kidney_mask(w, h, center, sinus=True)] = STRUCTURES['sinus']
        organ = STRUCTURES['liver'] if j == 0 else STRUCTURES['spleen']
        band = synthetic.kidney_mask(w, h, (center[0], max(5, center[1] - int(h * 0.18))))
        label[band & (label == 0)] = organ
        drafts.save_draft(new_id, label, 'medsam', {'labeled': ['parenchyma', 'sinus', 'liver', 'spleen'], 'review': 'ok'})
    from app.db.models_research import MaskAnnotation

    with session_scope('research') as db:  # 視為醫師確認過（分割訓練預設只用確認過的遮罩）
        for m in db.query(MaskAnnotation).all():
            m.status, m.verified_by, m.verified_at = 'reviewed', '林醫師', now_iso()
    for p in range(6):
        for side in ('right', 'left'):
            for rater in ('林醫師', '周醫師'):
                assert client.put('/api/annotation/grades', json={'patient_id': f'P-{p + 1:04d}', 'side': side, 'grade': (p + (side == 'left')) % 4, 'rater': rater}).status_code == 200
    version = client.post('/api/dataset-versions', json={'note': '訓練測試'}).json()['id']
    split = client.post('/api/splits', json={'seed': 1, 'folds': 2, 'test_ratio': 0.2}).json()['id']
    return {'client': client, 'version': version, 'split': split, 'images': [c[0] for c in created]}


def _same_state(a, b):
    return all(torch.equal(a[k], b[k]) for k in a)


def test_engine_resume_matches_uninterrupted(research):
    """停止後恢復的結果與不中斷相同（舊程式恢復時沒有還原亂數與 patience）。"""
    from app.ml import engine

    cfg = {**TINY, 'arch': 'unet', 'folds': ['fold-1'], 'epochs': 3}
    engine.train_run('RUN-A', 'segmentation', cfg, research['version'], research['split'], FakeCtx())
    # 第二次：第 1 個 epoch 完成後停止，再恢復
    with pytest.raises(Exception) as stopped:
        engine.train_run('RUN-B', 'segmentation', cfg, research['version'], research['split'], FakeCtx(stop_after_epochs=1))
    assert type(stopped.value).__name__ == 'StopRequested'
    assert (engine.run_dir('RUN-B') / 'fold-1' / 'last.pth').exists() and not (engine.run_dir('RUN-B') / 'fold-1' / 'done.json').exists()
    summary = engine.train_run('RUN-B', 'segmentation', cfg, research['version'], research['split'], FakeCtx())
    a = torch.load(engine.run_dir('RUN-A') / 'fold-1' / 'last.pth', weights_only=False)
    b = torch.load(engine.run_dir('RUN-B') / 'fold-1' / 'last.pth', weights_only=False)
    assert _same_state(a['model'], b['model'])
    hist = lambda run: [line.rsplit(',', 1)[0] for line in (engine.run_dir(run) / 'fold-1' / 'history.csv').read_text().splitlines()[1:]]  # noqa: E731  去掉耗時欄
    assert hist('RUN-A') == hist('RUN-B')
    assert summary['folds'][0]['best_epoch'] is not None and 'dice' in summary['oof']
    # out-of-fold 預測遮罩存成原尺寸，給交叉擬合特徵使用
    assert any(engine.seg_output_dir('RUN-B').rglob('*.png'))


def test_engine_grade_corn_and_missing_class(research):
    from app.core.errors import AppError
    from app.ml import data as mldata
    from app.ml import engine

    summary = engine.train_run('RUN-G', 'grade', {**TINY, 'epochs': 1, 'head': 'corn'}, research['version'], research['split'], FakeCtx())
    assert summary['temperature'] > 0 and 'qwk' in summary['oof']
    samples = [s for s in mldata.build('egfr', research['version'], research['split']) if s.target == 0]
    with pytest.raises(AppError) as err:
        mldata.check_classes('egfr', samples)  # 少了一個類別：停下來說明，不靜默訓練
    assert err.value.code == 'CLASS_MISSING'


def test_full_flow_subprocess_registry_pipeline_and_test_lock(research, monkeypatch):
    client = research['client']
    base = {'task': 'egfr', 'dataset_version_id': research['version'], 'split_id': research['split']}
    run = client.post('/api/training/runs', json={**base, 'name': 'eGFR 測試', 'config': {**TINY, 'epochs': 1, 'arch': 'resnet18'}}).json()
    wait_job(run['job_id'])
    detail = client.get(f'/api/training/runs/{run["id"]}').json()
    assert detail['status'] == 'completed', client.get(f'/api/jobs/{run["job_id"]}').json()
    assert detail['history'] and detail['summary']['oof']['n'] > 0

    oof = client.post(f'/api/training/runs/{run["id"]}/evaluate').json()
    assert oof['target'] == 'oof' and 'patient' in oof
    # 重新整理頁面後仍看得到最近一次評估
    assert client.get(f'/api/training/runs/{run["id"]}').json()['latest_evaluation']['id'] == oof['id']

    seg = client.post('/api/training/runs', json={**base, 'task': 'segmentation', 'config': {**TINY, 'epochs': 1, 'arch': 'unet'}}).json()
    wait_job(seg['job_id'])
    assert client.get(f'/api/training/runs/{seg["id"]}').json()['status'] == 'completed'

    assert client.post('/api/models', json={'run_id': run['id'], 'name': 'Bad Name'}).status_code == 422
    model = client.post('/api/models', json={'run_id': run['id'], 'name': 'egfr-test', 'version': '1.0.0'}).json()['id']
    seg_model = client.post('/api/models', json={'run_id': seg['id'], 'name': 'seg-test', 'version': '1.0.0'}).json()['id']
    assert client.post('/api/models', json={'run_id': run['id'], 'name': 'egfr-test', 'version': '1.0.0'}).status_code == 409
    card = client.get(f'/api/models/{model}').json()
    assert card['manifest']['contract_version'] == 3 and '研究用途' in card['model_card']

    job = client.post('/api/pipelines', json={'seg_model_id': seg_model, 'classifier_ids': [model], 'image_ids': research['images'][:2]}).json()['job_id']
    wait_job(job)
    assert client.get(f'/api/jobs/{job}').json()['status'] == 'completed', client.get(f'/api/jobs/{job}').json()
    results = client.get(f'/api/pipelines/{job}').json()
    assert len(results['images']) == 2 and model in results['models']

    # 臨床上線：要輸入模型名稱並從醫師名單選擇
    assert client.post(f'/api/models/{model}/stage', json={'stage': 'clinical', 'confirm_name': 'x', 'approver': '林醫師'}).status_code == 422
    client.post('/api/people', json={'name': '林醫師', 'kind': 'physician'})
    assert client.post(f'/api/models/{model}/stage', json={'stage': 'clinical', 'confirm_name': model, 'approver': '林醫師'}).json()['stage'] == 'clinical'

    # 固定測試集：只能一次
    ready = client.get(f'/api/models/{model}/test-readiness').json()
    assert ready['ready'] and ready['patients'] >= 1
    assert client.post(f'/api/models/{model}/test', json={'confirm': 'wrong'}).status_code == 422
    job = client.post(f'/api/models/{model}/test', json={'confirm': model}).json()['job_id']
    wait_job(job)
    assert client.get(f'/api/jobs/{job}').json()['status'] == 'completed', client.get(f'/api/jobs/{job}').json()
    assert client.get(f'/api/models/{model}/test-readiness').json()['locked']
    again = client.post(f'/api/models/{model}/test', json={'confirm': model})
    assert again.status_code == 409 and again.json()['error']['code'] == 'TEST_LOCKED'
    tests = [e for e in client.get(f'/api/models/{model}').json()['evaluations'] if e['target'] == 'test']
    assert len(tests) == 1

    # 測試鎖依任務：eGFR 評估過後，分割仍可評估（決策 D27）
    seg_ready = client.get(f'/api/models/{seg_model}/test-readiness').json()
    assert not seg_ready['locked'] and seg_ready['unverified_masks'] == 0 and seg_ready['ready']
    # 分割：某個測試病人側沒有確認的遮罩時，不能做最後評估
    from app.db.models_research import Image, MaskAnnotation, SplitEntry
    from app.db.session import session_scope

    with session_scope('research') as db:
        tp = [p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == research['split'], SplitEntry.group == 'test').all()]
        victim = db.query(Image).filter(Image.patient_id == tp[0], Image.status == 'usable').first()
        same_side = [i.id for i in db.query(Image).filter(Image.patient_id == victim.patient_id, Image.side == victim.side).all()]
        for mk in db.query(MaskAnnotation).filter(MaskAnnotation.image_id.in_(same_side)).all():
            mk.verified_by, mk.status = None, 'draft'
    blocked = client.get(f'/api/models/{seg_model}/test-readiness').json()
    assert blocked['unverified_masks'] == 1 and not blocked['ready'] and blocked['missing_sides']


def test_contract_and_tamper_rejected(research):
    from app.core.config import get_settings
    from app.core.errors import AppError
    from app.ml import engine, registry
    from app.ml.runs import create

    client = research['client']
    run = create('egfr', 't', research['version'], research['split'], {**TINY, 'epochs': 1}, '測試', start=False)['id']
    summary = engine.train_run(run, 'egfr', {**TINY, 'epochs': 1}, research['version'], research['split'], FakeCtx())
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope

    with session_scope('research') as db:
        r = db.get(TrainingRun, run)
        r.status, r.summary_json = 'completed', json.dumps(summary)
    model = client.post('/api/models', json={'run_id': run, 'name': 'tamper-test'}).json()['id']
    folder = get_settings().root / registry.detail(model)['manifest']['training']['run_id']  # noqa: F841
    model_folder = registry.model_dir('egfr', 'tamper-test', '1.0.0')
    with pytest.raises(AppError) as err:
        registry.load(model, 'segmentation')
    assert err.value.code == 'CONTRACT_MISMATCH'
    manifest = json.loads((model_folder / 'manifest.json').read_text(encoding='utf-8'))
    manifest['contract_version'] = 1
    (model_folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(AppError) as err:
        registry.load(model)
    assert err.value.code == 'CONTRACT_MISMATCH'
    manifest['contract_version'] = 2
    (model_folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with (model_folder / 'fold-1.pth').open('ab') as fh:
        fh.write(b'x')
    with pytest.raises(AppError) as err:
        registry.load(model)
    assert err.value.code == 'MODEL_TAMPERED'
    # 連 manifest 裡的雜湊一起改：仍以註冊時存進資料庫的紀錄為準（M3 #114）
    from app.ml.medsam import sha256_file

    manifest['contract_version'] = 3
    manifest['ensemble']['fold-1.pth'] = sha256_file(model_folder / 'fold-1.pth')
    (model_folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(AppError) as err:
        registry.load(model)
    assert err.value.code == 'MODEL_TAMPERED'


def test_features_experiments_and_nnunet_export(research):
    from app.ml import engine, nnunet

    client = research['client']
    fs = client.post('/api/features', json={'source': 'masks'}).json()
    wait_job(fs['job_id'])
    data = client.get(f'/api/features/{fs["id"]}').json()
    assert data['total'] == 12 and set(data['analysis']['by_side']) == {'right', 'left'}
    assert data['analysis']['by_side']['right']['ref_organ'] == 'liver' and data['analysis']['by_side']['left']['ref_organ'] == 'spleen'

    base = {'task': 'egfr', 'dataset_version_id': research['version'], 'split_id': research['split']}
    bad = client.post('/api/experiments', json={**base, 'template': 'ablation', 'feature_set_id': fs['id']})
    assert bad.status_code == 409 and bad.json()['error']['code'] == 'FEATURES_NOT_CROSS_FITTED'
    assert client.post('/api/features', json={'source': 'run', 'run_id': 'RUN-NONE'}).status_code == 409

    exp = client.post('/api/experiments', json={**base, 'template': 'init', 'base_config': {**TINY, 'epochs': 1}}).json()
    assert len(exp['runs']) == 2
    detail = client.get(f'/api/experiments/{exp["id"]}').json()
    assert all(r['status'] == 'draft' for r in detail['runs'])
    started = client.post(f'/api/training/runs/{exp["runs"][1]}/start')  # ImageNet：還沒下載權重
    assert started.status_code == 409 and started.json()['error']['code'] == 'WEIGHTS_NOT_DOWNLOADED'

    info = nnunet.export(research['version'], research['split'])
    raw = nnunet.roots()['nnUNet_raw'] / nnunet.DATASET_NAME
    assert info['cases'] == len(list((raw / 'imagesTr').glob('*_0000.png'))) == len(list((raw / 'labelsTr').glob('*.png'))) > 0
    dataset = json.loads((raw / 'dataset.json').read_text(encoding='utf-8'))
    assert dataset['labels'] == {'background': 0, 'parenchyma': 1, 'sinus': 2} and dataset['file_ending'] == '.png'
    splits = json.loads((nnunet.roots()['nnUNet_preprocessed'] / nnunet.DATASET_NAME / 'splits_final.json').read_text())
    assert len(splits) == len(info['folds']) and all(not set(s['train']) & set(s['val']) for s in splits)
    label = cv2.imdecode(np.fromfile(str(next((raw / 'labelsTr').glob('*.png'))), np.uint8), cv2.IMREAD_GRAYSCALE)
    assert set(np.unique(label)) <= {0, 1, 2}  # 肝脾在 nnU-Net 基準裡算背景
    assert engine is not None


def test_fetch_is_stoppable_and_resumes(tmp_path):
    """預訓練權重下載：分段下載、可以停止、從 .part 接續。"""
    import functools
    import http.server
    import threading

    from app.jobs.manager import StopRequested
    from app.ml.pretrained import _fetch

    payload = bytes(range(256)) * 4096  # 1 MB
    (tmp_path / 'srv').mkdir()
    (tmp_path / 'srv' / 'w.pth').write_bytes(payload)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / 'srv'))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_address[1]}/w.pth'

    class Ctx:
        def __init__(self, stop_after):
            self.n, self.stop_after = 0, stop_after

        def check_stop(self):
            self.n += 1
            if self.stop_after and self.n >= self.stop_after:
                raise StopRequested()

        def progress(self, *a, **k):
            pass

    dest = tmp_path / 'w.pth'
    with pytest.raises(StopRequested):
        _fetch(url, dest, Ctx(stop_after=2))
    part = dest.with_name('w.pth.part')
    assert part.exists() and 0 < part.stat().st_size < len(payload) and not dest.exists()
    _fetch(url, dest, Ctx(stop_after=None))  # 接續（伺服器不支援 Range 時會從頭下載，結果一樣）
    assert dest.read_bytes() == payload and not part.exists()
    server.shutdown()
