"""Conservative lifecycle transitions: DB-only, no clinical artifact deletion."""
from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict,Field

from ..core.errors import AppError
from . import store
from .auth import current

Entity=Literal['patients','exams','reports']
Action=Literal['archive','trash','restore','delete_empty']
router=APIRouter(prefix='/clinical/lifecycle',tags=['Clinical lifecycle'])


def chain(db,entity,identifier):
    """Raw minimal queries: do not recurse into service.required."""
    result=[]
    if entity=='frames':
        frame=db.execute('SELECT exam_id FROM frames WHERE id=?',(identifier,)).fetchone()
        if not frame:return result
        entity,identifier='exams',frame['exam_id']
    if entity not in {'patients','exams','reports'}:return result
    row=db.execute('SELECT * FROM clinical_lifecycle WHERE entity=? AND id=?',(entity,identifier)).fetchone()
    if row:result.append(dict(row))
    elif db.execute(f'SELECT 1 FROM {entity} WHERE id=?',(identifier,)).fetchone():
        raise AppError(503,'LIFECYCLE_MISSING','此紀錄缺少生命週期狀態，已停止存取；請檢查資料庫遷移與完整性。')
    if entity=='reports':
        report=db.execute('SELECT exam_id FROM reports WHERE id=?',(identifier,)).fetchone()
        if report:result+=chain(db,'exams',report['exam_id'])
    if entity=='exams':
        exam=db.execute('SELECT patient_id FROM exams WHERE id=?',(identifier,)).fetchone()
        if exam and exam['patient_id']:result+=chain(db,'patients',exam['patient_id'])
    return result


def effective(rows):
    return 'trashed' if any(r['state']=='trashed' for r in rows) else 'archived' if any(r['state']=='archived' for r in rows) else 'normal'


def guard(db,entity,identifier,*,write=False):
    if entity=='frames' and db.execute("SELECT 1 FROM temporary_cleanup WHERE frame_id=? AND status!='completed'",(identifier,)).fetchone():
        raise AppError(409,'TEMPORARY_CLEANUP_PENDING','此未保存影像正在清理，或前次清理中斷；請從作業監控檢查與重試。')
    state=effective(chain(db,entity,identifier))
    if state=='trashed':raise AppError(410,'RECORD_RECYCLED','此紀錄或所屬病人／檢查已回收，只能從回收區檢視摘要及恢復。')
    if write and state!='normal':raise AppError(409,'RECORD_ARCHIVED','此紀錄或所屬病人／檢查已封存，恢復前不可新增或修改內容。')


def state_sql(entity,alias):
    """Only trusted call sites supply SQL identifiers, never request text."""
    if (entity,alias) not in {('patients','p'),('exams','e'),('reports','r')}:
        raise ValueError('Unsupported lifecycle query')
    membership=f"(l.entity='{entity}' AND l.id={alias}.id)"
    if entity=='exams':membership+=" OR (l.entity='patients' AND l.id=e.patient_id)"
    if entity=='reports':membership+=" OR (l.entity='exams' AND l.id=r.exam_id) OR (l.entity='patients' AND l.id=(SELECT patient_id FROM exams WHERE id=r.exam_id))"
    return "CASE WHEN EXISTS(SELECT 1 FROM clinical_lifecycle l WHERE ("+membership+") AND l.state='trashed') THEN 'trashed' WHEN EXISTS(SELECT 1 FROM clinical_lifecycle l WHERE ("+membership+") AND l.state='archived') THEN 'archived' ELSE 'normal' END"


def describe(db,entity,identifier):
    if not db.execute(f'SELECT 1 FROM {entity} WHERE id=?',(identifier,)).fetchone():
        raise AppError(404,'NOT_FOUND','找不到指定紀錄。')
    rows=chain(db,entity,identifier)
    if not rows:raise AppError(404,'NOT_FOUND','找不到指定紀錄。')
    row=rows[0]
    target=dict(db.execute(f'SELECT * FROM {entity} WHERE id=?',(identifier,)).fetchone())
    counts={}
    exam_ids=[]
    if entity=='patients':
        exam_ids=[r[0] for r in db.execute('SELECT id FROM exams WHERE patient_id=?',(identifier,))]
        counts['exams']=len(exam_ids)
    else:exam_ids=[identifier if entity=='exams' else target['exam_id']]
    if exam_ids:
        slots=','.join('?' for _ in exam_ids)
        for table in ('frames','reports','clinical_operations','preview_operations'):
            counts[table]=db.execute(f'SELECT COUNT(*) FROM {table} WHERE exam_id IN ({slots})',exam_ids).fetchone()[0]
        counts['transfers']=db.execute(f'SELECT COUNT(*) FROM items i JOIN frames f ON f.id=i.frame_id WHERE f.exam_id IN ({slots})',exam_ids).fetchone()[0]
        counts['linked_receivers']=db.execute(f'SELECT COUNT(*) FROM exams WHERE id IN ({slots}) AND demo_session_id IS NOT NULL',exam_ids).fetchone()[0]
        # Edits after creation are history; only the creation version counts as empty.
        counts['case_data_edits']=db.execute(f'SELECT COUNT(*) FROM exam_basic_versions WHERE exam_id IN ({slots}) AND revision>1',exam_ids).fetchone()[0]
    if entity=='reports':counts['versions']=db.execute('SELECT COUNT(*) FROM report_versions WHERE report_id=?',(identifier,)).fetchone()[0]
    return {'entity':entity,'id':identifier,'name':target.get('name') or target.get('title') or f'報告 v{target.get("current_version",0)}',
            'state':row['state'],'effective_state':effective(rows),'revision':row['revision'],'restore_state':row['restore_state'],
            'parents':[{'entity':r['entity'],'id':r['id'],'state':r['state']} for r in rows[1:]],'references':counts}


