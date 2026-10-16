"""Receiver address validation, physician default plans, protocol 2 case data and
the needs-data state machine."""
from __future__ import annotations

import hashlib
import socket
import sqlite3
import time

import pytest

from test_clinical import PREVIEW, case, make_plan, manifest


def addr(address,interface='Ethernet',up=True,kind='private'):
    return {'interface':interface,'address':address,'family':4,'is_up':up,'kind':kind,'supported':True,'note':''}


def test_bind_address_validation_explains_each_mistake(monkeypatch):
    from backend.app.clinical import network
    from backend.app.core.errors import AppError
    monkeypatch.setattr(network,'interfaces',lambda:[addr('192.168.50.10'),addr('10.8.0.2','VPN',up=False),addr('127.0.0.1','Loopback',kind='loopback')])
    assert network.validate('192.168.50.10')['interface']=='Ethernet'
    assert network.validate('127.0.0.1',8443)['port']==8443
    for host,port,code in [('abc',None,'BIND_ADDRESS_INVALID'),('fe80::1',None,'BIND_IPV6_UNSUPPORTED'),('0.0.0.0',None,'BIND_WILDCARD'),
                           ('8.8.8.8',None,'BIND_NOT_PRIVATE'),('192.168.50.77',None,'BIND_NOT_LOCAL'),('10.8.0.2',None,'BIND_INTERFACE_DOWN'),
                           ('192.168.50.10',80,'PORT_RANGE'),('192.168.50.10',70000,'PORT_RANGE')]:
        with pytest.raises(AppError) as exc: network.validate(host,port)
        assert exc.value.code==code,(host,exc.value.code)
    assert network.classify('169.254.3.4')=='link_local' and network.classify('127.0.0.1')=='loopback'
    assert network.recommended([addr('192.168.50.10'),addr('169.254.1.1',kind='link_local')])=='192.168.50.10'
    # Two candidate LAN cards: never guess by sort order.
    assert network.recommended([addr('192.168.50.10'),addr('10.0.0.5','Wi-Fi')]) is None


def test_occupied_port_is_reported_not_shared(client):
    from backend.app.clinical import transfer
    blocker=socket.socket()
    if hasattr(socket,'SO_EXCLUSIVEADDRUSE'): blocker.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    blocker.bind(('127.0.0.1',0)); blocker.listen(1); port=blocker.getsockname()[1]
    try:
        r=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','port':port,'analysis':PREVIEW})
        assert r.status_code==409 and r.json()['error']['code']=='PORT_IN_USE',r.text
        assert transfer._active is None
        r=client.post('/api/clinical/demo-sessions',json={'host':'8.8.8.8','analysis':PREVIEW})
        assert r.json()['error']['code']=='BIND_NOT_PRIVATE'
        r=client.post('/api/clinical/demo-sessions',json={'host':'10.254.254.254','analysis':PREVIEW})
        assert r.json()['error']['code']=='BIND_NOT_LOCAL'  # e.g. A's address typed on B
    finally: blocker.close()
    try:
        ok=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':PREVIEW,'address_mode':'manual'})
        assert ok.status_code==200,ok.text
        settings=client.get('/api/clinical/receiver-settings').json()
        assert settings['saved']['host']=='127.0.0.1' and settings['saved_check']['valid'] and settings['ipv6_supported'] is False
    finally: transfer.shutdown()


