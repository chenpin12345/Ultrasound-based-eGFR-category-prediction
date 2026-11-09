"""全面功能檢查（2026-11-09）：建立一份「什麼都有」的合成工作區，把每一個 GET API 都用真實 ID 呼叫一遍，不能出現伺服器錯誤（500）。

只用合成影像。新增 GET API 時不用改這個測試：路徑參數會自動換成工作區裡真的存在的 ID。
"""

from __future__ import annotations

import hashlib
import json
import re

import cv2

from tests.conftest import wait_job
from tests.test_clinical_flow import _put
from tests.test_masksets import _seg_run
from tests.test_training import TINY, FakeCtx, research  # noqa: F401


def _egfr_run(research):  # noqa: F811
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope
    from app.ml import engine
    from app.ml.runs import create

    cfg = {**TINY, 'epochs': 1}
    run = create('egfr', 'e', research['version'], research['split'], cfg, '測試', start=False)['id']
    summary = engine.train_run(run, 'egfr', cfg, research['version'], research['split'], FakeCtx())
    with session_scope('research') as db:
        r = db.get(TrainingRun, run)
        r.status, r.summary_json, r.finished_at = 'completed', json.dumps(summary), '2026-11-09T10:00:00'
    return run


def test_every_get_api_works_on_a_full_workspace(research, workspace):  # noqa: F811
    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient

    from app.clinical import receiver
    from app.db.models_clinical import ClinicalAnalysis, ClinicalExam, ClinicalImage, ClinicalPatient, ClinicalReport
    from app.db.models_research import Batch, CirclingBatch, CirclingItem, Experiment, FeatureSet, Image, LayoutTemplate, MaskSet
    from app.db.models_system import Job
    from app.db.session import session_scope
    from app.main import create_app
    from tests import synthetic

    client = research['client']
    seg = _seg_run(research)
    egfr = _egfr_run(research)
    seg_model = client.post('/api/models', json={'run_id': seg, 'name': 'seg-smoke', 'version': '1.0.0'}).json()['id']
    egfr_model = client.post('/api/models', json={'run_id': egfr, 'name': 'egfr-smoke', 'version': '1.0.0'}).json()['id']
    client.post(f'/api/training/runs/{egfr}/evaluate')
    ms = client.post('/api/mask-sets', json={'seg_run_id': seg}).json()
    wait_job(ms['job_id'])
    pipe = client.post('/api/pipelines', json={'seg_model_id': seg_model, 'classifier_ids': [egfr_model], 'image_ids': research['images'][:2]}).json()['job_id']
    wait_job(pipe)
    client.post('/api/egfr/comparisons', json={'dataset_version_id': research['version'], 'split_id': research['split'], 'inputs': ['clinical'], 'classes': [2], 'start': False})
    client.post('/api/circling/batches', json={'kind': 'all'})
    for m in (seg_model, egfr_model):
        client.post(f'/api/models/{m}/stage', json={'stage': 'candidate'})
    client.put('/api/settings', json={'clinical_plan': {'segmentation': seg_model, 'egfr': egfr_model}})

    # 醫師端：一筆有分析、有報告的檢查
    started = client.post('/api/clinical/receiver/start', json={'address': '127.0.0.1'}).json()
    up = TestClient(receiver.upload_app())
    token = up.post('/pair', headers={'x-pair-code': started['code']}).json()['token']
    b = up.post('/batches', headers={'authorization': f'Bearer {token}'}, json={'case_code': 'SMOKE-1', 'age': 60, 'sex': 'M', 'diabetes': 'no'}).json()
    img, _ = synthetic.toshiba(622, 500, 4, 'left')
    data = cv2.imencode('.png', img)[1].tobytes()
    _put(up, token, b['batch_id'], 1, data, **{'x-side': 'left', 'x-spacing': '0.3'})
    up.post(f"/batches/{b['batch_id']}/finish", headers={'authorization': f'Bearer {token}'})
    with session_scope('system') as db:
        for (job_id,) in db.query(Job.id).filter(Job.kind.like('clinical_%')).all():
            wait_job(job_id)
    with session_scope('system') as db:
        for (job_id,) in db.query(Job.id).filter(Job.kind.like('clinical_%')).all():
            wait_job(job_id)
    client.post(f"/api/clinical/exams/{b['exam_id']}/report")
    client.post('/api/clinical/receiver/stop')

    with session_scope('research') as db:
        ids = {
            'image_id': research['images'][0], 'batch_id': db.query(Batch.id).first()[0], 'split_id': research['split'],
            'template_id': db.query(LayoutTemplate.id).first()[0], 'run_id': egfr, 'model_id': egfr_model, 'ms_id': ms['id'],
            'fs_id': db.query(FeatureSet.id).first()[0], 'exp_id': db.query(Experiment.id).first()[0], 'item_id': str(db.query(CirclingItem.id).first()[0]),
            'patient_id': None, 'task': 'grade', 'key': 'P-0001:right', 'kind': 'thumb', 'version': '1', 'job_id': pipe,
        }
        circling_batch = db.query(CirclingBatch.id).first()[0]
    with session_scope('clinical') as db:
        exam = db.get(ClinicalExam, b['exam_id'])
        ids.update(exam_id=exam.id, analysis_id=db.query(ClinicalAnalysis.id).first()[0], report_id=db.query(ClinicalReport.id).first()[0],
                   clinical_patient=db.query(ClinicalPatient.id).first()[0], clinical_image=db.query(ClinicalImage.id).first()[0])

    def fill(path: str) -> str:
        def sub(m: re.Match) -> str:
            name = m.group(1)
            if name == 'batch_id':
                return circling_batch if '/circling/' in path else (b['batch_id'] if '/receiver/' in path else ids['batch_id'])
            if name == 'patient_id':
                return ids['clinical_patient']
            if name == 'image_id' and '/clinical/' in path:
                return ids['clinical_image']
            if name == 'image_id' and '/mask-sets/' in path:
                return ids['image_id']
            return str(ids[name])
        return re.sub(r'\{(\w+)(?::\w+)?\}', sub, path)

    failures = []
    checked = 0
    for r in create_app(testing=True).routes:
        if not isinstance(r, APIRoute) or 'GET' not in r.methods or not r.path.startswith('/api') or r.path.endswith('/events'):
            continue
        url = fill(r.path)
        if r.path == '/api/annotation/queue/{task}':
            url += '?rater=林醫師'
        response = client.get(url)
        checked += 1
        if response.status_code >= 500:
            failures.append(f'{url} → {response.status_code} {response.text[:200]}')
    assert checked > 70
    assert not failures, '\n'.join(failures)
    # 一鍵流程結果、醫師端分析都真的有東西
    assert client.get(f'/api/pipelines/{pipe}').status_code == 200
    assert client.get(f"/api/clinical/exams/{ids['exam_id']}").json()['analysis']['steps']['segmentation']['status'] == 'done'
    assert hashlib.sha256(data).hexdigest()


def test_every_write_api_rejects_unknown_ids_without_crashing(client):
    """每一個寫入 API 用不存在的 ID、空白內容呼叫：要回清楚的錯誤（4xx），不能是伺服器錯誤（500）。"""
    from fastapi.routing import APIRoute

    from app.main import create_app

    skip = {'/api/session', '/api/pretrained/{name}/download'}  # 工作階段本身；下載會連網路
    failures, checked = [], 0
    for r in create_app(testing=True).routes:
        if not isinstance(r, APIRoute) or not r.path.startswith('/api') or r.path in skip:
            continue
        for method in sorted(r.methods - {'GET', 'HEAD'}):
            url = re.sub(r'\{(\w+)(?::\w+)?\}', lambda m: '999999' if m.group(1) in ('item_id', 'person_id', 'mask_id', 'group_id_int') else 'NOPE', r.path)
            response = {'POST': client.post, 'PUT': client.put, 'PATCH': client.patch}[method](url, json={})
            checked += 1
            if response.status_code >= 500:
                failures.append(f'{method} {url} → {response.status_code} {response.text[:200]}')
    client.post('/api/clinical/receiver/stop')
    assert checked > 80
    assert not failures, '\n'.join(failures)
