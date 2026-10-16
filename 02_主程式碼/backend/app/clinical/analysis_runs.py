"""Persistence wrapper only: never changes inference, masks or feature values."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from PIL import Image
from ..core.errors import AppError
from . import store
from .lifecycle import guard


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get(db,run_id,frame_id=None):
    row=db.execute('SELECT * FROM analysis_runs WHERE id=?',(run_id,)).fetchone()
    if not row:raise AppError(404,'ANALYSIS_NOT_FOUND','找不到指定分析版本。')
    result=store.rowdict(row)
    if frame_id is not None and result['frame_id']!=frame_id:
        raise AppError(422,'ANALYSIS_FRAME_MISMATCH','分析版本不屬於指定影像。')
    guard(db,'frames',result['frame_id'])
    return result


def latest(db,frame_id):
    row=db.execute('SELECT run_id FROM latest_analysis WHERE frame_id=?',(frame_id,)).fetchone()
    return get(db,row['run_id'],frame_id) if row else None


def publish(frame,exam,plan,basic,result,artifacts,*,actor=None,operation_id=None):
    """Journal first, write new files, atomically commit an immutable snapshot.

    An interrupted folder is retained with its journal and never served as a
    completed run. No existing original, run or legacy artifact is overwritten.
    """
    identifier=store.uid()
    relative=f'frames/{frame["id"]}/analyses/{identifier}'
    with store.transaction() as db:
        guard(db,'frames',frame['id'],write=True)
        db.execute('INSERT INTO analysis_publications VALUES(?,?,?,\'staging\',?,NULL,NULL)',(identifier,frame['id'],relative,time.time()))
    try:
        original=store.managed(frame['path'])
        if sha(original)!=frame['sha256']:raise AppError(409,'ORIGINAL_CHANGED','原始影像雜湊不符，停止保存分析。')
        with Image.open(original) as source:original_size=list(source.size)
        folder=store.managed(relative);folder.mkdir(parents=True,exist_ok=False)
        manifest={}
        for name,image in artifacts.items():
            if name not in {'processed','mask','overlay'}:raise AppError(422,'ARTIFACT_INVALID','未知的分析產物名稱。')
            temporary=folder/(name+'.tmp');target=folder/(name+'.png')
            with temporary.open('wb') as saved:
                image.save(saved,format='PNG')
                saved.flush()
                os.fsync(saved.fileno())
            os.replace(temporary,target)
            manifest[name]={'path':target.relative_to(store.root()).as_posix(),'sha256':sha(target),'size':list(image.size)}
        if 'mask' in manifest and 'overlay' in manifest and manifest['mask']['size']!=manifest['overlay']['size']:
            raise AppError(422,'ARTIFACT_GRID_MISMATCH','遮罩與疊圖尺寸不一致，不發布分析。')
        if result.get('has_mask') and not {'mask','overlay','processed'}.issubset(manifest):
            raise AppError(422,'ARTIFACT_MISSING','分割分析缺少必要產物，不發布分析。')
        model_snap=plan.get('snapshot',{})
        profile=plan.get('profile',{})
        processed_size=manifest.get('processed',{}).get('size')
        coordinates={'source_size':original_size,'processed_size':processed_size,
                     'mask_size':manifest.get('mask',{}).get('size'),'overlay_size':manifest.get('overlay',{}).get('size'),
                     'profile_mode':profile.get('mode'),'version':1}
        if profile.get('mode')=='legacy':
            coordinates.update(resize_before_crop=[1600,1200],crop_xyxy=[235,90,1259,1114])
        elif profile.get('mode')=='prepared':coordinates['crop_xyxy']=None
        # Record the unchanged implementations rather than inventing provenance.
        code=Path(__file__).resolve().parents[1]
        implementation={str(path.relative_to(code)).replace('\\','/'):sha(path) for path in [code/'clinical/analysis.py',code/'ml/features.py',code/'ml/contracts.py',code/'ml/models.py']}
        frozen_result={**result,'analysis_run_id':identifier}
        snapshot={'version':1,'evidence':'verified','original':{'id':frame['id'],'sha256':frame['sha256'],'size':original_size},
                  'exam':{'id':exam['id'],'kind':exam['kind'],'side':exam['side'],'revision':exam['revision']},
                  'plan_id':plan['id'],'plan_snapshot':model_snap,'profile':profile,
                  'configuration_sha256':hashlib.sha256(store.dumps({'plan':model_snap,'profile':profile}).encode()).hexdigest(),
                  'basic_input':basic,'coordinates':coordinates,'implementation_sha256':implementation,
                  'result':frozen_result,'artifacts':manifest,'completed_at':time.time()}
        with store.transaction() as db:
            guard(db,'frames',frame['id'],write=True)
            db.execute('INSERT INTO analysis_runs VALUES(?,?,?,?,?,?,?,?,?)',(identifier,frame['id'],exam['id'],plan['id'],operation_id,actor,'verified',store.dumps(snapshot),snapshot['completed_at']))
            db.execute('INSERT INTO latest_analysis VALUES(?,?) ON CONFLICT(frame_id) DO UPDATE SET run_id=excluded.run_id',(frame['id'],identifier))
            db.execute("UPDATE frames SET result=?,status='completed' WHERE id=?",(store.dumps(frozen_result),frame['id']))
            db.execute("UPDATE analysis_publications SET state='published',completed=? WHERE id=?",(time.time(),identifier))
            if operation_id:
                updated=db.execute("UPDATE clinical_operations SET status='completed',completed=? WHERE id=? AND status='running'",(time.time(),operation_id))
                if updated.rowcount!=1:raise AppError(409,'OPERATION_ENDED','分析作業已中止，過期結果不發布。')
                if actor:store.audit(db,actor,'analyze_frame_completed',operation_id)
        return frozen_result
    except BaseException as exc:
        with store.transaction() as db:
            db.execute("UPDATE analysis_publications SET state='failed',completed=?,error=? WHERE id=? AND state='staging'",(time.time(),getattr(exc,'code','PUBLICATION_FAILED'),identifier))
        raise


def artifact(db,run_id,name,frame_id=None):
    run=get(db,run_id,frame_id)
    if run['evidence']!='verified':raise AppError(409,'ANALYSIS_UNVERIFIED','舊分析產物關聯未核實，不顯示為有效分析附件。')
    item=run['snapshot']['artifacts'].get(name)
    if not item:raise AppError(404,'ARTIFACT_MISSING','此分析版本沒有這項產物。')
    path=store.managed(item['path'])
    if not path.is_file() or sha(path)!=item['sha256']:raise AppError(409,'ARTIFACT_CHANGED','分析產物遺失或雜湊不符。')
    with Image.open(path) as image:
        if list(image.size)!=item['size']:raise AppError(409,'ARTIFACT_GRID_MISMATCH','分析產物尺寸不符。')
    return path


def public(run):
    value=json.loads(store.dumps(run))
    for item in value['snapshot'].get('artifacts',{}).values():item.pop('path',None)
    for model in value['snapshot'].get('plan_snapshot',{}).get('models',{}).values():model.pop('path',None)
    return value


def recover():
    with store.transaction() as db:
        db.execute("UPDATE analysis_publications SET state='interrupted',completed=?,error='PROCESS_RESTARTED' WHERE state='staging'",(time.time(),))
