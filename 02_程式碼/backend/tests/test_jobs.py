"""背景工作：停止、恢復、重試、服務重啟後中斷、SSE。"""

from __future__ import annotations

import time

from tests.conftest import wait_job


def _register_test_handlers():
    from app.jobs.manager import register

    @register('test_sleep', resumable=True, label='測試')
    def sleep_job(ctx):
        for i in range(200):
            ctx.check_stop()
            ctx.progress(i / 2)
            time.sleep(0.02)
        return {'done': True, 'resumed': ctx.resume}

    @register('test_fail', label='測試失敗')
    def fail_job(ctx):
        raise RuntimeError(r'boom at C:\secret\path\file.txt')


def test_stop_resume_retry(client):
    from app.jobs.manager import get_manager

    _register_test_handlers()
    m = get_manager()
    job = m.submit('test_sleep', {}, created_by='測試')
    time.sleep(0.3)
    assert client.post(f'/api/jobs/{job}/stop').json()['status'] in {'stopping', 'stopped'}
    wait_job(job)
    for _ in range(50):
        if client.get(f'/api/jobs/{job}').json()['status'] == 'stopped':
            break
        time.sleep(0.05)
    assert client.get(f'/api/jobs/{job}').json()['status'] == 'stopped'
    client.post(f'/api/jobs/{job}/resume')
    wait_job(job)
    data = client.get(f'/api/jobs/{job}').json()
    assert data['status'] == 'completed' and data['result']['resumed'] is True

    failed = m.submit('test_fail', {})
    wait_job(failed)
    info = client.get(f'/api/jobs/{failed}').json()
    assert info['status'] == 'failed'
    assert 'secret' not in info['error_message']  # 不回傳本機路徑
    new = client.post(f'/api/jobs/{failed}/retry').json()['job_id']
    wait_job(new)
    assert client.get(f'/api/jobs/{new}').json()['retry_of'] == failed


def test_restart_marks_running_as_interrupted(client):
    from app.core.ids import now_iso
    from app.db.models_system import Job
    from app.db.session import session_scope
    from app.jobs.manager import get_manager

    with session_scope('system') as db:
        db.add(Job(id='JOB-old', kind='import', status='running', created_at=now_iso()))
    get_manager().recover()
    assert client.get('/api/jobs/JOB-old').json()['status'] == 'interrupted'


def test_sse_stream_delivers_events(client):
    from app.jobs.manager import get_manager

    _register_test_handlers()
    job = get_manager().submit('test_sleep', {})
    wait_job(job)
    with client.raw.stream('GET', f'/api/jobs/{job}/events') as r:
        text = ''.join(chunk for chunk in r.iter_text())
    assert 'event: queued' in text and 'event: completed' in text and 'event: end' in text


def test_delete_job_records_skips_active(client):
    from app.jobs.manager import get_manager

    _register_test_handlers()
    m = get_manager()
    done = m.submit('test_fail', {})
    wait_job(done)
    running = m.submit('test_sleep', {})
    time.sleep(0.2)
    r = client.post('/api/jobs/delete', json={'ids': [done, running]}).json()
    assert r == {'deleted': 1, 'skipped': 1}  # 執行中的不能刪
    assert client.get(f'/api/jobs/{done}').status_code == 404
    assert client.get(f'/api/jobs/{running}').status_code == 200
    client.post(f'/api/jobs/{running}/stop')
    wait_job(running)
