import sqlite3
import time
from contextlib import closing

import pytest
from PIL import Image


def test_restore_preserves_analysis_pdf_tombstone_and_cleanup_evidence(client,make_image,tmp_path,monkeypatch):
    from backend.app.core.config import AppSettings,get_settings
    from backend.app.clinical import store,service,temporary_cleanup
    from scripts import workspace_backup as backup
    settings=get_settings()
    monkeypatch.setattr(settings,'reports_dir',tmp_path/'separate-reports')
    monkeypatch.setattr(backup,'offline',lambda settings:None)  # Only the in-process test fixture exists.
    actor=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        exam=service.new_exam(db,'demo',None,'Restore fixture','left',{})
        db.execute("INSERT INTO plans VALUES('restore-plan','Synthetic only','{}','{}',1)")
    frame=service.save_frame(make_image(),exam,'network_demo',saved=True)
    monkeypatch.setattr(service,'infer',lambda *args:({'predicted_class':'fixture','has_mask':False},{'processed':Image.new('RGB',(32,24),'red')}))
    run=service.analyze_frame(frame,'restore-plan',actor=actor)['result']['analysis_run_id']
    report=client.post('/api/clinical/reports',json={'exam_id':exam,'frame_ids':[frame],'include_ai':True}).json()['id']
    generated=client.post(f'/api/clinical/reports/{report}/versions/1/pdf').json()
    assert client.request('DELETE',generated['url'],json={'expected_sha256':generated['sha256'],'reason':'restore fixture'}).status_code==200
    with store.transaction() as db:
        sid=store.uid();db.execute('INSERT INTO demo_sessions(id,owner,plan_id,state,created,expires) VALUES(?,?,NULL,?,?,?)',(sid,actor,'ended',1,time.time()+60))
        temp_exam=service.new_exam(db,'demo',None,'Cleanup fixture','left',{},sid)
    temp_frame=service.save_frame(make_image(),temp_exam,'network_demo')
    temporary_cleanup.cleanup_session(sid)
    with store.transaction() as db:
        db.execute('''INSERT INTO preview_operations
            (id,operation_key,exam_id,plan_id,actor,basic_input,source_sha256,status,created,completed,error_code,error_message)
            VALUES('restore-preview','restore-operation',?,'restore-plan',?,'{}',?,'cancelled',1,2,'CAPTURE_ENDED','Cancelled fixture')''',
            (exam,actor,'a'*64))
    destination=tmp_path/'new-history-backup'
    backup.backup(destination,settings,'clinical')
    target=tmp_path/'restored'
    restored=AppSettings(_env_file=None,data_dir=target/'research',models_dir=target/'models',clinical_dir=target/'clinical',
                         reports_dir=target/'reports',runtime_dir=target/'runtime',reference_features_dir=target/'features')
    backup.restore(destination,restored)
    with closing(sqlite3.connect(restored.clinical_dir/'clinical.sqlite3')) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT status FROM pdf_artifacts WHERE id=?',(generated['id'],)).fetchone()[0]=='deleted'
        assert db.execute('SELECT frame_id FROM analysis_runs WHERE id=?',(run,)).fetchone()[0]==frame
        assert db.execute('SELECT status FROM temporary_cleanup WHERE frame_id=?',(temp_frame,)).fetchone()[0]=='completed'
        assert db.execute('SELECT 1 FROM frames WHERE id=?',(temp_frame,)).fetchone() is None
        assert db.execute("SELECT status,source_sha256 FROM preview_operations WHERE id='restore-preview'").fetchone()==('cancelled','a'*64)
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE preview_operations SET status='completed' WHERE id='restore-preview'")
        with pytest.raises(sqlite3.IntegrityError):db.execute("DELETE FROM preview_operations WHERE id='restore-preview'")
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE analysis_runs SET evidence='legacy_unverified' WHERE id=?",(run,))
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE pdf_artifacts SET status='ready' WHERE id=?",(generated['id'],))
    for key in ('clinical','reports'):
        for path in backup.entries(destination/key):
            restored_path=backup.roots(restored)[key]/path.relative_to(destination/key)
            assert backup.sha(path)==backup.sha(restored_path)
    assert not list(restored.reports_dir.rglob('*.pdf'))


def test_restore_staging_supports_windows_long_paths(tmp_path,monkeypatch):
    from scripts import workspace_backup as backup
    from backend.app.core.config import AppSettings
    monkeypatch.setattr(backup,'offline',lambda settings:None)
    source=tmp_path/'source'
    settings=AppSettings(_env_file=None,data_dir=source/'research',models_dir=source/'models',clinical_dir=source/'clinical',
                         reports_dir=source/'reports',runtime_dir=source/'runtime',reference_features_dir=source/'features')
    settings.clinical_dir.mkdir(parents=True);settings.reports_dir.mkdir()
    with closing(sqlite3.connect(settings.clinical_dir/'clinical.sqlite3')) as db:db.execute('CREATE TABLE sample(id INTEGER)')
    artifact=settings.reports_dir/'nested'/'immutable.bin';artifact.parent.mkdir();artifact.write_bytes(b'long path fixture')
    destination=tmp_path/'backup';backup.backup(destination,settings,'clinical')
    target=tmp_path/('long-root-'+'x'*100)/('nested-'+'y'*60)
    restored=AppSettings(_env_file=None,data_dir=target/'research',models_dir=target/'models',clinical_dir=target/'clinical',
                         reports_dir=target/'reports',runtime_dir=tmp_path/'short-runtime',reference_features_dir=target/'features')
    backup.restore(destination,restored)
    assert backup.sha(restored.reports_dir/'nested/immutable.bin')==backup.sha(artifact)
