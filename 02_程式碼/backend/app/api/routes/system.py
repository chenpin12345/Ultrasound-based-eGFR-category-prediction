from __future__ import annotations

import json
import platform
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from ...core import audit
from ...core.config import get_settings
from ...db.models_research import Batch, ClinicalFeedback, Image, Patient
from ...db.models_system import AuditEntry, Job
from ...db.session import session_scope
from ...services import backups, doctor, index, settings_store, workspace
from ..deps import operator

router = APIRouter(tags=['系統'])


@router.get('/health')
def health():
    return {'status': 'ok'}


@router.get('/system/info')
def info():
    settings = get_settings()
    return {'python': platform.python_version(), 'host': settings.host, 'port': settings.port, 'version': '0.2.0（M1 資料基礎）'}


@router.get('/system/doctor')
def run_doctor():
    return {'checks': doctor.run()}


@router.get('/settings')
def get_settings_values():
    return settings_store.get_all()


@router.put('/settings')
def put_settings(values: dict[str, Any], request: Request):
    result = settings_store.update(values)
    audit.record(operator(request), '修改設定', 'settings', ','.join(values))
    return result


@router.get('/people')
def people():
    return {'people': settings_store.list_people()}


class PersonIn(BaseModel):
    name: str
    kind: str


@router.post('/people', status_code=201)
def add_person(payload: PersonIn, request: Request):
    person = settings_store.add_person(payload.name, payload.kind)
    audit.record(operator(request), '新增人員', 'person', str(person['id']), {'kind': payload.kind})
    return person


class PersonPatch(BaseModel):
    active: bool


@router.patch('/people/{person_id}')
def patch_person(person_id: int, payload: PersonPatch, request: Request):
    settings_store.set_active(person_id, payload.active)
    audit.record(operator(request), '啟用人員' if payload.active else '停用人員', 'person', str(person_id))
    return {'ok': True}


@router.get('/audit')
def audit_log(limit: int = Query(200, ge=1, le=1000)):
    with session_scope('system') as db:
        rows = db.query(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit).all()
        return {
            'entries': [
                {'time': r.time, 'actor': r.actor, 'action': r.action, 'target_type': r.target_type, 'target_id': r.target_id, 'result': r.result, 'detail': json.loads(r.detail_json or '{}')}
                for r in rows
            ]
        }


@router.get('/backups')
def list_backups():
    return {'backups': backups.list_backups()}


@router.post('/backups/snapshot')
def snapshot(request: Request):
    result = backups.daily_snapshot(force=True)
    audit.record(operator(request), '建立資料庫快照', 'backup', result['folder'])
    return result


def _clinical_counts() -> dict:
    """通知鈴的醫師端事件（B2）；醫師端資料庫有問題時不影響研究端的提醒。"""
    try:
        from ...clinical import home

        return home.counts()
    except Exception:  # noqa: BLE001
        return {}


@router.get('/overview')
def overview():
    with session_scope('research') as db:
        counts: dict[str, int] = {}
        for (status,) in db.query(Image.status).all():
            counts[status] = counts.get(status, 0) + 1
        patients = db.query(Patient).count()
        unmatched = db.query(Image).filter(Image.patient_id.is_(None), Image.status != 'excluded').count()
        batches = db.query(Batch).count()
        feedback = db.query(ClinicalFeedback).filter(ClinicalFeedback.decision.is_(None)).count()
    with session_scope('system') as db:
        failed = db.query(Job).filter(Job.status == 'failed').count()
        running = db.query(Job).filter(Job.status.in_(['queued', 'running', 'stopping'])).count()
    return {
        'images': {'total': sum(counts.values()), **counts},
        'patients': patients,
        'unmatched_images': unmatched,
        'batches': batches,
        'pending_feedback': feedback,
        'clinical': _clinical_counts(),
        'failed_jobs': failed,
        'running_jobs': running,
    }


# ---- 工作區整理（M2.5，決策 D29） ----
@router.post('/system/index')
def refresh_index(request: Request):
    result = index.refresh()
    audit.record(operator(request), '更新索引', 'index', '09_索引', {'skipped': result['skipped']})
    return result


class OpenFolderIn(BaseModel):
    kind: str
    id: str = ''


@router.post('/system/open-folder')
def open_folder(payload: OpenFolderIn):
    return workspace.open_folder(payload.kind, payload.id)


@router.get('/system/folder-migration')
def folder_migration_preview():
    return workspace.migration_preview()


@router.post('/system/folder-migration')
def folder_migration(request: Request):
    result = workspace.migrate_folders(operator(request))
    audit.record(operator(request), '依任務搬移訓練資料夾', 'models', f'{result["moved"]} 個', {'skipped': len(result['skipped'])})
    index.refresh_quietly()
    return result
