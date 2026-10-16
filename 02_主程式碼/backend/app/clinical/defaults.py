"""Physician default analysis plans, managed from the model center.

A default always names one immutable sealed plan (or explicit preview-only) per
source. It is never derived from the research "active" model, the newest upload or
list order. Sessions copy the resolved plan when they are created, so a later
default change only affects new sessions.
"""
from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, model_validator

from ..core.errors import AppError
from . import store
from .auth import current
from .cases import LABELS

router=APIRouter(prefix='/clinical',tags=['Physician defaults'])
SOURCES={'network_demo':'圖片傳輸','capture':'設備擷取'}


def requirements(plan):
    """Case fields the sealed classifier needs, decided by the immutable snapshot."""
    architecture=str(plan['snapshot']['models']['classifier'].get('architecture') or '').lower()
    return ['age','has_diabetes'] if 'mlp' in architecture else []


def summary(plan):
    snap=plan['snapshot']; classifier=snap['models']['classifier']; manifest=classifier.get('manifest') or {}
    segmenter=snap['models'].get('segmenter')
    return {'id':plan['id'],'name':plan['name'],'created':plan['created'],
            'profile':{k:plan['profile'].get(k) for k in ('mode','width','height','validated_for_patient')},
            'classifier':{'name':manifest.get('name'),'version':manifest.get('version'),'architecture':classifier.get('architecture'),
                          'class_count':manifest.get('class_count'),'class_names':manifest.get('class_names'),'sha256':classifier['sha256']},
            'segmenter':{'name':(segmenter.get('manifest') or {}).get('name'),'sha256':segmenter['sha256']} if segmenter else None,
            'manifest_sha256':snap.get('manifest_sha256'),'device':snap.get('device'),
            'requirements':[{'field':f,'label':LABELS[f]} for f in requirements(plan)]}


def problems(plan,source):
    """Why this sealed plan cannot analyze images from this source (empty = usable)."""
    from .analysis import verify_plan
    result=[]
    profile=plan['profile']
    if profile.get('mode')=='unknown': result.append('方案的來源前處理尚未確認，只能預覽。')
    elif not profile.get('width') or not profile.get('height'): result.append('方案未記錄來源影像尺寸。')
    if source=='capture' and not profile.get('validated_for_patient'):
        result.append('方案尚未確認適用於病人擷取影像。')
    try: verify_plan(plan)
    except AppError as exc: result.append(exc.message)
    return result


def latest(db,source):
    row=db.execute('SELECT * FROM clinical_default_plans WHERE source=? ORDER BY created DESC,rowid DESC LIMIT 1',(source,)).fetchone()
    return dict(row) if row else None


def status(db,source):
    from .service import required
    setting=latest(db,source)
    value={'source':source,'label':SOURCES[source],'setting':setting,'mode':setting['mode'] if setting else None,
           'plan':None,'analyzable':False,'problems':[]}
    if not setting:
        value['problems']=['模型區尚未設定'+SOURCES[source]+'的預設分析方案。']
    elif setting['mode']=='plan':
        plan=required(db,'plans',setting['plan_id'])
        value['plan']=summary(plan); value['problems']=problems(plan,source); value['analyzable']=not value['problems']
    return value


def check(db,plan_id,source):
    from .service import required
    plan=required(db,'plans',plan_id)
    issues=problems(plan,source)
    if issues: raise AppError(422,'PLAN_NOT_COMPATIBLE','此方案不能用於'+SOURCES[source]+'：'+' '.join(issues))
    return plan


def resolve(db,source,mode,plan_id=None):
    """Resolve a session's analysis choice once; returns (plan_mode, plan_id, setting_id)."""
    if mode=='preview_only': return 'preview_only',None,None
    if mode=='plan':
        check(db,plan_id,source); return 'plan',plan_id,None
    setting=latest(db,source)
    if not setting:
        raise AppError(409,'DEFAULT_PLAN_MISSING','模型區尚未設定'+SOURCES[source]+'的預設分析方案；請先設定，或在進階設定明確選擇「僅接收及預覽」。')
    if setting['mode']=='preview_only': return 'preview_only',None,setting['id']
    try: check(db,setting['plan_id'],source)
    except AppError as exc:
        raise AppError(409,'DEFAULT_PLAN_INVALID','目前預設方案無法使用，不會自動改用其他方案或改成僅預覽。'+exc.message) from None
    return 'plan',setting['plan_id'],setting['id']


class DefaultPlan(BaseModel):
    source: Literal['network_demo','capture']
    mode: Literal['plan','preview_only']
    plan_id: str|None=None
    evidence: str=Field(min_length=1,max_length=2000)

    @model_validator(mode='after')
    def consistent(self):
        if (self.mode=='plan')!=(self.plan_id is not None): raise ValueError('mode=plan 需要 plan_id；preview_only 不可帶 plan_id')
        if not self.evidence.strip(): raise ValueError('請填寫相容依據')
        return self


@router.get('/default-plans')
def default_plans(request: Request):
    current(request,'clinical.read')
    with store.read_transaction() as db:
        history=[dict(r) for r in db.execute('SELECT d.*,p.name AS plan_name FROM clinical_default_plans d LEFT JOIN plans p ON p.id=d.plan_id ORDER BY d.created DESC LIMIT 50')]
        return {'sources':{source:status(db,source) for source in SOURCES},'history':history}


@router.post('/default-plans')
def default_plan_set(payload: DefaultPlan,request: Request):
    user=current(request,'models.manage')
    with store.transaction() as db:
        if payload.mode=='plan': check(db,payload.plan_id,payload.source)
        identifier=store.uid()
        db.execute('INSERT INTO clinical_default_plans VALUES(?,?,?,?,?,?,?)',
                   (identifier,payload.source,payload.mode,payload.plan_id,payload.evidence.strip(),user['id'],time.time()))
        store.audit(db,user['id'],'set_default_plan',identifier)
    return {'id':identifier}
