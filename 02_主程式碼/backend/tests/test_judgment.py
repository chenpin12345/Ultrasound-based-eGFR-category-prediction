import json
from pathlib import Path

import pytest

from backend.app.core.errors import AppError
from backend.app.services.judgment_service import prepare_upload, validate_values


@pytest.mark.parametrize('row', [{}, {'age': '', 'has_diabetes': 0}, {'age': -1, 'has_diabetes': 0},
                                     {'age': 'nan', 'has_diabetes': 1}, {'age': 'inf', 'has_diabetes': 0},
                                     {'age': 50, 'has_diabetes': ''}, {'age': 50, 'has_diabetes': 2}])
def test_missing_or_invalid_basics_never_imputed(row):
    with pytest.raises(AppError):
        validate_values(row, 'image')


def test_upload_mapping_is_index_based_and_preserves_names(tmp_path):
    workspace = tmp_path / 'job'; workspace.mkdir()
    paths = ['job/input/000000-scan.jfif', 'job/input/000001-scan.jfif']
    config = {'analysis_mode': 'mlp', 'basic_metadata': [{'age': 42, 'has_diabetes': 0}, {'age': 70, 'has_diabetes': 1}]}
    prepare_upload(config, paths, ['scan.jfif', 'scan.jfif'], workspace, tmp_path)
    bundle = json.loads((workspace / 'handoff.json').read_text())
    assert [e['metadata']['age'] for e in bundle['entries']] == [42, 70]
    assert len({e['sample_id'] for e in bundle['entries']}) == 2
    assert [e['display_name'] for e in bundle['entries']] == ['scan.jfif'] * 2
    assert all(e['class_index'] is None for e in bundle['entries'])


def test_image_only_upload_needs_no_basics(tmp_path):
    workspace = tmp_path / 'job'; workspace.mkdir()
    config = {'analysis_mode': 'image_only'}
    prepare_upload(config, ['job/input/000000-10_scan.png'], ['10_scan.png'], workspace, tmp_path)
    bundle = json.loads((workspace / 'handoff.json').read_text())
    assert bundle['entries'][0]['metadata'] == {}
    assert bundle['entries'][0]['class_index'] is None


@pytest.fixture
def registered(client, monkeypatch):
    from backend.app.core.config import get_settings
    from backend.app.db.models import ModelRecord
    from backend.app.db.session import get_session_factory
    settings = get_settings()
    (settings.models_dir / 'metadata.json').write_text('{}')
    with get_session_factory()() as db:
        for mode, architecture in [('img', 'resnet18'), ('mlp', 'mlp-resnet18'), ('unet', 'unet')]:
            db.add(ModelRecord(id=mode, name=mode, task='segmentation' if mode == 'unet' else 'classification',
                               architecture=architecture, class_count=5, weights_path=f'{mode}.pth',
                               metadata_path='metadata.json', sha256=mode * 16, size_bytes=1, active=True))
        db.commit()
    monkeypatch.setattr('backend.app.api.routes.jobs.call_worker', lambda *a: None)
    monkeypatch.setattr('backend.app.api.routes.workflow.call_worker', lambda *a: None)


def test_onlyimg_does_not_require_unet(client, registered, make_image):
    from backend.app.db.session import get_session_factory
    from backend.app.db.models import ModelRecord
    with get_session_factory()() as db:
        db.delete(db.get(ModelRecord, 'unet')); db.commit()
    response = client.post('/api/jobs', data={'kind': 'quick_analysis', 'config': json.dumps({'analysis_mode': 'image_only', 'classifier_model_id': 'img'})}, files={'files': ('scan.png', make_image(), 'image/png')})
    assert response.status_code == 202, response.text
    assert 'unet_model_path' not in response.json()['config_json']


