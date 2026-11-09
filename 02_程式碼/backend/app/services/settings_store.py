"""系統設定與人員名單。"""

from __future__ import annotations

import json
from typing import Any

from ..core.errors import AppError
from ..core.ids import now_iso
from ..db.models_system import Person, Setting
from ..db.session import session_scope

DEFAULTS: dict[str, Any] = {
    'trash_retention_days': 30,
    'residual_check': True,
    'primary_split_id': None,  # 主切分：圈選批次、遮罩組、比較組預設使用（M2.5）
    'circling_colors': [],  # 醫師圈選的顏色對照：[{color: '#rrggbb', structure: kidney|sinus|liver|spleen}]（決策 D21）
    'circling_color_tolerance': 40,  # 顏色比對的容許距離（RGB 0–441）
    'clinical_plan': {'segmentation': None, 'egfr': None, 'grade': None},  # 醫師端分析方案（M3，D40、D41）
    'clinical_receiver_port': 8443,  # 雙機展示的上傳連接埠（D38）
    'clinical_device_mode': False,  # 超音波機器模式（D39；需要 IRB 同意，M3 階段 F 才提供）
}


def get_all() -> dict[str, Any]:
    out = dict(DEFAULTS)
    with session_scope('system') as db:
        for s in db.query(Setting).filter(Setting.key.in_(list(DEFAULTS))).all():
            out[s.key] = json.loads(s.value_json)
    return out


def update(values: dict[str, Any]) -> dict[str, Any]:
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise AppError(422, 'UNKNOWN_SETTING', '不認識的設定：' + '、'.join(sorted(unknown)))
    if 'trash_retention_days' in values and not (1 <= int(values['trash_retention_days']) <= 365):
        raise AppError(422, 'BAD_SETTING', '回收桶保留天數必須在 1 到 365 天之間。')
    if 'circling_colors' in values:
        import re

        colors = values['circling_colors']
        if not isinstance(colors, list) or any(
            not isinstance(c, dict) or not re.fullmatch(r'#[0-9a-fA-F]{6}', str(c.get('color', ''))) or c.get('structure') not in ('kidney', 'sinus', 'liver', 'spleen')
            for c in colors
        ):
            raise AppError(422, 'BAD_SETTING', '顏色對照格式不正確：每一列需要顏色（#rrggbb）與構造（腎臟外框、腎竇、肝、脾）。')
        if len({c['color'].lower() for c in colors}) != len(colors):
            raise AppError(422, 'BAD_SETTING', '同一種顏色只能對應一個構造。')
    if 'circling_color_tolerance' in values and not (5 <= int(values['circling_color_tolerance']) <= 150):
        raise AppError(422, 'BAD_SETTING', '顏色容許距離必須在 5 到 150 之間。')
    if 'clinical_plan' in values:
        from ..clinical.plan import validate

        values = {**values, 'clinical_plan': validate(values['clinical_plan'])}
    if 'clinical_receiver_port' in values:
        port = values['clinical_receiver_port']
        if not isinstance(port, int) or not (1024 <= port <= 65535) or port == 8000:
            raise AppError(422, 'BAD_SETTING', '上傳連接埠必須在 1024 到 65535 之間，而且不能是系統本身的 8000。')
    if values.get('clinical_device_mode'):
        raise AppError(422, 'BAD_SETTING', '超音波機器模式需要 IRB／醫院同意，會在 M3 第二階段（階段 F）提供，目前不能開啟。')
    if values.get('primary_split_id'):
        from ..db.models_research import Split

        with session_scope('research') as db:
            split = db.get(Split, values['primary_split_id'])
            if split is None or split.trashed_at:
                raise AppError(422, 'BAD_SETTING', '主切分必須是存在的資料切分。')
    with session_scope('system') as db:
        for key, value in values.items():
            db.merge(Setting(key=key, value_json=json.dumps(value, ensure_ascii=False), updated_at=now_iso()))
    if 'clinical_plan' in values:
        from ..clinical import models_cache

        models_cache.retain({m for m in values['clinical_plan'].values() if m})  # 換掉的模型從記憶體釋放
    return get_all()


def list_people(include_inactive: bool = True) -> list[dict[str, Any]]:
    with session_scope('system') as db:
        q = db.query(Person)
        if not include_inactive:
            q = q.filter(Person.active.is_(True))
        return [{'id': p.id, 'name': p.name, 'kind': p.kind, 'active': p.active, 'created_at': p.created_at} for p in q.order_by(Person.kind, Person.name).all()]


def add_person(name: str, kind: str) -> dict[str, Any]:
    name = name.strip()
    if not name or len(name) > 40:
        raise AppError(422, 'BAD_NAME', '姓名必須是 1 到 40 個字。')
    if kind not in {'physician', 'operator'}:
        raise AppError(422, 'BAD_KIND', '類型只能是醫師或操作者。')
    with session_scope('system') as db:
        if db.query(Person).filter(Person.name == name, Person.kind == kind).first():
            raise AppError(409, 'DUPLICATE_PERSON', '名單裡已經有這個人。')
        p = Person(name=name, kind=kind, active=True, created_at=now_iso())
        db.add(p)
        db.flush()
        return {'id': p.id, 'name': p.name, 'kind': p.kind, 'active': p.active}


def set_active(person_id: int, active: bool) -> None:
    with session_scope('system') as db:
        p = db.get(Person, person_id)
        if p is None:
            raise AppError(404, 'NOT_FOUND', '找不到這個人。')
        p.active = active
