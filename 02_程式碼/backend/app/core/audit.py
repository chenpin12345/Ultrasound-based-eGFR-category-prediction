"""稽核紀錄。不記錄病人個資、原始檔名或完整路徑。"""

from __future__ import annotations

import json
from typing import Any

from ..db.models_system import AuditEntry
from ..db.session import session_scope
from .ids import now_iso


def record(actor: str, action: str, target_type: str = '', target_id: str = '', detail: dict[str, Any] | None = None, result: str = '成功') -> None:
    with session_scope('system') as db:
        db.add(
            AuditEntry(
                time=now_iso(),
                actor=actor or '本機',
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail_json=json.dumps(detail or {}, ensure_ascii=False),
                result=result,
            )
        )
