"""雙機展示的接收（D38、M3-1、B10）。

- 「開始接收」另開一個**獨立的上傳小程式**：只綁定選定網路介面的 IP（不綁 0.0.0.0）、HTTPS 自簽憑證（依目前 IP 產生）、
  只有傳送頁、配對、上傳三個功能；不重跑主網站的啟動流程，也不讀主網站的 Cookie。
- 配對碼 6 位數、10 分鐘有效；資料庫只存雜湊。同一個來源輸錯 5 次就不能再試，直到換新的配對碼。配對碼放在請求標頭。
- 上傳串流寫進受限的 05_接收暫存（.part），有大小上限；A 端的原始檔名不保存。按「傳送完成」後由醫師端佇列處理。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import secrets
import socket
import threading
import time
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import now_iso, short_uid
from ..db.models_clinical import ReceiverBatch, ReceiverSession
from ..db.session import session_scope
from ..jobs.manager import JobContext, get_manager, register

MAX_BYTES = 32 * 1024 * 1024
CODE_MINUTES = 10
MAX_ATTEMPTS = 5
_state: dict[str, Any] = {}  # 目前的接收：session_id、code（明碼只在記憶體）、server、thread、attempts、tokens
_lock = threading.RLock()


# ---------- 網路介面與連接埠 ----------
def interfaces() -> list[dict[str, Any]]:
    """可用的私人網段 IPv4 介面（Wi-Fi、乙太網路、手機熱點）。"""
    import psutil

    stats = psutil.net_if_stats()
    out = []
    for name, addrs in psutil.net_if_addrs().items():
        if not stats.get(name) or not stats[name].isup:
            continue
        for a in addrs:
            if a.family != socket.AF_INET:
                continue
            ip = ipaddress.ip_address(a.address)
            if ip.is_private and not ip.is_loopback and not ip.is_link_local:
                out.append({'name': name, 'address': a.address})
    return sorted(out, key=lambda i: i['address'])


def port_free(address: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind((address, port))
            return True
        except OSError:
            return False


# ---------- 憑證 ----------
def cert_dir() -> Path:
    return get_settings().path('runtime') / 'run' / 'receiver'


def make_certificate(address: str) -> str:
    """依目前 IP 產生自簽憑證（1 天有效），回傳 SHA-256 指紋（AA:BB:…）。私鑰停止接收時刪除。"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'腎超工作台 {address}')])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(hours=1)).not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address))]), critical=False).sign(key, hashes.SHA256()))
    folder = cert_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (folder / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    digest = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ':'.join(digest[i:i + 2] for i in range(0, len(digest), 2))


# ---------- 接收工作階段 ----------
def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _new_code(session_id: str) -> dict[str, str]:
    code = f'{secrets.randbelow(1_000_000):06d}'
    expires = (dt.datetime.now().astimezone() + dt.timedelta(minutes=CODE_MINUTES)).isoformat(timespec='seconds')
    with session_scope('clinical') as db:
        s = db.get(ReceiverSession, session_id)
        s.code_hash, s.code_expires_at = _hash(code), expires
    with _lock:
        _state.update(code=code, attempts={})
    return {'code': code, 'expires_at': expires}


def status() -> dict[str, Any]:
    from ..services import settings_store

    with _lock:
        sid, code = _state.get('session_id'), _state.get('code')
    session = None
    if sid:
        with session_scope('clinical') as db:
            s = db.get(ReceiverSession, sid)
            if s and s.status == 'active':
                session = {'id': s.id, 'address': s.address, 'port': s.port, 'url': f'https://{s.address}:{s.port}', 'code': code,
                           'code_expires_at': s.code_expires_at, 'fingerprint': s.fingerprint, 'started_at': s.started_at}
    with session_scope('clinical') as db:
        batches = [_batch_dict(b) for b in db.query(ReceiverBatch).order_by(ReceiverBatch.created_at.desc()).limit(30).all()]
    port = int(settings_store.get_all()['clinical_receiver_port'])
    ifaces = interfaces()
    return {'session': session, 'interfaces': ifaces, 'suggested': ifaces[0]['address'] if len(ifaces) == 1 else None, 'port': port, 'batches': batches,
            'firewall_hint': f'第一次使用時，Windows 可能跳出防火牆詢問，請允許「私人網路」；手機熱點常被設成「公用網路」，需要在網路設定改成私人網路，或在防火牆允許 TCP {port} 連入。'}


def start(address: str | None, operator: str) -> dict[str, Any]:
    from ..services import settings_store

    with _lock:
        if _state.get('session_id'):
            raise AppError(409, 'RECEIVER_ACTIVE', '已經在接收中；要換網路介面請先停止接收。')
    port = int(settings_store.get_all()['clinical_receiver_port'])
    choices = [i['address'] for i in interfaces()]
    testing = get_settings().testing
    if not address:
        if len(choices) != 1:
            raise AppError(422, 'CHOOSE_INTERFACE', '找到多個（或沒有）私人網段的網路介面，請選擇要用哪一個（兩台電腦要連同一個 Wi-Fi 或手機熱點）。' if choices else '找不到私人網段的網路介面：請先連上 Wi-Fi 或手機熱點。')
        address = choices[0]
    if address not in choices and not (testing and address == '127.0.0.1'):
        raise AppError(422, 'BAD_INTERFACE', f'{address} 不是這台電腦目前的私人網段位址；請從清單選擇（不要填 A 電腦的位址）。')
    if not testing and not port_free(address, port):
        raise AppError(409, 'PORT_IN_USE', f'連接埠 {port} 已被其他程式使用，請在「設定 › 醫師端」換一個連接埠。')
    fingerprint = make_certificate(address)
    session_id = f'RS-{short_uid()}'
    with session_scope('clinical') as db:
        db.add(ReceiverSession(id=session_id, address=address, port=port, fingerprint=fingerprint, started_by=operator, started_at=now_iso()))
    with _lock:
        _state.clear()
        _state.update(session_id=session_id, tokens=set(), attempts={})
    code = _new_code(session_id)
    if not testing:
        _serve(address, port)
    try:  # 先載入分析方案的模型，第一次分析不用等
        get_manager().submit('clinical_warmup', {}, target='醫師端分析方案', created_by=operator)
    except AppError:
        pass
    return {**status()['session'], **code}


def _serve(address: str, port: int) -> None:
    import uvicorn

    folder = cert_dir()
    config = uvicorn.Config(upload_app(), host=address, port=port, ssl_certfile=str(folder / 'cert.pem'), ssl_keyfile=str(folder / 'key.pem'),
                            log_level='warning', lifespan='off')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name='clinical-receiver', daemon=True)
    thread.start()
    for _ in range(100):
        if server.started or not thread.is_alive():
            break
        time.sleep(0.05)
    if not server.started:
        raise AppError(409, 'RECEIVER_START_FAILED', f'上傳小程式無法在 {address}:{port} 啟動（可能被防火牆或其他程式擋住）。')
    with _lock:
        _state.update(server=server, thread=thread)


