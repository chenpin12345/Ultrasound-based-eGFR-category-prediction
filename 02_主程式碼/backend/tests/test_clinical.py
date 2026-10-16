from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import ssl
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import pytest

def new_exam(client,kind='demo'):
    patient=None
    if kind=='patient':
        response=client.post('/api/clinical/patients',json={'code':'patient-'+str(time.time_ns()),'name':'測試病人'})
        assert response.status_code==200,response.text
        patient=response.json()['id']
    response=client.post('/api/clinical/exams',json={'kind':kind,'patient_id':patient,'title':'腎臟超音波測試'})
    assert response.status_code==200,response.text
    return response.json()['id']

def test_local_capabilities_csrf_and_origin(client):
    from backend.app.clinical import store
    info=client.get('/api/local-session').json()
    assert info['kind']=='local_system' and info['display_name']=='本機操作'
    assert 'roles' not in info and 'username' not in info
    assert client.post('/api/clinical/patients',json={'code':'x','name':'x'},headers={'X-CSRF-Token':'wrong'}).status_code==403
    for headers in ({'Host':'example.com'}, {'Origin':'null'}, {'Origin':'https://bad.example'}, {'Sec-Fetch-Site':'same-site'}, {'Sec-Fetch-Site':'cross-site'}):
        assert client.get('/api/clinical/exams',headers=headers).status_code==403
        assert client.get('/',headers=headers).status_code==403
    assert client.get('/api/models').status_code==200
    with store.transaction() as db:
        db.execute("UPDATE local_sessions SET capabilities=? WHERE id=?", ('["research.read"]',info['session_id']))
    assert client.get('/api/models').status_code==200
    assert client.get('/api/clinical/exams').status_code==403
    assert client.post('/api/clinical/patients',json={'code':'x','name':'x'}).status_code==403


def test_old_accounts_disabled_and_local_revocation(client):
    from backend.app.clinical import store
    from backend.app.clinical.auth import COOKIE
    from backend.app.clinical.routes import _previews
    principal=client.get('/api/local-session').json()
    with store.transaction() as db:
        db.execute("INSERT INTO users(id,username,password,roles,active,actor_kind) VALUES('old-human','legacy','old-hash','[\"physician\"]',1,'human')")
        db.execute("INSERT INTO sessions VALUES('old-token','old-human','old-csrf',?)",(time.time()+3600,))
    for method,path in [('post','/api/auth/login'),('post','/api/auth/bootstrap'),('get','/api/auth/me'),('get','/api/auth/users'),('post','/api/auth/users'),('put','/api/auth/users/old-human')]:
        assert getattr(client,method)(path).status_code==410
    cookie=client.cookies.get(COOKIE)
    assert client.get('/api/local-session',headers={'Cookie':'clinical_session=old-token'}).status_code==401
    _previews['revocation-test']={'owner':principal['session_id']}
    assert client.delete('/api/local-session').status_code==200
    assert 'revocation-test' not in _previews
    assert client.get('/api/local-session',headers={'Cookie':COOKIE+'='+cookie}).status_code==401
    with store.transaction() as db:
        assert db.execute("SELECT password FROM users WHERE id='old-human'").fetchone()[0]=='old-hash'
        assert db.execute("SELECT count(*) FROM sessions WHERE user_id='old-human'").fetchone()[0]==1
        actor=db.execute("SELECT active,roles,password FROM users WHERE id=?",(principal['id'],)).fetchone()
        assert actor['active']==0 and actor['roles']=='[]' and actor['password'].startswith('!')