def test_default_plan_is_persistent_explicit_and_source_checked(client,tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.clinical import store
    status=client.get('/api/clinical/default-plans').json()['sources']
    assert status['network_demo']['setting'] is None and not status['network_demo']['analyzable']
    plan=make_plan(client)
    unknown=client.post('/api/clinical/plans',json={'name':'unknown source','model_id':client.get('/api/models').json()['items'][0]['id'],'profile':{'mode':'unknown'},'device':'cpu'}).json()['id']
    def put(**body): return client.post('/api/clinical/default-plans',json={'evidence':'核對來源尺寸與前處理',**body})
    assert put(source='network_demo',mode='plan',plan_id=unknown).json()['error']['code']=='PLAN_NOT_COMPATIBLE'
    assert put(source='capture',mode='plan',plan_id=plan).json()['error']['code']=='PLAN_NOT_COMPATIBLE'  # not validated for patients
    assert put(source='network_demo',mode='plan').status_code==422
    assert client.post('/api/clinical/default-plans',json={'source':'network_demo','mode':'plan','plan_id':plan,'evidence':' '}).status_code==422
    assert put(source='network_demo',mode='plan',plan_id=plan).status_code==200
    with pytest.raises(sqlite3.IntegrityError),store.transaction() as db: db.execute("UPDATE clinical_default_plans SET plan_id=NULL")
    # A fresh application instance (restart) reads the same backend setting.
    with TestClient(create_app(testing=True)) as other:
        other.headers['Origin']='http://testserver'
        challenge=other.get('/api/local-session/challenge',headers={'X-Local-Init':'1'}).json()['challenge']
        other.post('/api/local-session',json={'challenge':challenge},headers={'X-Local-Init':'1'})
        value=other.get('/api/clinical/default-plans').json()['sources']['network_demo']
        assert value['plan']['id']==plan and value['analyzable'] and value['plan']['requirements']==[]


def test_session_analysis_mode_is_explicit_and_locked(client):
    from backend.app.clinical import transfer,store
    assert client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1'}).json()['error']['code']=='ANALYSIS_MODE_REQUIRED'
    assert client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','plan_id':None}).status_code==422  # legacy field is not guessed
    missing=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':{'mode':'default'}})
    assert missing.status_code==409 and missing.json()['error']['code']=='DEFAULT_PLAN_MISSING'
    first=make_plan(client,name='first');second=make_plan(client,name='second')
    client.post('/api/clinical/default-plans',json={'source':'network_demo','mode':'plan','plan_id':first,'evidence':'e'})
    try:
        pair=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':{'mode':'default'}}).json()
        assert pair['protocol']==2 and pair['plan_label']=='first' and pair['requirements']==[]
        assert set(pair)=={'session_id','url','certificate','fingerprint','pair_token','expires','protocol','min_protocol','case_schema','requirements','plan_label'}
        client.post('/api/clinical/default-plans',json={'source':'network_demo','mode':'plan','plan_id':second,'evidence':'e'})
        with store.transaction() as db:
            row=db.execute('SELECT * FROM demo_sessions WHERE id=?',(pair['session_id'],)).fetchone()
            assert row['plan_id']==first and row['plan_mode']=='plan' and row['default_setting_id']
        with pytest.raises(sqlite3.IntegrityError),store.transaction() as db: db.execute('UPDATE demo_sessions SET plan_id=? WHERE id=?',(second,pair['session_id']))
        transfer.stop_owner(transfer._active['owner'],finish=False)
        resumed=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','session_id':pair['session_id'],'analysis':PREVIEW})
        assert resumed.json()['error']['code']=='SESSION_PLAN_LOCKED'
        resumed=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','session_id':pair['session_id']})
        assert resumed.status_code==200 and resumed.json()['plan_label']=='first'
    finally: transfer.shutdown()


@pytest.fixture
def receiver(client,monkeypatch):
    """A real receiver session driven through dispatch (no TLS round trip)."""
    from backend.app.clinical import transfer
    queued=[]
    monkeypatch.setattr(transfer,'enqueue',lambda *args:queued.append(args))
    def open_session(analysis):
        pair=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':analysis})
        assert pair.status_code==200,pair.text
        state=transfer._active
        bearer=transfer.dispatch(state,{'op':'/pair','method':'POST','body':{'token':pair.json()['pair_token']},'bearer':'','query':{}})['bearer']
        def call(op,body=None,**fields):
            return transfer.dispatch(state,{'op':op,'method':fields.pop('method','POST'),'body':body if body is not None else {},'bearer':'Bearer '+bearer,'query':fields.pop('query',{}),**fields})
        return call,pair.json()
    try: yield open_session,queued
    finally: transfer.shutdown()


def test_protocol_negotiation_conflicts_and_strict_case_schema(client,make_image,receiver):
    from backend.app.core.errors import AppError
    open_session,_=receiver
    call,_=open_session(PREVIEW)
    data=make_image();sha=hashlib.sha256(data).hexdigest()
    with pytest.raises(AppError) as exc: call('/batches',{'id':'old','items':[{'id':'a','sha256':sha}]})
    assert exc.value.status_code==426 and exc.value.code=='SENDER_UPGRADE_REQUIRED'
    body=manifest('b1',[('a',sha,case('A-1',age=50,diabetes='no'))])
    tampered={**body,'items':[{**body['items'][0],'case':case('A-1',age=51,diabetes='no')}]}
    with pytest.raises(AppError) as exc: call('/batches',tampered)
    assert exc.value.code=='CASE_DIGEST_MISMATCH'
    for bad in (case('X',age='50'),case('X',unknown_field=1),case('X',diabetes='maybe'),case('X',age=131),case(''),case('X',notes='a'*501)):
        with pytest.raises(AppError) as exc: call('/batches',manifest('b-bad',[('z',sha,bad)]))
        assert exc.value.code=='CASE_INVALID',bad
    assert call('/batches',body)=={'id':'b1'}
    assert call('/batches',body)=={'id':'b1'}  # identical retry is idempotent
    with pytest.raises(AppError) as exc: call('/batches',manifest('b1',[('a',sha,case('A-1',age=60,diabetes='no'))]))
    assert exc.value.code=='BATCH_CONFLICT'
    with pytest.raises(AppError) as exc: call('/items',data,batch='b1',item='a',sha256=hashlib.sha256(b'other').hexdigest())
    assert exc.value.code=='ITEM_CONFLICT'


def test_two_images_two_cases_never_mixed_and_demo_never_writes_patients(client,make_image,receiver):
    from backend.app.clinical import store
    open_session,_=receiver
    call,pair=open_session(PREVIEW)
    patient=client.post('/api/clinical/patients',json={'code':'P-REAL','name':'正式病人'}).json()['id']
    one,two=make_image((10,20,30)),make_image((200,10,10))
    cases=[case('CASE-A',patient_ref='P-REAL',patient_name='王小明',age=61,diabetes='yes',side='left',exam_name='腎臟超音波',exam_time='2026-10-13T09:30'),
           case('CASE-B',age=45,diabetes='unknown',side='right',notes='第二張')]
    call('/batches',manifest('pair',[('a',hashlib.sha256(one).hexdigest(),cases[0]),('b',hashlib.sha256(two).hexdigest(),cases[1])]))
    assert call('/items',one,batch='pair',item='a',sha256=hashlib.sha256(one).hexdigest())['status']=='received_only'
    assert call('/items',two,batch='pair',item='b',sha256=hashlib.sha256(two).hexdigest())['status']=='received_only'
    assert call('/items',two,batch='pair',item='b',sha256=hashlib.sha256(two).hexdigest())['status']=='received_only'  # retry: no duplicate
    batches=client.get('/api/clinical/demo-batches?session_id='+pair['session_id']).json()
    items={i['id']:i for i in batches[0]['items']}
    assert all('case_payload' not in i for i in items.values())
    a=client.get('/api/clinical/exams/'+items['a']['exam_id']).json();b=client.get('/api/clinical/exams/'+items['b']['exam_id']).json()
    assert (a['title'],a['side'],a['payload']['age'],a['payload']['has_diabetes'],a['payload']['patient_name'])==('CASE-A','left',61,1,'王小明')
    assert (b['title'],b['side'],b['payload']['age'],b['diabetes_status'])==('CASE-B','right',45,'unknown')
    assert 'has_diabetes' not in b['payload']  # unknown is never stored as "no"
    assert a['kind']=='demo' and a['patient_id'] is None and a['payload']['identity_verified'] is False
    assert client.get(a['frames'][0]['url']).content==one and client.get(b['frames'][0]['url']).content==two
    with store.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM exams WHERE demo_session_id=?',(pair['session_id'],)).fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM patients').fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM exams WHERE patient_id=?",(patient,)).fetchone()[0]==0
        version=db.execute('SELECT * FROM exam_basic_versions WHERE exam_id=?',(a['id'],)).fetchone()
        assert version['revision']==1 and version['source']=='transfer'


