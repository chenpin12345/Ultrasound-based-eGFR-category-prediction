import sqlite3
import time

import pytest


def fixtures(client,make_image):
    from backend.app.clinical import store,service
    patient=client.post('/api/clinical/patients',json={'code':'LIFE','name':'Lifecycle fixture'}).json()['id']
    exam=client.post('/api/clinical/exams',json={'kind':'patient','patient_id':patient,'title':'Lifecycle exam'}).json()['id']
    frame=service.save_frame(make_image(),exam,'capture',saved=True)
    report=client.post('/api/clinical/reports',json={'exam_id':exam,'frame_ids':[frame],'fields':{'physician':'Fixture'}}).json()['id']
    return patient,exam,frame,report


def action(client,entity,identifier,operation,expected=200):
    pre=client.get(f'/api/clinical/lifecycle/{entity}/{identifier}?action={operation}')
    assert pre.status_code==200,pre.text
    response=client.post(f'/api/clinical/lifecycle/{entity}/{identifier}',json={'action':operation,'expected_revision':pre.json()['revision'],'reason':'isolated lifecycle test'})
    assert response.status_code==expected,response.text
    return response.json()


def test_parent_recycle_blocks_old_urls_and_preserves_child_history(client,make_image):
    from backend.app.clinical import store
    patient,exam,frame,report=fixtures(client,make_image)
    with store.read_transaction() as db:before=db.execute('SELECT payload FROM report_versions WHERE report_id=?',(report,)).fetchall()
    action(client,'reports',report,'trash')
    action(client,'patients',patient,'trash')
    for url in (f'/api/clinical/exams/{exam}',f'/api/clinical/frames/{frame}/original',f'/api/clinical/reports/{report}',f'/api/clinical/reports/{report}/versions/1/pdf'):
        assert client.get(url).status_code==410,url
    assert client.get('/api/clinical/monitor/exams').json()['total']==0
    assert client.get('/api/clinical/monitor/exams?lifecycle=trashed').json()['total']==1
    assert client.get('/api/clinical/patients').json()==[]
    assert client.post('/api/clinical/exams',json={'kind':'patient','patient_id':patient,'title':'Must be blocked'}).status_code==410
    action(client,'reports',report,'restore',409)
    action(client,'patients',patient,'restore')
    assert client.get(f'/api/clinical/exams/{exam}').status_code==200
    assert client.get(f'/api/clinical/reports/{report}').status_code==410  # no automatic child restore
    action(client,'reports',report,'restore')
    assert client.get(f'/api/clinical/reports/{report}').status_code==200
    with store.read_transaction() as db:
        assert [tuple(r) for r in db.execute('SELECT payload FROM report_versions WHERE report_id=?',(report,))]==[tuple(r) for r in before]
        assert db.execute('SELECT COUNT(*) FROM clinical_lifecycle_events').fetchone()[0]==4


def test_archive_is_readable_but_blocks_mutations_and_empty_delete_is_conservative(client,make_image):
    patient,exam,frame,report=fixtures(client,make_image)
    action(client,'exams',exam,'archive')
    assert client.get(f'/api/clinical/exams/{exam}').status_code==200
    assert client.post(f'/api/clinical/frames/{frame}/save').status_code==409
    assert client.post('/api/clinical/reports',json={'exam_id':exam}).status_code==409
    action(client,'exams',exam,'delete_empty',409)
    action(client,'patients',patient,'delete_empty',409)
    action(client,'reports',report,'delete_empty',409)
    action(client,'exams',exam,'trash')
    restored=action(client,'exams',exam,'restore')
    assert restored['state']=='archived'
    action(client,'exams',exam,'restore')
    assert client.post(f'/api/clinical/frames/{frame}/save').status_code==200
    empty=client.post('/api/clinical/exams',json={'kind':'demo','title':'Empty mistake'}).json()['id']
    deleted=action(client,'exams',empty,'delete_empty')
    assert deleted['state']=='deleted' and deleted['files_deleted'] is False
    assert client.get(f'/api/clinical/exams/{empty}').status_code==404
    empty_patient=client.post('/api/clinical/patients',json={'code':'MISTAKE','name':'Empty mistaken record'}).json()['id']
    action(client,'patients',empty_patient,'delete_empty')


def test_stale_revision_and_new_references_block_submit(client):
    patient=client.post('/api/clinical/patients',json={'code':'RACE','name':'Fixture'}).json()['id']
    pre=client.get(f'/api/clinical/lifecycle/patients/{patient}?action=delete_empty').json()
    assert pre['allowed']
    client.post('/api/clinical/exams',json={'kind':'patient','patient_id':patient,'title':'New reference'})
    result=client.post(f'/api/clinical/lifecycle/patients/{patient}',json={'action':'delete_empty','expected_revision':pre['revision'],'reason':'test'})
    assert result.status_code==409
    action(client,'patients',patient,'archive')
    stale=client.post(f'/api/clinical/lifecycle/patients/{patient}',json={'action':'trash','expected_revision':pre['revision'],'reason':'test'})
    assert stale.status_code==409 and stale.json()['error']['code']=='REVISION_CONFLICT'


def test_busy_capture_prevents_transition_and_audit_is_immutable(client,make_image):
    from backend.app.clinical import store,resources
    patient,exam,_,_=fixtures(client,make_image)
    resources.reserve_session('fixture-owner','fixture-key')
    try:action(client,'exams',exam,'trash',409)
    finally:resources.release_session('fixture-owner','fixture-key')
    action(client,'exams',exam,'trash')
    with store.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM clinical_lifecycle_events')


def test_metadata_revision_invalidates_lifecycle_confirmation(client):
    exam=client.post('/api/clinical/exams',json={'kind':'demo','title':'Original'}).json()['id']
    pre=client.get(f'/api/clinical/lifecycle/exams/{exam}?action=archive').json()
    assert client.patch(f'/api/clinical/exams/{exam}?expected_revision=1',json={'kind':'demo','title':'Changed'}).status_code==200
    response=client.post(f'/api/clinical/lifecycle/exams/{exam}',json={'action':'archive','expected_revision':pre['revision'],'reason':'test'})
    assert response.status_code==409


def test_missing_lifecycle_fails_closed_and_report_capability_is_explicit(client,make_image):
    from backend.app.clinical import store
    _,exam,_,report=fixtures(client,make_image)
    info=client.get('/api/local-session').json()
    with store.transaction() as db:
        db.execute('UPDATE local_sessions SET capabilities=? WHERE id=?',('["clinical.read","clinical.operate"]',info['session_id']))
    assert client.post('/api/clinical/reports',json={'exam_id':exam}).status_code==403
    assert client.post(f'/api/clinical/reports/{report}/versions',json={'exam_id':exam,'expected_version':1}).status_code==403
    with store.transaction() as db:
        db.execute("DELETE FROM clinical_lifecycle WHERE entity='exams' AND id=?",(exam,))
    assert client.get(f'/api/clinical/exams/{exam}').status_code==503
    assert client.get(f'/api/clinical/reports/{report}').status_code==503
