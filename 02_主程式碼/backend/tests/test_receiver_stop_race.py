"""Deterministic receiver stop races; no network or real child process."""
import threading
import time


def test_old_listener_cannot_renew_lease_after_stop_or_stop_replacement(client,tmp_path,monkeypatch):
    from backend.app.clinical import transfer,resources,store
    owner=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        for identifier in ('old-receiver','new-receiver'):
            db.execute('INSERT INTO demo_sessions(id,owner,plan_id,state,created,expires) VALUES(?,?,NULL,?,?,?)',(identifier,owner,'active',time.time(),time.time()+60))
    entered=threading.Event();resume=threading.Event()
    class Pipe:
        def poll(self,_):
            entered.set()
            if not resume.wait(5):raise AssertionError('fixture did not release listener')
            return False
        def close(self):pass
    class Process:
        def __init__(self):self.terminated=False
        def terminate(self):self.terminated=True
        def join(self,_):pass
    old={'id':'old-receiver','owner':owner,'pipe':Pipe(),'process':Process(),'folder':tmp_path}
    new={'id':'new-receiver','owner':owner,'pipe':Pipe(),'process':Process(),'folder':tmp_path}
    monkeypatch.setattr(transfer,'_active',old)
    resources.reserve_session(owner,'demo:old-receiver',60)
    listener=threading.Thread(target=transfer.serve,args=(old,))
    listener.start()
    try:
        assert entered.wait(3)
        transfer.stop_owner(owner,finish=False)
        transfer._active=new
        resources.reserve_session(owner,'demo:new-receiver',60)
        resume.set();listener.join(5)
        assert not listener.is_alive()
        assert transfer._active is new
        assert resources.session_active(owner,'demo:new-receiver')
        assert not new['process'].terminated
        transfer.stop_owner(owner,finish=False,expected_state=old)
        transfer.stop_owner('different-owner',finish=False)
        assert transfer._active is new and not new['process'].terminated
    finally:
        resume.set();listener.join(5)
        transfer.stop_owner(owner,finish=False)
        resources.release_session(owner,'demo:old-receiver')
        resources.release_session(owner,'demo:new-receiver')