def test_interrupted_publish_leaves_no_mispaired_case(client,make_image,receiver,monkeypatch):
    from backend.app.clinical import transfer,store,service
    open_session,_=receiver
    call,pair=open_session(PREVIEW)
    data=make_image();sha=hashlib.sha256(data).hexdigest()
    call('/batches',manifest('crash',[('a',sha,case('CRASH-1'))]))
    def broken(*args,**kwargs): raise OSError('disk interrupted')
    monkeypatch.setattr(transfer,'insert_frame',broken)
    with pytest.raises(OSError): call('/items',data,batch='crash',item='a',sha256=sha)
    with store.transaction() as db:
        assert db.execute("SELECT status,staging_frame_id FROM items WHERE id='a'").fetchone()[:]==('pending',None)
        assert db.execute('SELECT COUNT(*) FROM exams WHERE demo_session_id=?',(pair['session_id'],)).fetchone()[0]==0
    frames=store.root()/'frames'
    assert not frames.exists() or not any(frames.iterdir())
    monkeypatch.setattr(transfer,'insert_frame',service.insert_frame)
    assert call('/items',data,batch='crash',item='a',sha256=sha)['status']=='received_only'
    # A process crash between the staging claim and the publishing commit.
    call('/batches',manifest('crash2',[('b',sha,case('CRASH-2'))]))
    staged=store.uid()
    with store.transaction() as db: db.execute("UPDATE items SET status='receiving',staging_frame_id=? WHERE id='b'",(staged,))
    service.write_original(data,staged)
    transfer.shutdown(); transfer.recover()
    assert not service.frame_folder(staged).exists()
    with store.transaction() as db:
        assert db.execute("SELECT status FROM items WHERE id='b'").fetchone()[0]=='pending'
        assert db.execute('SELECT COUNT(*) FROM exams WHERE demo_session_id=?',(pair['session_id'],)).fetchone()[0]==1


