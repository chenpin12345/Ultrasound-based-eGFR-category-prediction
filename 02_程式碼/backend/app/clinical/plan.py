"""醫師端的分析方案：分割、eGFR、回音分級三區各選一個模型（D41）。

- 優先「臨床上線」；某一區沒有時可以選「候選」，結果標示「尚未臨床核准・僅供研究展示」（D40）。
- 「研究」「退役」階段不能選；分析時再確認一次。
- 被分析方案或已簽核報告用到的模型不能退役、不能移入回收桶（M3-3 模型安全）。
"""

from __future__ import annotations

import json
from typing import Any

from ..core.errors import AppError
from ..db.models_research import ModelEntry
from ..db.session import session_scope

ZONES = ('segmentation', 'egfr', 'grade')
ALLOWED_STAGES = ('clinical', 'candidate')
CANDIDATE_LABEL = '尚未臨床核准・僅供研究展示'
EMPTY_PLAN = {zone: None for zone in ZONES}


def _models() -> dict[str, ModelEntry]:
    with session_scope('research') as db:
        rows = db.query(ModelEntry).filter(ModelEntry.trashed_at.is_(None)).all()
        for r in rows:
            db.expunge(r)
    return {r.id: r for r in rows}


def options() -> dict[str, list[dict[str, Any]]]:
    """每一區可以選的模型（臨床上線排前面）。"""
    out: dict[str, list[dict[str, Any]]] = {zone: [] for zone in ZONES}
    for m in _models().values():
        if m.task in out and m.stage in ALLOWED_STAGES:
            manifest = json.loads(m.manifest_json)
            oof = (manifest.get('metrics') or {}).get('oof') or {}
            out[m.task].append({'id': m.id, 'stage': m.stage, 'inputs': manifest.get('inputs'), 'classes': manifest.get('classes'),
                                'score': oof.get('auc_lt60', oof.get('dice_mean', oof.get('qwk'))), 'created_at': m.created_at})
    for zone in out:
        out[zone].sort(key=lambda o: (o['stage'] != 'clinical', o['id']))
    return out


def validate(plan: Any) -> dict[str, str | None]:
    """設定頁儲存分析方案時檢查：只能有三區、模型存在且任務相符、階段是臨床上線或候選。"""
    if not isinstance(plan, dict) or set(plan) - set(ZONES):
        raise AppError(422, 'BAD_SETTING', '分析方案只能指定分割、eGFR、回音分級三區的模型。')
    models = _models()
    clean: dict[str, str | None] = dict(EMPTY_PLAN)
    for zone, model_id in plan.items():
        if not model_id:
            continue
        m = models.get(model_id)
        if m is None or m.task != zone:
            raise AppError(422, 'BAD_SETTING', f'{model_id} 不是可用的{ZONE_LABELS[zone]}模型。')
        if m.stage not in ALLOWED_STAGES:
            raise AppError(422, 'BAD_SETTING', f'{model_id} 目前是「{STAGE_LABELS.get(m.stage, m.stage)}」，分析方案只能選「臨床上線」或「候選」的模型。')
        clean[zone] = model_id
    return clean


ZONE_LABELS = {'segmentation': '分割', 'egfr': 'eGFR', 'grade': '回音分級'}
STAGE_LABELS = {'research': '研究', 'candidate': '候選', 'clinical': '臨床上線', 'retired': '退役'}


def current() -> dict[str, Any]:
    """目前的分析方案、每一區用的模型與階段、是否有候選模型、還有哪些問題（開始前檢查用）。"""
    from ..services import settings_store

    plan = {**EMPTY_PLAN, **(settings_store.get_all().get('clinical_plan') or {})}
    models = _models()
    zones: dict[str, Any] = {}
    problems: list[str] = []
    for zone in ZONES:
        model_id = plan.get(zone)
        m = models.get(model_id) if model_id else None
        if model_id and (m is None or m.stage not in ALLOWED_STAGES):
            problems.append(f'{ZONE_LABELS[zone]}模型 {model_id} 已不能使用（被移除或階段改變），請重新選擇。')
            m = None
        zones[zone] = {'model_id': m.id if m else None, 'stage': m.stage if m else None, 'candidate': bool(m and m.stage == 'candidate')}
    egfr = models.get(zones['egfr']['model_id'] or '')
    if egfr is not None:
        manifest = json.loads(egfr.manifest_json)
        source = (manifest.get('input') or {}).get('mask_source') or {}
        seg = models.get(zones['segmentation']['model_id'] or '')
        if source.get('seg_run_id') and (seg is None or seg.run_id != source['seg_run_id']):
            problems.append(f'eGFR 模型 {egfr.id} 需要分割訓練 {source["seg_run_id"]} 註冊的分割模型（④ 遮罩通道）。')
    if not any(z['model_id'] for z in zones.values()):
        problems.append('還沒有選任何模型：請到「設定 › 醫師端」選分析方案，否則自動分析是空的。')
    return {'zones': zones, 'candidate': any(z['candidate'] for z in zones.values()), 'candidate_label': CANDIDATE_LABEL, 'problems': problems}


def referenced_models() -> dict[str, str]:
    """被分析方案或已簽核報告用到的模型 → 原因。"""
    from ..db.models_clinical import ClinicalAnalysis, ClinicalReport
    from ..services import settings_store

    refs: dict[str, str] = {}
    for zone, model_id in (settings_store.get_all().get('clinical_plan') or {}).items():
        if model_id:
            refs[model_id] = f'醫師端分析方案（{ZONE_LABELS.get(zone, zone)}）'
    with session_scope('clinical') as db:
        signed = db.query(ClinicalReport.analysis_id).filter(ClinicalReport.status == 'signed', ClinicalReport.analysis_id.isnot(None)).all()
        ids = [a for (a,) in signed]
        for a in db.query(ClinicalAnalysis).filter(ClinicalAnalysis.id.in_(ids)).all() if ids else []:
            for info in json.loads(a.models_json or '{}').values():
                if isinstance(info, dict) and info.get('model_id'):
                    refs.setdefault(info['model_id'], f'已簽核報告的分析 {a.id}')
    return refs


def ensure_not_referenced(model_ids: list[str], action: str) -> None:
    refs = referenced_models()
    used = [f'{m}（{refs[m]}）' for m in model_ids if m in refs]
    if used:
        raise AppError(409, 'MODEL_IN_USE', f'{"、".join(used)} 正在被醫師端使用，不能{action}。請先在「設定 › 醫師端」換掉，或保留這個模型。')
