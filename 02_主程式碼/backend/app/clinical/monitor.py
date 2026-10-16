"""Paginated metadata-only clinical views. Never return report text or image bytes."""
from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel,Field

from ..core.errors import AppError
from . import store
from .auth import current

router = APIRouter(prefix='/clinical/monitor', tags=['Clinical monitor'])

# SQL identifiers/expressions are exclusively fixed here; all user input is bound.
VIEWS = {
    'previews': ('preview_operations o JOIN exams e ON e.id=o.exam_id JOIN plans p ON p.id=o.plan_id','o',
                 'o.id,o.exam_id,o.plan_id,o.status,o.created,o.completed,o.error_code,o.error_message,e.title,p.name AS plan_name',
                 "o.id||' '||e.title||' '||p.name",'o.status','e.kind','1 AS sample_count'),
    'cleanup': ('temporary_cleanup c', 'c', 'c.id,c.session_id,c.frame_id,c.exam_id,c.status,c.created,c.completed,c.attempts,c.error AS error_message',
                "c.id||' '||c.frame_id||' '||c.session_id", 'c.status', None, 'NULL AS relationship_count'),
    'patients': ('patients p', 'p', 'p.id,p.code,p.name,p.created', 'p.code||\' \'||p.name', None, None,
                 "(SELECT COUNT(*) FROM exams e WHERE e.patient_id=p.id) AS exam_count"),
    'exams': ('exams e LEFT JOIN patients p ON p.id=e.patient_id', 'e', 'e.id,e.title,e.kind,e.side,e.patient_id,e.created,e.revision,p.name AS patient_name,p.code AS patient_code',
              "e.title||' '||COALESCE(p.name,'')||' '||COALESCE(p.code,'')", None, 'e.kind',
              '(SELECT COUNT(*) FROM frames f WHERE f.exam_id=e.id) AS frame_count,(SELECT COUNT(*) FROM reports r WHERE r.exam_id=e.id) AS report_count'),
    'reports': ('reports r JOIN exams e ON e.id=r.exam_id LEFT JOIN patients p ON p.id=e.patient_id', 'r',
                'r.id,r.exam_id,r.state,r.current_version,r.created,e.title,e.kind,p.name AS patient_name,p.code AS patient_code',
                "r.id||' '||e.title||' '||COALESCE(p.name,'')||' '||COALESCE(p.code,'')", 'r.state', 'e.kind',
                '(SELECT COUNT(*) FROM report_versions v WHERE v.report_id=r.id) AS version_count'),
    'receivers': ('demo_sessions s LEFT JOIN plans p ON p.id=s.plan_id', 's', 's.id,s.state,s.created,s.expires,p.name AS plan_name',
                  "s.id||' '||COALESCE(p.name,'')", 's.state', None,
                  '(SELECT COUNT(*) FROM batches b WHERE b.session_id=s.id) AS batch_count'),
    'operations': ('clinical_operations o JOIN exams e ON e.id=o.exam_id JOIN plans p ON p.id=o.plan_id', 'o',
                   'o.id,o.kind,o.frame_id,o.exam_id,o.plan_id,o.retry_of,o.status,o.created,o.completed,o.error_code,o.error_message,e.title,p.name AS plan_name',
                   "o.id||' '||e.title||' '||p.name", 'o.status', 'e.kind', '1 AS sample_count'),
    'audit': ('audit a LEFT JOIN users u ON u.id=a.actor', 'a',
              "a.id,a.action,a.entity,a.created,CASE WHEN u.actor_kind='local_system' THEN '本機操作' ELSE COALESCE(u.username,'歷史操作者') END AS actor_name", 
              "a.action||' '||a.entity", 'a.action', None, 'NULL AS relationship_count'),
}