def test_missing_data_waits_without_queue_slot_and_resumes_once(client,make_image,receiver):
    from backend.app.clinical import store
    open_session,queued=receiver
    plan=make_plan(client,architecture='mobilenetv2_mlp')
    call,pair=open_session({'mode':'plan','plan_id':plan})
    images=[make_image((i*40,10,10)) for i in range(3)]
    entries=[(str(i),hashlib.sha256(d).hexdigest(),case(f'M-{i}',age=50,diabetes='unknown')) for i,d in enumerate(images)]
    call('/batches',manifest('mlp',entries))
    for i,d in enumerate(images):  # three waiting items do not trip the 2-slot backpressure
        assert call('/items',d,batch='mlp',item=str(i),sha256=entries[i][1])['status']=='needs_data'
    assert not queued
    state=call('/batches',method='GET',query={'id':['mlp']})
    assert state['items'][0]['missing_fields']==['has_diabetes'] and state['items'][0]['case_code']=='M-0'
    batches=client.get('/api/clinical/demo-batches?session_id='+pair['session_id']).json()
    item=batches[0]['items'][0]; exam=client.get('/api/clinical/exams/'+item['exam_id']).json()
    assert exam['frames'][0]['status']=='needs_data' and exam['transfer']['missing_now']==['has_diabetes']
    assert 'has_diabetes' not in exam['payload']
    still=client.put(f'/api/clinical/exams/{exam["id"]}/case?expected_revision=1',json={'title':'M-0','side':'left','age':50})
    assert still.status_code==200 and still.json()['resumed']==0 and not queued
    done=client.put(f'/api/clinical/exams/{exam["id"]}/case?expected_revision=2',json={'title':'M-0','side':'left','age':50,'diabetes':'no'})
    assert done.json()=={'revision':3,'resumed':1}
    assert len(queued)==1 and queued[0][2]=='0'
    again=client.put(f'/api/clinical/exams/{exam["id"]}/case?expected_revision=3',json={'title':'M-0','side':'left','age':50,'diabetes':'no','notes':'複核'})
    assert again.json()['resumed']==0 and len(queued)==1
    stale=client.put(f'/api/clinical/exams/{exam["id"]}/case?expected_revision=3',json={'title':'M-0'})
    assert stale.status_code==409
    with store.transaction() as db:
        assert [r[0] for r in db.execute('SELECT source FROM exam_basic_versions WHERE exam_id=? ORDER BY revision',(exam['id'],))]==['transfer','manual','manual','manual']
        assert db.execute("SELECT status FROM items WHERE id='0'").fetchone()[0]=='queued'
    patient=client.post('/api/clinical/patients',json={'code':'P1','name':'甲'}).json()['id']
    pexam=client.post('/api/clinical/exams',json={'kind':'patient','patient_id':patient,'title':'t'}).json()['id']
    forbidden=client.put(f'/api/clinical/exams/{pexam}/case?expected_revision=1',json={'title':'t','patient_name':'乙'})
    assert forbidden.json()['error']['code']=='PATIENT_IDENTITY_FIXED'


