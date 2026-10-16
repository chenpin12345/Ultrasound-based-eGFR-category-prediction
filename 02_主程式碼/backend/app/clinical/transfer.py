from __future__ import annotations

import hashlib
import ipaddress
import json
import multiprocessing
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core.errors import AppError
from ..core.config import get_settings
from . import store, cases, defaults, network
from .auth import current, digest
from .service import required, new_exam, analyze_frame, frame_out, write_original, insert_frame, frame_folder
from .analysis import decode
from .resources import reserve_session,release_session

router=APIRouter(prefix='/clinical',tags=['Image transfer'])
_lock=threading.RLock()
_active=None
_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='demo-analysis')
_scheduled=set()
IDENTIFIER=re.compile(r'^[a-zA-Z0-9_-]{1,80}$')
HASH=re.compile(r'^[0-9a-f]{64}$')
PROTOCOL=2
# Item state machine (B side):
#   pending → receiving → {received_only | needs_data | queued}
#   needs_data → queued (once, when the case data becomes complete)
#   queued → analyzing → {completed | unavailable | failed};  analyzing → waiting (compute busy) → queued on resume
#   pending/queued/waiting/needs_data → cancelled
# "verified" is kept only for legacy rows written by protocol 1.
TERMINAL={'completed','unavailable','failed','cancelled','received_only'}
SETTLED=TERMINAL|{'needs_data'}  # transfer finished; analysis may still wait for case data
INFLIGHT=('queued','waiting','analyzing','verified')
QUEUE_LIMIT=2


def addresses():
    """Backward-compatible list of usable IPv4 listen addresses."""
    return sorted({i['address'] for i in network.interfaces() if i['supported']})


