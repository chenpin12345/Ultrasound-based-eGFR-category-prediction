from __future__ import annotations

import hashlib
import time
import shutil
from pathlib import Path

from ..core.errors import AppError
from . import store
from .analysis import decode, infer


def required(db, table, identifier):
    if table not in {'patients','exams','frames','plans','reports','demo_sessions','batches'}:
        raise ValueError('Invalid table')
    row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
    if not row:
        raise AppError(404,'NOT_FOUND','找不到指定紀錄。')
    from .lifecycle import guard
    guard(db,table,identifier)
    return store.rowdict(row)


def new_exam(db, kind, patient_id, title, side, basic, demo_session_id=None, *, source='manual', actor=None):
    if kind == 'patient':
        patient = required(db,'patients',patient_id)
        from .lifecycle import guard
        guard(db,'patients',patient_id,write=True)
        basic = {**basic,'patient':{k:patient[k] for k in ('id','code','name')}}
    elif patient_id:
        raise AppError(422,'DEMO_PATIENT_FORBIDDEN','示範不可引用正式病人。')
    identifier = store.uid()
    db.execute('INSERT INTO exams(id,kind,patient_id,title,side,payload,revision,created,demo_session_id) VALUES(?,?,?,?,?,?,1,?,?)',
               (identifier,kind,patient_id,title,side,store.dumps(basic),time.time(),demo_session_id))
    from .cases import record_version
    record_version(db,identifier,1,title,side,basic,source,actor)
    return identifier


