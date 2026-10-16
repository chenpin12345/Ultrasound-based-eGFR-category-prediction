"""Portable Windows image sender. Standard library only; never imports the AI application."""
from __future__ import annotations

import ctypes
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, urlopen, build_opener, HTTPSHandler, ProxyHandler, HTTPRedirectHandler

VERSION='2.0.0'
PROTOCOL=2
CASE_SCHEMA=1
MAX_BYTES=32*1024*1024
TERMINAL={'completed','unavailable','failed','cancelled','received_only'}
SETTLED=TERMINAL|{'needs_data'}  # transfer done; B may still wait for case data
# Case data stays in this process's memory only: never written to disk, URLs or logs.
STATE={'files':{},'queue':[],'pair':None,'bearer':None,'batch':None,'phase':'idle','message':'請先配對 B 電腦，再選擇圖片。','running':False,
       'requirements':[],'plan_label':None}
LOCK=threading.RLock()
TOKEN=secrets.token_urlsafe(32)
TEXT_LIMITS={'case_code':40,'patient_ref':40,'patient_name':60,'exam_name':80,'exam_time':32,'notes':500}
CONTROL=re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')
REQUIREMENT_LABELS={'age':'年齡','has_diabetes':'糖尿病狀態（有／無）'}

class RemoteError(Exception):
    def __init__(self,code,message,error=None): self.code=code; self.error=error; super().__init__(message)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def connection_message(reason):
    """A specific, actionable reason; TLS verification is never relaxed."""
    if isinstance(reason,ssl.SSLCertVerificationError):
        return '憑證不符：B 目前的憑證或位址與配對檔不一致（B 可能已重新開始接收或改用其他位址）。請匯入 B 最新產生的配對檔。'
    if isinstance(reason,ConnectionRefusedError):
        return '無法連線：B 的接收端未啟動，或連接埠已變更。請在 B 確認正在接收，並重新產生配對檔。'
    if isinstance(reason,(TimeoutError,socket.timeout)):
        return '連線逾時：請確認兩台電腦在同一網路，且 B 的防火牆允許此連接埠。'
    if isinstance(reason,ssl.SSLError): return 'TLS 連線失敗，未傳送任何資料；請重新匯入 B 的配對檔。'
    return '無法連線到 B（'+type(reason).__name__+'）；請確認網路與 B 的接收狀態。'

def remote(path,payload=None,headers=None,method=None):
    with LOCK: pair=STATE['pair']; bearer=STATE['bearer']
    if not pair: raise ValueError('請先匯入配對資料。')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=pair['certificate'])
    data=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
    req=Request(pair['url']+path,data=data,method=method or ('POST' if data is not None else 'GET'),
                headers={'Content-Type':'application/octet-stream' if isinstance(payload,bytes) else 'application/json',
                         'Authorization':'Bearer '+(bearer or ''),**(headers or {})})
    try:
        with build_opener(ProxyHandler({}),HTTPSHandler(context=context),NoRedirect()).open(req,timeout=40) as response:
            return json.load(response)
    except HTTPError as exc:
        try: body=json.load(exc); message=body.get('message') or f'接收端回覆 {exc.code}'; error=body.get('error')
        except (ValueError,AttributeError): message=f'接收端回覆 {exc.code}'; error=None
        raise RemoteError(exc.code,message,error) from exc
    except URLError as exc: raise RemoteError(0,connection_message(exc.reason),'NETWORK') from exc
    except (TimeoutError,socket.timeout,ConnectionError,ssl.SSLError) as exc: raise RemoteError(0,connection_message(exc),'NETWORK') from exc