def stop(reason: str = 'ended') -> None:
    with _lock:
        sid, server, thread = _state.get('session_id'), _state.get('server'), _state.get('thread')
        _state.clear()
    if server is not None:
        server.should_exit = True
        if thread is not None:
            thread.join(timeout=10)
    (cert_dir() / 'key.pem').unlink(missing_ok=True)
    if sid:
        with session_scope('clinical') as db:
            s = db.get(ReceiverSession, sid)
            if s and s.status == 'active':
                s.status, s.ended_at = reason, now_iso()


def recover() -> None:
    """網站重新啟動時，上次沒有停止的接收標成「中斷」（上傳小程式跟著網站結束）。"""
    with session_scope('clinical') as db:
        for s in db.query(ReceiverSession).filter(ReceiverSession.status == 'active').all():
            s.status, s.ended_at = 'interrupted', now_iso()
    (cert_dir() / 'key.pem').unlink(missing_ok=True)


def is_active() -> bool:
    with _lock:
        return bool(_state.get('session_id'))


def new_code() -> dict[str, str]:
    with _lock:
        sid = _state.get('session_id')
    if not sid:
        raise AppError(409, 'RECEIVER_INACTIVE', '目前沒有在接收。')
    return _new_code(sid)


# ---------- 上傳小程式的處理 ----------
def pair(code: str, client: str) -> str:
    with _lock:
        sid = _state.get('session_id')
        attempts = _state.setdefault('attempts', {})
        if not sid:
            raise AppError(409, 'RECEIVER_INACTIVE', 'B 電腦目前沒有在接收。')
        if attempts.get(client, 0) >= MAX_ATTEMPTS:
            raise AppError(429, 'TOO_MANY_ATTEMPTS', '配對碼輸錯太多次；請在 B 電腦按「換一個配對碼」。')
    with session_scope('clinical') as db:
        s = db.get(ReceiverSession, sid)
        expired = s.code_expires_at < now_iso()
        ok = secrets.compare_digest(s.code_hash, _hash((code or '').strip()))
    if expired:
        raise AppError(401, 'CODE_EXPIRED', '配對碼已過期；請在 B 電腦按「換一個配對碼」。')
    if not ok:
        with _lock:
            attempts[client] = attempts.get(client, 0) + 1
        raise AppError(401, 'BAD_CODE', f'配對碼不正確（剩 {MAX_ATTEMPTS - attempts[client]} 次）。')
    token = secrets.token_urlsafe(32)
    with _lock:
        _state.setdefault('tokens', set()).add(_hash(token))
    return token