def frame_folder(identifier):
    """The exact managed folder of one frame id; never a link or another path."""
    import re
    import stat
    if not re.fullmatch('[a-f0-9]{32}',identifier): raise ValueError('Invalid frame identity')
    base=(store.root()/'frames').resolve(); folder=base/identifier
    for part in (base,folder):
        if part.exists() and (part.is_symlink() or getattr(part.lstat(),'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('Frame folder is a link')
    return folder


def write_original(data, identifier):
    """Persist the received bytes unchanged (no re-encoding); returns (path, format)."""
    import os
    _, fmt = decode(data)
    folder = frame_folder(identifier)
    folder.mkdir(parents=True)
    path = folder/('original.jpg' if fmt=='JPEG' else 'original.png')
    try:
        with path.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    except BaseException:
        shutil.rmtree(folder); raise
    return path, fmt


def insert_frame(db, identifier, exam_id, data, path, source, *, saved=False, status='received', result=None):
    db.execute('INSERT INTO frames VALUES(?,?,?,?,?,?,?,?,?)',
               (identifier,exam_id,hashlib.sha256(data).hexdigest(),path.relative_to(store.root()).as_posix(),
                source,store.dumps(result) if result is not None else None,status,int(saved),time.time()))


def save_frame(data, exam_id, source, *, saved=False, analysis=None, artifacts=None, plan=None, basic=None, actor=None):
    decode(data)
    identifier = store.uid()
    digest=hashlib.sha256(data).hexdigest()
    if analysis: analysis={**analysis,'frame_id':identifier,'exam_id':exam_id,'sha256':digest}
    if analysis and plan is None:raise AppError(422,'ANALYSIS_PLAN_REQUIRED','保存分析需要當次封存方案與輸入快照。')
    with store.transaction() as db:
        exam=required(db,'exams',exam_id)
        from .lifecycle import guard
        guard(db,'exams',exam_id,write=True)
        if (source=='network_demo') != (exam['kind']=='demo'):
            raise AppError(422,'DOMAIN_MISMATCH','影像來源與檢查類型不符。')
    path,_=write_original(data,identifier)
    try:
        with store.transaction() as db:
            guard(db,'exams',exam_id,write=True)
            insert_frame(db,identifier,exam_id,data,path,source,saved=saved)
    except BaseException:
        shutil.rmtree(frame_folder(identifier))
        raise
    if analysis:
        from .analysis_runs import publish
        with store.read_transaction() as db:frame=required(db,'frames',identifier)
        try:publish(frame,exam,plan,basic if basic is not None else exam['payload'],analysis,artifacts or {},actor=actor)
        except BaseException:
            # Keep the saved original and journal; never pretend publication succeeded.
            with store.transaction() as db:
                db.execute("UPDATE frames SET status='failed',result=? WHERE id=?",(store.dumps({'code':'PUBLICATION_FAILED','message':'原圖已保存，分析產物保存失敗；請檢查作業紀錄。'}),identifier))
            raise
    return identifier


def analyze_frame(identifier, plan_id, basic=None, *, actor=None, retry_of=None):
    with store.transaction() as db:
        frame = required(db,'frames',identifier)
        from .lifecycle import guard
        guard(db,'frames',identifier,write=True)
        if frame['status']=='analyzing': raise AppError(409,'ANALYSIS_BUSY','此影像已在分析中。')
        exam = required(db,'exams',frame['exam_id'])
        plan = required(db,'plans',plan_id)
        if exam['kind']=='patient' and not plan['profile'].get('validated_for_patient',False):
            raise AppError(422,'PROFILE_DEMO_ONLY','此方案尚未確認病人影像適用性，僅可示範。')
        if retry_of:
            previous=db.execute('SELECT * FROM clinical_operations WHERE id=?',(retry_of,)).fetchone()
            if not previous or previous['frame_id']!=identifier or previous['plan_id']!=plan_id or previous['status'] not in {'failed','unavailable','interrupted'}:
                raise AppError(409,'OPERATION_NOT_RETRYABLE','此作業不可重試或目標已不符。')
        operation_id=store.uid()
        db.execute('''INSERT INTO clinical_operations(id,kind,frame_id,exam_id,plan_id,actor,retry_of,status,created)
                   VALUES(?,'frame_analysis',?,?,?,?,?,'running',?)''',
                   (operation_id,identifier,exam['id'],plan_id,actor,retry_of,time.time()))
        db.execute("UPDATE frames SET status='analyzing' WHERE id=?",(identifier,))
    try:
        result, artifacts = infer(store.managed(frame['path']).read_bytes(),plan,basic or exam['payload'])
        result.update(frame_id=identifier,sha256=frame['sha256'],exam_id=frame['exam_id'])
        from .analysis_runs import publish
        result=publish(frame,exam,plan,basic or exam['payload'],result,artifacts,actor=actor,operation_id=operation_id)
        # Publication finalized both the frame and operation in one transaction.
        # Do not write them again after another analysis may have started.
        return {'status':'completed','result':result,'operation_id':operation_id}
    except AppError as exc:
        if exc.status_code == 409:
            with store.transaction() as db:
                db.execute('UPDATE frames SET status=? WHERE id=?',(frame['status'],identifier))
                db.execute("UPDATE clinical_operations SET status='failed',completed=?,error_code=?,error_message=? WHERE id=?",(time.time(),exc.code,exc.message,operation_id))
            raise
        result={'code':exc.code,'message':exc.message}; state='unavailable'
    except Exception:
        result={'code':'INFERENCE_FAILED','message':'模型執行失敗；請確認模型相容性與運算資源。'}; state='failed'
    with store.transaction() as db:
        db.execute('UPDATE frames SET result=?,status=? WHERE id=?',(store.dumps(result),state,identifier))
        db.execute('UPDATE clinical_operations SET status=?,completed=?,error_code=?,error_message=? WHERE id=?',
                   (state,time.time(),result.get('code') if state!='completed' else None,result.get('message') if state!='completed' else None,operation_id))
        if actor:store.audit(db,actor,'analyze_frame_'+state,operation_id)
    return {'status':state,'result':result,'operation_id':operation_id}


def frame_out(row, plans=None):
    value = store.rowdict(row) if not isinstance(row,dict) else dict(row)
    value.pop('path',None)
    value['url']='/api/clinical/frames/'+value['id']+'/original'
    # The plan actually recorded with this result, never the current default.
    plan_id=(value.get('result') or {}).get('plan_id') if isinstance(value.get('result'),dict) else None
    value['result_plan']={'id':plan_id,**plans[plan_id]} if plans and plan_id in plans else None
    return value
