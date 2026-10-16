import hashlib
import json
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def setup_evaluation(client,make_image,monkeypatch):
    from backend.app.core.config import get_settings
    from backend.app.db.models import Dataset,DatasetSample,ModelRecord
    from backend.app.db.session import get_session_factory
    from backend.app.workers import evaluation_runner
    settings=get_settings()
    root=settings.data_dir/'datasets/cohort';root.mkdir(parents=True)
    folder=settings.models_dir/'binary';folder.mkdir()
    weights=b'fixture weights; prediction is separately stubbed in workflow tests'
    manifest={'name':'Binary','version':'1','task':'classification','architecture':'resnet18','class_count':2,
              'class_names':['eGFR < 60','eGFR ≥ 60'],'metadata_columns':[],'preprocessing':{}}
    (folder/'weights.pth').write_bytes(weights)
    (folder/'model_metadata.json').write_text(json.dumps(manifest),encoding='utf-8')
    with get_session_factory()() as db:
        db.add(Dataset(id='cohort',name='Known five-label cohort',root_path='datasets/cohort',sample_count=5));db.flush()
        for index in range(5):
            data=make_image((index,25,30),'PNG')
            (root/f'{index}.png').write_bytes(data)
            db.add(DatasetSample(id=f'sample-{index}',dataset_id='cohort',relative_path=f'{index}.png',
                                display_name=f'{index}.png',stored_name=f'{index}.png',sha256=hashlib.sha256(data).hexdigest(),
                                mime_type='image/png',size_bytes=len(data),width=32,height=24,class_index=index,split='test',metadata_json={}))
        db.add(ModelRecord(id='binary',**manifest,weights_path='binary/weights.pth',metadata_path='binary/model_metadata.json',
                           sha256=hashlib.sha256(weights).hexdigest(),size_bytes=len(weights)))
        db.commit()
    monkeypatch.setattr(evaluation_runner,'predict_one',lambda entry,*_: {'expected_index':entry['expected_index'],'predicted_index':entry['expected_index'],
                                                                         'probabilities':[1.0,0.0] if entry['expected_index']==0 else [0.0,1.0]})
    return {'model_id':'binary','dataset_id':'cohort','input_sources':{'images':{'kind':'dataset','id':'cohort'}},
            'split':'test','device':'cpu','source_evidence':'Isolated test fixture; no production images or clinical claim.'}


def submit(client,payload):
    checked=client.post('/api/evaluations/preflight',json=payload)
    assert checked.status_code==200,checked.text
    response=client.post('/api/evaluations',json={**payload,'expected_preflight_sha256':checked.json()['preflight_sha256']})
    assert response.status_code==201,response.text
    return response.json()['id']


def wait_done(client,identifier):
    for _ in range(150):
        result=client.get(f'/api/evaluations/{identifier}').json()
        if result['status'] not in {'queued','running'}:return result
        time.sleep(0.02)
    pytest.fail('Evaluation did not finish')


@pytest.mark.parametrize('started',[False,True])
def test_stop_preserves_partial_scope_and_retry_is_a_new_record(client,make_image,monkeypatch,started):
    from threading import Event
    from backend.app.api.worker_bridge import get_worker_manager
    from backend.app.workers import evaluation_runner
    payload=setup_evaluation(client,make_image,monkeypatch)
    manager=get_worker_manager();original_submit=manager.submit_job
    predict=evaluation_runner.predict_one
    entered,release=Event(),Event()
    def delayed(*args):
        entered.set()
        assert release.wait(10),'Test did not release in-flight prediction'
        return predict(*args)
    if started:monkeypatch.setattr(evaluation_runner,'predict_one',delayed)
    else:monkeypatch.setattr(manager,'submit_job',lambda *_:None)
    identifier=submit(client,payload)
    try:
        if started:assert entered.wait(5)
        response=client.post(f'/api/evaluations/{identifier}/stop')
        assert response.status_code==200,response.text
    finally:release.set()
    if not started:
        monkeypatch.setattr(manager,'submit_job',original_submit)
        original_submit(client.get(f'/api/evaluations/{identifier}').json()['job_id'])
    before=wait_done(client,identifier)
    assert before['status']=='stopped'
    assert before['completed_count']==(1 if started else 0)
    assert before['sample_count']==5 and before['result']['complete_cohort'] is False
    assert client.get(f'/api/evaluations/{identifier}/predictions').json()['total']==before['completed_count']
    assert client.post(f'/api/evaluations/{identifier}/stop').status_code==409
    monkeypatch.setattr(evaluation_runner,'predict_one',predict)
    retried=client.post(f'/api/evaluations/{identifier}/retry')
    assert retried.status_code==201,retried.text
    assert retried.json()['id']!=identifier and retried.json()['retry_of_id']==identifier
    assert wait_done(client,retried.json()['id'])['status']=='completed'
    assert client.get(f'/api/evaluations/{identifier}').json()==before


def test_restart_retains_evaluation_predictions_and_marks_interrupted(client,make_image,monkeypatch):
    from backend.app.api.worker_bridge import get_worker_manager
    from backend.app.workers.manager import WorkerManager
    from backend.app.db.models import EvaluationRecord,EvaluationPrediction,Job
    from backend.app.db.session import get_session_factory
    payload=setup_evaluation(client,make_image,monkeypatch)
    original=get_worker_manager()
    monkeypatch.setattr(original,'submit_job',lambda *_:None)
    identifier=submit(client,payload)
    with get_session_factory()() as db:
        record=db.get(EvaluationRecord,identifier)
        record.status='running';record.completed_count=1
        db.get(Job,record.job_id).status='running'
        db.add(EvaluationPrediction(evaluation_id=identifier,sample_id='sample-0',payload_json={'status':'completed','predicted_index':0,'probabilities':[1.,0.]}))
        db.commit()
    recovered=WorkerManager(session_factory=get_session_factory(),data_root=original.data_root,models_root=original.models_root,features_root=original.features_root)
    try:
        record=client.get(f'/api/evaluations/{identifier}').json()
        assert record['status']=='interrupted' and record['completed_count']==1
        assert record['result']['complete_cohort'] is False
        assert client.get(f'/api/evaluations/{identifier}/predictions').json()['total']==1
    finally:recovered.shutdown()


