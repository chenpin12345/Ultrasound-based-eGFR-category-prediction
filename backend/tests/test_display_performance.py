import json
from pathlib import Path
import pytest

def test_summary_does_not_decode_images_but_execution_still_rejects_corruption(client, monkeypatch):
    from backend.tests.test_workflow_handoff import dataset
    from backend.app.core.config import get_settings
    from backend.app.services import workflow_service
    from backend.app.db.models import Dataset, DatasetSample
    from backend.app.db.session import get_session_factory
    from sqlalchemy import select
    did=dataset(client)
    original=workflow_service.validate_image
    calls=[]
    def checked(*args, **kwargs):
        calls.append(args[0]); return original(*args, **kwargs)
    monkeypatch.setattr(workflow_service, 'validate_image', checked)
    response=client.get('/api/workflow/source',params={'kind':'dataset','id':did})
    assert response.status_code==200 and response.json()['image_count']==5
    assert calls==[]
    with get_session_factory()() as db:
        ds=db.get(Dataset,did); sample=db.scalar(select(DatasetSample).where(DatasetSample.dataset_id==did))
        image=get_settings().data_dir/ds.root_path/sample.relative_path
    image.write_bytes(b'corrupt test fixture')
    response=client.post('/api/jobs',json={'kind':'process','input_sources':{'images':{'kind':'dataset','id':did}},'config':{'steps':['convert']}})
    assert response.status_code in (400,422), response.text
    assert calls

@pytest.mark.parametrize('kind', ['inference','quick_analysis'])
def test_paginated_results_and_summary_preserve_full_contract(client, kind):
    from backend.app.core.config import get_settings
    from backend.app.db.models import Job
    from backend.app.db.session import get_session_factory
    items=[{'file':f'{i:03}.png','predicted_index':i%2,'predicted_class':['<60','>=60'][i%2],'confidence':.75,'probabilities':[.75,.25] if i%2==0 else [.25,.75]} for i in range(125)]
    result={'class_count':2,'class_names':['<60','>=60'],'items':items,'summary':{'counts':{'<60':63,'>=60':62}}}
    if kind=='quick_analysis': result={'analysis_mode':'image_only','inference':result}
    workspace=get_settings().jobs_dir/'large'; workspace.mkdir()
    with get_session_factory()() as db:
        db.add(Job(id='large',kind=kind,status='completed',workspace_path='jobs/large',config_json={'name':'large','input_paths':['large']*125},result_json=result)); db.commit()
    full=client.get('/api/jobs/large/results').json()['results']
    joined=[]
    for offset in (0,60,120):
        page=client.get('/api/jobs/large/results',params={'offset':offset,'limit':60}).json()['results']
        target=page['inference'] if kind=='quick_analysis' else page
        assert target['total']==125
        assert target['summary']['counts']=={'<60':63,'>=60':62}
        joined.extend(target['items'])
    assert joined==(full['inference'] if kind=='quick_analysis' else full)['items']
    summary=client.get('/api/jobs?view=summary').json()['items'][0]
    assert summary['name']=='large' and summary['result_count']==125
    assert 'result_json' not in summary and 'config_json' not in summary
    assert client.get('/api/jobs').json()['items'][0]['result_json']==result
    assert client.get('/api/jobs/large?view=summary').json()['result_json'] is None

def test_display_json_invalidates_and_never_shares_mutable_entries(tmp_path):
    from backend.app.services.display_cache import display_json
    file=tmp_path/'manifest.json'; file.write_text('{"entries":[1]}')
    first=display_json(file); first['entries'].clear()
    assert display_json(file)['entries']==[1]
    file.write_text('{"entries":[2,3]}')
    assert display_json(file)['entries']==[2,3]
    file.unlink()
    with pytest.raises(FileNotFoundError): display_json(file)

def test_dashboard_counts_are_global(client):
    from backend.tests.test_workflow_handoff import dataset
    dataset(client)
    summary=client.get('/api/workflow/dashboard-summary').json()
    assert summary['datasets']==1 and summary['models']==0 and summary['active_jobs']==0

def test_display_revision_and_count_include_training_without_double_count(client):
    from backend.tests.test_workflow_handoff import dataset
    from backend.app.db.models import Job, TrainingJob
    from backend.app.db.session import get_session_factory
    from backend.app.api.routes.workflow import _display_revision
    did=dataset(client)
    before=_display_revision()
    with get_session_factory()() as db:
        db.add(Job(id='train-display',kind='training',status='running',workspace_path='jobs/train-display'))
        db.flush()
        db.add(TrainingJob(id='train-detail',job_id='train-display',dataset_id=did,model_name='display',architecture='resnet18',status='running'))
        db.commit()
    assert client.get('/api/workflow/dashboard-summary').json()['active_jobs']==1
    assert _display_revision()!=before