def check_token(token: str | None) -> str:
    with _lock:
        sid = _state.get('session_id')
        ok = bool(token) and _hash(token) in _state.get('tokens', set())
    if not sid or not ok:
        raise AppError(401, 'NOT_PAIRED', '尚未配對或配對已失效，請重新輸入 B 電腦畫面上的配對碼。')
    return sid


def create_batch(session_id: str, data: dict[str, Any]) -> dict[str, Any]:
    from .exams import create_exam

    batch_id = f'RB-{short_uid()}'
    demo = bool(data.get('demo'))
    exam = create_exam(data.get('case_code'), {'age': data.get('age'), 'sex': data.get('sex'), 'diabetes': data.get('diabetes')},
                       source='demo_pack' if demo else 'upload', batch_id=batch_id, title=str(data.get('title') or ''), operator='A 電腦（雙機展示）',
                       clinical_source='demo_list' if demo else 'upload')
    with session_scope('clinical') as db:
        db.add(ReceiverBatch(id=batch_id, session_id=session_id, exam_id=exam['exam_id'], items_json='[]', created_at=now_iso()))
    return {'batch_id': batch_id, **exam, 'demo': demo}


def _batch(db, session_id: str, batch_id: str) -> ReceiverBatch:
    b = db.get(ReceiverBatch, batch_id)
    if b is None or b.session_id != session_id:
        raise AppError(404, 'BATCH_NOT_FOUND', '找不到這次傳送。')
    return b


def record_item(session_id: str, batch_id: str, item: dict[str, Any]) -> None:
    with session_scope('clinical') as db:
        b = _batch(db, session_id, batch_id)
        items = [i for i in json.loads(b.items_json) if i['seq'] != item['seq']]
        items.append(item)
        b.items_json = json.dumps(sorted(items, key=lambda i: i['seq']), ensure_ascii=False)


def finish(session_id: str, batch_id: str) -> dict[str, Any]:
    with session_scope('clinical') as db:
        b = _batch(db, session_id, batch_id)
        if b.status != 'receiving':
            raise AppError(409, 'BATCH_FINISHED', '這次傳送已經完成。')
        b.status, b.finished_at = 'finished', now_iso()
        exam_id = b.exam_id
    job_id = get_manager().submit('clinical_receive', {'batch_id': batch_id}, target=exam_id or '', created_by='A 電腦（雙機展示）')
    return {'exam_id': exam_id, 'job_id': job_id}


def _batch_dict(b: ReceiverBatch) -> dict[str, Any]:
    items = json.loads(b.items_json or '[]')
    counts: dict[str, int] = {}
    for i in items:
        counts[i['status']] = counts.get(i['status'], 0) + 1
    return {'id': b.id, 'exam_id': b.exam_id, 'status': b.status, 'created_at': b.created_at, 'finished_at': b.finished_at, 'items': len(items), 'counts': counts}


def summary(batch_id: str) -> dict[str, Any]:
    """傳送摘要（B10）：每張的狀態、SHA-256、大小、耗時；不含檔名與個資。"""
    with session_scope('clinical') as db:
        b = db.get(ReceiverBatch, batch_id)
        if b is None:
            raise AppError(404, 'BATCH_NOT_FOUND', '找不到這次傳送。')
        return {**_batch_dict(b), 'item_list': [{k: i.get(k) for k in ('seq', 'status', 'sha256', 'bytes', 'ms', 'image_id', 'message')} for i in json.loads(b.items_json or '[]')]}


@register('clinical_receive', pool='clinical', label='醫師端收圖與去識別化')
def receive_job(ctx: JobContext) -> dict[str, Any]:
    """處理一次傳送：每張存進受限區、去識別化、建立影像；完成後自動排入分析。"""
    from . import exams

    batch_id = ctx.config['batch_id']
    with session_scope('clinical') as db:
        b = db.get(ReceiverBatch, batch_id)
        exam_id, items = b.exam_id, json.loads(b.items_json or '[]')
    staging = exams.staging_dir(batch_id)
    received = [i for i in items if i['status'] == 'received']
    for n, item in enumerate(received, start=1):
        ctx.check_stop()
        path = staging / f'{item["seq"]}.part'
        try:
            result = exams.add_image(exam_id, batch_id, item['seq'], path, item['sha256'], item.get('meta') or {})
            item.update(status=result['status'], image_id=result.get('image_id'))
        except Exception as exc:  # noqa: BLE001  一張失敗不影響其他張
            item.update(status='failed', message=f'處理失敗：{type(exc).__name__}')
        ctx.progress(n / max(1, len(received)) * 90, f'{n}／{len(received)}')
    with session_scope('clinical') as db:
        db.get(ReceiverBatch, batch_id).items_json = json.dumps(items, ensure_ascii=False)
    import shutil

    shutil.rmtree(staging, ignore_errors=True)
    status = exams.refresh_status(exam_id)
    analysis = None
    if status not in ('layout_mismatch', 'failed', 'receiving'):
        from . import analysis as clinical_analysis

        analysis = clinical_analysis.start(exam_id, 'A 電腦（雙機展示）')
    return {'exam_id': exam_id, 'status': status, 'analysis': analysis}


