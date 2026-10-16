import time


def challenge(client):
    response = client.get('/api/local-session/challenge', headers={'X-Local-Init':'1'})
    assert response.status_code == 200
    return response.json()


def test_challenge_one_use_same_origin_and_no_default_account(client):
    assert client.get('/api/local-session/challenge').status_code == 403
    payload = challenge(client)
    headers = {'X-Local-Init':'1'}
    before = client.get('/api/local-session').json()
    assert client.post('/api/local-session',json=payload,headers={**headers,'Origin':'null'}).status_code == 403
    response = client.post('/api/local-session',json=payload,headers=headers)
    assert response.status_code == 200
    assert response.json() == before  # Another tab must not rotate a valid cookie/CSRF.
    assert client.post('/api/local-session',json=payload,headers=headers).status_code == 403


def test_expired_and_previous_boot_sessions_rejected(client):
    from backend.app.clinical import store
    original = client.get('/api/local-session').json()
    with store.transaction() as db:
        db.execute('UPDATE local_sessions SET expires=? WHERE id=?',(time.time()-1, original['session_id']))
    assert client.get('/api/models').status_code == 401
    response=client.post('/api/local-session',json=challenge(client),headers={'X-Local-Init':'1'})
    assert response.status_code==200
    assert response.json()['session_id'] != original['session_id']
    client.app.state.local_boot_id='next-server-boot'
    assert client.get('/api/models').status_code==401


def test_capture_leases_are_operation_scoped():
    from backend.app.clinical.resources import reserve_session,release_session,session_active
    reserve_session('browser-1','capture:operation-1')
    try:
        release_session('browser-2','capture:operation-1')
        release_session('browser-1','capture:operation-2')
        assert session_active('browser-1','capture:operation-1')
    finally:
        release_session('browser-1','capture:operation-1')
    assert not session_active('browser-1','capture:operation-1')
def test_local_session_read_does_not_reserve_clinical_write_lock(client):
    import sqlite3
    from backend.app.clinical import store
    with store.read_transaction() as reader:
        reader.execute('SELECT id FROM local_sessions').fetchall()
        writer=sqlite3.connect(store.root()/'clinical.sqlite3',timeout=0.1)
        try:
            writer.execute('BEGIN IMMEDIATE')
            writer.rollback()
        finally:writer.close()
