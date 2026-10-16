"""Independent before/after CPU run on all installed classifiers and real UNet.

Output is restricted evidence. No training, no new weights, no accuracy claim.
"""
from __future__ import annotations
import argparse
from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--all-samples',action='store_true',help='Use the single 975-image source dataset, not the five-image smoke set')
    parser.add_argument('--model-name',action='append',default=[],help='Exact classifier name; repeat for the three initial models')
    args = parser.parse_args()
    sys.path.insert(0, str(args.code.resolve()))
    import torch
    import numpy as np
    from PIL import Image
    from backend.app.ml.processing import run_processing_pipeline, list_images
    from backend.app.ml.segmentation import generate_masks
    from backend.app.ml.features import generate_feature_csv, read_csv_rows
    from backend.app.ml.inference import run_batch_inference, ModelCache
    import backend.app.ml.inference as implementation
    assert Path(implementation.__file__).resolve().is_relative_to(args.code.resolve())
    torch.set_num_threads(2)
    args.output.mkdir(parents=True, exist_ok=False)
    with closing(sqlite3.connect((args.data / 'isu_ai.sqlite3').resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        models = [dict(row) for row in db.execute('SELECT * FROM model_records ORDER BY name')]
        if args.all_samples:
            datasets=db.execute('SELECT dataset_id,COUNT(*) FROM dataset_samples GROUP BY dataset_id HAVING COUNT(*)=975').fetchall()
            assert len(datasets)==1,'Expected exactly one 975-image source dataset'
            samples=[dict(row) for row in db.execute('SELECT dataset_samples.*,datasets.root_path FROM dataset_samples JOIN datasets ON datasets.id=dataset_samples.dataset_id WHERE dataset_id=? ORDER BY dataset_samples.id',(datasets[0][0],))]
            assert [sum(sample['class_index']==i for sample in samples) for i in range(5)]==[142,229,232,242,130]
        else:
            samples = [dict(db.execute('SELECT dataset_samples.*, datasets.root_path FROM dataset_samples JOIN datasets ON datasets.id=dataset_samples.dataset_id WHERE class_index=? ORDER BY dataset_samples.id LIMIT 1', (i,)).fetchone()) for i in range(5)]
    if args.model_name:
        assert set(args.model_name)=={model['name'] for model in models if model['task']=='classification' and model['name'] in args.model_name},'Requested classifier not found'
    print(json.dumps({'phase':'start','samples':len(samples),'models':args.model_name or 'all','device':'cpu'}),flush=True)
    inputs = args.output / 'inputs'; inputs.mkdir()
    paths, basics, originals = [], {}, []
    for index, sample in enumerate(samples):
        source = args.data / sample['root_path'] / sample['relative_path']
        assert sha(source) == sample['sha256']
        target = inputs / (f'sample-{index}' + source.suffix)
        shutil.copy2(source, target); paths.append(target)
        metadata = json.loads(sample['metadata_json'])
        basics[target.stem] = {key: metadata[key] for key in ('age', 'has_diabetes')}
        originals.append({'class_index': sample['class_index'], 'sha256': sample['sha256'], 'dimensions': [sample['width'], sample['height']]})
    processed = run_processing_pipeline(paths, args.output / 'processing', ('convert', 'crop', 'rb'), seed=42)
    images = list_images(processed.output_dir)
    assert len(images) == len(samples)
    print(json.dumps({'phase':'preprocessing_complete','samples':len(images)}),flush=True)
    unet = next(row for row in models if row['name'] == 'unet_model')
    masks = generate_masks(images, source_root=processed.output_dir, output_root=args.output / 'masks', model_path=args.models / unet['weights_path'], device='cpu', refine=True)
    print(json.dumps({'phase':'masks_complete','samples':len(masks)}),flush=True)
    metadata_csv = args.output / 'basics.csv'
    with metadata_csv.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['image_name', 'age', 'has_diabetes']); writer.writeheader()
        writer.writerows({'image_name': p.name, **basics[p.stem]} for p in images)
    features = generate_feature_csv(images, args.output / 'features.csv', mask_dir=args.output / 'masks', metadata_csv=metadata_csv, diabetes_excel=None)
    assert not features.failed_features and not features.missing_masks
    evidence = {'originals': originals, 'processed': [sha(p) for p in images],
                'masks': [hashlib.sha256(np.array(Image.open(p)).tobytes()).hexdigest() for p in masks],
                'features': read_csv_rows(features.output_csv), 'classifiers': {}}
    cache = ModelCache(max_items=1)
    for model in models:
        if model['task'] != 'classification' or (args.model_name and model['name'] not in args.model_name):
            continue
        report = run_batch_inference(images, model_path=args.models / model['weights_path'],
            output_dir=args.output / 'inference' / model['id'], architecture=model['architecture'],
            metadata_csv=features.output_csv, device='cpu', cache=cache, include_images_in_zip=False)
        evidence['classifiers'][model['id']] = {'name': model['name'], 'classes': report.class_count,
            'weights_sha256': sha(args.models / model['weights_path']), 'manifest_sha256': sha(args.models / model['metadata_path']),
            'labels': [item.predicted_index for item in report.items], 'probabilities': [item.probabilities for item in report.items]}
        print(json.dumps({'phase':'classifier_complete','model':model['name'],'samples':len(report.items)}),flush=True)
    cache.clear()
    summary = {'classifiers': len(evidence['classifiers']), 'samples_per_classifier': len(samples), 'unet_masks': len(masks), 'device': 'cpu'}
    if args.compare:
        before = json.loads(args.compare.read_text(encoding='utf-8'))
        for key in ('originals', 'processed', 'masks'):
            assert evidence[key] == before[key], key
        for left, right in zip(evidence['features'], before['features'], strict=True):
            assert left.keys() == right.keys()
            for key in left:
                if key == 'image_name' or left[key] == '' or right[key] == '':
                    assert left[key] == right[key]
                else:
                    np.testing.assert_allclose(float(left[key]), float(right[key]), atol=1e-6, rtol=1e-6)
        assert evidence['classifiers'].keys() == before['classifiers'].keys()
        max_diff = 0.0
        for key, left in evidence['classifiers'].items():
            right = before['classifiers'][key]
            for field in ('name', 'classes', 'weights_sha256', 'manifest_sha256', 'labels'):
                assert left[field] == right[field]
            np.testing.assert_allclose(left['probabilities'], right['probabilities'], atol=1e-6, rtol=1e-6)
            max_diff = max(max_diff, float(np.max(np.abs(np.array(left['probabilities']) - right['probabilities']))))
        summary.update(passed=True, labels_identical=True, masks_pixel_identical=True, max_probability_difference=max_diff)
    (args.output / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
