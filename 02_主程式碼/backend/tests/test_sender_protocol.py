"""The portable sender (A) against the real TLS receiver (B), protocol 2."""
from __future__ import annotations

import time

import pytest

from test_clinical import make_plan


@pytest.fixture
def sender(monkeypatch):
    from tools.image_sender import sender as module
    state={'files':{},'queue':[],'pair':None,'bearer':None,'batch':None,'phase':'idle','message':'','running':False,'requirements':[],'plan_label':None}
    monkeypatch.setattr(module,'STATE',state)
    return module


def test_case_rules_match_receiver_and_copy_is_explicit(sender):
    from backend.app.clinical import cases
    case=sender.clean_case({'case_code':' A-1 ','age':'61','diabetes':'unknown','side':'left','notes':'第一行\n第二行','exam_time':'2026-10-13T09:30'})
    assert case=={'case_code':'A-1','age':61,'diabetes':'unknown','side':'left','notes':'第一行\n第二行','exam_time':'2026-10-13T09:30'}
    assert cases.parse(case).diabetes=='unknown' and sender.case_digest(case)==cases.digest(case)
    for bad in ({'age':45},{'case_code':'x','age':'4.5'},{'case_code':'x','age':True},{'case_code':'x','diabetes':'0'},{'case_code':'x','sex':'F'},{'case_code':'x\ny'}):
        with pytest.raises(ValueError): sender.clean_case(bad)
    sender.STATE['files']={'a':{'name':'a.jpg','case':None},'b':{'name':'b.jpg','case':{'case_code':'B-1','side':'right'}},'c':{'name':'c.jpg','case':None}}
    sender.STATE['requirements']=['age','has_diabetes']
    sender.set_case('a',{'case_code':'A-1','age':61,'diabetes':'yes','side':'left','patient_name':'王小明'})
    with pytest.raises(ValueError): sender.copy_case('a',[])
    result=sender.copy_case('a',['b','c'])
    assert sender.STATE['files']['b']['case']=={'age':61,'diabetes':'yes','patient_name':'王小明','case_code':'B-1','side':'right'}
    assert 'case_code' not in sender.STATE['files']['c']['case'] and sender.case_missing(sender.STATE['files']['c']['case'])==['case_code']
    assert [a['name'] for a in result['applied']]==['b.jpg','c.jpg']
    assert sender.case_missing({'case_code':'x','age':1,'diabetes':'unknown'})==['has_diabetes']


def test_old_pairing_file_and_unpaired_cases_are_refused(sender):
    with pytest.raises(ValueError,match='協定 2'): sender.pair_receiver({'protocol':1,'url':'https://127.0.0.1:1'},'00')
    sender.STATE.update(bearer='x',files={'a':{'name':'a.jpg','case':None,'path':None,'size':1}})
    with pytest.raises(ValueError,match='案例識別'): sender.queue_start(['a'],'batch')


def test_sender_end_to_end_two_cases_needs_data_and_specific_tls_error(client,sender,make_image,tmp_path):
    from backend.app.clinical import transfer,store
    plan=make_plan(client,name='e2e plan')
    client.post('/api/clinical/default-plans',json={'source':'network_demo','mode':'plan','plan_id':plan,'evidence':'e2e'})
    pair=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':{'mode':'default'}}).json()
    try:
        assert sender.pair_receiver(pair,pair['fingerprint'])['plan_label']=='e2e plan'
        files={}
        for name,color,case in [('one.jpg',(10,20,30),{'case_code':'E2E-1','age':40,'diabetes':'no','side':'left'}),
                                ('two.jpg',(90,20,30),{'case_code':'E2E-2','age':70,'diabetes':'yes','side':'right'})]:
            path=tmp_path/name;path.write_bytes(make_image(color))
            files[name]={'path':path,'name':name,'size':path.stat().st_size,'case':sender.clean_case(case)}
        sender.STATE['files']=files
        sender.queue_start(list(files),'batch')
        deadline=time.time()+60
        while sender.STATE['running'] and time.time()<deadline: time.sleep(.2)
        assert sender.STATE['phase']=='completed',sender.STATE['message']
        assert [i['status'] for i in sender.STATE['queue']]==['completed','completed']
        with store.transaction() as db:
            rows=db.execute('SELECT i.case_code,e.title,e.side,e.payload FROM items i JOIN exams e ON e.id=i.exam_id ORDER BY i.case_code').fetchall()
        assert [(r['case_code'],r['title'],r['side']) for r in rows]==[('E2E-1','E2E-1','left'),('E2E-2','E2E-2','right')]
        # B restarted receiving (new certificate); A still holds the old pairing:
        # reported as a certificate mismatch, never bypassed.
        transfer.stop_owner(transfer._active['owner'],finish=False)
        fresh=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','session_id':pair['session_id']}).json()
        sender.STATE['pair']={**fresh,'certificate':pair['certificate']}
        with pytest.raises(sender.RemoteError) as exc: sender.remote('/batches?id=x')
        assert exc.value.error=='NETWORK' and '憑證不符' in str(exc.value)
    finally: transfer.shutdown()
    with pytest.raises(sender.RemoteError) as exc: sender.remote('/batches?id=x')
    assert '無法連線' in str(exc.value) or '逾時' in str(exc.value)