def test_concurrent_report_first_render_is_single_artifact(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from reportlab.platypus import SimpleDocTemplate
    from backend.app.clinical.reports import render_pdf
    calls=[]
    original=SimpleDocTemplate.build
    def delayed_build(self,*args,**kwargs):
        calls.append(1)
        time.sleep(.1)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(SimpleDocTemplate,'build',delayed_build)
    rid=client.post('/api/clinical/reports',json={'exam_id':new_exam(client),'fields':{'findings':'同時預覽與下載測試'}}).json()['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths=list(pool.map(lambda _:render_pdf(rid,1),range(4)))
    assert len(calls)==1
    assert len(set(paths))==1
    assert paths[0].with_suffix('.sha256').read_text()==hashlib.sha256(paths[0].read_bytes()).hexdigest()

def test_immutable_domains_and_frame_identity(client,make_image):
    from backend.app.clinical import store
    from backend.app.clinical.service import save_frame
    from backend.app.core.errors import AppError
    demo=new_exam(client);patient=new_exam(client,'patient')
    with pytest.raises(AppError): save_frame(make_image(),patient,'network_demo')
    assert client.post('/api/clinical/exams/'+demo+'/frames',content=make_image()).status_code==422
    fid=save_frame(make_image(),demo,'network_demo',saved=True)
    with pytest.raises(sqlite3.IntegrityError),store.transaction() as db: db.execute("UPDATE exams SET kind='patient',patient_id='other' WHERE id=?",(demo,))
    with pytest.raises(sqlite3.IntegrityError),store.transaction() as db: db.execute('UPDATE frames SET exam_id=? WHERE id=?',(patient,fid))
    r=client.post('/api/clinical/reports',json={'exam_id':patient,'frame_ids':[fid]})
    assert r.status_code==422

def test_report_revision_confirmation_pdf_and_void(client,make_image):
    from backend.app.clinical.service import save_frame
    exam=new_exam(client);fid=save_frame(make_image(),exam,'network_demo',saved=True)
    payload={'exam_id':exam,'fields':{'findings':'超音波所見\n' * 140,'diagnosis':'由醫師填寫的判讀','physician':'測試醫師'},'frame_ids':[fid]}
    r=client.post('/api/clinical/reports',json=payload);assert r.status_code==200,r.text
    rid=r.json()['id']
    def change(action,version):return client.post(f'/api/clinical/reports/{rid}/versions',json={**payload,'action':action,'expected_version':version,'acknowledge_missing':True})
    assert change('pending',1).status_code==200
    assert change('confirmed',1).status_code==409
    assert change('confirmed',2).status_code==200
    assert change('draft',3).status_code==409
    assert client.get(f'/api/clinical/reports/{rid}/versions/3/pdf').status_code==404
    assert client.post(f'/api/clinical/reports/{rid}/versions/3/pdf').status_code==200
    first=client.get(f'/api/clinical/reports/{rid}/versions/3/pdf')
    assert first.status_code==200,first.text[:100] if first.status_code!=200 else ''
    assert first.content.startswith(b'%PDF')
    assert client.get(f'/api/clinical/reports/{rid}/versions/3/pdf?download=true').content==first.content
    from pypdf import PdfReader
    pdf=PdfReader(io.BytesIO(first.content)); assert len(pdf.pages)>1
    for page in pdf.pages: assert '非正式診斷書' in page.extract_text()
    assert change('revise',3).status_code==200
    assert client.get(f'/api/clinical/reports/{rid}/versions/3/pdf').content==first.content
    assert change('void',4).status_code==200
    assert client.get(f'/api/clinical/reports/{rid}/versions/3/pdf').status_code==404
    assert client.post(f'/api/clinical/reports/{rid}/versions/3/pdf').status_code==200
    void=client.get(f'/api/clinical/reports/{rid}/versions/3/pdf')
    assert '已作廢' in PdfReader(io.BytesIO(void.content)).pages[0].extract_text()

def test_decode_and_preprocess_parity(tmp_path,make_image):
    import cv2
    import numpy as np
    from backend.app.clinical.analysis import decode,preprocess
    from backend.app.core.errors import AppError
    from backend.app.ml.processing import crop_images,remove_blue_lines
    with pytest.raises(AppError): decode(b'not an image')
    for fmt,suffix in [('JPEG','jpg'),('PNG','png')]:
        original=tmp_path/f'original-{suffix}';original.mkdir()
        data=make_image((55,115,135),fmt);(original/('sample.'+suffix)).write_bytes(data)
        cropped=tmp_path/f'crop-{suffix}';rb=tmp_path/f'rb-{suffix}'
        assert crop_images(original,cropped)==(1,0)
        assert remove_blue_lines(cropped,rb)==(1,0)
        image,actual=decode(data)
        got=preprocess(image,actual,{'mode':'legacy','width':32,'height':24},data)
        expected=cv2.imdecode(np.fromfile(str(rb/('sample.'+suffix)),np.uint8),cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(got,expected)
        np.testing.assert_array_equal(preprocess(image,actual,{'mode':'prepared','width':32,'height':24},data),cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR))
        with pytest.raises(AppError): preprocess(image,actual,{'mode':'unknown'},data)

def test_model_snapshot_and_real_inference(client,make_image,tmp_path):
    import torch
    torch.set_num_threads(1)
    from backend.app.ml.models import build_classifier
    from backend.app.ml.inference import run_batch_inference
    from backend.app.clinical.service import save_frame
    from backend.app.clinical import store
    buffer=io.BytesIO();torch.save(build_classifier('mobilenetv2',num_classes=2).state_dict(),buffer)
    manifest={'name':'test image classifier','version':'1','task':'classification','architecture':'mobilenetv2','class_count':2,'class_names':['low','high'],'metadata_columns':[],'preprocessing':{'size':[224,224]}}
    r=client.post('/api/models',data={'manifest_json':json.dumps(manifest)},files={'weights':('model.pth',buffer.getvalue(),'application/octet-stream')})
    assert r.status_code==201,r.text
    r=client.post('/api/clinical/plans',json={'name':'verified test plan','model_id':r.json()['id'],'profile':{'mode':'prepared','width':32,'height':24,'evidence':'synthetic test fixture'},'device':'cpu'})
    assert r.status_code==200,r.text
    plan_id=r.json()['id'];exam=new_exam(client);data=make_image();fid=save_frame(data,exam,'network_demo')
    result=client.post(f'/api/clinical/frames/{fid}/analyze?plan_id={plan_id}',json={})
    assert result.status_code==200,result.text
    assert result.json()['status']=='completed',result.text
    assert result.json()['result']['frame_id']==fid
    assert sum(p['probability'] for p in result.json()['result']['probabilities'])==pytest.approx(1)
    assert client.get(f'/api/clinical/frames/{fid}/mask').status_code==404
    with store.transaction() as db: plan=store.rowdict(db.execute('SELECT * FROM plans WHERE id=?',(plan_id,)).fetchone())
    source=tmp_path/'input.jpg';source.write_bytes(data)
    report=run_batch_inference([source],model_path=store.managed(plan['snapshot']['models']['classifier']['path']),output_dir=tmp_path/'out',device='cpu')
    assert result.json()['result']['probabilities'][0]['probability']==pytest.approx(report.items[0].probabilities[0],abs=1e-6)
    model_path=store.managed(plan['snapshot']['models']['classifier']['path'])
    model_path.write_bytes(b'tampered model')
    changed=client.post(f'/api/clinical/frames/{fid}/analyze?plan_id={plan_id}',json={})
    assert changed.status_code==409 and changed.json()['error']['code']=='PLAN_INVALID'

def test_gpu_auto_arbitration(monkeypatch):
    import torch
    from backend.app.clinical.resources import resolve_device,clinical_lease,gpu_lock
    from backend.app.core.errors import AppError
    monkeypatch.setattr(torch.cuda,'is_available',lambda:True)
    assert resolve_device('auto')=='cuda'
    with gpu_lock,pytest.raises(AppError) as exc:
        with clinical_lease('cuda'): pass
    assert exc.value.code=='GPU_BUSY'


@pytest.mark.parametrize('basic,expected',[
    ({},'METADATA_REQUIRED'),
    ({'age':45},'METADATA_REQUIRED'),
    ({'age':float('nan'),'has_diabetes':0},'METADATA_REQUIRED'),
    ({'age':45,'has_diabetes':2},'METADATA_REQUIRED'),
    ({'age':45,'has_diabetes':0},'INVALID_MASK'),
])
def test_invalid_mlp_inputs_never_run_classifier(client,make_image,monkeypatch,basic,expected):
    from types import SimpleNamespace
    import torch
    from backend.app.clinical import analysis
    from backend.app.ml import inference,segmentation
    from backend.app.core.errors import AppError
    calls=[]
    def classifier(*args):
        calls.append(args)
        raise AssertionError('Invalid input reached classification')
    monkeypatch.setattr(analysis,'verify_plan',lambda plan:None)
    monkeypatch.setattr(inference,'read_model_metadata',lambda path:SimpleNamespace(architecture='mobilenetv2_mlp'))
    monkeypatch.setattr(inference.DEFAULT_MODEL_CACHE,'get',lambda *args:classifier)
    # Deliberately empty foreground: an invalid segmentation must stop classification.
    class EmptySegmenter:
        def __call__(self,tensor):return {'out':torch.zeros((1,2,512,512))}
    monkeypatch.setattr(segmentation,'load_unet',lambda *args:EmptySegmenter())
    monkeypatch.setattr(analysis,'_segmenters',{})
    plan={'id':'test-gating','profile':{'mode':'prepared','width':32,'height':24},
          'snapshot':{'device':'cpu','models':{
              'classifier':{'path':'bundles/test/weights.pth','sha256':'test'},
              'segmenter':{'path':'bundles/test/unet.pth','sha256':'empty-mask'}}}}
    with pytest.raises(AppError) as exc:analysis.infer(make_image(),plan,basic)
    assert exc.value.code==expected
    assert not calls

PREVIEW={'mode':'preview_only'}

def case(code,**fields):
    return {'case_code':code,**fields}

def manifest(batch,entries):
    """Protocol 2 batch: each image carries its own case data and digest."""
    from backend.app.clinical.cases import digest
    return {'protocol':2,'case_schema':1,'id':batch,
            'items':[{'id':i,'sha256':s,'case':c,'case_sha256':digest(c)} for i,s,c in entries]}

def test_https_receiver_transfer_retry_pairing_and_cleanup(client,make_image):
    from backend.app.clinical import transfer,store
    start=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':PREVIEW})
    assert start.status_code==200,start.text
    pair=start.json();context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.load_verify_locations(cadata=pair['certificate'])
    bearer=''
    def remote(path,body=None,headers=None):
        data=body if isinstance(body,bytes) else json.dumps(body).encode() if body is not None else None
        req=Request(pair['url']+path,data=data,headers={'Authorization':'Bearer '+bearer,**(headers or {})})
        with urlopen(req,context=context,timeout=10) as response:return json.load(response)
    try:
        with pytest.raises(URLError): urlopen(pair['url']+'/batches',timeout=5)
        bearer=remote('/pair',{'token':pair['pair_token']})['bearer']
        with pytest.raises(HTTPError) as exc:remote('/pair',{'token':pair['pair_token']})
        assert exc.value.code==401
        with pytest.raises(HTTPError) as exc:remote('/api/clinical/patients')
        assert exc.value.code==404
        data=make_image();sha=hashlib.sha256(data).hexdigest()
        remote('/batches',manifest('batch1',[('first',sha,case('C1')),('second',sha,case('C2')),('bad',hashlib.sha256(b'bad').hexdigest(),case('C3'))]))
        headers={'X-Batch-ID':'batch1','X-Item-ID':'first','X-Content-SHA256':sha}
        with pytest.raises(HTTPError) as exc:remote('/items',data+b'x',headers)
        assert exc.value.code==422
        remote('/items',data,headers)
        deadline=time.time()+10
        while time.time()<deadline:
            state=remote('/batches?id=batch1')
            if next(i for i in state['items'] if i['id']=='first')['status']=='received_only':break
            time.sleep(.05)
        else: pytest.fail('Analysis state did not settle')
        remote('/items',data,headers)
        remote('/control',{'batch_id':'batch1','action':'pause'})
        with pytest.raises(HTTPError) as exc:remote('/items',data,{**headers,'X-Item-ID':'second'})
        assert exc.value.code==409
        old=bearer;pair=client.post(f'/api/clinical/demo-sessions/{pair["session_id"]}/pair',json={}).json()
        with pytest.raises(HTTPError):remote('/batches?id=batch1')
        bearer=remote('/pair',{'token':pair['pair_token']})['bearer'];assert bearer!=old
        remote('/control',{'batch_id':'batch1','action':'resume'})
        remote('/items',data,{**headers,'X-Item-ID':'second'})
        remote('/items',b'bad',{**headers,'X-Item-ID':'bad','X-Content-SHA256':hashlib.sha256(b'bad').hexdigest()})
        transfer._executor.submit(lambda:None).result(10)
        batches=client.get('/api/clinical/demo-batches?session_id='+pair['session_id']).json()
        valid=[i for i in batches[0]['items'] if i['frame_id']]
        assert len(valid)==2 and valid[0]['frame']['exam_id']!=valid[1]['frame']['exam_id']
        assert all(client.get(i['frame']['url']).content==data for i in valid)
        client.post('/api/clinical/frames/'+valid[0]['frame_id']+'/save',json={})
        assert client.post(f'/api/clinical/demo-sessions/{pair["session_id"]}/stop',json={}).status_code==200
        transfer._executor.submit(lambda:None).result(10)
        assert client.get(valid[0]['frame']['url']).status_code==200
        assert client.get(valid[1]['frame']['url']).status_code==404
    finally:transfer.shutdown()

def make_plan(client,architecture='mobilenetv2',name='verified test plan',**profile):
    """A real sealed plan around a freshly built (untrained) 2-class classifier."""
    import torch
    from backend.app.ml.models import build_classifier
    buffer=io.BytesIO();torch.save(build_classifier('mobilenetv2',num_classes=2).state_dict(),buffer)
    manifest={'name':'test image classifier '+name,'version':str(time.time_ns()),'task':'classification','architecture':'mobilenetv2','class_count':2,'class_names':['low','high'],'metadata_columns':[],'preprocessing':{'size':[224,224]}}
    r=client.post('/api/models',data={'manifest_json':json.dumps(manifest)},files={'weights':('model.pth',buffer.getvalue(),'application/octet-stream')})
    assert r.status_code==201,r.text
    r=client.post('/api/clinical/plans',json={'name':name,'model_id':r.json()['id'],'profile':{'mode':'prepared','width':32,'height':24,'evidence':'synthetic test fixture',**profile},'device':'cpu'})
    assert r.status_code==200,r.text
    plan_id=r.json()['id']
    if architecture!='mobilenetv2':
        # Requirement rules read the sealed snapshot; emulate an MLP classifier's
        # snapshot without training one (inference is not exercised through it).
        from backend.app.clinical import store
        with store.transaction() as db:
            row=store.rowdict(db.execute('SELECT * FROM plans WHERE id=?',(plan_id,)).fetchone())
            row['snapshot']['models']['classifier']['architecture']=architecture
            new=store.uid()
            db.execute('INSERT INTO plans VALUES(?,?,?,?,?)',(new,name,store.dumps(row['profile']),store.dumps(row['snapshot']),time.time()))
        plan_id=new
    return plan_id

def test_bounded_queue_cancel_and_manual_case_retention(client,make_image,monkeypatch):
    from backend.app.clinical import transfer,store
    manual=new_exam(client)
    plan=make_plan(client)
    started=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':{'mode':'plan','plan_id':plan}})
    assert started.status_code==200,started.text
    pair=started.json()
    state=transfer._active
    queued=[]
    monkeypatch.setattr(transfer,'enqueue',lambda *args:queued.append(args))
    def call(op,body=None,**fields):
        return transfer.dispatch(state,{'op':op,'method':'POST','body':body or {},'bearer':'Bearer '+bearer,'query':{},**fields})
    bearer=''
    try:
        bearer=call('/pair',{'token':pair['pair_token']})['bearer']
        data=make_image();sha=hashlib.sha256(data).hexdigest()
        call('/batches',manifest('bounded',[(str(i),sha,case(f'B{i}')) for i in range(3)]))
        call('/items',data,batch='bounded',item='0',sha256=sha)
        call('/items',data,batch='bounded',item='1',sha256=sha)
        from backend.app.core.errors import AppError
        with pytest.raises(AppError) as exc:call('/items',data,batch='bounded',item='2',sha256=sha)
        assert exc.value.status_code==429
        call('/control',{'batch_id':'bounded','action':'pause'})
        transfer.process_item(*queued[0])
        with store.transaction() as db:assert db.execute("SELECT status FROM items WHERE id='0'").fetchone()[0]=='waiting'
        call('/control',{'batch_id':'bounded','action':'cancel'})
        for args in queued:transfer.process_item(*args)
        with store.transaction() as db:assert {r[0] for r in db.execute('SELECT status FROM items')}=={'cancelled'}
        transfer.stop_owner(state['owner']);transfer._executor.submit(lambda:None).result(10)
        assert client.get('/api/clinical/exams/'+manual).status_code==200
        with store.transaction() as db: assert not db.execute('SELECT 1 FROM frames').fetchone()
    finally:transfer.shutdown()

def test_session_exclusion_and_missing_profile(client):
    from backend.app.clinical.resources import reserve_session,release_session
    from backend.app.core.errors import AppError
    reserve_session('doctor1','capture:doctor1')
    try:
        with pytest.raises(AppError):reserve_session('doctor2','demo:doctor2')
        assert client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':PREVIEW}).status_code==409
    finally:release_session('doctor1')
    response=client.post('/api/clinical/plans',json={'name':'bad','model_id':'missing','profile':{'mode':'prepared','width':-1}})
    assert response.status_code==422

def test_sender_filters_and_scan_is_lazy(tmp_path,make_image):
    from tools.image_sender.sender import scan
    folder=tmp_path/'real';folder.mkdir();(folder/'a.jpg').write_bytes(make_image());(folder/'ignored.pth').write_bytes(b'model')
    mask=folder/'mask-output';mask.mkdir();(mask/'m.png').write_bytes(make_image(image_format='PNG'))
    assert [p.name for p in scan(folder)]==['a.jpg']

@pytest.mark.parametrize('classes,coral,logits',[(2,False,[0.0]),(3,False,[1.,2.,3.]),(5,False,[1.,2.,3.,4.,5.]),(3,True,[2.,1.]),(5,True,[4.,3.,2.,1.])])
def test_shared_numeric_contract(classes,coral,logits):
    import torch
    from backend.app.ml.models import single_image_probabilities,coral_logits_to_probs
    value=torch.tensor([logits]);probs,index=single_image_probabilities(value,classes,coral)
    expected=coral_logits_to_probs(value,num_classes=classes)[0] if coral else torch.softmax(value,dim=1)[0] if classes!=2 else torch.tensor([.5,.5])
    torch.testing.assert_close(probs,expected)
    assert index==int(expected.argmax())

def test_recovery_preserves_verified_image_and_retries_without_duplication(client,make_image,monkeypatch):
    from backend.app.clinical import transfer,store
    from backend.app.clinical.service import new_exam,save_frame
    owner=client.get('/api/local-session').json()['id'];sid=store.uid();bid=store.uid()
    with store.transaction() as db:
        db.execute('INSERT INTO demo_sessions(id,owner,plan_id,state,created,expires) VALUES(?,?,NULL,?,?,?)',(sid,owner,'active',time.time(),time.time()+3600))
        db.execute('INSERT INTO batches VALUES(?,?,?,?)',(bid,sid,'running',time.time()))
        exam=new_exam(db,'demo',None,'recovery','unspecified',{},sid)
    data=make_image();fid=save_frame(data,exam,'network_demo')
    with store.transaction() as db:db.execute('INSERT INTO items(id,batch_id,sha256,frame_id,status,created) VALUES(?,?,?,?,?,?)',('retry',bid,hashlib.sha256(data).hexdigest(),fid,'analyzing',time.time()))
    transfer.recover()
    with store.transaction() as db:
        assert db.execute('SELECT state FROM demo_sessions WHERE id=?',(sid,)).fetchone()[0]=='interrupted'
        assert db.execute('SELECT status FROM items').fetchone()[0]=='waiting'
        assert db.execute('SELECT COUNT(*) FROM frames').fetchone()[0]==1
    # A crash between file persistence and the status commit is recovered safely.
    from backend.app.clinical.service import analyze_frame
    with store.transaction() as db: db.execute("UPDATE frames SET status='analyzing' WHERE id=?",(fid,))
    transfer.recover()
    with store.transaction() as db:assert db.execute('SELECT status FROM frames WHERE id=?',(fid,)).fetchone()[0]=='received'