# ---------- 上傳小程式（只在區網、只能上傳） ----------
def upload_app():
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, JSONResponse
    from starlette.routing import Route

    from . import exams

    def err(exc: AppError) -> JSONResponse:
        return JSONResponse({'error': {'code': exc.code, 'message': exc.message}}, status_code=exc.status_code)

    def bearer(request: Request) -> str:
        auth = request.headers.get('authorization', '')
        return check_token(auth[7:] if auth.lower().startswith('bearer ') else None)

    async def page(request: Request):
        return HTMLResponse(SEND_PAGE, headers={'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'"})

    async def do_pair(request: Request):
        try:
            return JSONResponse({'token': pair(request.headers.get('x-pair-code', ''), request.client.host if request.client else '?')})
        except AppError as exc:
            return err(exc)

    async def batches(request: Request):
        try:
            sid = bearer(request)
            body = await request.json()
            return JSONResponse(create_batch(sid, body if isinstance(body, dict) else {}))
        except AppError as exc:
            return err(exc)

    async def item(request: Request):
        started = time.monotonic()
        try:
            sid = bearer(request)
            batch_id, seq = request.path_params['batch_id'], int(request.path_params['seq'])
            with session_scope('clinical') as db:
                if _batch(db, sid, batch_id).status != 'receiving':
                    raise AppError(409, 'BATCH_FINISHED', '這次傳送已經完成，不能再加影像。')
            expected = (request.headers.get('x-sha256') or '').lower()
            length = int(request.headers.get('content-length') or 0)
            if length > MAX_BYTES:
                raise AppError(413, 'TOO_LARGE', '每張影像最多 32 MB。')
            target = exams.staging_dir(batch_id) / f'{seq}.part'
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            with target.open('wb') as fh:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise AppError(413, 'TOO_LARGE', '每張影像最多 32 MB。')
                    digest.update(chunk)
                    fh.write(chunk)
            head = target.read_bytes()[:8]
            if not (head.startswith(b'\x89PNG') or head.startswith(b'\xff\xd8')):
                target.unlink(missing_ok=True)
                raise AppError(415, 'NOT_IMAGE', '只接受 JPG 或 PNG。')
            actual = digest.hexdigest()
            if expected and actual != expected:
                target.unlink(missing_ok=True)
                raise AppError(422, 'HASH_MISMATCH', '檔案在傳送中損毀（SHA-256 不符），請重送。')
            meta = {'demo': request.headers.get('x-demo') == '1', 'side': request.headers.get('x-side') or None,
                    'pixel_spacing_mm': float(request.headers['x-spacing']) if request.headers.get('x-spacing') else None}
            with session_scope('clinical') as db:
                dup = any(i['sha256'] == actual and i['seq'] != seq and i['status'] == 'received' for i in json.loads(_batch(db, sid, batch_id).items_json))
            status = 'duplicate' if dup else 'received'
            if dup:
                target.unlink(missing_ok=True)
            entry = {'seq': seq, 'status': status, 'sha256': actual, 'bytes': size, 'ms': round((time.monotonic() - started) * 1000), 'meta': meta}
            record_item(sid, batch_id, entry)
            return JSONResponse({k: entry[k] for k in ('seq', 'status', 'sha256', 'bytes', 'ms')})
        except AppError as exc:
            return err(exc)
        except ValueError:
            return err(AppError(422, 'BAD_REQUEST', '傳送的資料格式不正確。'))

    async def do_finish(request: Request):
        try:
            return JSONResponse(finish(bearer(request), request.path_params['batch_id']))
        except AppError as exc:
            return err(exc)

    async def batch_status(request: Request):
        try:
            sid = bearer(request)
            with session_scope('clinical') as db:
                _batch(db, sid, request.path_params['batch_id'])
            return JSONResponse(summary(request.path_params['batch_id']))
        except AppError as exc:
            return err(exc)

    return Starlette(routes=[
        Route('/', page),
        Route('/pair', do_pair, methods=['POST']),
        Route('/batches', batches, methods=['POST']),
        Route('/batches/{batch_id}/items/{seq:int}', item, methods=['PUT']),
        Route('/batches/{batch_id}/finish', do_finish, methods=['POST']),
        Route('/batches/{batch_id}', batch_status),
    ])


SEND_PAGE = (Path(__file__).with_name('send_page.html')).read_text(encoding='utf-8') if (Path(__file__).with_name('send_page.html')).exists() else ''