@pytest.mark.parametrize('mode,model,extra', [('mlp','img',{}), ('image_only','mlp',{}), ('mlp','mlp',{}), ('image_only','img',{'judgment_stage':'features'})])
def test_invalid_job_inputs_rejected(client, registered, make_image, mode, model, extra):
    response = client.post('/api/jobs', data={'kind': 'quick_analysis', 'config': json.dumps({'analysis_mode': mode, 'classifier_model_id': model, **extra})}, files={'files': ('scan.png', make_image(), 'image/png')})
    assert response.status_code == 422, response.text


def test_source_feature_versions_require_complete_artifacts(client, registered):
    from backend.tests.test_workflow_handoff import dataset, run, source
    from backend.app.core.config import get_settings
    did = dataset(client)
    first = client.post('/api/jobs', json={'kind': 'features', 'input_sources': source('dataset', did), 'config': {}}).json()['id']
    run(first)
    response = client.get('/api/workflow/inference-sources', params={'dataset_id': did})
    assert [v['id'] for v in response.json()['versions']] == [first]
    workspace = get_settings().jobs_dir / first
    bundle = json.loads((workspace/'handoff.json').read_text(encoding='utf-8'))
    # Delete only this test's copied mask; the original dataset is untouched.
    (get_settings().data_dir / bundle['entries'][0]['mask']).unlink()
    assert client.get('/api/workflow/inference-sources', params={'dataset_id': did}).json()['versions'] == []


def test_legacy_inference_csv_matches_original_upload_name(client, registered, make_image):
    from backend.app.core.config import get_settings
    from backend.app.services.workflow_service import read_rows
    response = client.post('/api/jobs', data={'kind':'inference', 'config':json.dumps({'model_id':'mlp'})}, files=[
        ('files',('掃描.jpg',make_image(),'image/jpeg')),
        ('feature_csv',('features.csv','image_name,age,has_diabetes,Length_px,Contrast_Ratio\n掃描.jpg,62,1,600,0.9\n'.encode('utf-8-sig'),'text/csv'))])
    assert response.status_code == 202, response.text
    config=response.json()['config_json']
    rows=read_rows(get_settings().data_dir/config['metadata_csv'])
    assert rows['000000-掃描.jpg']['age']=='62'
    assert rows['000000-掃描.jpg']['Length_px']=='600'


def test_legacy_inference_rejects_unpaired_csv(client, registered, make_image):
    response = client.post('/api/jobs', data={'kind':'inference', 'config':json.dumps({'model_id':'mlp'})}, files=[
        ('files',('scan.jpg',make_image(),'image/jpeg')),
        ('feature_csv',('features.csv',b'image_name,age,has_diabetes,Length_px,Contrast_Ratio\nother.jpg,62,1,600,0.9\n','text/csv'))])
    assert response.status_code == 422


@pytest.mark.parametrize('stage', ['raw','processed','masks','features'])
def test_source_stage_is_server_derived_and_basics_match_sample(tmp_path, stage):
    from types import SimpleNamespace
    from backend.app.services.judgment_service import prepare_source, write_rows
    workspace=tmp_path/'job'; workspace.mkdir()
    write_rows(workspace/'metadata.csv', [])
    config={'analysis_mode':'mlp','metadata_csv':'job/metadata.csv','basic_metadata':{'sample':{'age':58,'has_diabetes':1}}}
    bundle={'entries':[{'sample_id':'sample','display_name':'scan','image':'job/image.png','mask':'job/mask.png',
                        'metadata':{'age':1,'has_diabetes':0,'Length_px':600,'Contrast_Ratio':.9}}], 'has_features':stage=='features'}
    job=SimpleNamespace(kind={'raw':'dataset','processed':'process','masks':'masks','features':'features'}[stage])
    prepare_source(config,bundle,job,workspace,tmp_path)
    assert config['judgment_stage']==stage
    assert bundle['entries'][0]['metadata']['age']==58
    assert bundle['entries'][0]['metadata']['Length_px']==600


def test_corrupt_judgment_upload_is_rejected(client, registered):
    response=client.post('/api/jobs',data={'kind':'quick_analysis','config':json.dumps({'analysis_mode':'image_only','classifier_model_id':'img'})},files={'files':('scan.png',b'not an image','image/png')})
    assert response.status_code==422
