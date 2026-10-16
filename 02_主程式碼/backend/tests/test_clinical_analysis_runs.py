import hashlib
import sqlite3
import time

import pytest
from PIL import Image


def setup_frame(client,make_image):
    from backend.app.clinical import store,service
    actor=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        exam=service.new_exam(db,'demo',None,'Analysis version fixture','left',{'age':50,'has_diabetes':0})
        db.execute('INSERT INTO plans VALUES(?,?,?,?,?)',('run-plan','Isolated fake plan','{"mode":"prepared"}','{}',time.time()))
    frame=service.save_frame(make_image(),exam,'network_demo',saved=True)
    return actor,exam,frame


def infer_fixture(color):
    return {'predicted_class':'fixture','features':{'Length_px':0},'has_mask':False}, {'processed':Image.new('RGB',(32,24),color)}


def test_reanalysis_creates_distinct_immutable_artifacts_and_reports_keep_selected_run(client,make_image,monkeypatch):
    from backend.app.clinical import store,service
    actor,exam,frame=setup_frame(client,make_image)
    monkeypatch.setattr(service,'infer',lambda *args:infer_fixture('red'))
    first=service.analyze_frame(frame,'run-plan',actor=actor)['result']['analysis_run_id']
    before=client.get(f'/api/clinical/analyses/{first}/processed').content
    payload={'exam_id':exam,'frame_ids':[frame],'include_ai':True,'fields':{'findings':'Frozen result'}}
    report=client.post('/api/clinical/reports',json=payload).json()['id']
    monkeypatch.setattr(service,'infer',lambda *args:infer_fixture('blue'))
    second=service.analyze_frame(frame,'run-plan',actor=actor)['result']['analysis_run_id']
    assert first!=second
    assert client.get(f'/api/clinical/analyses/{first}/processed').content==before
    assert client.get(f'/api/clinical/frames/{frame}/processed').content!=before
    saved=client.post(f'/api/clinical/reports/{report}/versions',json={**payload,'expected_version':1})
    assert saved.status_code==200,saved.text
    records=client.get(f'/api/clinical/reports/{report}').json()['versions']
    assert all(record['payload']['images'][0]['analysis_run_id']==first for record in records)
    assert records[0]['payload']['images'][0]['analysis']['features']['Length_px']==0  # valid zero retained
    assert client.post(f'/api/clinical/reports/{report}/versions',json={**payload,'expected_version':2,'analysis_run_ids':{frame:second}}).status_code==200
    assert client.get(f'/api/clinical/reports/{report}').json()['versions'][0]['payload']['images'][0]['analysis_run_id']==second
    history=client.get(f'/api/clinical/frames/{frame}/analyses/history')
    assert history.status_code==200 and len(history.json())==2
    assert all('path' not in row['snapshot']['artifacts']['processed'] for row in history.json())
    with store.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM clinical_operations WHERE status='completed'").fetchone()[0]==2
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM analysis_runs WHERE id=?',(first,))
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE analysis_runs SET snapshot='{}' WHERE id=?",(first,))


def test_wrong_frame_and_tampered_artifact_are_not_served(client,make_image,monkeypatch):
    from backend.app.clinical import store,service,analysis_runs
    _,exam,frame=setup_frame(client,make_image)
    monkeypatch.setattr(service,'infer',lambda *args:infer_fixture('red'))
    run=service.analyze_frame(frame,'run-plan')['result']['analysis_run_id']
    other=service.save_frame(make_image(),exam,'network_demo',saved=True)
    response=client.post('/api/clinical/reports',json={'exam_id':exam,'frame_ids':[other],'include_ai':True,'analysis_run_ids':{other:run}})
    assert response.status_code==422
    with store.read_transaction() as db:path=analysis_runs.artifact(db,run,'processed')
    path.write_bytes(b'tampered fixture')
    assert client.get(f'/api/clinical/analyses/{run}/processed').status_code==409


def test_failed_publication_retains_original_and_journal_without_new_latest(client,make_image,monkeypatch):
    from backend.app.clinical import store,service
    _,_,frame=setup_frame(client,make_image)
    monkeypatch.setattr(service,'infer',lambda *args:infer_fixture('red'))
    first=service.analyze_frame(frame,'run-plan')['result']['analysis_run_id']
    original=client.get(f'/api/clinical/frames/{frame}/original').content
    monkeypatch.setattr(service,'infer',lambda *args:({'has_mask':True},{'mask':Image.new('L',(10,10)),'overlay':Image.new('RGB',(20,20))}))
    response=service.analyze_frame(frame,'run-plan')
    assert response['status']=='unavailable'
    assert client.get(f'/api/clinical/frames/{frame}/original').content==original
    with store.read_transaction() as db:
        assert db.execute('SELECT run_id FROM latest_analysis WHERE frame_id=?',(frame,)).fetchone()[0]==first
        assert db.execute("SELECT COUNT(*) FROM analysis_publications WHERE state='failed'").fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM analysis_runs').fetchone()[0]==1


def test_saved_preview_uses_its_actual_basic_input_and_versions(client,make_image):
    from backend.app.clinical import store,service
    actor,_,_=setup_frame(client,make_image)
    patient=client.post('/api/clinical/patients',json={'code':'PREVIEW','name':'Fixture'}).json()['id']
    exam=client.post('/api/clinical/exams',json={'kind':'patient','patient_id':patient,'title':'Preview','age':80}).json()['id']
    with store.read_transaction() as db:plan=store.rowdict(db.execute('SELECT * FROM plans WHERE id=?',('run-plan',)).fetchone())
    result,artifacts=infer_fixture('green')
    frame=service.save_frame(make_image(),exam,'capture',saved=True,analysis=result,artifacts=artifacts,plan=plan,basic={'age':45,'has_diabetes':1},actor=actor)
    history=client.get(f'/api/clinical/frames/{frame}/analyses/history').json()
    assert history[0]['snapshot']['basic_input']=={'age':45,'has_diabetes':1}
    assert history[0]['snapshot']['original']['sha256']==hashlib.sha256(make_image()).hexdigest()


def test_interrupted_publication_is_not_automatically_published(client,make_image):
    from backend.app.clinical import store,analysis_runs
    _,_,frame=setup_frame(client,make_image)
    with store.transaction() as db:db.execute('INSERT INTO analysis_publications VALUES(?,?,?,\'staging\',?,NULL,NULL)',('interrupted-publication',frame,'frames/fixture/analyses/interrupted',time.time()))
    analysis_runs.recover();analysis_runs.recover()
    with store.read_transaction() as db:
        assert db.execute('SELECT state FROM analysis_publications').fetchone()[0]=='interrupted'
        assert db.execute('SELECT COUNT(*) FROM analysis_runs').fetchone()[0]==0