def busy_reasons(db,entity,identifier):
    from .resources import any_session_active,clinical_lock
    reasons=[]
    from .pdf_artifacts import busy
    if busy(db,entity,identifier):reasons.append('此紀錄的 PDF 正在生成、傳送或刪除。')
    # A capture may not yet have a saved frame. Block conservatively while any
    # local stream owns a lease or inference is still computing.
    if any_session_active() or clinical_lock.locked():reasons.append('擷取／分析來源仍在使用，請先停止來源並等待運算退出。')
    if entity=='patients':
        exams=[r[0] for r in db.execute('SELECT id FROM exams WHERE patient_id=?',(identifier,))]
    elif entity=='exams':exams=[identifier]
    else:exams=[db.execute('SELECT exam_id FROM reports WHERE id=?',(identifier,)).fetchone()[0]]
    if exams:
        slots=','.join('?' for _ in exams)
        if db.execute(f"SELECT 1 FROM temporary_cleanup WHERE exam_id IN ({slots}) AND status!='completed' LIMIT 1",exams).fetchone():reasons.append('暫存影像清理尚未完成，請先從作業監控檢查與重試。')
        if db.execute(f"SELECT 1 FROM frames WHERE exam_id IN ({slots}) AND status='analyzing' LIMIT 1",exams).fetchone():reasons.append('此檢查的影像仍在分析。')
        if db.execute(f"SELECT 1 FROM clinical_operations WHERE exam_id IN ({slots}) AND status='running' LIMIT 1",exams).fetchone():reasons.append('仍有執行中的分析作業。')
        if db.execute(f"SELECT 1 FROM preview_operations WHERE exam_id IN ({slots}) AND status='running' LIMIT 1",exams).fetchone():reasons.append('仍有執行中的預覽分析。')
        if db.execute(f"SELECT 1 FROM exams e JOIN demo_sessions s ON s.id=e.demo_session_id WHERE e.id IN ({slots}) AND s.state='active' LIMIT 1",exams).fetchone():reasons.append('此示範案例的雙機接收仍開啟，請先結束接收。')
    return reasons


def preflight(db,entity,identifier,action):
    result=describe(db,entity,identifier)
    reasons=busy_reasons(db,entity,identifier)
    state=result['state']
    if action in {'archive','trash'}:
        if result['effective_state']!='normal' and not (action=='trash' and result['effective_state']=='archived'):
            reasons.append('目前生命週期不允許此操作。')
    elif action=='restore':
        if state=='normal':reasons.append('此紀錄本身未封存或回收，請先恢復受限父層。')
        if any(parent['state']!='normal' for parent in result['parents']):reasons.append('請先恢復所屬病人／檢查，再恢復此紀錄。')
    elif action=='delete_empty':
        if entity=='reports' or any(result['references'].values()):reasons.append('有關聯內容／歷史引用，或對象為報告，不能永久刪除。')
        if any(parent['state']!='normal' for parent in result['parents']):reasons.append('父層受限時不能永久刪除子層。')
    return {**result,'action':action,'allowed':not reasons,'blocking_reasons':reasons,
            'recoverable':action!='delete_empty','files_deleted':False}


class Transition(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    action: Action
    expected_revision:int=Field(ge=1)
    reason:str=Field(min_length=1,max_length=2000)


@router.get('/{entity}/{identifier}')
def inspect(entity:Entity,identifier:str,request:Request,action:Action='trash'):
    current(request,'clinical.read')
    with store.read_transaction() as db:return preflight(db,entity,identifier,action)


@router.post('/{entity}/{identifier}')
def transition(entity:Entity,identifier:str,payload:Transition,request:Request):
    actor=current(request,'reports.manage' if entity=='reports' else 'clinical.operate')
    # Serialize with the current PDF renderer until its per-report artifact
    # coordinator replaces it. No lock is released before DB commit.
    from .reports import _render_lock
    if not _render_lock.acquire(blocking=False):raise AppError(409,'REPORT_BUSY','PDF 作業進行中，請稍後重試。')
    try:
        with store.transaction() as db:
            before=preflight(db,entity,identifier,payload.action)
            if before['revision']!=payload.expected_revision:raise AppError(409,'REVISION_CONFLICT','資料已變更，請重新預檢。')
            if not before['allowed']:raise AppError(409,'LIFECYCLE_BLOCKED','此操作目前被阻擋。',{'reasons':before['blocking_reasons']})
            if payload.action=='delete_empty':
                if entity=='exams':db.execute('DELETE FROM exam_basic_versions WHERE exam_id=?',(identifier,))
                db.execute(f'DELETE FROM {entity} WHERE id=?',(identifier,))
                after={'state':'deleted','id':identifier,'files_deleted':False}
            else:
                state={'archive':'archived','trash':'trashed','restore':before['restore_state'] if before['state']=='trashed' else 'normal'}[payload.action]
                restore=before['state'] if payload.action=='trash' else 'normal'
                db.execute('UPDATE clinical_lifecycle SET state=?,restore_state=?,revision=revision+1,updated=? WHERE entity=? AND id=?',(state,restore,time.time(),entity,identifier))
                after=describe(db,entity,identifier)
            event=store.uid()
            db.execute('INSERT INTO clinical_lifecycle_events VALUES(?,?,?,?,?,?,?,?,?)',(event,entity,identifier,payload.action,actor['id'],payload.reason,store.dumps(before),store.dumps(after),time.time()))
            store.audit(db,actor['id'],'lifecycle_'+payload.action,identifier)
        return {'event_id':event,**after}
    finally:_render_lock.release()