def certificate(host,folder):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Local image demonstration')])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
          .not_valid_after(now+timedelta(hours=24)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]),critical=False)
          .sign(key,hashes.SHA256()))
    pem=cert.public_bytes(serialization.Encoding.PEM)
    (folder/'cert.pem').write_bytes(pem)
    (folder/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    return pem.decode(),cert.fingerprint(hashes.SHA256()).hex()


def session_plan(db,session):
    """The plan locked on this session (None for preview-only)."""
    return required(db,'plans',session['plan_id']) if session['plan_id'] else None


def start(owner,host,*,port=None,analysis=None,session_id=None,mode='manual'):
    global _active
    with _lock:
        if _active: raise AppError(409,'SESSION_BUSY','一次僅能開啟一個示範接收會話。')
        bind=network.validate(host,port)
        identifier=session_id or store.uid()
        reserve_session(owner,'demo:'+identifier,86400)
        process=parent=None
        folder=get_settings().runtime_dir/'receiver'/identifier
        try:
            with store.transaction() as db:
                if session_id:
                    row=required(db,'demo_sessions',session_id)
                    if row['state']=='ended' or row['expires']<time.time():
                        raise AppError(409,'SESSION_EXPIRED','此會話不可恢復。')
                    if row['protocol']!=PROTOCOL:
                        raise AppError(409,'SESSION_PROTOCOL','此會話由舊版接收流程建立，無法以新版協定恢復；請結束後重新開始接收。')
                    db.execute("UPDATE demo_sessions SET state='active',host=?,port=? WHERE id=?",(bind['host'],port,identifier))
                    store.audit(db,owner,'receiver_resumed',identifier)
                else:
                    plan_mode,plan_id,setting_id=defaults.resolve(db,'network_demo',analysis['mode'],analysis.get('plan_id'))
                    db.execute('''INSERT INTO demo_sessions(id,owner,plan_id,state,created,expires,plan_mode,default_setting_id,protocol,host,port)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(identifier,owner,plan_id,'active',time.time(),time.time()+24*3600,
                                                               plan_mode,setting_id,PROTOCOL,bind['host'],port))
                row=required(db,'demo_sessions',identifier)
                plan=session_plan(db,row)
            folder.mkdir(parents=True,exist_ok=True)
            pem,fingerprint=certificate(bind['host'],folder)
            from .receiver import run
            ctx=multiprocessing.get_context('spawn'); parent,child=ctx.Pipe()
            process=ctx.Process(target=run,args=(child,bind['host'],str(folder/'cert.pem'),str(folder/'key.pem'),port or 0),daemon=True)
            process.start(); child.close()
            if not parent.poll(15): raise AppError(503,'RECEIVER_START','接收程序啟動逾時。')
            info=parent.recv()
            if 'port' not in info: raise network.bind_error(info.get('error'))
            token=secrets.token_urlsafe(32)
            state={'id':identifier,'owner':owner,'plan_id':row['plan_id'],'plan_mode':row['plan_mode'],'process':process,'pipe':parent,
                   'token':digest(token),'bearer':None,'pair_expires':time.time()+300,'folder':folder,
                   'url':f'https://{bind["host"]}:{info["port"]}','certificate':pem,'fingerprint':fingerprint,
                   'requirements':defaults.requirements(plan) if plan else [],'plan_label':plan['name'] if plan else '僅接收及預覽'}
            with store.transaction() as db:
                db.execute('INSERT INTO receiver_settings VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET mode=excluded.mode,host=excluded.host,port=excluded.port,updated=excluded.updated',
                           (mode,bind['host'],port,time.time()))
            _active=state
            threading.Thread(target=serve,args=(state,),daemon=True).start()
            return pairing(state,token)
        except BaseException:
            if process and process.pid:
                if process.is_alive(): process.terminate()
                process.join(5)
            if parent: parent.close()
            (folder/'key.pem').unlink(missing_ok=True)
            release_session(owner,'demo:'+identifier)
            with store.transaction() as db: db.execute("UPDATE demo_sessions SET state='interrupted' WHERE id=? AND owner=? AND state='active'",(identifier,owner))
            raise


def pairing(state,token):
    # No patient data here; requirements tell A which case fields the plan needs.
    return {'session_id':state['id'],'url':state['url'],'certificate':state['certificate'],
            'fingerprint':state['fingerprint'],'pair_token':token,'expires':state['pair_expires'],
            'protocol':PROTOCOL,'min_protocol':PROTOCOL,'case_schema':cases.CASE_SCHEMA,
            'requirements':state['requirements'],'plan_label':state['plan_label']}


def refresh_pair(session_id,owner):
    with _lock:
        state=_active
        if not state or state['id']!=session_id: raise AppError(409,'NOT_ACTIVE','接收程序未啟動。')
        token=secrets.token_urlsafe(32); state.update(token=digest(token),bearer=None,pair_expires=time.time()+300)
        with store.transaction() as db:
            db.execute("UPDATE batches SET state='paused' WHERE session_id=? AND state='running'",(session_id,))
            store.audit(db,owner,'receiver_pair_refreshed',session_id)
        return pairing(state,token)


def serve(state):
    while _active is state:
        try:
            if not state['pipe'].poll(1):
                # poll can finish after stop/restart. Never let the old listener
                # resurrect a lease or stop the replacement receiver.
                with _lock:
                    if _active is not state: break
                    with store.read_transaction() as db:
                        valid=db.execute("SELECT expires FROM demo_sessions WHERE id=? AND state='active' AND expires>?",(state['id'],time.time())).fetchone()
                    if not valid: stop_owner(state['owner'],expected_state=state)
                    else: reserve_session(state['owner'],'demo:'+state['id'],max(0,valid['expires']-time.time()))
                continue
            packet=state['pipe'].recv()
            try: value=dispatch(state,packet); code=200
            except AppError as exc: code=exc.status_code; value={'error':exc.code,'message':exc.message}
            except (ValueError,TypeError,KeyError): code=422; value={'error':'INVALID_REQUEST','message':'要求格式錯誤。'}
            except Exception: code=500; value={'error':'RECEIVER_OPERATION_FAILED','message':'接收端處理失敗，請於 B 查看作業紀錄。'}
            state['pipe'].send((code,value))
        except (EOFError,OSError):
            stop_owner(state['owner'],finish=False,expected_state=state)
            break


def register_batch(state,body):
    if body.get('protocol')!=PROTOCOL or body.get('case_schema')!=cases.CASE_SCHEMA:
        raise AppError(426,'SENDER_UPGRADE_REQUIRED','傳送工具版本與接收端不相容：接收端需要協定 2（含逐張案例資料）。請更新 A 的傳送工具後重新配對。')
    entries=body.get('items',[]); batch_id=str(body.get('id',''))
    if not IDENTIFIER.fullmatch(batch_id) or not isinstance(entries,list) or not 1<=len(entries)<=1000: raise ValueError()
    clean=[]
    for entry in entries:
        item_id,sha,case_sha=str(entry['id']),str(entry['sha256']),str(entry['case_sha256'])
        if not IDENTIFIER.fullmatch(item_id) or not HASH.fullmatch(sha) or not HASH.fullmatch(case_sha): raise ValueError()
        case=cases.parse(entry['case'])
        if cases.digest(entry['case'])!=case_sha: raise AppError(422,'CASE_DIGEST_MISMATCH','案例資料摘要不符，可能在傳輸中被修改；請重新建立批次。')
        clean.append((item_id,sha,case_sha,case,entry['case']))
    if len({c[0] for c in clean})!=len(clean): raise ValueError()
    with store.transaction() as db:
        old=db.execute('SELECT * FROM batches WHERE id=?',(batch_id,)).fetchone()
        if old:
            if old['session_id']!=state['id']: raise AppError(409,'BATCH_CONFLICT','批次識別衝突。')
            existing={(r['id'],r['sha256'],r['case_sha256']) for r in db.execute('SELECT * FROM items WHERE batch_id=?',(batch_id,))}
            if existing!={c[:3] for c in clean}: raise AppError(409,'BATCH_CONFLICT','重試清單的影像或案例資料與原批次不同；不覆寫已登記的項目。')
            return {'id':batch_id}
        count=db.execute('SELECT COUNT(*) FROM items JOIN batches ON items.batch_id=batches.id WHERE session_id=?',(state['id'],)).fetchone()[0]
        if count+len(clean)>1000: raise AppError(413,'SESSION_LIMIT','單次會話最多 1000 張圖片。')
        db.execute('INSERT INTO batches VALUES(?,?,?,?)',(batch_id,state['id'],'running',time.time()))
        db.executemany('''INSERT INTO items(id,batch_id,sha256,frame_id,status,error,created,case_code,case_sha256,case_payload)
                       VALUES(?,?,?,NULL,'pending',NULL,?,?,?,?)''',
                       [(i,batch_id,h,time.time(),case.case_code,c,cases.canonical(raw).decode('utf-8')) for i,h,c,case,raw in clean])
    return {'id':batch_id}


def receive_item(state,batch_id,item_id,claimed_sha,body):
    """Validate, then publish image + case + item in one commit (no partial pairing)."""
    with store.transaction() as db:
        batch=required(db,'batches',batch_id)
        if batch['session_id']!=state['id']: raise AppError(404,'BATCH_NOT_FOUND','找不到批次。')
        item=db.execute('SELECT * FROM items WHERE batch_id=? AND id=?',(batch_id,item_id)).fetchone()
        if not item: raise AppError(404,'ITEM_NOT_FOUND','項目不在確認清單。')
        if claimed_sha!=item['sha256']: raise AppError(409,'ITEM_CONFLICT','項目影像與登記內容不同；不覆寫已登記的項目。')
        if item['status']!='pending': return {'id':item['id'],'status':item['status']}
        if batch['state']!='running': raise AppError(409,'BATCH_PAUSED','批次已暫停。')
        active=db.execute(f"SELECT COUNT(*) FROM items JOIN batches b ON b.id=items.batch_id WHERE b.session_id=? AND items.status IN ({','.join('?'*len(INFLIGHT))})",(state['id'],*INFLIGHT)).fetchone()[0]
        if active>=QUEUE_LIMIT: raise AppError(429,'BACKPRESSURE','分析佇列已滿，請等待。')
    started=time.perf_counter()
    if hashlib.sha256(body).hexdigest()!=claimed_sha: raise AppError(422,'HASH_MISMATCH','圖片雜湊不符。')
    try: decode(body)
    except AppError:
        with store.transaction() as db: db.execute("UPDATE items SET status='failed',error='INVALID_IMAGE',case_payload=NULL WHERE batch_id=? AND id=? AND status='pending'",(batch_id,item_id))
        return {'id':item_id,'status':'failed'}
    with store.transaction() as db:
        paths=[store.managed(r['path']) for r in db.execute("SELECT path FROM frames WHERE saved=0 AND source='network_demo'")]
    used=sum(p.stat().st_size for p in paths if p.is_file())
    if used+len(body)>2*1024**3: raise AppError(413,'STORAGE_LIMIT','影像暫存已達 2 GB（含待補資料的影像），請先補資料、保存或結束未保存的會話。')
    frame_id=store.uid()
    with store.transaction() as db:
        claimed=db.execute("UPDATE items SET status='receiving',staging_frame_id=? WHERE batch_id=? AND id=? AND status='pending'",(frame_id,batch_id,item_id))
        if claimed.rowcount!=1: raise AppError(409,'ITEM_BUSY','此項目正在處理，請稍後查詢狀態。')
    try:
        path,_=write_original(body,frame_id)
        with store.transaction() as db:
            session=required(db,'demo_sessions',state['id']); item=db.execute('SELECT * FROM items WHERE batch_id=? AND id=?',(batch_id,item_id)).fetchone()
            case=cases.parse(json.loads(item['case_payload']))
            payload=cases.transfer_payload(case)
            exam_id=new_exam(db,'demo',None,case.case_code,case.side,payload,state['id'],source='transfer')
            plan=session_plan(db,session)
            if not plan:
                status,missing='received_only',[]
                insert_frame(db,frame_id,exam_id,body,path,'network_demo',result={'message':'本會話設定為「僅接收及預覽」，未進行分析。'})
            else:
                missing=cases.missing(payload,defaults.requirements(plan))
                status='needs_data' if missing else 'queued'
                insert_frame(db,frame_id,exam_id,body,path,'network_demo',status='needs_data' if missing else 'received',
                             result=missing_result(missing) if missing else None)
            db.execute('''UPDATE items SET frame_id=?,exam_id=?,status=?,missing_fields=?,case_payload=NULL,staging_frame_id=NULL,
                       verification_ms=? WHERE batch_id=? AND id=?''',
                       (frame_id,exam_id,status,store.dumps(missing) if missing else None,round((time.perf_counter()-started)*1000,2),batch_id,item_id))
    except BaseException:
        discard_staging(batch_id,item_id,frame_id)
        raise
    if status=='queued': enqueue(state['id'],batch_id,item_id,frame_id,state['plan_id'])
    return {'id':item_id,'status':status}


def missing_result(missing):
    return {'code':'METADATA_REQUIRED','missing':missing,
            'message':'待補資料：'+'、'.join(cases.LABELS[m] for m in missing)+'。補齊後會自動分析一次。'}


def discard_staging(batch_id,item_id,frame_id):
    """Undo an unpublished receive: only the exact staged folder, and only if unreferenced."""
    import shutil
    with store.transaction() as db:
        if db.execute('SELECT 1 FROM frames WHERE id=?',(frame_id,)).fetchone(): return
        folder=frame_folder(frame_id)
        if folder.exists(): shutil.rmtree(folder)
        db.execute("UPDATE items SET status='pending',staging_frame_id=NULL WHERE batch_id=? AND id=? AND status='receiving' AND staging_frame_id=?",(batch_id,item_id,frame_id))


def dispatch(state,packet):
    with _lock:
        if _active is not state: raise AppError(410,'SESSION_ENDED','會話已結束。')
        with store.transaction() as db:
            session=required(db,'demo_sessions',state['id'])
            valid=db.execute("SELECT 1 FROM demo_sessions WHERE id=? AND state='active' AND expires>?",(state['id'],time.time())).fetchone()
        if not valid or session['state']!='active' or session['expires']<time.time(): raise AppError(401,'SESSION_EXPIRED','接收會話已結束或到期。')
        body=packet['body']; op=packet['op']
        if op=='/pair':
            if state['bearer'] or time.time()>state['pair_expires'] or not secrets.compare_digest(digest(str(body.get('token',''))),state['token']):
                raise AppError(401,'PAIR_REJECTED','配對資料已使用或到期，請在 B 重新產生配對檔。')
            bearer=secrets.token_urlsafe(32); state['bearer']=digest('Bearer '+bearer)
            return {'session_id':state['id'],'bearer':bearer,'protocol':PROTOCOL}
        if not state['bearer'] or not secrets.compare_digest(digest(packet['bearer']),state['bearer']):
            raise AppError(401,'PAIR_REQUIRED','請重新配對。')
        if op=='/batches' and packet['method']=='POST': return register_batch(state,body)
        if op=='/items': return receive_item(state,packet['batch'],packet['item'],packet['sha256'],body)
        batch_id=body.get('batch_id') if isinstance(body,dict) else None
        if op=='/batches': batch_id=packet['query'].get('id',[''])[0]
        with store.transaction() as db:
            batch=required(db,'batches',batch_id)
            if batch['session_id']!=state['id']: raise AppError(404,'BATCH_NOT_FOUND','找不到批次。')
            if op=='/batches':
                # A sees transfer state by case code only; AI results stay on B.
                return {'id':batch_id,'state':batch['state'],'items':[{**dict(r),'missing_fields':json.loads(r['missing_fields']) if r['missing_fields'] else []}
                        for r in db.execute('SELECT id,status,error,sha256,case_sha256,case_code,missing_fields FROM items WHERE batch_id=? ORDER BY created,id',(batch_id,))]}
            if op=='/control':
                action=body.get('action'); mapped={'pause':'paused','resume':'running','cancel':'cancelled'}
                if action not in mapped: raise ValueError()
                if batch['state']=='cancelled' and action!='cancel': raise AppError(409,'BATCH_CANCELLED','已取消的批次不能繼續。')
                db.execute('UPDATE batches SET state=? WHERE id=?',(mapped[action],batch_id))
                if action=='cancel': db.execute("UPDATE items SET status='cancelled',case_payload=NULL WHERE batch_id=? AND status IN ('pending','verified','waiting','queued','needs_data')",(batch_id,))
                if action=='resume':
                    for item in db.execute("SELECT * FROM items WHERE batch_id=? AND status IN ('waiting','verified','queued') ORDER BY created LIMIT ?",(batch_id,QUEUE_LIMIT)):
                        if item['status']!='queued': db.execute("UPDATE items SET status='queued' WHERE batch_id=? AND id=?",(batch_id,item['id']))
                        enqueue(state['id'],batch_id,item['id'],item['frame_id'],state['plan_id'])
                return {'state':mapped[action]}
        raise ValueError()


def enqueue(session_id,batch_id,item_id,frame_id,plan_id):
    key=(batch_id,item_id)
    with _lock:
        if key in _scheduled: return
        _scheduled.add(key)
    def execute():
        try: process_item(session_id,batch_id,item_id,frame_id,plan_id)
        finally:
            with _lock: _scheduled.discard(key)
    _executor.submit(execute)


def process_item(session_id,batch_id,item_id,frame_id,plan_id):
    started=time.perf_counter()
    if not plan_id: return
    try:
        with store.transaction() as db:
            session=required(db,'demo_sessions',session_id); batch=required(db,'batches',batch_id)
            item=db.execute('SELECT status FROM items WHERE batch_id=? AND id=?',(batch_id,item_id)).fetchone()
            if session['state']!='active' or batch['state']=='cancelled' or item['status'] not in ('queued','waiting','verified'): return
            if batch['state']!='running':
                db.execute("UPDATE items SET status='waiting' WHERE batch_id=? AND id=?",(batch_id,item_id)); return
            db.execute("UPDATE items SET status='analyzing' WHERE batch_id=? AND id=?",(batch_id,item_id))
        result=analyze_frame(frame_id,plan_id,actor=session['owner'])
        status=result['status']; error=result['result'].get('code') if status!='completed' else None
        if status=='unavailable' and error=='METADATA_REQUIRED':
            # Case data changed between scheduling and inference: wait for data again.
            with store.transaction() as db:
                exam=db.execute('SELECT e.payload FROM frames f JOIN exams e ON e.id=f.exam_id WHERE f.id=?',(frame_id,)).fetchone()
                plan=required(db,'plans',plan_id); missing=cases.missing(store.rowdict(exam)['payload'],defaults.requirements(plan))
                db.execute("UPDATE items SET status='needs_data',missing_fields=?,error=NULL WHERE batch_id=? AND id=?",(store.dumps(missing),batch_id,item_id))
                db.execute('UPDATE frames SET status=?,result=? WHERE id=?',('needs_data',store.dumps(missing_result(missing)),frame_id))
            return
    except AppError as exc:
        # Compute busy is recoverable: wait, pause the batch and tell both sides.
        status='waiting' if exc.status_code==409 else 'failed'; error=exc.code
        with store.transaction() as db: db.execute("UPDATE batches SET state='paused' WHERE id=? AND state!='cancelled'",(batch_id,))
    except Exception: status='failed'; error='ANALYSIS_FAILED'
    with store.transaction() as db:
        db.execute('UPDATE items SET status=?,error=?,analysis_ms=? WHERE batch_id=? AND id=?',(status,error,round((time.perf_counter()-started)*1000,2),batch_id,item_id))
        settle_batch(db,batch_id)


def settle_batch(db,batch_id):
    if not db.execute(f"SELECT 1 FROM items WHERE batch_id=? AND status NOT IN ({','.join('?'*len(SETTLED))})",(batch_id,*SETTLED)).fetchone():
        db.execute("UPDATE batches SET state='completed' WHERE id=? AND state!='cancelled'",(batch_id,))


def resume_case(exam_id):
    """After case data is saved: continue a waiting transfer item exactly once."""
    scheduled=[]
    with store.transaction() as db:
        exam=required(db,'exams',exam_id)
        rows=db.execute('''SELECT i.*,s.plan_id,s.state AS session_state,b.state AS batch_state FROM items i JOIN batches b ON b.id=i.batch_id
                        JOIN demo_sessions s ON s.id=b.session_id WHERE i.exam_id=? AND i.status='needs_data' ''',(exam_id,)).fetchall()
        for row in rows:
            plan=required(db,'plans',row['plan_id'])
            missing=cases.missing(exam['payload'],defaults.requirements(plan))
            if missing:
                db.execute('UPDATE items SET missing_fields=? WHERE batch_id=? AND id=?',(store.dumps(missing),row['batch_id'],row['id']))
                db.execute('UPDATE frames SET result=? WHERE id=?',(store.dumps(missing_result(missing)),row['frame_id']))
                continue
            if row['session_state']!='active' or row['batch_state']=='cancelled':
                db.execute('UPDATE frames SET status=?,result=? WHERE id=?',('received',store.dumps({'message':'資料已補齊，但接收會話已結束；可在案例頁以進階分析手動執行。'}),row['frame_id']))
                continue
            moved=db.execute("UPDATE items SET status='queued',missing_fields=NULL WHERE batch_id=? AND id=? AND status='needs_data'",(row['batch_id'],row['id']))
            if moved.rowcount==1:
                db.execute("UPDATE frames SET status='received',result=NULL WHERE id=?",(row['frame_id'],))
                scheduled.append((row['batch_id'],row['id'],row['frame_id'],row['plan_id']))
            if row['batch_state']=='completed': db.execute("UPDATE batches SET state='running' WHERE id=?",(row['batch_id'],))
        session_id=exam['demo_session_id']
    for batch_id,item_id,frame_id,plan_id in scheduled: enqueue(session_id,batch_id,item_id,frame_id,plan_id)
    return len(scheduled)


def cleanup_session(session_id):
    from .temporary_cleanup import cleanup_session as clean
    clean(session_id)


def stop_owner(owner,finish=True,*,expected_state=None):
    global _active
    with _lock:
        state=_active
        if not state or state['owner']!=owner or (expected_state is not None and state is not expected_state): return
        _active=None
        release_session(owner,'demo:'+state['id'])
        with store.transaction() as db:
            db.execute('UPDATE demo_sessions SET state=? WHERE id=?',('ended' if finish else 'interrupted',state['id']))
            db.execute("UPDATE batches SET state='paused' WHERE session_id=? AND state='running'",(state['id'],))
            if finish: db.execute("UPDATE items SET status='cancelled',case_payload=NULL WHERE batch_id IN(SELECT id FROM batches WHERE session_id=?) AND status IN ('pending','verified','waiting','queued','needs_data')",(state['id'],))
        state['process'].terminate(); state['process'].join(5); state['pipe'].close()
        (state['folder']/'key.pem').unlink(missing_ok=True)
    if finish:
        # Serialize cleanup behind any currently running inference.
        _executor.submit(cleanup_session,state['id'])


def recover():
    from .temporary_cleanup import recover as recover_cleanup
    recover_cleanup()
    for key in (get_settings().runtime_dir/'receiver').glob('*/key.pem'):
        if key.resolve().is_relative_to((get_settings().runtime_dir/'receiver').resolve()): key.unlink(missing_ok=True)
    with store.transaction() as db:
        staged=[dict(r) for r in db.execute("SELECT batch_id,id,staging_frame_id FROM items WHERE status='receiving'")]
    for row in staged:
        # A receive interrupted before its single publishing commit leaves no
        # frame/exam row; discard only that exact staged folder and retry later.
        if row['staging_frame_id']: discard_staging(row['batch_id'],row['id'],row['staging_frame_id'])
    with store.transaction() as db:
        db.execute("UPDATE demo_sessions SET state='interrupted' WHERE state='active'")
        db.execute("UPDATE batches SET state='paused' WHERE state='running'")
        db.execute("UPDATE items SET status='waiting' WHERE status IN ('verified','analyzing','queued')")
        db.execute("UPDATE frames SET status='received' WHERE status='analyzing'")
        expired=[r['id'] for r in db.execute('SELECT id FROM demo_sessions WHERE expires<? OR state=?',(time.time(),'ended'))]
    for sid in expired: cleanup_session(sid)


def shutdown():
    if _active: stop_owner(_active['owner'],finish=False)
    _executor.submit(lambda:None).result(timeout=120)


def expire():
    from .routes import _previews,_preview_lock
    with _preview_lock:
        for identifier in list(_previews):
            if _previews[identifier]['created']<time.time()-300: _previews.pop(identifier,None)
    if _active:
        with store.transaction() as db: session=required(db,'demo_sessions',_active['id'])
        if session['expires']<time.time(): stop_owner(_active['owner'])
    with store.transaction() as db:
        expired=[r['id'] for r in db.execute('SELECT id FROM demo_sessions WHERE expires<? OR state=?',(time.time(),'ended'))]
    for sid in expired: cleanup_session(sid)


class AnalysisChoice(BaseModel):
    """Explicit: use the model-center default, preview only, or one named plan."""
    model_config=ConfigDict(extra='forbid')
    mode: Literal['default','preview_only','plan']
    plan_id: str|None=None

    @model_validator(mode='after')
    def consistent(self):
        if (self.mode=='plan')!=(self.plan_id is not None): raise ValueError('mode=plan 需要 plan_id；其他模式不可帶 plan_id')
        return self


class SessionCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    host: str=Field(min_length=1,max_length=64)
    port: int|None=None
    address_mode: Literal['auto','manual']='manual'
    analysis: AnalysisChoice|None=None
    session_id: str|None=None


@router.get('/receiver-addresses')
def receiver_addresses(request: Request):
    current(request,'clinical.read'); return addresses()


@router.get('/receiver-settings')
def receiver_settings(request: Request):
    current(request,'clinical.read')
    items=network.interfaces()
    with store.read_transaction() as db:
        row=db.execute('SELECT * FROM receiver_settings WHERE id=1').fetchone()
    saved=dict(row) if row else None
    check=None
    if saved:
        # Remembered, but never trusted: revalidate against the current interfaces.
        try: network.validate(saved['host'],saved['port']); check={'valid':True}
        except AppError as exc: check={'valid':False,'code':exc.code,'message':exc.message}
    return {'interfaces':items,'recommended':network.recommended(items),'saved':saved,'saved_check':check,
            'protocol':PROTOCOL,'ipv6_supported':False}


@router.post('/receiver-settings/validate')
def receiver_validate(payload: SessionCreate,request: Request):
    current(request,'clinical.operate')
    return network.validate(payload.host,payload.port)


@router.post('/demo-sessions')
def session_create(payload: SessionCreate,request: Request):
    user=current(request,'clinical.operate')
    if payload.session_id:
        if payload.analysis is not None: raise AppError(422,'SESSION_PLAN_LOCKED','恢復會話沿用建立時鎖定的方案，不能改變分析模式。')
        return start(user['id'],payload.host,port=payload.port,session_id=payload.session_id,mode=payload.address_mode)
    if payload.analysis is None:
        raise AppError(422,'ANALYSIS_MODE_REQUIRED','請明確指定分析模式：使用模型區預設方案、僅接收及預覽，或指定方案。')
    return start(user['id'],payload.host,port=payload.port,analysis=payload.analysis.model_dump(),mode=payload.address_mode)


@router.get('/demo-sessions')
def session_list(request: Request):
    current(request,'clinical.read')
    with store.transaction() as db:
        return [dict(r) for r in db.execute('SELECT s.*,p.name AS plan_name,p.created AS plan_created FROM demo_sessions s LEFT JOIN plans p ON p.id=s.plan_id ORDER BY s.created DESC')]


@router.post('/demo-sessions/{identifier}/{action}')
def session_control(identifier: str,action: str,request: Request):
    user=current(request,'clinical.operate')
    if action=='pair': return refresh_pair(identifier,user['id'])
    if action!='stop': raise AppError(404,'ACTION_UNKNOWN','不支援此操作。')
    with store.transaction() as db:
        row=required(db,'demo_sessions',identifier)
        store.audit(db,user['id'],'receiver_stopped',identifier)
    if _active and _active['id']==identifier: stop_owner(_active['owner'])
    else:
        with store.transaction() as db: db.execute("UPDATE demo_sessions SET state='ended' WHERE id=?",(identifier,))
        _executor.submit(cleanup_session,identifier)
    return {'state':'ended'}


def plan_names(db):
    return {r['id']:{'name':r['name'],'created':r['created']} for r in db.execute('SELECT id,name,created FROM plans')}


@router.get('/demo-batches')
def batch_list(request: Request,session_id: str):
    current(request,'clinical.read')
    with store.transaction() as db:
        session=required(db,'demo_sessions',session_id)
        names=plan_names(db)
        # Local capabilities authorize control; the historical owner remains unchanged.
        result=[]
        for batch in db.execute('SELECT * FROM batches WHERE session_id=? ORDER BY created',(session_id,)):
            value=dict(batch); value['items']=[]
            for item in db.execute('SELECT * FROM items WHERE batch_id=? ORDER BY created,id',(batch['id'],)):
                record=store.rowdict(item); record.pop('case_payload',None)
                record['missing_fields']=json.loads(item['missing_fields']) if item['missing_fields'] else []
                if item['frame_id']:
                    frame=required(db,'frames',item['frame_id']); record['frame']=frame_out(frame,names)
                value['items'].append(record)
            result.append(value)
    return result


@router.get('/demo-batches/{identifier}/summary')
def batch_summary(identifier: str,request: Request):
    current(request,'clinical.read')
    with store.transaction() as db:
        batch=required(db,'batches',identifier);session=required(db,'demo_sessions',batch['session_id'])
        # Local capabilities authorize control; the historical owner remains unchanged.
        items=[dict(r) for r in db.execute('SELECT id,case_code,status,sha256,case_sha256,verification_ms,analysis_ms FROM items WHERE batch_id=? ORDER BY created,id',(identifier,))]
    summary={'batch_id':identifier,'state':batch['state'],'plan_mode':session['plan_mode'],'scope':'真實圖片傳輸與分析流程摘要，不含診斷文字','items':items,
             'counts':{status:sum(i['status']==status for i in items) for status in sorted({i['status'] for i in items})}}
    return Response(store.dumps(summary),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="batch-{identifier}.json"'})
