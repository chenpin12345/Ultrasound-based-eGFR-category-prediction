from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter,Depends,Query,Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import func,select
from sqlalchemy.orm import Session

from ...core.config import AppSettings,get_settings
from ...core.errors import AppError
from ...db.models import EvaluationPrediction,EvaluationRecord,Job
from ...db.session import get_db
from ...schemas.evaluation import EvaluationCreate,ReferenceMaskRegistration
from ...services import evaluation_service as service
from ..worker_bridge import get_worker_manager

router=APIRouter(prefix='/evaluations',tags=['evaluations'])


@router.post('/reference-masks/preflight')
def reference_preflight(payload:ReferenceMaskRegistration,db:Session=Depends(get_db),settings:AppSettings=Depends(get_settings)):
    from ...services import reference_masks
    evidence,fingerprint=reference_masks.preflight(db,settings,payload)
    return {'evidence':evidence,'preflight_sha256':fingerprint}


@router.post('/reference-masks',status_code=201)
def reference_register(payload:ReferenceMaskRegistration,request:Request,db:Session=Depends(get_db),settings:AppSettings=Depends(get_settings)):
    from ...clinical.auth import current
    from ...services import reference_masks
    actor=current(request,'research.execute')
    return reference_masks.register(db,settings,payload,actor['id'])


def required(db,identifier):
    record=db.get(EvaluationRecord,identifier)
    if not record:raise AppError(404,'EVALUATION_NOT_FOUND','找不到指定評估。')
    return record


@router.post('/preflight')
def preflight(payload:EvaluationCreate,db:Session=Depends(get_db),settings:AppSettings=Depends(get_settings)):
    snapshot,_,fingerprint=service.preflight(db,settings,payload)
    return {'snapshot':snapshot,'preflight_sha256':fingerprint}


@router.post('',status_code=201)
def create(payload:EvaluationCreate,db:Session=Depends(get_db),settings:AppSettings=Depends(get_settings)):
    record=service.create(db,settings,payload)
    # If submission fails, durable queued work remains visible and is recoverable.
    get_worker_manager().submit_job(record.job_id)
    return service.record_out(record,details=True)


@router.get('')
def listing(model_id:str|None=None,status:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    filters=[]
    if model_id:filters.append(EvaluationRecord.model_id==model_id)
    if status:filters.append(EvaluationRecord.status==status)
    query=select(EvaluationRecord).where(*filters)
    total=db.scalar(select(func.count()).select_from(EvaluationRecord).where(*filters)) or 0
    records=db.scalars(query.order_by(EvaluationRecord.created_at.desc(),EvaluationRecord.id).offset(offset).limit(limit))
    return {'items':[service.record_out(record) for record in records],'total':total,'offset':offset,'limit':limit}


@router.get('/{identifier}')
def detail(identifier:str,db:Session=Depends(get_db)):
    return service.record_out(required(db,identifier),details=True)


@router.get('/{identifier}/predictions')
def predictions(identifier:str,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    required(db,identifier)
    query=select(EvaluationPrediction).where(EvaluationPrediction.evaluation_id==identifier)
    total=db.scalar(select(func.count()).select_from(EvaluationPrediction).where(EvaluationPrediction.evaluation_id==identifier)) or 0
    return {'items':[record.payload_json for record in db.scalars(query.order_by(EvaluationPrediction.sample_id).offset(offset).limit(limit))],
            'total':total,'offset':offset,'limit':limit}


@router.post('/{identifier}/stop')
def stop(identifier:str,db:Session=Depends(get_db)):
    record=required(db,identifier)
    if record.status not in {'queued','running'}:raise AppError(409,'EVALUATION_FINALIZED','評估已結束，不能再停止。')
    job=db.get(Job,record.job_id);job.stop_requested=True
    db.commit()
    return {'id':identifier,'stop_requested':True}


@router.post('/{identifier}/retry',status_code=201)
def retry(identifier:str,db:Session=Depends(get_db),settings:AppSettings=Depends(get_settings)):
    previous=required(db,identifier)
    if previous.status not in {'failed','partial','stopped','interrupted'}:raise AppError(409,'EVALUATION_NOT_RETRYABLE','只可重試失敗、部分完成、已停止或中斷的評估。')
    payload=EvaluationCreate.model_validate(previous.snapshot_json['request'])
    # Exact old scope, no automatic substitution if source/weight/default changed.
    payload.expected_preflight_sha256=service.digest(previous.snapshot_json)
    record=service.create(db,settings,payload,retry_of=previous.id)
    get_worker_manager().submit_job(record.job_id)
    return service.record_out(record,details=True)


@router.get('/{identifier}/compare/{other_id}')
def compare(identifier:str,other_id:str,db:Session=Depends(get_db)):
    first,second=required(db,identifier),required(db,other_id)
    reasons=[]
    for key in ('task','cohort_sha256','metric_version'):
        if getattr(first,key)!=getattr(second,key):reasons.append(key)
    for key in ('class_schema','preprocessing_version'):
        if first.snapshot_json[key]!=second.snapshot_json[key]:reasons.append(key)
    if first.status!='completed' or second.status!='completed':reasons.append('incomplete_cohort')
    # A ranking is never calculated for incompatible populations or definitions.
    return {'compatible':not reasons,'incompatible_fields':reasons,'records':[service.record_out(first),service.record_out(second)]}


@router.get('/{identifier}/export')
def export(identifier:str,format:str=Query('json',pattern='^(json|csv)$'),db:Session=Depends(get_db)):
    record=required(db,identifier)
    items=[item.payload_json for item in db.scalars(select(EvaluationPrediction).where(EvaluationPrediction.evaluation_id==identifier).order_by(EvaluationPrediction.sample_id))]
    if format=='json':
        data=json.dumps(jsonable_encoder({**service.record_out(record,details=True),'predictions':items}),ensure_ascii=False,allow_nan=False,indent=2)
        media='application/json'
    else:
        stream=io.StringIO(newline='')
        fields=['evaluation_id','model_id','weight_sha256','cohort_sha256','metric_version','sample_id','original_sha256','image_sha256','status','expected_index','predicted_index','probabilities','foreground_counts','error_code','reason']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for item in items:
            row={**item,'evaluation_id':record.id,'model_id':record.model_id,'weight_sha256':record.snapshot_json['weight_sha256'],
                 'cohort_sha256':record.cohort_sha256,'metric_version':record.metric_version}
            row={key:json.dumps(row[key],ensure_ascii=False) if isinstance(row.get(key),(list,dict)) else row.get(key,'') for key in fields}
            # Spreadsheet formula neutralization without altering stored evidence.
            row={key:("'"+value if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')) else value) for key,value in row.items()}
            writer.writerow(row)
        data='\ufeff'+stream.getvalue();media='text/csv'
    return Response(data,media_type=media,headers={'Content-Disposition':f'attachment; filename="evaluation-{record.id}.{format}"','Cache-Control':'no-store'})
