"""醫師端首頁（B1）與通知（B2）用的統計。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db.models_clinical import ClinicalAnalysis, ClinicalExam, ClinicalReport, ReceiverSession
from ..db.session import session_scope


def counts() -> dict[str, Any]:
    """通知鈴與首頁共用：待補資料、版面不符、待簽核、分析失敗、今天收到的檢查、是否接收中。"""
    from . import receiver

    today = datetime.now().strftime('%Y-%m-%d')
    with session_scope('clinical') as db:
        live = db.query(ClinicalExam).filter(ClinicalExam.trashed_at.is_(None))
        by_status: dict[str, int] = {}
        for (status,) in live.with_entities(ClinicalExam.status).all():
            by_status[status] = by_status.get(status, 0) + 1
        today_n = live.filter(ClinicalExam.received_at >= today).count()
        pending = db.query(ClinicalReport).filter(ClinicalReport.trashed_at.is_(None), ClinicalReport.status == 'pending').count()
        drafts = db.query(ClinicalReport).filter(ClinicalReport.trashed_at.is_(None), ClinicalReport.status == 'draft').count()
        active = db.query(ReceiverSession).filter(ReceiverSession.status == 'active').first() is not None
    return {'needs_data': by_status.get('needs_data', 0), 'layout_mismatch': by_status.get('layout_mismatch', 0), 'failed': by_status.get('failed', 0) + by_status.get('partial', 0),
            'ready': by_status.get('ready', 0), 'analyzing': by_status.get('analyzing', 0) + by_status.get('receiving', 0), 'pending_sign': pending, 'drafts': drafts,
            'today': today_n, 'receiver_active': active and receiver.is_active()}


def overview() -> dict[str, Any]:
    from ..services import settings_store
    from ..services.backups import list_backups
    from . import plan, receiver

    current = plan.current()
    status = receiver.status()
    backups = list_backups()
    checks = [
        {'key': 'plan', 'label': '分析方案', 'ok': any(z.get('model_id') for z in current['zones'].values()) and not current['problems'],
         'detail': '、'.join(f'{plan.ZONE_LABELS[k]}：{v.get("model_id") or "未選"}' for k, v in current['zones'].items()) + ('；' + '；'.join(current['problems']) if current['problems'] else ''),
         'to': '/settings?tab=clinical'},
        {'key': 'network', 'label': '接收位址', 'ok': bool(status['interfaces']),
         'detail': '、'.join(i['address'] for i in status['interfaces']) or '找不到私人網段的網路介面（請連上 Wi-Fi 或手機熱點）', 'to': '/clinical/acquisition'},
        {'key': 'port', 'label': '接收連接埠', 'ok': True, 'detail': f'TCP {settings_store.get_all()["clinical_receiver_port"]}', 'to': '/settings?tab=clinical'},
        {'key': 'backup', 'label': '最近備份', 'ok': bool(backups), 'detail': backups[0]['time'] if backups else '還沒有備份', 'to': '/settings?tab=backup'},
    ]
    with session_scope('clinical') as db:
        recent = [{'id': a.id, 'exam_id': a.exam_id, 'status': a.status, 'created_at': a.created_at, 'candidate': a.candidate}
                  for a in db.query(ClinicalAnalysis).order_by(ClinicalAnalysis.created_at.desc()).limit(8).all()]
    return {'checks': checks, 'counts': counts(), 'candidate': current['candidate'], 'candidate_label': plan.CANDIDATE_LABEL, 'recent_analyses': recent,
            'receiver': status['session']}
