import csv
import io
import json

import pytest
from PIL import Image, ImageDraw


def dataset(client, with_masks=True):
    files = []
    for index, egfr in enumerate([10, 20, 40, 70, 95]):
        image = Image.new('RGB', (64, 64), (20, 30, 40))
        ImageDraw.Draw(image).ellipse((12, 12, 52, 52), fill=(100 + index * 20, 90, 80))
        buffer = io.BytesIO(); image.save(buffer, 'PNG')
        name = f'{egfr}_scan.png'
        files.append(('files', (name, buffer.getvalue(), 'image/png')))
        if with_masks:
            mask = Image.new('L', (64, 64)); ImageDraw.Draw(mask).ellipse((12, 12, 52, 52), fill=255)
            buffer = io.BytesIO(); mask.save(buffer, 'PNG')
            files.append(('masks', (name, buffer.getvalue(), 'image/png')))
    metadata = 'image_name,age,gender,has_diabetes\n' + ''.join(f'{e}_scan.png,60,0,0\n' for e in [10, 20, 40, 70, 95])
    files.append(('metadata', ('metadata.csv', metadata.encode(), 'text/csv')))
    response = client.post('/api/datasets', data={'name': 'Workflow fixture'}, files=files)
    assert response.status_code == 201, response.text
    return response.json()['id']


def source(kind, id):
    return {'images': {'kind': kind, 'id': id}}


@pytest.fixture
def no_worker(monkeypatch):
    monkeypatch.setattr('backend.app.api.routes.workflow.call_worker', lambda *args: None)


def run(job_id):
    from backend.app.api.worker_bridge import get_worker_manager
    from backend.app.workers.runner import run_persisted_job
    run_persisted_job(get_worker_manager(), job_id)


def test_dataset_snapshot_preserves_bytes_metadata_and_does_not_mutate_source(client, no_worker):
    from backend.app.core.config import get_settings
    from backend.app.db.session import get_session_factory
    from backend.app.services.workflow_service import resolve_source, SourceRef
    settings = get_settings()
    id = dataset(client)
    with get_session_factory()() as db:
        original = resolve_source(db, settings, SourceRef(kind='dataset', id=id))
    response = client.post('/api/jobs', json={'kind': 'process', 'input_sources': source('dataset', id), 'config': {'steps': ['convert']}})
    assert response.status_code == 202, response.text
    job_id = response.json()['id']
    manifest = json.loads((settings.jobs_dir / job_id / 'handoff.json').read_text(encoding='utf-8'))
    for before, after in zip(original['entries'], manifest['entries'], strict=True):
        assert before['sample_id'] == after['sample_id']
        assert (settings.data_dir / before['image']).read_bytes() == (settings.data_dir / after['image']).read_bytes()
        assert before['metadata'] == after['metadata']
        assert before['split'] == after['split']
    run(job_id)
    assert client.get(f'/api/jobs/{job_id}').json()['status'] == 'completed'
    summary = client.get('/api/workflow/source', params={'kind': 'job', 'id': job_id})
    assert summary.status_code == 200, summary.text
    assert summary.json()['image_count'] == 5
    assert summary.json()['mask_count'] == 0
    assert str(settings.data_dir) not in summary.text


def test_features_handoff_creates_independent_training_dataset(client, no_worker):
    from backend.app.core.config import get_settings
    from backend.app.db.session import get_session_factory
    from backend.app.db.models import DatasetSample
    from sqlalchemy import select
    id = dataset(client)
    response = client.post('/api/jobs', json={'kind': 'features', 'input_sources': source('dataset', id), 'config': {}})
    assert response.status_code == 202, response.text
    job_id = response.json()['id']; run(job_id)
    assert client.get(f'/api/jobs/{job_id}').json()['status'] == 'completed'
    summary = client.get('/api/workflow/source', params={'kind': 'job', 'id': job_id})
    assert summary.status_code == 200, summary.text
    assert summary.json()['has_features'] is True
    response = client.post('/api/datasets/from-results', json={'name': 'Derived', 'input_sources': source('job', job_id)})
    assert response.status_code == 201, response.text
    derived_id = response.json()['id']
    assert derived_id != id
    assert client.get('/api/workflow/source', params={'kind': 'dataset', 'id': derived_id}).json()['has_features'] is True
    with get_session_factory()() as db:
        old = {s.stored_name: s for s in db.scalars(select(DatasetSample).where(DatasetSample.dataset_id == id))}
        new = list(db.scalars(select(DatasetSample).where(DatasetSample.dataset_id == derived_id)))
        for row in new:
            previous = old[row.stored_name]
            assert (row.sha256, row.class_index, row.split, row.fold) == (previous.sha256, previous.class_index, previous.split, previous.fold)
            assert row.metadata_json['age'] == '60'
            assert float(row.metadata_json['Length_px']) > 0
            assert row.mask is not None
    assert client.delete(f'/api/jobs/{job_id}').status_code == 204
    assert client.get('/api/workflow/source', params={'kind': 'dataset', 'id': derived_id}).status_code == 200
    assert (get_settings().datasets_dir / derived_id / 'lineage.json').is_file()


def test_missing_masks_rejects_handoff_and_cleans_only_new_workspace(client, no_worker):
    from backend.app.core.config import get_settings
    id = dataset(client, with_masks=False)
    root = get_settings().jobs_dir
    before = set(root.iterdir())
    response = client.post('/api/jobs', json={'kind': 'features', 'input_sources': source('dataset', id), 'config': {}})
    assert response.status_code == 422, response.text
    assert set(root.iterdir()) == before
    assert client.get(f'/api/datasets/{id}').status_code == 200


