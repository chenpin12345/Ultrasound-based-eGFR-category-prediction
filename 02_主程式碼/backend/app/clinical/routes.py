from __future__ import annotations

import hashlib
import io
import threading
import time
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from ..core.errors import AppError
from . import store, reports, pdf_artifacts
from .auth import current
from .analysis import MAX_IMAGE_BYTES, create_plan, infer
from .service import required, new_exam, save_frame, analyze_frame, frame_out
from .resources import reserve_session,release_session
from .lifecycle import guard,state_sql

router = APIRouter(prefix='/clinical', tags=['Clinical workspace'])
_previews = {}
_preview_lock = threading.Lock()

def physician(request):
    return current(request, 'clinical.read' if request.method in {'GET','HEAD'} else 'clinical.operate')

class Patient(BaseModel):
    code: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=120)

class Exam(BaseModel):
    kind: Literal['patient','demo']
    patient_id: str | None = None
    title: str = Field(min_length=1,max_length=200)
    side: Literal['left','right','both','unspecified'] = 'unspecified'
    age: float | None = Field(default=None,ge=0,le=130)
    has_diabetes: Literal[0,1] | None = None

class Plan(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    model_id: str
    segmenter_id: str | None = None
    profile: dict
    device: Literal['auto','cpu','cuda'] = 'auto'
    @field_validator('profile')
    @classmethod
    def validate_profile(cls,value):
        return Profile(**value).model_dump()

class Profile(BaseModel):
    mode: Literal['unknown','legacy','prepared']
    width: int = Field(default=0,ge=0,le=16000)
    height: int = Field(default=0,ge=0,le=16000)
    evidence: str = Field(default='',max_length=10000)
    validated_for_patient: bool = False
    version: Literal[1] = 1

class Report(BaseModel):
    exam_id: str
    expected_version: int = Field(default=0,ge=0)
    fields: dict[str,str] = Field(default_factory=dict)
    frame_ids: list[str] = Field(default_factory=list,max_length=20)
    include_ai: bool = False
    analysis_run_ids: dict[str,str] = Field(default_factory=dict,max_length=20)
    acknowledge_missing: bool = False
    action: Literal['draft','pending','confirmed','revise','void'] = 'draft'

@router.get('/patients')
def patients(request: Request):
    physician(request)
    with store.transaction() as db:
        return [dict(r) for r in db.execute(f"SELECT p.* FROM patients p WHERE ({state_sql('patients','p')})='normal' ORDER BY created DESC LIMIT 500")]

@router.post('/patients')
def patient_create(payload: Patient, request: Request):
    user=physician(request)
    with store.transaction() as db:
        if db.execute('SELECT 1 FROM patients WHERE code=?',(payload.code,)).fetchone():
            raise AppError(409,'PATIENT_EXISTS','病人識別碼已存在。')
        identifier=store.uid()
        db.execute('INSERT INTO patients VALUES(?,?,?,?)',(identifier,payload.code,payload.name,time.time()))
        store.audit(db,user['id'],'create_patient',identifier)
    return {'id':identifier}

@router.get('/plans')
def plans(request: Request):
    current(request)
    from .defaults import summary
    with store.transaction() as db:
        rows=[store.rowdict(r) for r in db.execute('SELECT * FROM plans ORDER BY created DESC')]
    for row in rows:
        row['summary']=summary(row)
        for model in row['snapshot']['models'].values():
            model.pop('path',None)
    return rows

@router.post('/plans')
def plan_create(payload: Plan, request: Request):
    user=current(request,'models.manage')
    if payload.profile['mode']=='unknown': payload.profile['validated_for_patient']=False
    return {'id':create_plan(**payload.model_dump(),actor=user['id'])}

@router.get('/exams')
def exams(request: Request, kind: Literal['patient','demo'] | None=None):
    physician(request)
    with store.transaction() as db:
        return [store.rowdict(r) for r in db.execute(f"SELECT e.* FROM exams e WHERE (? IS NULL OR kind=?) AND ({state_sql('exams','e')})='normal' ORDER BY created DESC LIMIT 500",(kind,kind))]

@router.post('/exams')
def exam_create(payload: Exam,request: Request):
    user=physician(request)
    basic={k:v for k,v in payload.model_dump().items() if k in ('age','has_diabetes') and v is not None}
    if 'has_diabetes' in basic: basic['diabetes_status']='yes' if basic['has_diabetes']==1 else 'no'
    with store.transaction() as db:
        identifier=new_exam(db,payload.kind,payload.patient_id,payload.title,payload.side,basic,actor=user['id'])
        store.audit(db,user['id'],'create_exam',identifier)
    return {'id':identifier}

@router.get('/exams/{identifier}')
def exam_get(identifier: str, request: Request):
    physician(request)
    import json
    from . import cases, defaults
    from .transfer import plan_names
    with store.transaction() as db:
        result=required(db,'exams',identifier)
        names=plan_names(db)
        result['frames']=[frame_out(r,names) for r in db.execute('SELECT * FROM frames WHERE exam_id=? ORDER BY created',(identifier,))]
        result['diabetes_status']=cases.diabetes_status(result['payload'])
        # Transfer context: the plan locked on the receiving session (not today's default).
        result['transfer']=None
        item=db.execute('''SELECT i.id,i.batch_id,i.status,i.missing_fields,i.frame_id,i.case_code,s.id AS session_id,s.state AS session_state,
                        s.plan_mode,s.plan_id FROM items i JOIN batches b ON b.id=i.batch_id JOIN demo_sessions s ON s.id=b.session_id
                        WHERE i.exam_id=? ORDER BY i.created DESC LIMIT 1''',(identifier,)).fetchone()
        if item:
            plan=required(db,'plans',item['plan_id']) if item['plan_id'] else None
            result['transfer']={**dict(item),'missing_fields':json.loads(item['missing_fields']) if item['missing_fields'] else [],
                                'plan':defaults.summary(plan) if plan else None,
                                'missing_now':cases.missing(result['payload'],defaults.requirements(plan)) if plan else []}
        result['versions']=[dict(r) for r in db.execute('SELECT revision,source,actor,created,payload_sha256 FROM exam_basic_versions WHERE exam_id=? ORDER BY revision DESC',(identifier,))]
    return result

def save_case(identifier,expected_revision,title,side,payload_for,user):
    from .cases import update_exam
    from .transfer import resume_case
    with store.transaction() as db:
        exam=required(db,'exams',identifier)
        guard(db,'exams',identifier,write=True)
        if exam['revision']!=expected_revision:
            raise AppError(409,'REVISION_CONFLICT','檢查資料已變更，請重新載入。')
        revision=update_exam(db,exam,title,side,payload_for(exam),'manual',user['id'])
        store.audit(db,user['id'],'update_case_data',identifier)
    # Older runs and confirmed reports keep their own snapshot; only waiting
    # transfer items continue, once, with this new data version.
    return {'revision':revision,'resumed':resume_case(identifier)}

@router.patch('/exams/{identifier}')
def exam_metadata(identifier: str,payload: Exam,request: Request,expected_revision: int):
    user=physician(request)
    with store.read_transaction() as db:
        exam=required(db,'exams',identifier)
    if exam['kind']!=payload.kind or exam['patient_id']!=payload.patient_id:
        raise AppError(422,'IMMUTABLE_IDENTITY','檢查類型與病人關聯不可變更。')
    def merged(exam):
        basic={k:v for k,v in exam['payload'].items() if k not in ('age','has_diabetes','diabetes_status')}
        basic.update({k:v for k,v in payload.model_dump().items() if k in ('age','has_diabetes') and v is not None})
        if 'has_diabetes' in basic: basic['diabetes_status']='yes' if basic['has_diabetes']==1 else 'no'
        return basic
    return save_case(identifier,expected_revision,payload.title,payload.side,merged,user)

@router.put('/exams/{identifier}/case')
def exam_case(identifier: str,payload: dict,request: Request,expected_revision: int):
    user=physician(request)
    from pydantic import ValidationError
    from .cases import CaseUpdate, edited_payload
    try: update=CaseUpdate.model_validate(payload)
    except ValidationError as exc:
        raise AppError(422,'VALIDATION_ERROR','請檢查案例資料。',[{'field':'.'.join(str(p) for p in e['loc']),'message':e['msg']} for e in exc.errors()]) from None
    return save_case(identifier,expected_revision,update.title,update.side,lambda exam:edited_payload(exam,update),user)

async def image_body(request):
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>MAX_IMAGE_BYTES:
            raise AppError(413,'IMAGE_SIZE','圖片超過 32 MB。')
    return bytes(content)

@router.post('/exams/{identifier}/frames')
async def frame_upload(identifier: str,request: Request):
    physician(request)
    data=await image_body(request)
    return {'id':await run_in_threadpool(save_frame,data,identifier,'capture',saved=True)}

@router.post('/frames/{identifier}/analyze')
def frame_analyze(identifier: str,request: Request,plan_id: str):
    user=physician(request)
    return analyze_frame(identifier,plan_id,actor=user['id'])

@router.post('/frames/{identifier}/save')
def frame_save(identifier: str,request: Request):
    user=physician(request)
    with store.transaction() as db:
        required(db,'frames',identifier)
        guard(db,'frames',identifier,write=True)
        db.execute('UPDATE frames SET saved=1 WHERE id=?',(identifier,))
        store.audit(db,user['id'],'save_frame',identifier)
    return {'saved':True}

@router.get('/frames/{identifier}/{artifact}')
def frame_artifact(identifier: str,artifact: Literal['original','processed','mask','overlay'],request: Request):
    physician(request)
    with store.read_transaction() as db:
        frame=required(db,'frames',identifier)
        path=store.managed(frame['path'])
        if artifact!='original':
            from . import analysis_runs
            run=analysis_runs.latest(db,identifier)
            if not run:raise AppError(404,'ARTIFACT_MISSING','尚無可追溯的分析產物。')
            path=analysis_runs.artifact(db,run['id'],artifact,identifier)
    if not path.is_file(): raise AppError(404,'ARTIFACT_MISSING','尚無此影像產物。')
    return FileResponse(path,headers={'Cache-Control':'no-store'})

@router.get('/frames/{identifier}/analyses/history')
def frame_analyses(identifier:str,request:Request):
    physician(request)
    from . import analysis_runs
    with store.read_transaction() as db:
        required(db,'frames',identifier)
        names={r['id']:r['name'] for r in db.execute('SELECT id,name FROM plans')}
        return [{**analysis_runs.public(store.rowdict(row)),'plan_name':names.get(row['plan_id'])} for row in db.execute('SELECT * FROM analysis_runs WHERE frame_id=? ORDER BY created DESC,id DESC',(identifier,))]

@router.get('/analyses/{identifier}/{artifact}')
def analysis_artifact(identifier:str,artifact:Literal['processed','mask','overlay'],request:Request):
    physician(request)
    from . import analysis_runs
    with store.read_transaction() as db:path=analysis_runs.artifact(db,identifier,artifact)
    return FileResponse(path,headers={'Cache-Control':'no-store'})

@router.post('/preview')
async def preview(request: Request,exam_id: str,plan_id: str,operation_id: str):
    user=physician(request)
    with store.transaction() as db:
        exam=required(db,'exams',exam_id); plan=required(db,'plans',plan_id)
    if exam['kind']!='patient': raise AppError(422,'DOMAIN_MISMATCH','擷取分析需要病人檢查。')
    if not plan['profile'].get('validated_for_patient'): raise AppError(422,'PROFILE_DEMO_ONLY','請先驗證此方案適用於擷取來源。')
    key = capture_key(user, operation_id)
    reserve_session(user['session_id'],key)
    try:
        with store.read_transaction() as db:guard(db,'exams',exam_id,write=True)
    except BaseException:
        release_session(user['session_id'],key)
        raise
    from .resources import session_active
    preview_operation=store.uid()
    try:
        with store.transaction() as db:
            guard(db,'exams',exam_id,write=True)
            db.execute('INSERT INTO preview_operations(id,operation_key,exam_id,plan_id,actor,basic_input,status,created) VALUES(?,?,?,?,?,?,?,?)',
                       (preview_operation,operation_id,exam_id,plan_id,user['id'],store.dumps(exam['payload']),'running',time.time()))
    except BaseException:
        release_session(user['session_id'],key);raise
    try:
        data=await image_body(request)
        with store.transaction() as db:db.execute('UPDATE preview_operations SET source_sha256=? WHERE id=?',(hashlib.sha256(data).hexdigest(),preview_operation))
        def execute_preview():
            if not session_active(user['session_id'],key):
                raise AppError(410,'CAPTURE_ENDED','擷取已結束，尚未開始的分析已取消。')
            return infer(data,plan,exam['payload'])
        result,artifacts=await run_in_threadpool(execute_preview)
        current(request)
        if not session_active(user['session_id'], key):
            raise AppError(410,'CAPTURE_ENDED','擷取已結束，過期結果不會回填。')
    except BaseException as exc:
        release_session(user['session_id'],key)
        code=exc.code if isinstance(exc,AppError) else 'PREVIEW_FAILED'
        status='cancelled' if code=='CAPTURE_ENDED' else 'failed'
        with store.transaction() as db:
            db.execute('UPDATE preview_operations SET status=?,completed=?,error_code=?,error_message=? WHERE id=?',
                       (status,time.time(),code,exc.message if isinstance(exc,AppError) else '預覽分析失敗或請求中斷；未保存影像不會自動重送。',preview_operation))
        raise
    identifier=store.uid(); result.update(frame_id=identifier,exam_id=exam_id,sha256=hashlib.sha256(data).hexdigest(),preview_operation_id=preview_operation)
    with store.transaction() as db:
        db.execute("UPDATE preview_operations SET status='completed',completed=?,result_summary=? WHERE id=?",
                   (time.time(),store.dumps({'predicted_class':result.get('predicted_class'),'probabilities':result.get('probabilities'),'preview_id':identifier}),preview_operation))
    with _preview_lock:
        _previews.clear()  # One bounded clinical stream; never overlays a different frame.
        _previews[identifier]={'owner':user['session_id'],'operation':operation_id,'created':time.time(),'exam':exam_id,'data':data,'result':result,'artifacts':artifacts,'plan':plan,'basic':exam['payload']}
    return {'id':identifier,'result':result,'artifacts':list(artifacts)}

@router.post('/preview/release')
def release_preview(request: Request, operation_id: str):
    user=physician(request);release_session(user['session_id'],capture_key(user, operation_id))
    return {'released':True}

def capture_key(user, operation_id):
    import re
    if not re.fullmatch(r'[a-f0-9-]{32,36}', operation_id):
        raise AppError(422,'CAPTURE_ID_INVALID','擷取操作識別碼不正確。')
    return 'capture:'+user['session_id']+':'+operation_id


def preview_entry(identifier,user):
    with _preview_lock:
        value=_previews.get(identifier)
        if not value or value['owner']!=user['session_id'] or time.time()-value['created']>300:
            raise AppError(410,'PREVIEW_EXPIRED','影格已更新或到期，請重新凍結。')
        with store.read_transaction() as db:guard(db,'exams',value['exam'])
        return value

@router.get('/preview/{identifier}/{artifact}')
def preview_image(identifier: str,artifact: str,request: Request):
    value=preview_entry(identifier,physician(request))
    if artifact=='original': return Response(value['data'],media_type='image/png',headers={'Cache-Control':'no-store'})
    if artifact not in value['artifacts']: raise AppError(404,'ARTIFACT_MISSING','尚無此產物。')
    buffer=io.BytesIO(); value['artifacts'][artifact].save(buffer,'PNG')
    return Response(buffer.getvalue(),media_type='image/png',headers={'Cache-Control':'no-store'})

@router.post('/preview/{identifier}/save')
def preview_save(identifier: str,request: Request):
    user=physician(request);value=preview_entry(identifier,user)
    return {'id':save_frame(value['data'],value['exam'],'capture',saved=True,analysis=value['result'],artifacts=value['artifacts'],plan=value['plan'],basic=value['basic'],actor=user['id'])}

@router.get('/reports')
def report_list(request: Request):
    physician(request)
    with store.transaction() as db: return [dict(r) for r in db.execute(f"SELECT r.* FROM reports r WHERE ({state_sql('reports','r')})='normal' ORDER BY created DESC LIMIT 500")]

@router.get('/reports/{identifier}')
def report_get(identifier: str,request: Request):
    physician(request)
    with store.transaction() as db:
        report=required(db,'reports',identifier)
        from .lifecycle import chain,effective
        report['effective_lifecycle']=effective(chain(db,'reports',identifier))
        report['versions']=[store.rowdict(r) for r in db.execute('SELECT * FROM report_versions WHERE report_id=? ORDER BY version DESC',(identifier,))]
        report['missing_items']=reports.missing_items(report['versions'][0]['payload']) if report['versions'] else ['尚無報告版本']
    return report

@router.post('/reports')
def report_create(payload: Report,request: Request):
    user=current(request,'reports.manage')
    if payload.action!='draft' or payload.expected_version!=0: raise AppError(422,'DRAFT_REQUIRED','請先建立草稿。')
    with store.transaction() as db:
        snapshot=reports.validate_payload(db,payload.exam_id,payload.fields,payload.frame_ids,payload.include_ai,payload.analysis_run_ids)
        identifier=store.uid()
        db.execute('INSERT INTO reports VALUES(?,?,0,?,?)',(identifier,payload.exam_id,'draft',time.time()))
        number=reports.version(db,identifier,snapshot,'draft',user['id'],0)
    return {'id':identifier,'version':number}

@router.post('/reports/{identifier}/versions')
def report_update(identifier: str,payload: Report,request: Request):
    user=current(request,'reports.manage')
    with pdf_artifacts.lease(identifier),store.transaction() as db:
        report=required(db,'reports',identifier)
        if payload.exam_id!=report['exam_id']: raise AppError(422,'DOMAIN_MISMATCH','不可變更報告檢查。')
        allowed={'draft':{'draft','pending','void'},'pending':{'draft','confirmed','void'},'confirmed':{'revise','void'}}
        if payload.action not in allowed.get(report['state'],set()): raise AppError(409,'REPORT_TRANSITION','報告狀態不允許此操作。')
        old=store.rowdict(db.execute('SELECT * FROM report_versions WHERE report_id=? AND version=?',(identifier,report['current_version'])).fetchone())
        snapshot=reports.validate_payload(db,payload.exam_id,payload.fields,payload.frame_ids,payload.include_ai,payload.analysis_run_ids,old['payload'])
        if payload.action in {'confirmed','void'}:
            snapshot=old['payload']  # Confirmation signs the exact reviewed version.
        if payload.action=='confirmed' and not snapshot['fields'].get('physician','').strip():
            raise AppError(422,'PHYSICIAN_REQUIRED','確認前請填寫判讀醫師。')
        if payload.action=='confirmed' and reports.missing_items(snapshot) and not payload.acknowledge_missing:
            raise AppError(422,'REPORT_INCOMPLETE_ACK_REQUIRED','報告仍有缺項，請明確確認後再確認版本。',{'missing_items':reports.missing_items(snapshot)})
        number=reports.version(db,identifier,snapshot,'draft' if payload.action=='revise' else payload.action,user['id'],payload.expected_version)
        if payload.action=='confirmed':
            db.execute('INSERT INTO report_confirmations VALUES(?,?,?,?,?,?,?)',
                       (identifier,number,payload.expected_version,user['id'],store.dumps(reports.missing_items(snapshot)),int(payload.acknowledge_missing),time.time()))
    return {'id':identifier,'version':number}

@router.get('/reports/{identifier}/versions/{number}/pdf')
def report_pdf(identifier: str,number: int,request: Request,download: bool=False):
    physician(request)
    return pdf_artifacts.read_version(identifier,number,download)

@router.get('/reports/{identifier}/versions/{number}/pdf-artifacts')
def report_pdf_list(identifier:str,number:int,request:Request):
    physician(request)
    with store.read_transaction() as db:return pdf_artifacts.list_records(db,identifier,number)

@router.post('/reports/{identifier}/versions/{number}/pdf')
def report_pdf_generate(identifier:str,number:int,request:Request):
    user=current(request,'reports.manage')
    return pdf_artifacts.generate(identifier,number,user['id'])

@router.get('/pdf-artifacts/{identifier}')
def report_pdf_artifact(identifier:str,request:Request,download:bool=False):
    physician(request)
    return pdf_artifacts.read(identifier,download)

class PdfDeletion(BaseModel):
    expected_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    reason:str=Field(min_length=1,max_length=2000)

@router.delete('/pdf-artifacts/{identifier}')
def report_pdf_delete(identifier:str,payload:PdfDeletion,request:Request):
    user=current(request,'reports.manage')
    if not payload.reason.strip():raise AppError(422,'REASON_REQUIRED','請填寫刪除理由。')
    return pdf_artifacts.delete(identifier,payload.expected_sha256,payload.reason.strip(),user['id'])
