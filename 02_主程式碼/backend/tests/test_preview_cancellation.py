from concurrent.futures import ThreadPoolExecutor
import threading


def fixture(client):
    from backend.app.clinical import store
    patient=client.post('/api/clinical/patients',json={'code':'cancel-fixture','name':'Synthetic only'}).json()['id']
    exam=client.post('/api/clinical/exams',json={'kind':'patient','patient_id':patient,'title':'Cancel fixture'}).json()['id']
    with store.transaction() as db:db.execute("INSERT INTO plans VALUES('cancel-plan','Fake plan','{\"validated_for_patient\":true}','{}',1)")
    return exam,client.get('/api/local-session').json()


def test_invalid_body_releases_its_own_capture_lease(client,monkeypatch):
    from backend.app.clinical import routes,resources
    from backend.app.core.errors import AppError
    exam,user=fixture(client);op='a'*32
    async def invalid(request):raise AppError(413,'IMAGE_SIZE','Fixture oversized body')
    monkeypatch.setattr(routes,'image_body',invalid)
    response=client.post(f'/api/clinical/preview?exam_id={exam}&plan_id=cancel-plan&operation_id={op}',content=b'fixture')
    assert response.status_code==413
    assert not resources.session_active(user['session_id'],routes.capture_key(user,op))
    record=client.get('/api/clinical/monitor/previews').json()['items'][0]
    assert record['status']=='failed' and record['error_code']=='IMAGE_SIZE'


def test_released_before_worker_start_never_calls_model(client,make_image,monkeypatch):
    from backend.app.clinical import routes,resources
    exam,user=fixture(client);op='b'*32;calls=[]
    async def cancelled(request):
        resources.release_session(user['session_id'],routes.capture_key(user,op))
        return make_image()
    monkeypatch.setattr(routes,'image_body',cancelled)
    monkeypatch.setattr(routes,'infer',lambda *args:calls.append('must not run'))
    assert client.post(f'/api/clinical/preview?exam_id={exam}&plan_id=cancel-plan&operation_id={op}',content=b'fixture').status_code==410
    assert calls==[]
    assert client.get('/api/clinical/monitor/previews').json()['items'][0]['status']=='cancelled'


def test_released_inflight_compute_keeps_lock_until_exit_and_never_publishes_stale_preview(client,make_image,monkeypatch):
    from backend.app.clinical import routes,resources
    exam,_=fixture(client);op='c'*32;entered=threading.Event();finish=threading.Event()
    before=set(routes._previews)
    def compute(*args):
        with resources.clinical_lease('cpu'):
            entered.set()
            if not finish.wait(5):raise RuntimeError('fixture timeout')
            return {'probabilities':[]},{}
    monkeypatch.setattr(routes,'infer',compute)
    with ThreadPoolExecutor(max_workers=1) as executor:
        request=executor.submit(client.post,f'/api/clinical/preview?exam_id={exam}&plan_id=cancel-plan&operation_id={op}',content=make_image())
        try:
            assert entered.wait(3)
            assert client.post(f'/api/clinical/preview/release?operation_id={op}',json={}).status_code==200
            assert resources.clinical_lock.locked()
        finally:finish.set()
        assert request.result(5).status_code==410
    assert not resources.clinical_lock.locked() and set(routes._previews)==before
    assert client.get('/api/clinical/monitor/previews').json()['items'][0]['status']=='cancelled'


def test_preview_history_survives_restart_and_blocks_empty_exam_deletion(client):
    import sqlite3
    import time
    import pytest
    from backend.app.clinical import store,monitor
    exam,user=fixture(client)
    with store.transaction() as db:
        db.execute('INSERT INTO preview_operations(id,operation_key,exam_id,plan_id,actor,basic_input,status,created) VALUES(?,?,?,?,?,?,?,?)',
                   ('interrupted-preview','d'*32,exam,'cancel-plan',user['id'],'{}','running',time.time()))
    monitor.recover();monitor.recover()
    listing=client.get('/api/clinical/monitor/previews').json()
    assert listing['total']==1 and listing['items'][0]['status']=='interrupted'
    assert 'basic_input' not in listing['items'][0]
    check=client.get(f'/api/clinical/lifecycle/exams/{exam}?action=delete_empty').json()
    assert not check['allowed'] and check['references']['preview_operations']==1
    with store.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE preview_operations SET status='completed'")