def test_invalid_and_unfinished_sources_do_not_fallback(client, no_worker):
    id = dataset(client)
    assert client.get('/api/workflow/source', params={'kind': 'dataset', 'id': 'missing'}).status_code == 404
    assert client.get('/api/workflow/source', params={'kind': 'job', 'id': '../escape'}).status_code == 422
    queued = client.post('/api/jobs', json={'kind': 'process', 'input_sources': source('dataset', id), 'config': {'steps': ['convert']}}).json()['id']
    assert client.get('/api/workflow/source', params={'kind': 'job', 'id': queued}).status_code == 409
    response = client.post('/api/jobs', json={'kind': 'process', 'input_sources': source('dataset', id), 'config': {'input_paths': ['secret']}})
    assert response.status_code == 422


def test_mismatched_auxiliary_sample_ids_rejected(client, no_worker):
    first, second = dataset(client), dataset(client)
    sources = source('dataset', first); sources['masks'] = {'kind': 'dataset', 'id': second}
    response = client.post('/api/jobs', json={'kind': 'features', 'input_sources': sources, 'config': {}})
    assert response.status_code == 422, response.text


def test_copied_inputs_survive_upstream_job_deletion(client, no_worker):
    from backend.app.core.config import get_settings
    id = dataset(client)
    first = client.post('/api/jobs', json={'kind': 'process', 'input_sources': source('dataset', id), 'config': {'steps': ['convert']}}).json()['id']
    run(first)
    second = client.post('/api/jobs', json={'kind': 'process', 'input_sources': source('job', first), 'config': {'steps': ['convert']}})
    assert second.status_code == 202, second.text
    assert client.delete(f'/api/jobs/{first}').status_code == 204
    run(second.json()['id'])
    assert client.get(f"/api/jobs/{second.json()['id']}").json()['status'] == 'completed'


def test_real_masks_features_and_inference_match_original_executor(client, no_worker, tmp_path):
    """Synthetic weights only: verify handoff plumbing, never claim clinical accuracy."""
    import torch
    from scripts.e2e_verify import _upload_random_unet, AcceptanceReport
    from backend.app.core.config import get_settings
    from backend.app.db.session import get_session_factory
    from backend.app.services.workflow_service import resolve_source, SourceRef
    from backend.app.ml.models import build_classifier
    from backend.app.ml.contracts import CLASS_NAMES, METADATA_FIELDS
    from backend.app.ml.inference import run_batch_inference

    previous_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        id = dataset(client)
        unet = _upload_random_unet(client, AcceptanceReport())
        response = client.post('/api/jobs', json={
            'kind': 'masks', 'input_sources': source('dataset', id),
            'config': {'model_id': unet['id'], 'device': 'cpu', 'refine': False},
        })
        assert response.status_code == 202, response.text
        masks_id = response.json()['id']; run(masks_id)
        assert client.get(f'/api/jobs/{masks_id}').json()['status'] == 'completed'
        summary = client.get('/api/workflow/source', params={'kind': 'job', 'id': masks_id})
        assert summary.status_code == 200, summary.text
        assert summary.json()['mask_count'] == 5
        assert summary.json()['has_features'] is False
        response = client.post('/api/jobs', json={'kind': 'features', 'input_sources': source('job', masks_id), 'config': {}})
        assert response.status_code == 202, response.text
        features_id = response.json()['id']; run(features_id)
        summary = client.get('/api/workflow/source', params={'kind': 'job', 'id': features_id})
        assert summary.status_code == 200, summary.text
        assert summary.json()['has_features'] is True

        torch.manual_seed(1701)
        classifier = build_classifier('mlp-resnet18')
        weights = io.BytesIO(); torch.save(classifier.state_dict(), weights)
        manifest = {
            'name': 'Synthetic handoff verifier', 'version': 'test-only', 'task': 'classification',
            'architecture': 'mlp-resnet18', 'class_count': 5,
            'class_names': [CLASS_NAMES[i] for i in range(5)], 'metadata_columns': list(METADATA_FIELDS),
            'preprocessing': {'mode': 'RGB', 'size': [224, 224],
                              'mean': [0.485, 0.456, 0.406], 'std': [0.229, 0.224, 0.225]},
        }
        uploaded = client.post('/api/models', data={'manifest_json': json.dumps(manifest)},
                               files={'weights': ('synthetic.pth', weights.getvalue(), 'application/octet-stream')})
        assert uploaded.status_code == 201, uploaded.text
        model_id = uploaded.json()['id']
        response = client.post('/api/jobs', json={
            'kind': 'inference', 'input_sources': source('job', features_id),
            'config': {'model_id': model_id, 'device': 'cpu'},
        })
        assert response.status_code == 202, response.text
        job_id = response.json()['id']; run(job_id)
        completed = client.get(f'/api/jobs/{job_id}').json()
        assert completed['status'] == 'completed', completed
        settings = get_settings()
        with get_session_factory()() as db:
            original = resolve_source(db, settings, SourceRef(kind='job', id=features_id))
        config = completed['config_json']
        direct = run_batch_inference(
            [settings.data_dir / e['image'] for e in original['entries']],
            model_path=settings.models_dir / config['model_path'],
            output_dir=tmp_path / 'direct', architecture=config['architecture'],
            metadata_csv=settings.data_dir / config['metadata_csv'], device='cpu',
        ).to_dict()
        actual = completed['result_json']['items']
        assert len(actual) == len(direct['items']) == 5
        for left, right in zip(actual, direct['items'], strict=True):
            assert left['predicted_index'] == right['predicted_index']
            assert left['probabilities'] == right['probabilities']
        assert client.get(f'/api/jobs/{job_id}/download?format=csv').status_code == 200
        assert client.get(f'/api/jobs/{job_id}/download?format=zip').status_code == 200
    finally:
        torch.set_num_threads(previous_threads)
