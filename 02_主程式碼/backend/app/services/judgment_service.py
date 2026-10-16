"""Managed AI judgment orchestration; numerical implementations remain unchanged."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from ..core.errors import AppError
from ..core.security import safe_resolve, relative_path, sha256_file
from .workflow_service import read_rows


def validate_values(row, name, *, features=False):
    fields = ('age', 'has_diabetes', 'Length_px', 'Contrast_Ratio') if features else ('age', 'has_diabetes')
    for field in fields:
        try:
            value = float(row[field])
            valid = math.isfinite(value) and (value in (0, 1) if field == 'has_diabetes' else value >= 0)
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise AppError(422, 'JUDGMENT_METADATA_REQUIRED', f'{name}：請提供有效的 {field}，不會自動補值。')


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ['image_name'] + sorted({k for row in rows for k in row if k != 'image_name'})
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def prepare_upload(config, paths, names, workspace, data_root):
    """Pair metadata by upload index, never by potentially duplicate client filename."""
    basic = config.pop('basic_metadata', [])
    mlp = config['analysis_mode'] == 'mlp'
    if mlp and (not isinstance(basic, list) or len(basic) != len(paths)):
        raise AppError(422, 'JUDGMENT_METADATA_REQUIRED', '每張圖片都需要年齡與糖尿病狀態。')
    entries = []
    for index, (path, name) in enumerate(zip(paths, names, strict=True)):
        row = basic[index] if mlp and isinstance(basic[index], dict) else {}
        row = {k: row.get(k) for k in ('age', 'has_diabetes')} if mlp else {}
        if mlp:
            validate_values(row, name)
        entries.append({'sample_id': f'{workspace.name}:{index}', 'image': path, 'display_name': name,
                        'metadata': row, 'mask': None, 'class_index': None})
    bundle = {'dataset_id': None, 'entries': entries, 'has_features': False}
    (workspace / 'handoff.json').write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
    metadata = workspace / 'input' / 'metadata.csv'
    write_rows(metadata, [{**e['metadata'], 'image_name': Path(e['image']).name} for e in entries])
    config.update(metadata_csv=relative_path(metadata, data_root), judgment_stage='raw')


def prepare_source(config, bundle, source_job, workspace, data_root):
    # Stage comes from a validated server source, never from a client claim.
    if bundle.get('has_features'):
        stage = 'features'
    elif source_job and source_job.kind == 'masks':
        stage = 'masks'
    elif source_job and source_job.kind == 'process':
        stage = 'processed'
    else:
        stage = 'raw'
    overrides = config.pop('basic_metadata', None)
    if overrides is not None:
        if not isinstance(overrides, dict) or set(overrides) != {e['sample_id'] for e in bundle['entries']}:
            raise AppError(422, 'JUDGMENT_METADATA_REQUIRED', '基本資料必須對應全部來源樣本。')
        for entry in bundle['entries']:
            row = overrides[entry['sample_id']]
            if not isinstance(row, dict):
                raise AppError(422, 'JUDGMENT_METADATA_REQUIRED', '基本資料格式錯誤。')
            entry['metadata'].update({k: row.get(k) for k in ('age', 'has_diabetes')})
    if config['analysis_mode'] == 'mlp':
        for entry in bundle['entries']:
            validate_values(entry['metadata'], entry['display_name'], features=stage == 'features')
        if stage == 'masks' and any(not e.get('mask') for e in bundle['entries']):
            raise AppError(422, 'MISSING_MASK', '來源工作缺少配對遮罩。')
    metadata = safe_resolve(data_root, config['metadata_csv'])
    write_rows(metadata, [{**e['metadata'], 'image_name': Path(e['image']).name} for e in bundle['entries']])
    (workspace / 'handoff.json').write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
    config['judgment_stage'] = stage


def prepare_inference_upload(config, paths, original_names, workspace, data_root):
    """Bind legacy uploaded CSV rows to managed names without altering feature values."""
    mlp = 'mlp' in config.get('architecture', '').lower()
    rows = read_rows(safe_resolve(data_root, config['metadata_csv'])) if config.get('metadata_csv') else {}
    counts = {name: original_names.count(name) for name in original_names}
    entries = []
    for index, (path, name) in enumerate(zip(paths, original_names, strict=True)):
        stored = Path(path).name
        row = rows.get(stored)
        if row is None and counts[name] == 1:
            row = rows.get(name)
        row = dict(row or {})
        if mlp:
            validate_values(row, name, features=True)
        entries.append({'sample_id': f'{workspace.name}:{index}', 'image': path, 'display_name': name,
                        'metadata': row, 'mask': None, 'class_index': None})
    if rows:
        mapped = workspace / 'input' / 'mapped-features.csv'
        write_rows(mapped, [{**e['metadata'], 'image_name': Path(e['image']).name} for e in entries])
        config['metadata_csv'] = relative_path(mapped, data_root)
        config['feature_csv'] = config['metadata_csv']
    (workspace / 'handoff.json').write_text(json.dumps({'dataset_id': None, 'entries': entries,
                                                      'has_features': mlp}, ensure_ascii=False), encoding='utf-8')


def run_judgment(image_paths, *, workspace, data_root, models_root, config, progress=None):
    from ..ml.processing import copy_inputs, list_images, run_processing_pipeline
    from ..ml.segmentation import generate_masks
    from ..ml.features import generate_feature_csv, index_masks
    from ..ml.inference import run_batch_inference
    from .analysis_service import _phase
    from .artifact_service import create_result_archive

    workspace, data_root, models_root = map(Path, (workspace, data_root, models_root))
    bundle = json.loads((workspace / 'handoff.json').read_text(encoding='utf-8'))
    mlp = config['analysis_mode'] == 'mlp'
    stage = config['judgment_stage']
    classifier = safe_resolve(models_root, config['classifier_model_path'])
    if sha256_file(classifier) != config['selected_model']['sha256']:
        raise ValueError('分類權重與建立工作時不同，已停止。')
    manifest = json.loads((classifier.parent / 'model_metadata.json').read_text(encoding='utf-8-sig'))
    if manifest != config['selected_model']['manifest']:
        raise ValueError('模型配套設定已變更，已停止。')
    if stage == 'raw':
        processed = run_processing_pipeline(image_paths, workspace / 'processing', ('convert', 'crop', 'rb'),
                                            seed=int(config.get('random_seed', 42)), progress=_phase(progress, 0, 30))
        processed_dir = processed.output_dir
    else:
        processed_dir = copy_inputs(image_paths, workspace / 'processing' / 'output')
    images = list_images(processed_dir)
    by_stem = {p.stem.casefold(): p for p in images}
    if len(by_stem) != len(bundle['entries']):
        raise ValueError('處理產物數量或檔名配對不一致。')
    for entry in bundle['entries']:
        entry['original_image'] = entry['image']
        path = by_stem.get(Path(entry['image']).stem.casefold())
        if not path:
            raise ValueError('缺少對應處理圖片。')
        entry['image'] = relative_path(path, data_root)
    metadata = workspace / 'features' / 'basic.csv'
    write_rows(metadata, [{**e['metadata'], 'image_name': Path(e['image']).name} for e in bundle['entries']])
    features = None
    masks_dir = None
    if mlp:
        for entry in bundle['entries']:
            validate_values(entry['metadata'], entry['display_name'], features=stage == 'features')
        if stage == 'features':
            features = metadata
            masks_dir = safe_resolve(data_root, config['mask_dir']) if config.get('mask_dir') else None
        else:
            if stage == 'masks':
                masks_dir = safe_resolve(data_root, config['mask_dir'])
            else:
                unet = safe_resolve(models_root, config['unet_model_path'])
                if sha256_file(unet) != config['selected_segmenter']['sha256']:
                    raise ValueError('分割權重與建立工作時不同，已停止。')
                masks_dir = workspace / 'masks'
                generate_masks(images, source_root=processed_dir, output_root=masks_dir, model_path=unet,
                               device=config.get('device'), refine=True, progress=_phase(progress, 30, 55))
            report = generate_feature_csv(images, workspace / 'features' / 'features.csv', mask_dir=masks_dir,
                                          metadata_csv=metadata, diabetes_excel=None, progress=_phase(progress, 55, 75))
            if report.missing_masks or report.missing_metadata or report.failed_features:
                raise ValueError('特徵產物缺漏，停止分類；可查看工作中已完成產物。')
            features = report.output_csv
        rows = read_rows(features)
        masks = index_masks(masks_dir)
        for entry in bundle['entries']:
            name = Path(entry['image']).name
            row = rows.get(name, {})
            validate_values(row, name, features=True)
            entry['metadata'] = row
            mask = masks.get(Path(name).stem)
            entry['mask'] = relative_path(mask, data_root) if mask else None
            # Display-only image in the existing UNet coordinate system; never an inference input.
            if mask:
                from PIL import Image
                with Image.open(safe_resolve(data_root, entry['image'])) as im, Image.open(mask) as m:
                    if im.size == m.size:
                        entry['overlay_image'] = entry['image']
                    elif stage not in ('features', 'masks') and m.size == (512, 512):
                        preview = workspace / 'previews' / (Path(name).stem + '.png')
                        preview.parent.mkdir(exist_ok=True)
                        im.convert('RGB').resize((512, 512), Image.Resampling.BILINEAR).save(preview)
                        entry['overlay_image'] = relative_path(preview, data_root)
    bundle['has_features'] = mlp
    bundle['analysis_mode'] = config['analysis_mode']
    bundle['model'] = config['selected_model']
    bundle['segmenter'] = config.get('selected_segmenter') if mlp else None
    bundle['processing'] = {'reused_stage': stage, 'random_seed': config.get('random_seed', 42)}
    (workspace / 'judgment-results.json').write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
    report = run_batch_inference(images, model_path=classifier, output_dir=workspace / 'inference',
                                architecture=config['architecture'], coral=bool(config.get('coral')),
                                metadata_csv=features, device=config.get('device'), progress=_phase(progress, 75, 100))
    payload = report.to_dict()
    payload.update(csv=relative_path(report.csv_path, data_root), zip=relative_path(report.zip_path, data_root))
    sources = [processed_dir, workspace / 'inference', workspace / 'judgment-results.json', metadata]
    if features and features != metadata:
        sources.append(features)
    if masks_dir:
        sources.append(masks_dir)
    archive = create_result_archive(workspace, sources, filename='ai_judgment.zip')
    return {'operation': 'quick_analysis', 'analysis_mode': config['analysis_mode'], 'inference': payload,
            'processing': {'steps': ['convert', 'crop', 'rb'] if stage == 'raw' else [], 'reused_stage': stage},
            'csv': payload['csv'], 'archive_path': relative_path(archive, data_root),
            'model': config['selected_model'], 'segmenter': config.get('selected_segmenter') if mlp else None}
