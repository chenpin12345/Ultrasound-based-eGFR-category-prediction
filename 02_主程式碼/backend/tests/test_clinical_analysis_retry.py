import time


def test_retry_uses_new_operation_link_without_overwriting_failure(client,make_image,monkeypatch):
    from backend.app.clinical import store,service
    actor=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        exam=service.new_exam(db,'demo',None,'Retry fixture','left',{})
        db.execute("INSERT INTO plans VALUES('retry-plan','Immutable fixture plan','{}','{}',?)",(time.time(),))
    frame=service.save_frame(make_image(),exam,'network_demo',saved=True)
    def failed(*args):raise RuntimeError('fixture')
    monkeypatch.setattr(service,'infer',failed)
    original=service.analyze_frame(frame,'retry-plan',actor=actor)
    assert original['status']=='failed'
    monkeypatch.setattr(service,'infer',lambda *args:({'predicted_class':'fixture','has_mask':False},{}))
    response=client.post(f'/api/clinical/monitor/operations/{original["operation_id"]}/retry',json={})
    assert response.status_code==200 and response.json()['status']=='completed'
    retried=response.json()['operation_id'];assert retried!=original['operation_id']
    with store.read_transaction() as db:
        assert db.execute('SELECT status FROM clinical_operations WHERE id=?',(original['operation_id'],)).fetchone()[0]=='failed'
        assert db.execute('SELECT retry_of FROM clinical_operations WHERE id=?',(retried,)).fetchone()[0]==original['operation_id']
        assert db.execute('SELECT COUNT(*) FROM analysis_runs WHERE operation_id=?',(retried,)).fetchone()[0]==1
    assert client.post(f'/api/clinical/monitor/operations/{retried}/retry',json={}).status_code==409
