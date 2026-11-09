"""路由表、本機工作階段、人員名單、設定。"""

from __future__ import annotations

from fastapi.routing import APIRoute


def test_every_api_route_is_registered(workspace):
    from app.core import routes_table
    from app.main import create_app

    app = create_app(testing=True)
    missing = [
        r.path
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith('/api') and not any(routes_table.is_public(m, r.path) for m in r.methods) and not routes_table.is_registered(r.path)
    ]
    assert missing == []


def test_session_required_and_csrf(client):
    raw = client.raw
    raw.cookies.clear()
    assert raw.get('/api/overview').status_code == 401
    # 重新建立工作階段後，讀取可以、沒有 CSRF 的寫入不行
    h = {'x-local-init': '1', 'origin': 'http://testserver'}
    challenge = raw.get('/api/session/challenge', headers=h).json()['challenge']
    csrf = raw.post('/api/session', json={'challenge': challenge}, headers=h).json()['csrf']
    assert raw.get('/api/overview').status_code == 200
    assert raw.post('/api/people', json={'name': '林醫師', 'kind': 'physician'}).status_code == 403
    assert raw.post('/api/people', json={'name': '林醫師', 'kind': 'physician'}, headers={'x-csrf-token': csrf}).status_code == 201


def test_cross_origin_rejected(client):
    r = client.raw.get('/api/overview', headers={'origin': 'http://evil.example'})
    assert r.status_code == 403
    assert r.json()['error']['code'] == 'ORIGIN_REJECTED'


def test_challenge_single_use(client):
    raw = client.raw
    h = {'x-local-init': '1', 'origin': 'http://testserver'}
    challenge = raw.get('/api/session/challenge', headers=h).json()['challenge']
    raw.cookies.clear()
    assert raw.post('/api/session', json={'challenge': challenge}, headers=h).status_code == 200
    raw.cookies.clear()
    assert raw.post('/api/session', json={'challenge': challenge}, headers=h).status_code == 403


def test_people_and_audit(client):
    r = client.post('/api/people', json={'name': '周醫師', 'kind': 'physician'})
    assert r.status_code == 201
    assert client.post('/api/people', json={'name': '周醫師', 'kind': 'physician'}).status_code == 409
    pid = r.json()['id']
    assert client.patch(f'/api/people/{pid}', json={'active': False}).status_code == 200
    people = client.get('/api/people').json()['people']
    assert people[0]['active'] is False
    actions = [e['action'] for e in client.get('/api/audit').json()['entries']]
    assert '新增人員' in actions and '停用人員' in actions


def test_settings_validation(client):
    assert client.put('/api/settings', json={'trash_retention_days': 0}).status_code == 422
    assert client.put('/api/settings', json={'unknown': 1}).status_code == 422
    assert client.put('/api/settings', json={'trash_retention_days': 45}).json()['trash_retention_days'] == 45


def test_unknown_api_rejected(client):
    r = client.get('/api/not-a-real-route')
    assert r.status_code == 403
    assert r.json()['error']['code'] == 'API_NOT_REGISTERED'


def test_snapshot_twice_same_day(client, workspace):
    # 同一天第二次快照要能取代第一次：Windows 上連線沒關會讓 .part 資料夾改名失敗
    for _ in range(2):
        r = client.post('/api/backups/snapshot')
        assert r.status_code == 200, r.text
    daily = workspace / '07_備份' / '每日資料庫'
    assert [p.name for p in daily.iterdir()] == [r.json()['folder']]
    manifest = (daily / r.json()['folder'] / 'manifest.json').read_text(encoding='utf-8')
    assert '"integrity": "ok"' in manifest
    assert client.get('/api/backups').json()['backups'][0]['kind'] == '每日資料庫快照'