def pair_receiver(pair,fingerprint):
    if pair.get('protocol')!=PROTOCOL or pair.get('case_schema')!=CASE_SCHEMA:
        raise ValueError('配對檔版本不相容：此傳送工具使用協定 2（逐張案例資料）。請確認 B 已更新，並使用 B 新產生的配對檔。')
    parsed=urlsplit(pair['url']); address=ipaddress.ip_address(parsed.hostname or '')
    if parsed.scheme!='https' or parsed.path not in ('','/') or parsed.username or parsed.query or parsed.fragment or not (address.is_private or address.is_loopback):
        raise ValueError('配對位址必須為區域網路 HTTPS 位址。')
    actual=hashlib.sha256(ssl.PEM_cert_to_DER_cert(pair['certificate'])).hexdigest()
    if not secrets.compare_digest(actual,fingerprint.lower().replace(':','').replace(' ','')) or actual!=pair['fingerprint']:
        raise ValueError('指紋不符，請與 B 電腦畫面核對。')
    if time.time()>pair['expires']: raise ValueError('配對資料已到期，請在 B 重新產生。')
    with LOCK:
        if STATE['running']: raise ValueError('請先暫停，再重新配對。')
        previous=STATE['pair']
        if STATE['batch'] and previous and previous['session_id']!=pair['session_id']:
            raise ValueError('恢復批次必須配對原會話；如需新會話請先清除已結束的清單。')
        STATE.update(pair=pair,bearer=None)
    result=remote('/pair',{'token':pair['pair_token']})
    requirements=[r for r in pair.get('requirements',[]) if r in REQUIREMENT_LABELS]
    with LOCK: STATE.update(bearer=result['bearer'],phase='ready',requirements=requirements,plan_label=pair.get('plan_label'),
                            message='配對完成。請為每張圖片填寫案例資料；圖片只會在明確選取後傳送。')
    return {'session_id':result['session_id'],'plan_label':pair.get('plan_label'),'requirements':requirements}

def clean_case(raw):
    """Same rules as B's schema 1. Only what the user typed; empty means not provided."""
    if not isinstance(raw,dict): raise ValueError('案例資料格式錯誤。')
    unknown=set(raw)-set(TEXT_LIMITS)-{'age','diabetes','side'}
    if unknown: raise ValueError('不支援的欄位：'+'、'.join(sorted(unknown)))
    case={}
    for key,limit in TEXT_LIMITS.items():
        value=raw.get(key)
        if value is None or (isinstance(value,str) and not value.strip()): continue
        if not isinstance(value,str): raise ValueError(key+' 必須是文字。')
        value=value.strip()
        if len(value)>limit: raise ValueError(f'{key} 最多 {limit} 字。')
        if CONTROL.search(value) or (key!='notes' and '\n' in value): raise ValueError(key+' 含有不允許的字元。')
        case[key]=value
    if 'case_code' not in case: raise ValueError('請填寫案例識別。')
    age=raw.get('age')
    if age not in (None,''):
        if isinstance(age,bool) or not (isinstance(age,int) or (isinstance(age,str) and age.strip().isdigit())): raise ValueError('年齡須為 0–130 的整數。')
        age=int(age)
        if not 0<=age<=130: raise ValueError('年齡須為 0–130 的整數。')
        case['age']=age
    diabetes=raw.get('diabetes')
    if diabetes not in (None,''):
        if diabetes not in ('yes','no','unknown'): raise ValueError('糖尿病狀態只能是有、無或未知。')
        case['diabetes']=diabetes
    side=raw.get('side') or 'unspecified'
    if side not in ('left','right','both','unspecified'): raise ValueError('側別錯誤。')
    case['side']=side
    if 'exam_time' in case:
        try: datetime.fromisoformat(case['exam_time'])
        except ValueError: raise ValueError('檢查時間格式錯誤。') from None
    return case