def test_complete_case_is_analyzed_automatically_with_the_session_plan(client,make_image):
    from backend.app.clinical import transfer,store
    plan=make_plan(client,name='auto plan')
    client.post('/api/clinical/default-plans',json={'source':'network_demo','mode':'plan','plan_id':plan,'evidence':'e'})
    pair=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':{'mode':'default'}}).json()
    state=transfer._active
    try:
        bearer=transfer.dispatch(state,{'op':'/pair','method':'POST','body':{'token':pair['pair_token']},'bearer':'','query':{}})['bearer']
        data=make_image();sha=hashlib.sha256(data).hexdigest()
        call=lambda op,body,**f:transfer.dispatch(state,{'op':op,'method':'POST','body':body,'bearer':'Bearer '+bearer,'query':{},**f})
        call('/batches',manifest('auto',[('a',sha,case('AUTO-1',age=55,diabetes='no'))]))
        assert call('/items',data,batch='auto',item='a',sha256=sha)['status']=='queued'
        transfer._executor.submit(lambda:None).result(60)
        with store.transaction() as db:
            item=db.execute("SELECT * FROM items WHERE id='a'").fetchone()
            assert item['status']=='completed',dict(item)
            runs=db.execute('SELECT plan_id,snapshot FROM analysis_runs WHERE frame_id=?',(item['frame_id'],)).fetchall()
            assert len(runs)==1 and runs[0]['plan_id']==plan
            assert db.execute("SELECT state FROM batches WHERE id='auto'").fetchone()[0]=='completed'
    finally: transfer.shutdown()


def test_edited_case_history_blocks_permanent_delete_but_empty_exam_can_go(client):
    from backend.app.clinical import store
    empty=client.post('/api/clinical/exams',json={'kind':'demo','title':'empty'}).json()['id']
    edited=client.post('/api/clinical/exams',json={'kind':'demo','title':'edited'}).json()['id']
    client.put(f'/api/clinical/exams/{edited}/case?expected_revision=1',json={'title':'edited','age':30})
    check=client.get(f'/api/clinical/lifecycle/exams/{edited}?action=delete_empty').json()
    assert not check['allowed'] and check['references']['case_data_edits']==1
    check=client.get(f'/api/clinical/lifecycle/exams/{empty}?action=delete_empty').json()
    assert check['allowed'],check
    r=client.post(f'/api/clinical/lifecycle/exams/{empty}',json={'action':'delete_empty','expected_revision':check['revision'],'reason':'建立錯誤'})
    assert r.status_code==200,r.text
    with store.transaction() as db:
        assert not db.execute('SELECT 1 FROM exam_basic_versions WHERE exam_id=?',(empty,)).fetchone()
        with pytest.raises(sqlite3.IntegrityError): db.execute('DELETE FROM exam_basic_versions WHERE exam_id=?',(edited,))


def test_case_update_never_rewrites_previous_run_and_history_shows_actual_plan(client,make_image):
    from backend.app.clinical.service import save_frame
    plan=make_plan(client,name='analysis plan A')
    exam=client.post('/api/clinical/exams',json={'kind':'demo','title':'run test','age':40,'has_diabetes':0}).json()['id']
    fid=save_frame(make_image(),exam,'network_demo')
    assert client.post(f'/api/clinical/frames/{fid}/analyze?plan_id={plan}',json={}).json()['status']=='completed'
    other=make_plan(client,name='plan B')
    client.post('/api/clinical/default-plans',json={'source':'network_demo','mode':'plan','plan_id':other,'evidence':'e'})
    client.put(f'/api/clinical/exams/{exam}/case?expected_revision=1',json={'title':'run test','age':70,'diabetes':'yes'})
    history=client.get(f'/api/clinical/frames/{fid}/analyses/history').json()
    assert history[0]['snapshot']['basic_input']['age']==40 and history[0]['snapshot']['exam']['revision']==1
    assert history[0]['plan_name']=='analysis plan A'
    frame=client.get('/api/clinical/exams/'+exam).json()['frames'][0]
    assert frame['result_plan']['name']=='analysis plan A'
