"""API 路由表（改寫自腎超新的 capabilities.py）。

不登入、不分角色，但每個 /api 路由仍必須登記在這裡：沒有登記的路由一律拒絕，
避免新增的 API 在沒人注意的情況下被開放。tests/test_routes_table.py 會檢查每個路由都有登記。
"""

from __future__ import annotations

PUBLIC_EXACT = {
    ('GET', '/api/health'),
    ('GET', '/api/session/challenge'),
    ('POST', '/api/session'),
}

# 登記的前綴。讀取與寫入都需要本機工作階段，寫入另外需要 CSRF token。
REGISTERED_PREFIXES: tuple[str, ...] = (
    '/api/session',
    '/api/system/',
    '/api/settings',
    '/api/people',
    '/api/audit',
    '/api/backups',
    '/api/jobs',
    '/api/inbox',
    '/api/imports',
    '/api/images',
    '/api/templates',
    '/api/patients',
    '/api/splits',
    '/api/dataset-versions',
    '/api/annotation',
    '/api/circling',
    '/api/clinical',
    '/api/egfr',
    '/api/mask-sets',
    '/api/pretrained',
    '/api/training',
    '/api/experiments',
    '/api/models',
    '/api/evaluations',
    '/api/features',
    '/api/pipelines',
    '/api/feedback',
    '/api/trash',
    '/api/overview',
    '/api/docs',
    '/api/openapi.json',
)


def is_public(method: str, path: str) -> bool:
    return (method.upper(), path) in PUBLIC_EXACT


def is_registered(path: str) -> bool:
    return any(path == p.rstrip('/') or path.startswith(p) for p in REGISTERED_PREFIXES)
