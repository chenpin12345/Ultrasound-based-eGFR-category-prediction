import sqlite3
import time

import pytest


def test_monitor_exact_paging_over_old_500_limit_without_medical_payloads(client):
    from backend.app.clinical import store
    owner=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        for index in range(537):
            key=f'p-{index:04}'
            db.execute('INSERT INTO patients VALUES(?,?,?,?)',(key,f'CODE{index:04}',f'Fixture {index:04}',1000+index))
            db.execute('INSERT INTO exams(id,kind,patient_id,title,side,payload,revision,created) VALUES(?,?,?,?,?,?,1,?)',
                       (f'e-{index:04}','patient',key,f'Exam {index:04}','left','{"private_notes":"must_not_be_loaded"}',1000+index))
        store.audit(db,owner,'fixture_action','p-0000')
    identifiers=[]
    for offset in range(0,537,50):
        result=client.get(f'/api/clinical/monitor/patients?offset={offset}').json()
        assert result['total']==537
        assert len(result['items'])==min(50,537-offset)
        identifiers.extend(row['id'] for row in result['items'])
    assert len(identifiers)==len(set(identifiers))==537
    response=client.get('/api/clinical/monitor/exams?search=CODE0536&kind=patient')
    assert response.json()['total']==1
    assert 'payload' not in response.json()['items'][0] and 'private_notes' not in response.text
    assert response.json()['items'][0]['patient_name']=='Fixture 0536'
    selected=client.get('/api/clinical/monitor/patients?exact_id=p-0536').json()
    assert selected['total']==1 and selected['items'][0]['id']=='p-0536'
    assert client.get('/api/clinical/monitor/patients?search=%25').json()['total']==0
    assert client.get('/api/clinical/monitor/patients?date_from=1000&date_to=1009').json()['total']==10
    assert client.get('/api/clinical/monitor/patients?date_from=1009&date_to=1000').status_code==422
    assert client.get('/api/clinical/monitor/patients?status=unknown').status_code==422
    assert client.get('/api/clinical/monitor/audit').json()['items'][0]['actor_name']=='本機操作'
    assert response.headers['cache-control']=='no-store'


def frame_fixture(client,make_image):
    from backend.app.clinical import store,service
    actor=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        exam=service.new_exam(db,'demo',None,'Isolated operation','left',{})
        db.execute('INSERT INTO plans VALUES(?,?,?,?,?)',('fixture-plan','Known fixture plan','{}','{}',time.time()))
    frame=service.save_frame(make_image(),exam,'network_demo',saved=True)
    return actor,exam,frame


def test_analysis_operation_history_success_failure_and_resource_busy(client,make_image,monkeypatch):
    from backend.app.clinical import store,service
    from backend.app.core.errors import AppError
    actor,exam,frame=frame_fixture(client,make_image)
    monkeypatch.setattr(service,'infer',lambda *args:({'predicted_class':'fixture'},{}))
    result=client.post(f'/api/clinical/frames/{frame}/analyze?plan_id=fixture-plan').json()
    assert result['status']=='completed'
    operations=client.get('/api/clinical/monitor/operations').json()
    assert operations['total']==1 and operations['items'][0]['id']==result['operation_id']
    with store.read_transaction() as db:
        assert db.execute('SELECT actor FROM clinical_operations').fetchone()[0]==actor
    def busy(*args):raise AppError(409,'GPU_BUSY','運算資源使用中。')
    monkeypatch.setattr(service,'infer',busy)
    assert client.post(f'/api/clinical/frames/{frame}/analyze?plan_id=fixture-plan').status_code==409
    with store.read_transaction() as db:
        assert db.execute('SELECT status FROM frames WHERE id=?',(frame,)).fetchone()[0]=='completed'
    operations=client.get('/api/clinical/monitor/operations?status=failed').json()
    assert operations['total']==1 and operations['items'][0]['error_code']=='GPU_BUSY'
    with store.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM clinical_operations WHERE id=?',(result['operation_id'],))
    from backend.app.db.models import Job
    from backend.app.db.session import get_session_factory
    from sqlalchemy import select
    with get_session_factory()() as db:
        assert not list(db.scalars(select(Job)))  # No clinical identifiers copied into research jobs.


def test_interrupted_analysis_is_not_reported_as_complete(client,make_image):
    from backend.app.clinical import store,monitor
    actor,exam,frame=frame_fixture(client,make_image)
    with store.transaction() as db:
        db.execute("INSERT INTO clinical_operations(id,kind,frame_id,exam_id,plan_id,actor,status,created) VALUES(?,'frame_analysis',?,?,?,?,'running',?)",('interrupted',frame,exam,'fixture-plan',actor,time.time()))
        db.execute("UPDATE frames SET status='analyzing' WHERE id=?",(frame,))
    monitor.recover();monitor.recover()
    result=client.get('/api/clinical/monitor/operations?status=interrupted').json()
    assert result['total']==1 and result['items'][0]['error_code']=='PROCESS_RESTARTED'
    with store.read_transaction() as db:
        assert db.execute('SELECT status FROM frames WHERE id=?',(frame,)).fetchone()[0]=='failed'
