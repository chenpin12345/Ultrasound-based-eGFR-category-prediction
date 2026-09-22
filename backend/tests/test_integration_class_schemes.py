"""Inference-only regression tests; no training or source weights are changed."""
import csv
import json

import pytest
import torch
from PIL import Image

from backend.app.ml.contracts import ModelMetadata, classification_labels, remap_five_class
from backend.app.ml.inference import ModelCache, run_batch_inference


@pytest.mark.parametrize('count,expected', [(2,[0,0,0,1,1]),(3,[0,0,1,2,2]),(5,[0,1,2,3,4])])
def test_schemes_round_trip_and_original_labels(count, expected):
    meta = ModelMetadata(architecture='resnet18', class_count=count)
    restored = ModelMetadata.from_dict(meta.to_dict())
    assert restored.class_names == classification_labels(count)
    assert [remap_five_class(i,count) for i in range(5)] == expected
    assert restored.class_count == count


@pytest.mark.parametrize('count,logits,prediction', [(2,[0.0],0),(2,[0.01],1),(2,[-0.01],0),(3,[0.,0.,1.],2),(5,[0.,1.,0.,0.,0.],1)])
def test_inference_boundary_labels_and_csv(tmp_path, count, logits, prediction):
    weights = tmp_path / 'fixture.pth'
    metadata = ModelMetadata(architecture='resnet18', class_count=count)
    (tmp_path / 'model_metadata.json').write_text(json.dumps(metadata.to_dict()), encoding='utf-8')
    img = tmp_path / 'input.png'
    Image.new('RGB',(19,27)).save(img)
    class FixedModel:
        def __call__(self, _image):
            return torch.tensor(logits) if count == 2 else torch.tensor([logits])
    class FixedCache:
        def get(self, *_): return FixedModel()
    report = run_batch_inference([img], model_path=weights, output_dir=tmp_path/'out', device='cpu', cache=FixedCache())
    assert report.items[0].predicted_index == prediction
    assert report.items[0].predicted_class == classification_labels(count)[prediction]
    assert len(report.items[0].probabilities) == count
    assert sum(report.items[0].probabilities) == pytest.approx(1)
    if logits == [0.0]: assert report.items[0].probabilities == [.5,.5]
    with report.csv_path.open(encoding='utf-8-sig') as handle:
        row = next(csv.DictReader(handle))
    assert row['class_count'] == str(count)
    assert len([k for k in row if k.startswith('probability_')]) == count


def test_cache_separates_class_heads_and_weights(tmp_path, monkeypatch):
    import backend.app.ml.inference as inference
    first, second = tmp_path/'a.pth', tmp_path/'b.pth'
    first.write_bytes(b'a'); second.write_bytes(b'b')
    monkeypatch.setattr(inference, 'load_classifier', lambda *a, **kw: object())
    cache = ModelCache(10)
    two = ModelMetadata(architecture='resnet18', class_count=2)
    three = ModelMetadata(architecture='resnet18', class_count=3)
    value = cache.get(first,two,'cpu')
    assert cache.get(first,two,'cpu') is value
    assert cache.get(first,three,'cpu') is not value
    assert cache.get(second,two,'cpu') is not value


def test_distinct_training_statistics_preserved():
    left = ModelMetadata(architecture='mlp-resnet18').to_dict()
    right = json.loads(json.dumps(left))
    right['train_stats']['age']['mean'] += 5
    assert ModelMetadata.from_dict(left).train_stats != ModelMetadata.from_dict(right).train_stats


def test_unsupported_head_rejected():
    with pytest.raises(ValueError): ModelMetadata(architecture='resnet18',class_count=4)


def test_missing_gallery_dataset_is_not_exposed(client):
    assert client.get('/api/datasets/unknown/gallery-results?sample_ids=unknown').status_code == 404


@pytest.mark.parametrize('count', [2,3,5])
def test_display_confusion_matrix_maps_without_overwriting_labels(count):
    from backend.app.api.routes.jobs import _inference_evaluation
    entries={str(i):{'class_index':i} for i in range(5)}
    result={'class_count':count,'items':[{'file':str(i),'predicted_index':remap_five_class(i,count),'probabilities':[.2]*count} for i in range(5)]}
    evaluation=_inference_evaluation(result,entries,'dataset')
    assert len(evaluation['confusion_matrix'])==count
    assert sum(evaluation['confusion_matrix'][i][i] for i in range(count))==5
    assert [entries[str(i)]['class_index'] for i in range(5)]==list(range(5))
    assert all(item['probabilities']==[.2]*count for item in result['items'])
