"""Single-local-operator sessions; never impersonate a human account."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import TypedDict

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from ..core.errors import AppError
from . import store

router = APIRouter(tags=['Local operation'])
COOKIE = 'isu_local_session'
CAPABILITIES = ('research.read', 'research.execute', 'models.manage', 'clinical.read',
                'clinical.operate', 'reports.manage', 'system.manage')
_attempts = defaultdict(deque)
_lock = threading.RLock()


class LocalPrincipal(TypedDict):
    id: str
    kind: str
    display_name: str
    capabilities: list[str]
    csrf: str
    session_id: str
    expires_at: float


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def check_origin(request: Request):
    host = request.url.hostname
    peer = request.client.host if request.client else ''
    testing = getattr(request.app.state, 'local_testing', False)
    test_peer = testing and peer == 'testclient' and host == 'testserver'
    try:
        local_peer = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local_peer = False
    if not test_peer and (host not in {'127.0.0.1', 'localhost', '::1'} or not local_peer):
        raise AppError(403, 'LOCAL_ONLY', '主應用僅接受本機 loopback 存取。')
    origin = request.headers.get('origin')
    if origin is not None and origin != str(request.base_url).rstrip('/'):
        raise AppError(403, 'ORIGIN_REJECTED', '不允許此網頁來源。')
    site = request.headers.get('sec-fetch-site')
    if site is not None and site not in {'same-origin', 'none'}:
        raise AppError(403, 'ORIGIN_REJECTED', '不允許跨來源要求。')


def _session(request: Request):
    token = request.cookies.get(COOKIE, '')
    if not token:
        return None
    with store.read_transaction() as db:
        row = db.execute("""SELECT local_sessions.* FROM local_sessions JOIN users ON users.id=actor_id
            WHERE token_hash=? AND boot_id=? AND expires>? AND revoked IS NULL AND actor_kind='local_system' """,
            (digest(token), request.app.state.local_boot_id, time.time())).fetchone()
    if row is None:
        return None
    return LocalPrincipal(id=row['actor_id'], kind='local_system', display_name='本機操作',
                          capabilities=json.loads(row['capabilities']), csrf=row['csrf'],
                          session_id=row['id'], expires_at=row['expires'])


def current(request: Request, capability: str | None = None) -> LocalPrincipal:
    check_origin(request)
    principal = _session(request)
    if principal is None:
        raise AppError(401, 'LOCAL_SESSION_REQUIRED', '本機會話已失效，請重新初始化後再操作。')
    if capability and capability not in principal['capabilities']:
        raise AppError(403, 'CAPABILITY_REQUIRED', '此會話沒有執行此操作的能力。')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not secrets.compare_digest(
        request.headers.get('x-csrf-token', ''), principal['csrf']
    ):
        raise AppError(403, 'CSRF_REQUIRED', '請更新本機會話後重新確認操作。')
    return principal


def rate_limit(key):
    with _lock:
        now = time.monotonic()
        queue = _attempts[key]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= 30:
            raise AppError(429, 'SESSION_RATE_LIMIT', '初始化過於頻繁，請稍後重試。')
        queue.append(now)


def _bootstrap_request(request: Request):
    check_origin(request)
    if request.headers.get('x-local-init') != '1':
        raise AppError(403, 'LOCAL_INIT_REQUIRED', '缺少本機初始化標頭。')
    if request.method == 'POST':
        if request.headers.get('origin') != str(request.base_url).rstrip('/'):
            raise AppError(403, 'ORIGIN_REQUIRED', '初始化必須來自同源網頁。')
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise AppError(415, 'JSON_REQUIRED', '初始化僅接受 JSON。')


@router.get('/local-session/challenge')
def challenge(request: Request):
    _bootstrap_request(request)
    rate_limit(request.app.state.local_boot_id)
    token = secrets.token_urlsafe(32)
    with _lock:
        challenges = request.app.state.local_challenges
        now = time.monotonic()
        for key in list(challenges):
            if challenges[key] <= now:
                del challenges[key]
        challenges[digest(token)] = now + 120
    return {'challenge': token, 'expires_in': 120}


class Initialize(BaseModel):
    challenge: str


@router.post('/local-session')
def initialize(payload: Initialize, request: Request, response: Response):
    _bootstrap_request(request)
    with _lock:
        expires = request.app.state.local_challenges.pop(digest(payload.challenge), 0)
    if expires <= time.monotonic():
        raise AppError(403, 'CHALLENGE_EXPIRED', '初始化挑戰已使用或過期。')
    existing = _session(request)
    if existing:
        return existing
    token, csrf, identifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), store.uid()
    now = time.time()
    with store.transaction() as db:
        row = db.execute("SELECT id FROM users WHERE actor_kind='local_system'").fetchone()
        actor = row['id'] if row else store.uid()
        if row is None:
            db.execute('INSERT INTO users(id,username,password,roles,active,actor_kind) VALUES(?,?,?,?,0,?)',
                       (actor, 'local-system-' + actor, '!password-login-disabled!', '[]', 'local_system'))
        db.execute('INSERT INTO local_sessions VALUES(?,?,?,?,?,?,?,?,NULL)',
                   (identifier, digest(token), actor, csrf, store.dumps(CAPABILITIES),
                    request.app.state.local_boot_id, now, now + 8 * 3600))
        store.audit(db, actor, 'local_session_initialized', identifier)
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict',
                        secure=request.url.scheme == 'https', max_age=8 * 3600, path='/')
    return LocalPrincipal(id=actor, kind='local_system', display_name='本機操作', capabilities=list(CAPABILITIES),
                          csrf=csrf, session_id=identifier, expires_at=now + 8 * 3600)


@router.get('/local-session')
def session_info(request: Request):
    return current(request)


@router.delete('/local-session')
def revoke(request: Request, response: Response):
    principal = current(request)
    with store.transaction() as db:
        db.execute('UPDATE local_sessions SET revoked=? WHERE id=?', (time.time(), principal['session_id']))
        store.audit(db, principal['id'], 'local_session_revoked', principal['session_id'])
    from .resources import release_session
    release_session(principal['session_id'])
    from .routes import _previews, _preview_lock
    with _preview_lock:
        for key in list(_previews):
            if _previews[key]['owner'] == principal['session_id']:
                _previews.pop(key)
    response.delete_cookie(COOKIE, path='/')
    return {'revoked': True}


@router.api_route('/auth/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def legacy_disabled(path: str, request: Request):
    check_origin(request)
    raise AppError(410, 'ACCOUNT_AUTH_DISABLED', '帳號登入及管理已停用；請使用本機操作會話。')
