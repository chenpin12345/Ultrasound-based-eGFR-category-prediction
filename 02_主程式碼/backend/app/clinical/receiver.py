"""Network process: fixed image protocol only, no clinical database or main-app proxy."""
from __future__ import annotations

import errno
import json
import socket
import ssl
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

MAX_BYTES=32*1024*1024


def bind_error(exc):
    """Map a bind failure to a stable code without leaking OS paths."""
    number=getattr(exc,'winerror',None) or exc.errno
    if number in (errno.EADDRINUSE,10048): return 'PORT_IN_USE'
    if number in (errno.EADDRNOTAVAIL,10049): return 'ADDRESS_NOT_AVAILABLE'
    if number in (errno.EACCES,10013): return 'BIND_DENIED'
    return 'RECEIVER_START_FAILED'


def run(pipe, host, cert, key, port=0):
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert,key)
    class Server(HTTPServer):
        keep_running=True
        # SO_REUSEADDR on Windows would let two programs share a port; require
        # exclusive use so an occupied port is reported instead of hijacked.
        allow_reuse_address=False
        def server_bind(self):
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
        def get_request(self):
            connection,address=self.socket.accept()
            connection.settimeout(5)
            try: return context.wrap_socket(connection,server_side=True),address
            except BaseException:
                connection.close(); raise
    class Handler(BaseHTTPRequestHandler):
        server_version='ImageReceiver/1'
        def log_message(self,*args): pass
        def setup(self):
            super().setup(); self.connection.settimeout(15)
        def reply(self,code,value):
            body=json.dumps(value,ensure_ascii=False).encode()
            self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def handle_request(self):
            route=urlsplit(self.path)
            allowed={'POST':{'/pair','/batches','/items','/control'},'GET':{'/batches'}}
            if route.path not in allowed.get(self.command,set()): return self.reply(404,{'error':'NOT_FOUND'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if self.headers.get('Transfer-Encoding') or not 0<=length<=MAX_BYTES:
                    return self.reply(413,{'error':'BODY_LIMIT'})
                if route.path!='/items' and length>1024*1024: return self.reply(413,{'error':'BODY_LIMIT'})
                body=self.rfile.read(length)
                if len(body)!=length: return self.reply(400,{'error':'INCOMPLETE_BODY'})
                value=body if route.path=='/items' else json.loads(body or b'{}')
                if not isinstance(value,(dict,bytes)): return self.reply(400,{'error':'INVALID_BODY'})
                packet={'op':route.path,'method':self.command,'body':value,'query':parse_qs(route.query),
                        'bearer':self.headers.get('Authorization',''),
                        'batch':self.headers.get('X-Batch-ID',''),'item':self.headers.get('X-Item-ID',''),
                        'sha256':self.headers.get('X-Content-SHA256','')}
                pipe.send(packet)
                if not pipe.poll(30):
                    self.server.keep_running=False
                    return self.reply(503,{'error':'APPLICATION_UNAVAILABLE'})
                code,result=pipe.recv(); self.reply(code,result)
            except (ValueError,TypeError,KeyError): self.reply(400,{'error':'INVALID_REQUEST'})
            except (OSError,EOFError,TimeoutError): self.close_connection=True
        do_POST=handle_request
        do_GET=handle_request
    try:
        try: server=Server((host,port),Handler)
        except OSError as exc:
            pipe.send({'error':bind_error(exc)}); return
        server.timeout=.5
        pipe.send({'port':server.server_port})
        while server.keep_running: server.handle_request()
        server.server_close()
    except Exception:
        try: pipe.send({'error':'RECEIVER_START_FAILED'})
        except OSError: pass
    finally: pipe.close()