def test_explicit_evaluation_preserves_sources_and_exports_complete_contract(client,make_image,monkeypatch):
    payload=setup_evaluation(client,make_image,monkeypatch)
    assert client.get('/api/evaluations').json()['total']==0
    assert client.post('/api/evaluations',json=payload).status_code==409
    identifier=submit(client,payload)
    result=wait_done(client,identifier)
    assert result['status']=='completed',result
    assert result['result']['metrics']['accuracy']==1
    assert result['result']['metrics']['confusion_matrix']==[[3,0],[0,2]]
    assert result['completed_count']==result['sample_count']==5
    assert result['snapshot']['leakage']['training_overlap']=='unknown'
    predictions=client.get(f'/api/evaluations/{identifier}/predictions?limit=2&offset=2').json()
    assert predictions['total']==5 and len(predictions['items'])==2
    exported=client.get(f'/api/evaluations/{identifier}/export').json()
    assert exported['snapshot']['class_schema']['class_count']==2
    assert len(exported['predictions'])==5
    assert 'weight_sha256' in client.get(f'/api/evaluations/{identifier}/export?format=csv').text
    assert client.delete('/api/models/binary').status_code==409
    assert client.get(f'/api/evaluations/{identifier}/compare/{identifier}').json()['compatible'] is True
    summary=client.get('/api/models/binary').json()['evaluation_summary']
    assert summary['evaluation_id']==identifier and summary['metrics']['accuracy']==1
    assert summary['selection']=='latest_created_not_best' and summary['sample_count']==5
    assert summary['weight_sha256']==result['snapshot']['weight_sha256']
    assert summary['configuration_sha256']==result['snapshot']['configuration_sha256']
    assert summary['scope']==result['snapshot']['scope']
    assert client.get('/api/models').json()['items'][0]['evaluation_summary']==summary
    assert client.delete(f'/api/jobs/{result["job_id"]}').status_code==409


def test_partial_is_not_full_and_retry_creates_new_immutable_record(client,make_image,monkeypatch):
    payload=setup_evaluation(client,make_image,monkeypatch)
    from backend.app.workers import evaluation_runner
    original=evaluation_runner.predict_one
    def fail_one(entry,*args):
        if entry['sample_id']=='sample-2':raise ValueError('fixture failure')
        return original(entry,*args)
    monkeypatch.setattr(evaluation_runner,'predict_one',fail_one)
    identifier=submit(client,payload)
    result=wait_done(client,identifier)
    assert result['status']=='partial' and result['completed_count']==4
    assert result['result']['complete_cohort'] is False
    assert result['result']['errors'][0]['sample_id']=='sample-2'
    summary=client.get('/api/models/binary').json()['evaluation_summary']
    assert summary['status']=='partial' and summary['metrics']=={}
    assert summary['evaluated_sample_count']==4 and summary['reason']
    monkeypatch.setattr(evaluation_runner,'predict_one',original)
    retried=client.post(f'/api/evaluations/{identifier}/retry')
    assert retried.status_code==201,retried.text
    new=wait_done(client,retried.json()['id'])
    assert new['retry_of_id']==identifier and new['status']=='completed'
    assert client.get(f'/api/evaluations/{identifier}').json()==result
    assert client.get(f'/api/evaluations/{identifier}/compare/{new["id"]}').json()['compatible'] is False
    from backend.app.db.session import get_session_factory
    with get_session_factory()() as db:
        with pytest.raises(IntegrityError):db.execute(text('UPDATE evaluation_records SET status=\'running\' WHERE id=:id'),{'id':identifier})
        db.rollback()
        with pytest.raises(IntegrityError):db.execute(text('DELETE FROM evaluation_predictions WHERE evaluation_id=:id'),{'id':identifier})
        db.rollback()


def test_preflight_detects_changed_inputs_and_missing_independent_mask(client,make_image,monkeypatch):
    payload=setup_evaluation(client,make_image,monkeypatch)
    checked=client.post('/api/evaluations/preflight',json=payload).json()
    from backend.app.core.config import get_settings
    (get_settings().data_dir/'datasets/cohort/0.png').write_bytes(make_image((55,55,55),'PNG'))
    assert client.post('/api/evaluations',json={**payload,'expected_preflight_sha256':checked['preflight_sha256']}).status_code==409
    from backend.app.db.session import get_session_factory
    from backend.app.db.models import ModelRecord
    with get_session_factory()() as db:
        model=db.get(ModelRecord,'binary');model.task='segmentation';model.architecture='unet';model.class_names=['background','foreground'];db.commit()
    manifest=get_settings().models_dir/'binary/model_metadata.json'
    content=json.loads(manifest.read_text());content.update(task='segmentation',architecture='unet',class_names=['background','foreground'])
    manifest.write_text(json.dumps(content),encoding='utf-8')
    response=client.post('/api/evaluations/preflight',json=payload)
    assert response.status_code==422,response.text
    assert response.json()['error']['code']=='REFERENCE_MASK_UNVERIFIED'
