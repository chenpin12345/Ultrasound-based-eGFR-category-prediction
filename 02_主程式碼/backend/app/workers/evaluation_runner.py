"""Evaluation worker; the manager already owns any required GPU lock."""
from __future__ import annotations

import csv
import json
import math
import logging

from sqlalchemy import select

from ..core.security import safe_resolve, sha256_file
from ..db.models import EvaluationPrediction, EvaluationRecord, Job, JobEvent, utc_now
from ..services.evaluation_metrics import classification_metrics,foreground_counts,segmentation_metrics
from ..services.evaluation_service import digest

LOGGER=logging.getLogger(__name__)


def predict_one(entry,record,workspace,manager):
    """Call unchanged inference and segmentation entry points, not a new model."""
    from ..ml.inference import run_batch_inference
    from ..ml.segmentation import generate_masks
    image=safe_resolve(manager.data_root,entry['image'])
    if sha256_file(image)!=entry['image_sha256']:
        raise ValueError('IMAGE_HASH_CHANGED')
    folder=safe_resolve(workspace,'results',entry['sample_id'])
    folder.mkdir(parents=True,exist_ok=False)
    weight=workspace/'model/weights.pth'
    if record.task=='classification':
        metadata=folder/'metadata.csv'
        row={**entry.get('metadata',{}),'image_name':image.name}
        with metadata.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(row));writer.writeheader();writer.writerow(row)
        report=run_batch_inference([image],model_path=weight,output_dir=folder,metadata_csv=metadata,
                                   device=record.snapshot_json['device'],include_images_in_zip=False)
        item=report.items[0].to_dict()
        if not all(math.isfinite(value) for value in item['probabilities']):raise ValueError('NONFINITE_PREDICTION')
        return {'predicted_index':item['predicted_index'],'probabilities':item['probabilities'],'expected_index':entry['expected_index']}
    from PIL import Image
    import numpy as np
    reference=safe_resolve(manager.data_root,entry['mask'])
    if sha256_file(reference)!=entry['reference_mask_sha256']:raise ValueError('REFERENCE_HASH_CHANGED')
    paths=generate_masks([image],source_root=image.parent,output_root=folder,model_path=weight,device=record.snapshot_json['device'],refine=True)
    with Image.open(reference) as original,Image.open(paths[0]) as predicted:
        truth,guess=np.asarray(original.convert('L')),np.asarray(predicted.convert('L'))
        if not np.isin(truth,[0,255]).all():raise ValueError('REFERENCE_NOT_BINARY_0_255')
        counts=foreground_counts(truth==255,guess==255)
    return {'foreground_counts':counts,'prediction_sha256':sha256_file(paths[0])}


def run_evaluation(manager,job_id):
    errors=[];successes=[];stopped=False;record=None
    try:
        with manager.session_factory() as db:
            record=db.scalar(select(EvaluationRecord).where(EvaluationRecord.job_id==job_id))
            job=db.get(Job,job_id)
            if record is None or record.status!='queued' or job.status!='queued':return
            if job.stop_requested:stopped=True
            record.status='running';job.status='running';job.started_at=utc_now()
            db.add(JobEvent(job_id=job_id,event_type='started',data_json={'evaluation_id':record.id}))
            db.commit()
        workspace=safe_resolve(manager.data_root,job.workspace_path)
        snapshot=record.snapshot_json
        if sha256_file(workspace/'model/weights.pth')!=snapshot['weight_sha256'] or sha256_file(workspace/'model/model_metadata.json')!=snapshot['manifest_file_sha256']:
            raise ValueError('MODEL_SNAPSHOT_CHANGED')
        entries=json.loads((workspace/'inputs.json').read_text(encoding='utf-8'))
        cohort=[{key:item.get(key) for key in ('sample_id','original_sha256','image_sha256','size','split','expected_index','metadata','reference_mask_sha256')} for item in entries]
        if digest(sorted(cohort,key=lambda item:item['sample_id']))!=record.cohort_sha256:raise ValueError('COHORT_SNAPSHOT_CHANGED')
        for entry in entries:
            with manager.session_factory() as db:
                current=db.get(Job,job_id)
                if current.stop_requested:stopped=True
            if stopped:break
            try:
                payload={'status':'completed',**predict_one(entry,record,workspace,manager)}
                successes.append(payload)
            except Exception as exc:
                LOGGER.exception('Evaluation %s sample %s failed',record.id,entry['sample_id'])
                # Controlled types, no raw filesystem paths or hidden exclusion.
                payload={'status':'failed','error_code':type(exc).__name__,'reason':'此樣本推論或產物驗證失敗；請檢查來源與模型。'}
                errors.append({'sample_id':entry['sample_id'],**payload})
            payload.update({key:entry.get(key) for key in ('sample_id','image_sha256','original_sha256','expected_index')})
            with manager.session_factory() as db:
                db.add(EvaluationPrediction(evaluation_id=record.id,sample_id=entry['sample_id'],payload_json=payload))
                db.get(EvaluationRecord,record.id).completed_count=len(successes)
                current=db.get(Job,job_id);current.progress=(len(successes)+len(errors))/record.sample_count*100
                db.add(JobEvent(job_id=job_id,event_type='progress',data_json={'completed':len(successes),'failed':len(errors),'total':record.sample_count}))
                db.commit()
        status='stopped' if stopped else 'partial' if errors and successes else 'failed' if errors else 'completed'
        metrics=classification_metrics([row['expected_index'] for row in successes],[row['predicted_index'] for row in successes],snapshot['class_schema']['class_count']) if record.task=='classification' else segmentation_metrics([row['foreground_counts'] for row in successes])
        result={'metrics':metrics,'errors':errors,'requested_sample_count':record.sample_count,'evaluated_sample_count':len(successes),
                'complete_cohort':status=='completed','scope':snapshot['scope'],'actual_device':snapshot['device']}
    except Exception as exc:
        LOGGER.exception('Evaluation job %s failed',job_id)
        status='failed'
        result={'metrics':None,'complete_cohort':False,'error_code':type(exc).__name__,'reason':'評估輸入快照驗證或工作執行失敗，已保留紀錄。'}
    if record is None:return
    with manager.session_factory() as db:
        current=db.get(EvaluationRecord,record.id)
        if current.status not in {'queued','running'}:return
        current.status=status;current.result_json=result;current.completed_at=utc_now();current.completed_count=len(successes)
        job=db.get(Job,job_id);job.status='failed' if status=='partial' else status;job.result_json={'evaluation_id':record.id,'evaluation_status':status}
        job.completed_at=utc_now();job.progress=100 if status=='completed' else job.progress
        if status in {'failed','partial'}:job.error_code='EVALUATION_INCOMPLETE';job.error_message='評估未完整完成，請查看逐筆失敗原因。'
        db.add(JobEvent(job_id=job_id,event_type=job.status,data_json=job.result_json));db.commit()
