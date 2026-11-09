"""M3 階段 A：醫師端資料表與資料夾、分析方案（候選標示）、用到的模型受保護、醫師端佇列、模型預熱。只用合成資料。"""

from __future__ import annotations

import threading

import pytest

from tests.conftest import wait_job
from tests.test_egfr import _run, cohort  # noqa: F401  共用 20 位合成病人
from tests.test_training import TINY


def test_clinical_tables_folders_and_restricted(client, workspace):
    import sqlalchemy as sa

    from app.db.session import get_engine
    from app.services import workspace as ws

    tables = set(sa.inspect(get_engine('clinical')).get_table_names())
    assert {'clinical_patients', 'clinical_exams', 'clinical_images', 'clinical_analyses', 'clinical_edits', 'clinical_reports',
            'clinical_report_versions', 'receiver_sessions', 'receiver_batches'} <= tables
    base = workspace / '05_醫師端'
    assert all((base / sub).is_dir() for sub in ('01_原始', '02_影像', '03_報告', '04_分析', '05_接收暫存'))
    assert (base / '說明.txt').exists()
    for sub, status in (('01_原始', 403), ('05_接收暫存', 403), ('02_影像', 200)):
        assert client.post('/api/system/open-folder', json={'kind': 'relpath', 'id': f'05_醫師端/{sub}'}).status_code == status
    # M3 之前的空資料夾只刪空的
    (base / '報告').mkdir()
    (base / '檢查').mkdir()
    (base / '檢查' / 'keep.txt').write_text('x', encoding='utf-8')
    assert ws.cleanup_legacy_clinical_dirs() == 1 and not (base / '報告').exists() and (base / '檢查').exists()


def test_analysis_plan_candidate_and_model_protection(cohort):  # noqa: F811
    client = cohort['client']
    run, _ = _run(cohort, {**TINY, 'epochs': 1})
    model = client.post('/api/models', json={'run_id': run, 'name': 'clin-a', 'version': '1.0.0'}).json()['id']
    plan = client.get('/api/clinical/plan').json()
    assert plan['options']['egfr'] == [] and plan['current']['problems']  # 研究階段不能選；還沒選任何模型
    bad = client.put('/api/settings', json={'clinical_plan': {'egfr': model}})
    assert bad.status_code == 422 and '候選' in bad.json()['error']['message']
    assert client.put('/api/settings', json={'clinical_plan': {'segmentation': model}}).status_code == 422  # 任務不符
    client.post(f'/api/models/{model}/stage', json={'stage': 'candidate'})
    assert client.put('/api/settings', json={'clinical_plan': {'egfr': model}}).status_code == 200
    current = client.get('/api/clinical/plan').json()['current']
    assert current['zones']['egfr'] == {'model_id': model, 'stage': 'candidate', 'candidate': True}
    assert current['candidate'] and current['candidate_label'] == '尚未臨床核准・僅供研究展示' and current['problems'] == []
    # 被分析方案用到的模型不能退役、不能移入回收桶
    retire = client.post(f'/api/models/{model}/stage', json={'stage': 'retired'}).json()
    assert retire['error']['code'] == 'MODEL_IN_USE'
    assert client.post('/api/training/runs/trash', json={'run_ids': [run]}).json()['error']['code'] == 'MODEL_IN_USE'
    # 其他醫師端設定
    assert client.put('/api/settings', json={'clinical_device_mode': True}).status_code == 422
    assert client.put('/api/settings', json={'clinical_receiver_port': 8000}).status_code == 422
    assert client.put('/api/settings', json={'clinical_receiver_port': 8443}).status_code == 200
    # 預熱：在醫師端佇列載入模型（只讀權重、雜湊以資料庫為準）
    job = client.post('/api/clinical/warmup').json()['job_id']
    wait_job(job)
    info = client.get(f'/api/jobs/{job}').json()
    assert info['status'] == 'completed' and info['zone'] == 'clinical', info
    assert [d['model_id'] for d in info['result']['loaded']] == [model]
    assert client.get('/api/clinical/plan').json()['loaded'][0]['model_id'] == model
    # 換掉方案後就可以退役
    client.put('/api/settings', json={'clinical_plan': {'egfr': None}})
    assert client.get('/api/clinical/plan').json()['loaded'] == []  # 換掉的模型從記憶體釋放
    assert client.post(f'/api/models/{model}/stage', json={'stage': 'retired'}).json()['stage'] == 'retired'


def test_clinical_pool_is_not_blocked_by_exclusive_jobs(client):
    from app.jobs.manager import get_manager, register

    release = threading.Event()

    @register('test_long_training', exclusive=True)
    def long_training(ctx):
        release.wait(30)
        return {}

    @register('test_clinical_quick', pool='clinical')
    def clinical_quick(ctx):
        return {'ok': True}

    manager = get_manager()
    blocker = manager.submit('test_long_training')
    queued_behind = manager.submit('test_long_training')  # 這個會排在訓練後面
    quick = manager.submit('test_clinical_quick')
    manager.wait(quick, timeout=10)  # 醫師端的工作不用等訓練
    from app.db.models_system import Job
    from app.db.session import session_scope

    with session_scope('system') as db:
        assert db.get(Job, quick).status == 'completed' and db.get(Job, queued_behind).status == 'queued'
    release.set()
    manager.wait(blocker, timeout=10)
    manager.wait(queued_behind, timeout=10)
    from app.jobs.manager import HANDLERS

    for kind in ('test_long_training', 'test_clinical_quick'):  # 測試用的工作種類不留在全域（文件檢查會掃描）
        HANDLERS.pop(kind, None)


@pytest.mark.parametrize('busy', [False, True])
def test_device_choice_uses_cpu_while_training(client, busy):
    from app.clinical import models_cache
    from app.core.ids import now_iso
    from app.db.models_system import Job
    from app.db.session import session_scope

    if busy:
        with session_scope('system') as db:
            db.add(Job(id='JOB-TRAINING', kind='train', target='', status='running', config_json='{}', created_by='', created_at=now_iso()))
    device, note = models_cache.device_choice()
    assert (device, bool(note)) == (('cpu', True) if busy else ('auto', False))
