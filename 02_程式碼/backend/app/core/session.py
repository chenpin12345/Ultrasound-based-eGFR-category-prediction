"""本機工作階段（改寫自腎超新 clinical/auth.py）。

不登入：開啟網頁時前端自動取得 challenge 並建立工作階段。安全性來自
「只接受本機連線＋同源檢查＋HttpOnly Cookie＋寫入需要 CSRF token」。
"""

from __future__ import annotations

import hashlib
import ipaddress
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from ..db.models_system import LocalSession
from ..db.session import session_scope
from .errors import AppError

router = APIRouter(tags=['工作階段'])
COOKIE = 'kidney_session'
LIFETIME = 8 * 3600
_attempts: dict[str, deque] = defaultdict(deque)
_lock = threading.RLock()


@dataclass
class Principal:
    session_id: str
    csrf: str
    expires_at: float


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def check_origin(request: Request) -> None:
    host = request.url.hostname
    peer = request.client.host if request.client else ''
    testing = getattr(request.app.state, 'testing', False)
    if testing and peer == 'testclient' and host == 'testserver':
        local = True
    else:
        try:
            local = ipaddress.ip_address(peer).is_loopback and host in {'127.0.0.1', 'localhost', '::1'}
        except ValueError:
            local = False
    if not local:
        raise AppError(403, 'LOCAL_ONLY', '系統只接受這台電腦本機的連線。')
    origin = request.headers.get('origin')
    if origin is not None and origin != str(request.base_url).rstrip('/'):
        raise AppError(403, 'ORIGIN_REJECTED', '不允許從其他網頁來源操作。')
    site = request.headers.get('sec-fetch-site')
    if site is not None and site not in {'same-origin', 'none'}:
        raise AppError(403, 'ORIGIN_REJECTED', '不允許跨來源要求。')


def _lookup(request: Request) -> Principal | None:
    token = request.cookies.get(COOKIE, '')
    if not token:
        return None
    with session_scope('system') as db:
        row = (
            db.query(LocalSession)
            .filter(
                LocalSession.token_hash == digest(token),
                LocalSession.boot_id == request.app.state.boot_id,
                LocalSession.expires > time.time(),
                LocalSession.revoked.is_(None),
            )
            .one_or_none()
        )
        if row is None:
            return None
        return Principal(session_id=row.id, csrf=row.csrf, expires_at=row.expires)


def require(request: Request) -> Principal:
    check_origin(request)
    principal = _lookup(request)
    if principal is None:
        raise AppError(401, 'SESSION_REQUIRED', '本機工作階段已失效，請重新整理頁面。')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not secrets.compare_digest(
        request.headers.get('x-csrf-token', ''), principal.csrf
    ):
        raise AppError(403, 'CSRF_REQUIRED', '請重新整理頁面後再操作。')
    return principal


def _rate_limit(key: str) -> None:
    with _lock:
        now = time.monotonic()
        queue = _attempts[key]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= 30:
            raise AppError(429, 'SESSION_RATE_LIMIT', '建立工作階段太頻繁，請稍後再試。')
        queue.append(now)


def _bootstrap_check(request: Request) -> None:
    check_origin(request)
    if request.headers.get('x-local-init') != '1':
        raise AppError(403, 'LOCAL_INIT_REQUIRED', '缺少本機初始化標頭。')
    if request.method == 'POST' and request.headers.get('origin') != str(request.base_url).rstrip('/'):
        raise AppError(403, 'ORIGIN_REQUIRED', '工作階段必須由本系統的網頁建立。')


@router.get('/session/challenge')
def challenge(request: Request):
    _bootstrap_check(request)
    _rate_limit(request.app.state.boot_id)
    token = secrets.token_urlsafe(32)
    with _lock:
        pending = request.app.state.challenges
        now = time.monotonic()
        for key in [k for k, exp in pending.items() if exp <= now]:
            del pending[key]
        pending[digest(token)] = now + 120
    return {'challenge': token, 'expires_in': 120}


class Initialize(BaseModel):
    challenge: str


@router.post('/session')
def create(payload: Initialize, request: Request, response: Response):
    _bootstrap_check(request)
    with _lock:
        expires = request.app.state.challenges.pop(digest(payload.challenge), 0)
    if expires <= time.monotonic():
        raise AppError(403, 'CHALLENGE_EXPIRED', '初始化挑戰已使用或過期，請重新整理頁面。')
    existing = _lookup(request)
    if existing:
        return {'csrf': existing.csrf, 'expires_at': existing.expires_at}
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = time.time()
    with session_scope('system') as db:
        db.add(
            LocalSession(
                id=secrets.token_hex(16),
                token_hash=digest(token),
                csrf=csrf,
                boot_id=request.app.state.boot_id,
                created=now,
                expires=now + LIFETIME,
            )
        )
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=LIFETIME, path='/')
    return {'csrf': csrf, 'expires_at': now + LIFETIME}


@router.get('/session')
def info(request: Request):
    p = require(request)
    return {'csrf': p.csrf, 'expires_at': p.expires_at}


@router.delete('/session')
def revoke(request: Request, response: Response):
    p = require(request)
    with session_scope('system') as db:
        db.query(LocalSession).filter(LocalSession.id == p.session_id).update({'revoked': time.time()})
    response.delete_cookie(COOKIE, path='/')
    return {'revoked': True}
