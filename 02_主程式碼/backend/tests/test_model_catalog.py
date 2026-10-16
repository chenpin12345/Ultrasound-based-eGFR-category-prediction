import hashlib
import json


def seed_models(count):
    from backend.app.db.models import ModelRecord
    from backend.app.db.session import get_session_factory
    from backend.app.core.config import get_settings
    with get_session_factory()() as db:
        for index in range(count):
            identifier=f'catalog-{index:04}'
            manifest={'name': f'Model {index:04}', 'version': '1', 'task': 'classification',
                      'architecture': 'resnet18', 'class_count': 2, 'class_names': ['eGFR < 60','eGFR ≥ 60'],
                      'metadata_columns': [], 'preprocessing': {}}
            folder=get_settings().models_dir/identifier
            folder.mkdir()
            (folder/'model_metadata.json').write_text(json.dumps(manifest),encoding='utf-8')
            digest=hashlib.sha256(identifier.encode()).hexdigest()
            db.add(ModelRecord(id=identifier,**manifest,weights_path=f'{identifier}/weights.pth',
                               metadata_path=f'{identifier}/model_metadata.json',sha256=digest,size_bytes=1))
        db.commit()


def test_catalog_pagination_exact_total_filters_and_deep_link(client):
    seed_models(237)
    found=[]
    for offset in range(0,237,50):
        response=client.get('/api/models',params={'limit':50,'offset':offset,'sort':'name'})
        assert response.status_code==200,response.text
        page=response.json()
        assert page['total']==237
        found.extend(model['id'] for model in page['items'])
    assert len(found)==len(set(found))==237
    filtered=client.get('/api/models?search=0236&class_count=2&source=external&architecture=resnet18').json()
    assert filtered['total']==1
    assert client.get('/api/models?search=%25').json()['total']==0
    detail=client.get('/api/models/catalog-0236').json()
    assert detail['configuration']['status']=='consistent'
    assert detail['class_schema']['class_names']==['eGFR < 60','eGFR ≥ 60']
    assert detail['source_info']['status']=='unverified'
    assert 'best_metric' not in detail
    assert 'weights_path' not in detail
    assert detail['evaluation_summary']['status']=='not_evaluated'
    assert detail['evaluation_summary']['metrics']=={}


def test_catalog_does_not_fabricate_missing_model_configuration(client):
    from backend.app.core.config import get_settings
    seed_models(1)
    manifest=get_settings().models_dir/'catalog-0000/model_metadata.json'
    content=json.loads(manifest.read_text())
    content['class_names'].reverse()
    manifest.write_text(json.dumps(content),encoding='utf-8')
    detail=client.get('/api/models/catalog-0000').json()
    assert detail['configuration']['status']=='unverified'
    assert detail['configuration']['train_stats'] is None
    assert detail['configuration']['sha256'] is None


def test_sealed_plan_blocks_model_deletion_by_hash_without_rewriting_history(client):
    from backend.app.clinical import store
    seed_models(1)
    model=client.get('/api/models/catalog-0000').json()
    snapshot={'models':{'classifier':{'sha256':model['sha256']}}}
    with store.transaction() as db:
        db.execute('INSERT INTO plans VALUES(?,?,?,?,?)',('sealed','歷史方案','{}',store.dumps(snapshot),1))
    response=client.delete('/api/models/catalog-0000')
    assert response.status_code==409,response.text
    assert response.json()['error']['details']['references'][0]['id']=='sealed'
    assert client.get('/api/models/catalog-0000').status_code==200
    with store.transaction() as db:
        assert json.loads(db.execute('SELECT snapshot FROM plans WHERE id=?',('sealed',)).fetchone()[0])==snapshot


def test_job_references_do_not_hydrate_result_blobs(client):
    from backend.app.db.models import Job
    from backend.app.db.session import get_session_factory,get_engine
    from sqlalchemy import event
    seed_models(1)
    with get_session_factory()() as db:
        db.add(Job(id='large-result',kind='inference',status='completed',workspace_path='jobs/large-result',
                   config_json={'model_id':'catalog-0000'},result_json={'large_blob':'x'*100000}))
        db.commit()
    statements=[]
    def capture(_connection,_cursor,statement,_parameters,_context,_many):statements.append(statement)
    event.listen(get_engine(),'before_cursor_execute',capture)
    try:
        result=client.get('/api/models/catalog-0000').json()
        assert any(item['id']=='large-result' for item in result['references'])
        assert not any('jobs.result_json' in statement for statement in statements)
    finally:event.remove(get_engine(),'before_cursor_execute',capture)