def case_digest(case):
    return hashlib.sha256(json.dumps(case,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()

def case_missing(case):
    with LOCK: required=list(STATE['requirements'])
    missing=[]
    if case is None: return ['case_code']+required
    if 'case_code' not in case: missing.append('case_code')
    if 'age' in required and 'age' not in case: missing.append('age')
    if 'has_diabetes' in required and case.get('diabetes') not in ('yes','no'): missing.append('has_diabetes')
    return missing

def set_case(identifier,raw):
    case=clean_case(raw)
    with LOCK:
        if identifier not in STATE['files']: raise ValueError('找不到圖片。')
        STATE['files'][identifier]['case']=case
    return {'case':case,'missing':case_missing(case)}

def copy_case(source,targets):
    """Explicit copy chosen by the user; case code and side stay per image."""
    with LOCK:
        origin=STATE['files'].get(source,{}).get('case')
        if not origin: raise ValueError('來源圖片尚未填寫案例資料。')
        if not targets or source in targets or any(t not in STATE['files'] for t in targets): raise ValueError('請勾選要套用的其他圖片。')
        applied=[]
        for target in targets:
            record=STATE['files'][target]; own=record.get('case') or {}
            copied={k:v for k,v in origin.items() if k not in ('case_code','side')}
            # Without its own case code the image stays incomplete and cannot be sent.
            record['case']={**copied,'side':own.get('side','unspecified'),**({'case_code':own['case_code']} if 'case_code' in own else {})}
            applied.append({'name':record['name'],'case_code':own.get('case_code')})
    return {'applied':applied,'fields':[k for k in origin if k not in ('case_code','side')]}

def desktop():
    if os.name=='nt':
        # Windows resolves redirected/OneDrive Desktop for the signed-in user.
        buffer=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,0x10,None,0,buffer)==0: return Path(buffer.value)
    return Path.home()/'Desktop'

def choose(mode):
    import tkinter as tk
    from tkinter import filedialog
    with LOCK:
        if STATE['running']: raise ValueError('請先暫停傳送。')
    root=tk.Tk(); root.withdraw(); root.attributes('-topmost',True)
    initial=desktop()/'腎超_照片'
    try:
        if mode=='files': selected=filedialog.askopenfilenames(parent=root,title='選擇原始超音波圖片',initialdir=str(initial if initial.is_dir() else desktop()),filetypes=[('JPEG / PNG','*.jpg *.jpeg *.png')]); paths=map(Path,selected)
        else:
            selected=filedialog.askdirectory(parent=root,title='選擇超音波圖片資料夾',initialdir=str(initial if initial.is_dir() else desktop()))
            paths=scan(Path(selected)) if selected else []
        records={}; excluded=0
        for path in paths:
            if path.is_symlink() or path.suffix.lower() not in {'.jpg','.jpeg','.png'} or any('mask' in part.lower() for part in path.parts): excluded+=1; continue
            size=path.stat().st_size
            if not 0<size<=MAX_BYTES: excluded+=1; continue
            records[uuid.uuid4().hex]={'path':path,'name':path.name,'size':size,'case':None}
            if len(records)>=50000: break
    finally: root.destroy()
    with LOCK: STATE['files']=records; STATE['message']=f'列出 {len(records)} 張；排除 {excluded} 個不適用項目。未選取任何圖片。'
    return {'count':len(records),'excluded':excluded}

def scan(folder):
    for parent,dirs,files in os.walk(folder,followlinks=False):
        dirs[:]=[d for d in dirs if 'mask' not in d.lower() and not (Path(parent)/d).is_symlink()]
        for name in files:
            if Path(name).suffix.lower() in {'.jpg','.jpeg','.png'}: yield Path(parent)/name

def queue_start(ids,mode):
    with LOCK:
        if STATE['running']: raise ValueError('已有傳送作業。')
        if not STATE['bearer']: raise ValueError('請先配對。')
        if STATE['queue']: raise ValueError('請繼續既有批次或清除清單後再建立。')
        if not 1<=len(ids)<=1000 or len(set(ids))!=len(ids): raise ValueError('每批請選取 1 至 1000 張圖片。')
        incomplete=[STATE['files'][i]['name'] for i in ids if not (STATE['files'][i].get('case') or {}).get('case_code')]
        if incomplete: raise ValueError('以下圖片尚未填寫案例識別，未建立批次：'+'、'.join(incomplete[:10])+('…' if len(incomplete)>10 else ''))
        # Freeze each image's own case data now; later edits never change a sent batch.
        STATE['queue']=[{'id':uuid.uuid4().hex,'file':STATE['files'][identifier],'status':'pending','sha256':None,
                         'case':dict(STATE['files'][identifier]['case']),'case_sha256':case_digest(STATE['files'][identifier]['case']),
                         'case_code':STATE['files'][identifier]['case']['case_code']} for identifier in ids]
        STATE.update(batch=uuid.uuid4().hex,phase='running',running=True,mode=mode,message='計算原始檔案雜湊，建立確認清單。')
    threading.Thread(target=worker,daemon=True).start()

def worker():
    try:
        with LOCK: queue=STATE['queue']; batch=STATE['batch']
        for item in queue:
            if item['sha256'] is None:
                data=item['file']['path'].read_bytes()
                if len(data)>MAX_BYTES: raise ValueError('選取後檔案大小已變更，請重新建立批次。')
                item['sha256']=hashlib.sha256(data).hexdigest()
        remote('/batches',{'protocol':PROTOCOL,'case_schema':CASE_SCHEMA,'id':batch,
                           'items':[{'id':i['id'],'sha256':i['sha256'],'case':i['case'],'case_sha256':i['case_sha256']} for i in queue]})
        status=remote('/batches?id='+batch)
        by_id={i['id']:i for i in status['items']}
        for item in queue:
            confirmed=by_id[item['id']]
            if confirmed['sha256']!=item['sha256'] or confirmed.get('case_sha256')!=item['case_sha256']: raise ValueError('接收端清單的影像或案例資料摘要不符，已停止。')
            item['status']=confirmed['status']; item['error']=confirmed.get('error'); item['missing_fields']=confirmed.get('missing_fields') or []
        with LOCK: phase=STATE['phase']
        if phase!='running':
            remote('/control',{'batch_id':batch,'action':'cancel' if phase=='cancelled' else 'pause'}); return
        if status['state']=='paused': remote('/control',{'batch_id':batch,'action':'resume'})
        for item in queue:
            with LOCK:
                if STATE['phase']!='running': break
            if item['status'] in SETTLED: continue
            start=time.perf_counter()
            if item['status']=='pending':
                item['status']='sending'
                data=item['file']['path'].read_bytes()
                if hashlib.sha256(data).hexdigest()!=item['sha256']: raise ValueError('圖片在選取後被修改，已暫停。')
                while True:
                    try:
                        reply=remote('/items',data,{'X-Batch-ID':batch,'X-Item-ID':item['id'],'X-Content-SHA256':item['sha256']})
                        item['status']=reply['status']; item['transfer_ms']=round((time.perf_counter()-start)*1000); break
                    except RemoteError as exc:
                        if exc.code!=429: raise
                        with LOCK:
                            if STATE['phase']!='running': return
                        time.sleep(1)
            while item['status'] not in SETTLED:
                time.sleep(.5)
                status=remote('/batches?id='+batch)
                confirmed=next(i for i in status['items'] if i['id']==item['id'])
                item['status']=confirmed['status']; item['error']=confirmed.get('error'); item['missing_fields']=confirmed.get('missing_fields') or []
                if status['state']=='paused': raise ValueError('接收端已暫停（例如運算資源使用中）；影像已安全保存在 B，不會重送。請於 B 確認後按「繼續」。')
            item['total_ms']=round((time.perf_counter()-start)*1000)
            with LOCK:
                if STATE['mode']=='manual': STATE['phase']='paused'; break
        with LOCK:
            if all(i['status'] in SETTLED for i in queue) and STATE['phase']!='cancelled':
                waiting=sum(i['status']=='needs_data' for i in queue)
                STATE.update(phase='completed',message='批次傳送完成。'+(f'{waiting} 張待 B 補資料後分析。' if waiting else '')+'完整分析與報告請於 B 檢視。')
            elif STATE['phase']=='paused': STATE['message']='已暫停。繼續將核對 B 的狀態，不重送已完成項目。'
            elif STATE['phase']=='cancelled': STATE['message']='已取消未開始項目，已完成結果保留在 B。'
        if STATE['phase']=='paused': remote('/control',{'batch_id':batch,'action':'pause'})
    except Exception as exc:
        with LOCK: STATE.update(phase='paused',message=str(exc))
    finally:
        with LOCK: STATE['running']=False

def control(action,mode=None):
    with LOCK:
        if action=='clear':
            if STATE['running']: raise ValueError('當前圖片尚未結束。')
            if STATE['queue'] and STATE['phase'] not in {'completed','cancelled'}: raise ValueError('請先取消或完成批次，再清除清單。')
            STATE.update(queue=[],batch=None,phase='ready'); return {}
        batch=STATE['batch']
        if not batch: raise ValueError('尚無批次。')
        if action=='resume':
            if STATE['running']: raise ValueError('請等候目前圖片完成。')
            if STATE['phase']=='cancelled': raise ValueError('批次已取消。')
            STATE.update(running=True,phase='running',mode=mode or STATE['mode'])
            threading.Thread(target=worker,daemon=True).start(); return {}
        if action not in {'pause','cancel'}: raise ValueError('操作錯誤。')
        STATE['phase']='paused' if action=='pause' else 'cancelled'
    try: remote('/control',{'batch_id':batch,'action':action})
    except RemoteError as exc:
        if exc.code!=404: raise
    return {}

def serve(port=0,open_browser=True):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,code,value,content_type='application/json; charset=utf-8'):
            data=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
            self.send_response(code); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(data)
        def handle_request(self):
            try:
                base=f'127.0.0.1:{self.server.server_port}'
                if self.headers.get('Host')!=base: return self.reply(403,{'error':'本機存取限定。'})
                origin=self.headers.get('Origin')
                if origin and origin!='http://'+base: return self.reply(403,{'error':'來源不符。'})
                route=urlsplit(self.path)
                if self.command=='GET' and route.path in {'/','/sender.js'}:
                    name='index.html' if route.path=='/' else 'sender.js'
                    return self.reply(200,(Path(__file__).parent/name).read_bytes(),'text/html; charset=utf-8' if name.endswith('html') else 'text/javascript; charset=utf-8')
                if not secrets.compare_digest(self.headers.get('X-Local-Token',''),TOKEN): return self.reply(403,{'error':'請從工具開啟的頁面操作。'})
                if self.command=='GET':
                    query=parse_qs(route.query)
                    if route.path=='/api/status':
                        with LOCK: value={'phase':STATE['phase'],'message':STATE['message'],'running':STATE['running'],'paired':bool(STATE['bearer']),
                            'count':len(STATE['files']),'batch':STATE['batch'],'version':VERSION,'protocol':PROTOCOL,'plan_label':STATE['plan_label'],
                            'requirements':[{'field':r,'label':REQUIREMENT_LABELS[r]} for r in STATE['requirements']],
                            'queue':[{k:v for k,v in i.items() if k not in ('file','case')} for i in STATE['queue']]}
                        return self.reply(200,value)
                    if route.path=='/api/files':
                        page=max(0,int(query.get('page',['0'])[0]))
                        with LOCK: value=[{'id':i,'name':v['name'],'size':v['size'],'case_code':(v.get('case') or {}).get('case_code'),
                                           'missing':case_missing(v.get('case'))} for i,v in list(STATE['files'].items())[page*20:(page+1)*20]]
                        return self.reply(200,value)
                    if route.path=='/api/case':
                        with LOCK: record=STATE['files'][query['id'][0]]; value={'name':record['name'],'case':record.get('case'),'missing':case_missing(record.get('case'))}
                        return self.reply(200,value)
                    if route.path=='/api/image':
                        with LOCK: path=STATE['files'][query['id'][0]]['path']
                        data=path.read_bytes()
                        if len(data)>MAX_BYTES: raise ValueError('檔案過大。')
                        return self.reply(200,data,'image/png' if path.suffix.lower()=='.png' else 'image/jpeg')
                if self.command=='POST':
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=1024*1024: raise ValueError('要求過大。')
                    body=json.loads(self.rfile.read(size))
                    if route.path=='/api/pair': return self.reply(200,pair_receiver(body['pair'],body['fingerprint']))
                    if route.path=='/api/choose': return self.reply(200,choose(body.get('mode','folder')))
                    if route.path=='/api/case': return self.reply(200,set_case(body['id'],body['case']))
                    if route.path=='/api/copy-case': return self.reply(200,copy_case(body['source'],list(body['targets'])))
                    if route.path=='/api/start': queue_start(body['ids'],body['mode']); return self.reply(200,{'ok':True})
                    if route.path=='/api/control': return self.reply(200,control(body['action'],body.get('mode')))
                    if route.path=='/api/shutdown':
                        with LOCK:
                            if STATE['running']: raise ValueError('請先暫停並等候目前圖片結束。')
                        self.reply(200,{'ok':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
                self.reply(404,{'error':'找不到功能。'})
            except Exception as exc: self.reply(400,{'error':str(exc)})
        do_GET=handle_request
        do_POST=handle_request
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    if open_browser: webbrowser.open(f'http://127.0.0.1:{server.server_port}/#{TOKEN}')
    server.serve_forever()

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        import tkinter
        root=tkinter.Tk();root.withdraw();root.update();root.destroy()
        assert (Path(__file__).parent/'index.html').is_file()
        assert (Path(__file__).parent/'sender.js').is_file()
        assert ssl.OPENSSL_VERSION
        assert clean_case({'case_code':'SELF-TEST','age':'50','diabetes':'unknown'})=={'case_code':'SELF-TEST','age':50,'diabetes':'unknown','side':'unspecified'}
        Path(sys.argv[2]).write_text(json.dumps({'ok':True,'version':VERSION,'protocol':PROTOCOL,'case_schema':CASE_SCHEMA,'portable':bool(getattr(sys,'frozen',False)),'tls':ssl.OPENSSL_VERSION,'desktop_resolved':desktop().is_dir()}),encoding='utf-8')
    else: serve()
