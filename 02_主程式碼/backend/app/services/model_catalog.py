"""Read-only catalog provenance; never derives research scores from filenames."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing

from sqlalchemy import func, or_, select

from ..core.config import AppSettings
from ..core.security import safe_resolve
from ..db.models import EvaluationRecord, Job, ModelRecord, TrainingJob


def evaluation_summaries(db, models: list[ModelRecord]) -> dict[str, dict]:
    """One bounded query, no prediction/error blobs and no implicit best ranking."""
    if not models:
        return {}
    by_id = {model.id: model for model in models}
    e = EvaluationRecord
    ranked = select(e.id, func.row_number().over(
        partition_by=e.model_id, order_by=(e.created_at.desc(), e.id.desc())
    ).label('position')).where(e.model_id.in_(by_id)).subquery()
    rows = db.execute(select(
        e.id, e.model_id, e.status, e.dataset_id, e.sample_count, e.completed_count,
        e.completed_at, e.metric_version,
        e.snapshot_json['weight_sha256'].as_string().label('weight'),
        e.snapshot_json['configuration_sha256'].as_string().label('configuration'),
        e.snapshot_json['dataset_name'].as_string().label('dataset_name'),
        e.snapshot_json['split'].as_string().label('split'),
        e.snapshot_json['scope'].as_string().label('scope'),
        e.result_json['complete_cohort'].as_boolean().label('complete'),
        e.result_json['metrics']['accuracy'].as_float().label('accuracy'),
        e.result_json['metrics']['macro_f1'].as_float().label('macro_f1'),
        e.result_json['metrics']['macro_per_image']['dice'].as_float().label('dice'),
        e.result_json['metrics']['macro_per_image']['iou'].as_float().label('iou'),
    ).join(ranked, ranked.c.id == e.id).where(ranked.c.position == 1)).mappings()
    result = {}
    for row in rows:
        complete = (row['status'] == 'completed' and row['complete'] is True
                    and row['completed_count'] == row['sample_count']
                    and row['weight'] == by_id[row['model_id']].sha256)
        keys = ('accuracy', 'macro_f1') if by_id[row['model_id']].task == 'classification' else ('dice', 'iou')
        result[row['model_id']] = {
            'evaluation_id': row['id'], 'status': row['status'],
            'reason': None if complete else '最近評估尚未完整完成或權重識別不符；不顯示為完整模型成績。',
            'weight_sha256': row['weight'], 'configuration_sha256': row['configuration'],
            'dataset_id': row['dataset_id'], 'dataset_name': row['dataset_name'],
            'split': row['split'], 'scope': row['scope'], 'sample_count': row['sample_count'],
            'evaluated_sample_count': row['completed_count'], 'completed_at': row['completed_at'],
            'metric_version': row['metric_version'],
            'metrics': {key: row[key] for key in keys} if complete else {},
        }
    return result


def references(db, model: ModelRecord, settings: AppSettings) -> list[dict]:
    result = []
    if model.active:
        result.append({'kind': 'default', 'id': model.id, 'name': '研究預設模型', 'status': 'active'})
    for identifier, status in db.execute(select(EvaluationRecord.id,EvaluationRecord.status).where(EvaluationRecord.model_id==model.id)):
        result.append({'kind':'evaluation','id':identifier,'name':'模型評估','status':status})
    predicates = [Job.config_json[key].as_string() == model.weights_path for key in ('model_path','classifier_model_path','unet_model_path')]
    predicates += [Job.config_json[key].as_string() == model.id for key in ('model_id','classifier_model_id','unet_model_id')]
    # Do not hydrate multi-thousand-image result JSON just to list references.
    for identifier, kind, status in db.execute(select(Job.id,Job.kind,Job.status).where(or_(*predicates))):
        result.append({'kind':'research_job','id':identifier,'name':kind,'status':status})
    path = settings.clinical_dir / 'clinical.sqlite3'
    if path.is_file():
        # Read-only URI: catalog requests must not create/migrate a clinical DB.
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as clinical:
            for identifier, name, raw in clinical.execute('SELECT id,name,snapshot FROM plans'):
                snapshot = json.loads(raw)
                if any(item.get('sha256') == model.sha256 for item in snapshot.get('models', {}).values()):
                    result.append({'kind': 'clinical_plan', 'id': identifier, 'name': name, 'status': 'sealed'})
    return result


def detail(db, model: ModelRecord, settings: AppSettings) -> dict:
    manifest = None
    reason = None
    config_hash = None
    try:
        path = safe_resolve(settings.models_dir, model.metadata_path)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('模型設定超過大小限制。')
        manifest = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(manifest, dict):
            raise ValueError('模型設定不是物件。')
        if model.task == 'classification':
            from ..ml.contracts import ModelMetadata
            # Both registry-upload manifests and the existing training writer's
            # explicit numeric contract are supported, without changing either.
            training_format = all(key in manifest for key in ('contract_version','metadata_fields','image_size','image_mode','normalization_mean','normalization_std'))
            if manifest.get('task') != 'classification' and not training_format:
                raise ValueError('模型設定任務來源未核實。')
            actual = ModelMetadata.from_dict(manifest)
            registered = ModelMetadata.from_dict({key:getattr(model,key) for key in ('architecture','class_count','class_names','metadata_columns','preprocessing')})
            for key in ('architecture','coral','class_count','class_names','metadata_fields','image_size','image_mode','normalization_mean','normalization_std'):
                if getattr(actual,key) != getattr(registered,key):
                    raise ValueError(f'模型設定 {key} 與登錄資料不符。')
            if 'mlp' in model.architecture and not manifest.get('train_stats'):
                raise ValueError('MLP 缺少此權重專屬的 train_stats，不使用共同預設代替。')
        else:
            for key in ('task','architecture','class_count','class_names','metadata_columns','preprocessing'):
                if manifest.get(key) != getattr(model,key):
                    raise ValueError(f'模型設定 {key} 與登錄資料不符。')
        if manifest.get('sha256', model.sha256) != model.sha256:
            raise ValueError('模型設定內的權重識別與登錄資料不符。')
        config_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # Do not disclose filesystem paths from OSError to the browser.
        reason = '模型設定檔缺失或無法讀取。' if isinstance(exc, OSError) else str(exc)
        manifest = None
    schema = {'version': 'ordered-classes-v1', 'task': model.task, 'class_count': model.class_count, 'class_names': model.class_names}
    schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    training = db.get(TrainingJob, model.source_training_job_id) if model.source_training_job_id else None
    from .checkpoint_provenance import summary as checkpoint_summary
    checkpoint=checkpoint_summary(model,db.get(Job,training.job_id),settings) if training else None
    return {
        'configuration': {'status': 'consistent' if manifest else 'unverified', 'reason': reason, 'sha256': config_hash,
                          'train_stats': manifest.get('train_stats') if manifest else None},
        'class_schema': {**schema, 'sha256': schema_hash, 'status': 'consistent' if manifest else 'unverified'},
        'source_info': {'kind': 'local_training' if training else 'imported', 'status': checkpoint['status'] if checkpoint else 'unverified',
                        'reason': checkpoint['reason'] if checkpoint else '尚未建立權重、checkpoint 與評估資料範圍的可驗證關聯。',
                        'training_job_id': training.id if training else None},
        'training_record': None if training is None else {
            'job_id': training.job_id, 'training_job_id': training.id, 'status': training.status,
            'selection_metric': 'validation_loss', 'selection_direction': 'minimize',
            'recorded_best_validation_loss': training.best_metric,
            'completed_epoch': training.current_epoch,
            'checkpoint_source':checkpoint,
            'note': '這是訓練工作紀錄，不是指定權重的已驗證評估；最後 epoch 不等於最佳 epoch。',
        },
        'references': references(db, model, settings),
    }
