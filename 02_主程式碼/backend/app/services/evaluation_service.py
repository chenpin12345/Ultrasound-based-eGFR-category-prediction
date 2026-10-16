"""Explicit, immutable research evaluation. Uses existing inference operations."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

from sqlalchemy import select

from ..core.errors import AppError
from ..core.security import relative_path, safe_resolve, sha256_file
from ..db.models import Dataset, DatasetSample, EvaluationRecord, Job, MaskProvenance, ModelRecord, utc_now, uuid_str
from .evaluation_metrics import CLASSIFICATION_VERSION, SEGMENTATION_VERSION, evaluation_label
from .model_catalog import detail
from .workflow_service import resolve_inputs


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def preflight(db,settings,payload):
    from PIL import Image
    model=db.get(ModelRecord,payload.model_id)
    dataset=db.get(Dataset,payload.dataset_id)
    if not model or not dataset:
        raise AppError(404,'EVALUATION_SOURCE_MISSING','找不到指定模型或資料集。')
    if model.status not in {'ready','completed'}:
        raise AppError(409,'MODEL_NOT_READY','模型尚未就緒。')
    info=detail(db,model,settings)
    if info['configuration']['status']!='consistent':
        raise AppError(422,'MODEL_CONFIGURATION_UNVERIFIED','模型配套尚未核實，不能建立評估。')
    weight=safe_resolve(settings.models_dir,model.weights_path)
    manifest_path=safe_resolve(settings.models_dir,model.metadata_path)
    if not weight.is_file() or sha256_file(weight)!=model.sha256:
        raise AppError(409,'MODEL_CHANGED','模型權重不存在或內容已改變。')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    bundle=resolve_inputs(db,settings,payload.input_sources)
    if bundle.get('dataset_id')!=dataset.id:
        raise AppError(422,'EVALUATION_DATASET_MISMATCH','處理來源與標籤資料集不一致。')
    samples={sample.id:sample for sample in db.scalars(select(DatasetSample).where(DatasetSample.dataset_id==dataset.id))}
    selected=[]
    excluded=[]
    image_splits={}
    patient_splits={}
    patient_unknown=0
    for sample in samples.values():
        split='val' if sample.split in ('validation','valid') else sample.split
        image_splits.setdefault(sample.sha256,set()).add(split)
        patient=(sample.metadata_json or {}).get('patient_id')
        if patient is None or str(patient).strip()=='': patient_unknown+=1
        else: patient_splits.setdefault(str(patient),set()).add(split)
    for entry in bundle['entries']:
        sample=samples.get(entry['sample_id'])
        if sample is None:
            raise AppError(422,'EVALUATION_IDENTITY_MISMATCH','無法確認處理影像的原始樣本身分。')
        split='val' if sample.split in ('validation','valid') else sample.split
        if payload.split!='all' and split!=payload.split:
            excluded.append({'sample_id':sample.id,'reason':'outside_requested_split'})
            continue
        path=safe_resolve(settings.data_dir,entry['image'])
        with Image.open(path) as image: size=list(image.size)
        item={**entry,'original_sha256':sample.sha256,'image_sha256':sha256_file(path),'size':size,'split':split}
        if model.task=='classification':
            try: item['expected_index']=evaluation_label(sample.class_index,model.class_count)
            except ValueError as exc: raise AppError(422,'EVALUATION_LABEL_MISSING','每張評估影像都需要可核實的原始五級標籤。') from exc
            if 'mlp' in model.architecture:
                from ..ml.contracts import METADATA_FIELDS, normalize_metadata
                if not bundle.get('has_features') or any(item['metadata'].get(key) in (None,'') for key in METADATA_FIELDS):
                    raise AppError(422,'EVALUATION_FEATURES_MISSING','MLP 評估需要相同影像版本的完整特徵。')
                try:
                    values=normalize_metadata(item['metadata'],manifest['train_stats'])
                    if not all(math.isfinite(value) for value in values) or float(item['metadata']['has_diabetes']) not in (0,1):
                        raise ValueError('Nonfinite or invalid binary feature.')
                except (KeyError,ValueError,TypeError) as exc: raise AppError(422,'EVALUATION_FEATURES_INVALID','MLP 配套或特徵值不相容。') from exc
        else:
            reference=sample.mask
            provenance=db.get(MaskProvenance,reference.id) if reference else None
            if not provenance or provenance.kind!='independent_reference':
                raise AppError(422,'REFERENCE_MASK_UNVERIFIED','缺少獨立參考 Mask 來源；模型自己產生的遮罩不能當作評估答案。')
            evidence=provenance.evidence_json
            if not entry.get('mask') or size!=[512,512] or [reference.width,reference.height]!=size:
                raise AppError(422,'REFERENCE_MASK_ALIGNMENT','參考 Mask 必須與已處理的 512×512 影像位於相同座標；不自動拉伸。')
            mask=safe_resolve(settings.data_dir,entry['mask'])
            if (sha256_file(mask)!=reference.sha256 or evidence.get('mask_sha256')!=reference.sha256
                or evidence.get('image_sha256')!=item['image_sha256'] or evidence.get('coordinate_mapping')!='identity'
                or not evidence.get('source') or not evidence.get('reviewer')):
                raise AppError(422,'REFERENCE_MASK_EVIDENCE','參考 Mask 的來源、雜湊或對位證據不完整。')
            item['reference_mask_sha256']=reference.sha256
            item['reference_provenance']=evidence
        selected.append(item)
    if not selected:
        raise AppError(422,'EMPTY_EVALUATION','指定 split 沒有可評估樣本，不會以 0% 代替。')
    from ..clinical.resources import resolve_device
    try: device=resolve_device(payload.device)
    except ValueError as exc: raise AppError(422,'DEVICE_UNAVAILABLE',str(exc)) from exc
    cohort=[{key:item.get(key) for key in ('sample_id','original_sha256','image_sha256','size','split','expected_index','metadata','reference_mask_sha256')} for item in selected]
    cohort_sha=digest(sorted(cohort,key=lambda item:item['sample_id']))
    snapshot={'model_id':model.id,'model_name':model.name,'weight_sha256':model.sha256,'manifest':manifest,
              'manifest_file_sha256':sha256_file(manifest_path),'configuration_sha256':info['configuration']['sha256'],
              'class_schema':info['class_schema'],'dataset_id':dataset.id,'dataset_name':dataset.name,
              'input_sources':payload.input_sources.model_dump(exclude_none=True),'source_evidence':payload.source_evidence,
              'split':payload.split,'sample_count':len(selected),'excluded':excluded,'device':device,
              'preprocessing_version':'existing-inference-v1','cohort_sha256':cohort_sha,
              'leakage':{'cross_split_image_groups':sum(len(splits-{None})>1 for splits in image_splits.values()),
                         'cross_split_patient_groups':sum(len(splits-{None})>1 for splits in patient_splits.values()),
                         'samples_without_patient_id':patient_unknown,'training_overlap':'unknown',
                         'warning':'未核實歷史訓練樣本，無法排除訓練資料洩漏。本評估不是經證實的獨立測試。'},
              'scope':'指定研究資料重測；不是獨立臨床測試或海報重現',
              'request':payload.model_dump(exclude={'expected_preflight_sha256'})}
    return snapshot,selected,digest(snapshot)


def create(db,settings,payload,*,retry_of=None):
    snapshot,entries,fingerprint=preflight(db,settings,payload)
    if payload.expected_preflight_sha256!=fingerprint:
        raise AppError(409,'EVALUATION_PREFLIGHT_CHANGED','請先檢查評估範圍；資料或設定變更後須重新確認。')
    identifier,job_id=uuid_str(),uuid_str()
    workspace=safe_resolve(settings.data_dir,'jobs',job_id)
    workspace.mkdir(parents=True,exist_ok=False)
    model=db.get(ModelRecord,payload.model_id)
    try:
        model_dir=workspace/'model';model_dir.mkdir()
        shutil.copy2(safe_resolve(settings.models_dir,model.weights_path),model_dir/'weights.pth')
        shutil.copy2(safe_resolve(settings.models_dir,model.metadata_path),model_dir/'model_metadata.json')
        if sha256_file(model_dir/'weights.pth')!=model.sha256 or sha256_file(model_dir/'model_metadata.json')!=snapshot['manifest_file_sha256']:
            raise AppError(409,'MODEL_CHANGED','複製期間模型已改變。')
        for item in entries:
            for role,hash_key in [('image','image_sha256'),('mask','reference_mask_sha256')]:
                if role=='mask' and model.task!='segmentation':continue
                source=safe_resolve(settings.data_dir,item[role])
                target=safe_resolve(workspace,'input',item['sample_id'],role+source.suffix)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
                if sha256_file(target)!=item[hash_key]:
                    raise AppError(409,'EVALUATION_INPUT_CHANGED','複製期間輸入產物已改變。')
                item[role]=relative_path(target,settings.data_dir)
        (workspace/'inputs.json').write_text(json.dumps(entries,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        job=Job(id=job_id,kind='evaluation',dataset_id=payload.dataset_id,workspace_path=relative_path(workspace,settings.data_dir),
                config_json={'operation':'evaluation','evaluation_id':identifier,'model_id':model.id,'device':snapshot['device']})
        record=EvaluationRecord(id=identifier,model_id=model.id,job_id=job_id,dataset_id=payload.dataset_id,retry_of_id=retry_of,
                                task=model.task,snapshot_json=snapshot,cohort_sha256=snapshot['cohort_sha256'],
                                metric_version=CLASSIFICATION_VERSION if model.task=='classification' else SEGMENTATION_VERSION,
                                sample_count=len(entries),completed_count=0,status='queued')
        db.add(job);db.flush();db.add(record);db.commit()
    except BaseException:
        db.rollback()
        # Exact newly allocated managed job directory; no existing user data.
        if workspace.resolve().is_relative_to((settings.data_dir/'jobs').resolve()):shutil.rmtree(workspace)
        raise
    return record


def record_out(record,*,details=False):
    snapshot=record.snapshot_json
    result={'id':record.id,'job_id':record.job_id,'model_id':record.model_id,'model_name':snapshot['model_name'],
            'dataset_id':record.dataset_id,'dataset_name':snapshot['dataset_name'],'task':record.task,'status':record.status,
            'split':snapshot['split'],'sample_count':record.sample_count,'completed_count':record.completed_count,
            'cohort_sha256':record.cohort_sha256,'metric_version':record.metric_version,'retry_of_id':record.retry_of_id,
            'created_at':record.created_at,'completed_at':record.completed_at,'result':record.result_json}
    if details:result['snapshot']=snapshot
    elif result['result']:
        result['result']={key:value for key,value in result['result'].items() if key not in {'errors'}}
    return result
