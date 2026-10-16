from concurrent.futures import ThreadPoolExecutor
import threading


def test_model_delete_and_reference_mutations_serialize_without_blocking_reads_or_capture_release(client):
    entered=threading.Event();release=threading.Event();second_entered=threading.Event()
    @client.app.post('/api/models/coordination-fixture')
    def first():
        entered.set()
        if not release.wait(5):raise RuntimeError('test release timeout')
        return {'ok':True}
    @client.app.post('/api/clinical/plans/coordination-fixture')
    def second():
        second_entered.set();return {'ok':True}
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_request=executor.submit(client.post,'/api/models/coordination-fixture',json={})
        try:
            assert entered.wait(3)
            second_request=executor.submit(client.post,'/api/clinical/plans/coordination-fixture',json={})
            assert client.get('/api/models').status_code==200
            assert client.post('/api/clinical/preview/release?operation_id='+'a'*32,json={}).status_code==200
            assert not second_entered.wait(.15)
        finally:release.set()
        assert first_request.result(5).status_code==200
        assert second_request.result(5).status_code==200 and second_entered.is_set()


def test_gate_includes_all_reference_writers_but_not_clinical_analysis():
    from backend.app.core.model_coordination import coordinates
    for path in ('/api/models/m','/api/jobs','/api/jobs/j/inference','/api/workflow/run','/api/evaluations','/api/datasets/from-results','/api/clinical/plans'):
        assert coordinates('POST',path)
        assert not coordinates('GET',path)
    assert not coordinates('POST','/api/clinical/preview')
    assert not coordinates('POST','/api/clinical/preview/release')