@router.get('/{section}')
def listing(section: Literal['patients','exams','reports','receivers','operations','audit','cleanup','previews'], request: Request,
            search: str = Query('',max_length=200), status: str | None = Query(None,max_length=100),
            exact_id: str | None = Query(None,max_length=100),
            lifecycle: Literal['normal','archived','trashed'] = 'normal',
            kind: Literal['patient','demo'] | None = None,
            date_from: float | None = Query(None,ge=0,allow_inf_nan=False),
            date_to: float | None = Query(None,ge=0,allow_inf_nan=False),
            sort: Literal['newest','oldest'] = 'newest',offset: int = Query(0,ge=0),limit: int = Query(50,ge=1,le=200)):
    current(request,'clinical.read')
    if date_from is not None and date_to is not None and date_from > date_to:
        raise AppError(422,'DATE_RANGE_INVALID','開始日期不可晚於結束日期。')
    source, alias, fields, searchable, state, type_field, counts = VIEWS[section]
    clauses=[]; values=[]
    from .lifecycle import state_sql
    lifecycle_entity='exams' if section in {'operations','previews'} else section
    if lifecycle_entity in {'patients','exams','reports'}:
        lifecycle_alias={'patients':'p','exams':'e','reports':'r'}[lifecycle_entity]
        expression=state_sql(lifecycle_entity,lifecycle_alias)
        clauses.append(f'({expression})=?');values.append(lifecycle)
        fields+=f',({expression}) AS effective_lifecycle'
        counts+=f",(SELECT revision FROM clinical_lifecycle WHERE entity='{lifecycle_entity}' AND id={lifecycle_alias}.id) AS lifecycle_revision"
    elif lifecycle!='normal':raise AppError(422,'FILTER_UNSUPPORTED','此紀錄不使用封存／回收篩選。')
    if exact_id is not None:
        clauses.append(f'{alias}.id=?');values.append(exact_id)
    if search.strip():
        clauses.append(f"({searchable}) LIKE ? ESCAPE '\\'")
        values.append('%'+search.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    if status:
        if not state:raise AppError(422,'FILTER_UNSUPPORTED','此清單沒有作業／報告狀態欄位。')
        clauses.append(f'{state}=?');values.append(status)
    if kind:
        if not type_field:raise AppError(422,'FILTER_UNSUPPORTED','此清單不使用病人／示範類型。')
        clauses.append(f'{type_field}=?');values.append(kind)
    for value,operator in ((date_from,'>='),(date_to,'<=')):
        if value is not None:clauses.append(f'{alias}.created{operator}?');values.append(value)
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    direction='DESC' if sort=='newest' else 'ASC'
    with store.read_transaction() as db:
        total=db.execute(f'SELECT COUNT(*) FROM {source}{where}',values).fetchone()[0]
        rows=db.execute(f'SELECT {fields},{counts} FROM {source}{where} ORDER BY {alias}.created {direction},{alias}.id LIMIT ? OFFSET ?',(*values,limit,offset)).fetchall()
    return {'items':[dict(row) for row in rows],'total':total,'offset':offset,'limit':limit,'updated_at':time.time()}


class CleanupRetry(BaseModel):
    reason:str=Field(min_length=1,max_length=2000)


@router.post('/cleanup/{identifier}/retry')
def retry_cleanup(identifier:str,payload:CleanupRetry,request:Request):
    actor=current(request,'clinical.operate')
    if not payload.reason.strip():raise AppError(422,'REASON_REQUIRED','請填寫重試理由。')
    from .temporary_cleanup import run
    with store.read_transaction() as db:
        row=db.execute('SELECT status FROM temporary_cleanup WHERE id=?',(identifier,)).fetchone()
        if not row:raise AppError(404,'NOT_FOUND','找不到清理作業。')
        if row['status'] not in {'failed','interrupted'}:raise AppError(409,'CLEANUP_NOT_RETRYABLE','此清理作業不可重試，請重新整理狀態。')
    result=run(identifier,actor=actor['id'],reason=payload.reason.strip())
    if result['status']!='completed':raise AppError(409,'CLEANUP_FAILED',result['error'])
    return result


@router.post('/operations/{identifier}/retry')
def retry_analysis(identifier:str,request:Request):
    actor=current(request,'clinical.operate')
    from .service import analyze_frame
    with store.read_transaction() as db:
        row=db.execute('SELECT * FROM clinical_operations WHERE id=?',(identifier,)).fetchone()
        if not row:raise AppError(404,'NOT_FOUND','找不到分析作業。')
        if row['status'] not in {'failed','unavailable','interrupted'}:
            raise AppError(409,'OPERATION_NOT_RETRYABLE','只有失敗、無法分析或中斷的作業可重試。')
        frame_id,plan_id=row['frame_id'],row['plan_id']
    return analyze_frame(frame_id,plan_id,actor=actor['id'],retry_of=identifier)


def recover():
    """Startup only; never pretend interrupted synchronous inference completed."""
    with store.transaction() as db:
        db.execute("UPDATE preview_operations SET status='interrupted',completed=?,error_code='PROCESS_RESTARTED',error_message='主程式中斷；未保存預覽影像不會自動重送。' WHERE status='running'",(time.time(),))
        db.execute("UPDATE frames SET status='failed' WHERE status='analyzing' AND id IN (SELECT frame_id FROM clinical_operations WHERE status='running')")
        db.execute("UPDATE clinical_operations SET status='interrupted',completed=?,error_code='PROCESS_RESTARTED',error_message='主程式中斷；未完成分析沒有自動重送。' WHERE status='running'",(time.time(),))
