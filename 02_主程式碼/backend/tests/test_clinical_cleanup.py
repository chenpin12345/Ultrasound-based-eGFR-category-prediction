import sqlite3
import time

import pytest


def fixture(client,make_image):
    from backend.app.clinical import store,service
    actor=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        session=store.uid()
        db.execute('INSERT INTO demo_sessions(id,owner,plan_id,state,created,expires) VALUES(?,?,NULL,?,?,?)',(session,actor,'ended',time.time(),time.time()+60))
        exam=service.new_exam(db,'demo',None,'Temporary cleanup fixture','left',{},session)
    frame=service.save_frame(make_image(),exam,'network_demo')
    return session,exam,frame


def test_failure_keeps_blocking_journal_and_explicit_retry_completes(client,make_image,monkeypatch):
    from backend.app.clinical import store,temporary_cleanup as cleanup
    session,exam,frame=fixture(client,make_image)
    def locked(*args,**kwargs):raise PermissionError('fixture only')
    with monkeypatch.context() as patch:
        patch.setattr(cleanup.shutil,'rmtree',locked)
        cleanup.cleanup_session(session)
    listing=client.get('/api/clinical/monitor/cleanup').json()
    row=listing['items'][0]
    assert listing['total']==1 and row['status']=='failed' and 'path' not in row
    assert client.get(f'/api/clinical/frames/{frame}/original').status_code==409
    assert client.post(f'/api/clinical/frames/{frame}/save',json={}).status_code==409
    assert not client.get(f'/api/clinical/lifecycle/exams/{exam}').json()['allowed']
    cleanup.cleanup_session(session)  # no silent repeated deletion attempts
    assert client.get('/api/clinical/monitor/cleanup').json()['items'][0]['attempts']==1
    assert client.post(f'/api/clinical/monitor/cleanup/{row["id"]}/retry',json={'reason':'檔案占用已解除'}).status_code==200
    assert client.get(f'/api/clinical/frames/{frame}/original').status_code==404
    with store.transaction() as db:
        assert db.execute('SELECT 1 FROM exams WHERE id=?',(exam,)).fetchone()  # history retained
        assert db.execute('SELECT COUNT(*) FROM cleanup_attempts').fetchone()[0]==2
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM temporary_cleanup')


def test_saved_referenced_and_recycled_frames_are_never_cleaned(client,make_image):
    from backend.app.clinical import store,temporary_cleanup as cleanup
    for protect in ('saved','report','recycled','publication'):
        session,exam,frame=fixture(client,make_image)
        with store.transaction() as db:
            if protect=='saved':db.execute('UPDATE frames SET saved=1 WHERE id=?',(frame,))
            elif protect=='report':db.execute('INSERT INTO reports VALUES(?,?,0,?,?)',(store.uid(),exam,'draft',time.time()))
            elif protect=='recycled':db.execute("UPDATE clinical_lifecycle SET state='trashed' WHERE entity='exams' AND id=?",(exam,))
            else:db.execute('INSERT INTO analysis_publications(id,frame_id,path,state,created) VALUES(?,?,?,?,?)',(store.uid(),frame,'fixture','staging',time.time()))
        cleanup.cleanup_session(session)
        with store.read_transaction() as db:
            assert db.execute('SELECT 1 FROM frames WHERE id=?',(frame,)).fetchone()
    assert client.get('/api/clinical/monitor/cleanup').json()['total']==0


def test_interrupted_journal_blocks_access_and_does_not_automatically_retry(client,make_image,monkeypatch):
    from backend.app.clinical import store,temporary_cleanup as cleanup
    session,_,frame=fixture(client,make_image)
    with monkeypatch.context() as patch:
        patch.setattr(cleanup,'run',lambda *args,**kwargs:None)
        cleanup.cleanup_session(session)
    cleanup.recover()
    row=client.get('/api/clinical/monitor/cleanup').json()['items'][0]
    assert row['status']=='interrupted'
    cleanup.cleanup_session(session)
    with store.read_transaction() as db:assert db.execute('SELECT 1 FROM frames WHERE id=?',(frame,)).fetchone()
    assert client.post(f'/api/clinical/monitor/cleanup/{row["id"]}/retry',json={'reason':'確認中斷作業'}).status_code==200


def test_out_of_scope_path_is_not_deleted(client,make_image):
    from backend.app.clinical import store,temporary_cleanup as cleanup
    session,exam,frame=fixture(client,make_image)
    with store.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE frames SET path='clinical.sqlite3' WHERE id=?",(frame,))
        db.execute('INSERT INTO frames VALUES(?,?,?,?,?,NULL,?,?,?)',(store.uid(),exam,'0'*64,'clinical.sqlite3','network_demo','received',0,time.time()))
    cleanup.cleanup_session(session)
    assert (store.root()/'clinical.sqlite3').is_file()
    assert any(row['status']=='failed' for row in client.get('/api/clinical/monitor/cleanup').json()['items'])


def test_confirmation_records_explicit_ack_without_changing_reviewed_payload(client):
    from backend.app.clinical import store
    exam=client.post('/api/clinical/exams',json={'kind':'demo','title':'Incomplete report fixture'}).json()['id']
    payload={'exam_id':exam,'fields':{'physician':'判讀者'},'frame_ids':[]}
    report=client.post('/api/clinical/reports',json=payload).json()['id']
    url=f'/api/clinical/reports/{report}/versions'
    assert client.post(url,json={**payload,'action':'pending','expected_version':1}).status_code==200
    assert client.post(url,json={**payload,'action':'confirmed','expected_version':2}).status_code==422
    assert client.post(url,json={**payload,'action':'confirmed','expected_version':2,'acknowledge_missing':True}).status_code==200
    with store.transaction() as db:
        reviewed=db.execute('SELECT payload FROM report_versions WHERE report_id=? AND version=2',(report,)).fetchone()[0]
        confirmed=db.execute('SELECT payload FROM report_versions WHERE report_id=? AND version=3',(report,)).fetchone()[0]
        assert reviewed==confirmed
        row=db.execute('SELECT * FROM report_confirmations WHERE report_id=?',(report,)).fetchone()
        assert row['acknowledged']==1 and row['reviewed_version']==2 and '尚未加入影像' in row['missing_items']
        with pytest.raises(sqlite3.IntegrityError):db.execute('UPDATE report_confirmations SET acknowledged=0')
