"""Explicit PDF generation, immutable identity, tombstones and read leases."""
from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager

from fastapi.responses import FileResponse
from ..core.config import get_settings
from ..core.errors import AppError
from . import store,reports
from .service import required
from .lifecycle import guard

_active=set()


def begin(report_id):
    # Registration and lifecycle checks share the same short gate. Never hold
    # the gate while streaming, acquiring a DB transaction or rendering.
    with reports._render_lock:
        if report_id in _active:raise AppError(409,'REPORT_BUSY','此報告正在生成、傳送或刪除 PDF，請稍後重試。')
        _active.add(report_id)


def end(report_id):
    with reports._render_lock:_active.discard(report_id)


@contextmanager
def lease(report_id):
    begin(report_id)
    try:yield
    finally:end(report_id)


def busy(db,entity,identifier):
    # Called while lifecycle holds the registration gate.
    if entity=='reports':return identifier in _active
    if entity=='exams':ids=db.execute('SELECT id FROM reports WHERE exam_id=?',(identifier,))
    else:ids=db.execute('SELECT r.id FROM reports r JOIN exams e ON e.id=r.exam_id WHERE e.patient_id=?',(identifier,))
    return any(row[0] in _active for row in ids)


def managed(relative):
    base=get_settings().reports_dir.resolve()
    path=(base/relative).resolve()
    if not path.is_relative_to(base) or path==base or path.suffix!='.pdf':raise AppError(422,'REPORT_PATH_INVALID','PDF 路徑不在受管理範圍。')
    return path


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source(db,report_id,number,write=False):
    report=required(db,'reports',report_id)
    guard(db,'reports',report_id,write=write)
    row=db.execute('SELECT * FROM report_versions WHERE report_id=? AND version=?',(report_id,number)).fetchone()
    if not row:raise AppError(404,'VERSION_NOT_FOUND','找不到報告版本。')
    record=store.rowdict(row)
    variant='void' if report['state']=='void' else 'original'
    return record,variant


def public(row):
    value=dict(row);value.pop('path',None)
    value['url']=f'/api/clinical/pdf-artifacts/{value["id"]}' if value['status']=='ready' else None
    return value


def list_records(db,report_id,number):
    _,variant=source(db,report_id,number)
    return {'variant':variant,'items':[public(row) for row in db.execute('SELECT * FROM pdf_artifacts WHERE report_id=? AND version=? ORDER BY created DESC,id DESC',(report_id,number))]}


def generate(report_id,number,actor):
    with lease(report_id):
        with store.transaction() as db:
            record,variant=source(db,report_id,number,write=True)
            template=record['payload'].get('template_version',1)
            if template not in (1,2):raise AppError(422,'TEMPLATE_UNSUPPORTED','找不到此版本報告的模板，不使用最新版替代。')
            existing=db.execute("SELECT * FROM pdf_artifacts WHERE report_id=? AND version=? AND variant=? AND status='ready' ORDER BY created DESC,id DESC LIMIT 1",(report_id,number,variant)).fetchone()
            if existing:
                checked_path(existing)
                return public(existing)
            # Verify exact frozen originals before starting a new build.
            for item in record['payload'].get('images',[]):
                original=store.managed(item['path'])
                if not original.is_file() or digest(original)!=item['sha256']:
                    raise AppError(409,'REPORT_SOURCE_MISSING','報告引用的原圖遺失或內容不符，無法重建；不會使用其他影像替代。')
            identifier=store.uid();relative=f'generated/{identifier}.pdf';operation=store.uid();now=time.time()
            db.execute('INSERT INTO pdf_artifacts VALUES(?,?,?,?,?,?,NULL,?,\'generating\',?,?,NULL,NULL)',
                (identifier,report_id,number,template,variant,relative,hashlib.sha256(store.dumps(record['payload']).encode()).hexdigest(),actor,now))
            db.execute('INSERT INTO pdf_operations VALUES(?,?,\'generate\',\'pending\',?,?,?,NULL,NULL)',(operation,identifier,actor,'使用者明確生成／重建',now))
        try:
            path=managed(relative)
            with reports._render_lock:
                if template==1:reports._render_pdf(report_id,number,destination=path,void_override=variant=='void')
                else:
                    from .report_v2 import render
                    render(record,path,report_id,number,variant=='void')
            sha=digest(path)
            with store.transaction() as db:
                source(db,report_id,number,write=True)
                db.execute("UPDATE pdf_artifacts SET status='ready',sha256=?,completed=? WHERE id=? AND status='generating'",(sha,time.time(),identifier))
                db.execute("UPDATE pdf_operations SET status='completed',completed=? WHERE id=?",(time.time(),operation))
                store.audit(db,actor,'pdf_generate',identifier)
                return public(db.execute('SELECT * FROM pdf_artifacts WHERE id=?',(identifier,)).fetchone())
        except BaseException as exc:
            with store.transaction() as db:
                db.execute("UPDATE pdf_artifacts SET status='failed',completed=?,error=? WHERE id=? AND status='generating'",(time.time(),getattr(exc,'code','PDF_GENERATION_FAILED'),identifier))
                db.execute("UPDATE pdf_operations SET status='failed',completed=?,error=? WHERE id=? AND status='pending'",(time.time(),getattr(exc,'code','PDF_GENERATION_FAILED'),operation))
            raise


def checked_path(row):
    if row['status']!='ready':raise AppError(410 if row['status']=='deleted' else 409,'PDF_NOT_READY','PDF 已刪除或尚未完成；預覽與下載不會重新產生檔案。')
    path=managed(row['path'])
    if not path.is_file() or digest(path)!=row['sha256']:raise AppError(409,'PDF_CHANGED','PDF 遺失或雜湊不符，停止傳送。')
    return path


class LeasedPdfResponse(FileResponse):
    def __init__(self,path,report_id,**kwargs):
        super().__init__(path,**kwargs);self.report_id=report_id
    async def __call__(self,scope,receive,send):
        # Do not delegate to an untracked path-send extension: retain the lease
        # until the final body send (or disconnect) has actually finished.
        scope={**scope,'extensions':{key:value for key,value in scope.get('extensions',{}).items() if key!='http.response.pathsend'}}
        try:await super().__call__(scope,receive,send)
        finally:end(self.report_id)


def read(identifier,download=False):
    with store.read_transaction() as db:
        row=db.execute('SELECT * FROM pdf_artifacts WHERE id=?',(identifier,)).fetchone()
        if not row:raise AppError(404,'PDF_NOT_FOUND','找不到 PDF 產物。')
        report_id=row['report_id']
    begin(report_id)
    try:
        with store.read_transaction() as db:
            row=db.execute('SELECT * FROM pdf_artifacts WHERE id=?',(identifier,)).fetchone()
            _,variant=source(db,report_id,row['version'])
            if row['variant']!=variant:raise AppError(409,'PDF_VARIANT_STALE','此 PDF 未反映報告作廢狀態，請明確生成作廢版本。')
            path=checked_path(row)
        return LeasedPdfResponse(path,report_id,media_type='application/pdf',filename=f'report-{report_id}-v{row["version"]}.pdf' if download else None,headers={'Cache-Control':'no-store'})
    except BaseException:end(report_id);raise


def read_version(report_id,number,download=False):
    with store.read_transaction() as db:
        _,variant=source(db,report_id,number)
        row=db.execute('SELECT * FROM pdf_artifacts WHERE report_id=? AND version=? AND variant=? ORDER BY created DESC,id DESC LIMIT 1',(report_id,number,variant)).fetchone()
        if not row:raise AppError(404,'PDF_NOT_GENERATED','尚未產生此版本 PDF，請按產生 PDF。')
    return read(row['id'],download)


def delete(identifier,expected_sha,reason,actor):
    with store.read_transaction() as db:
        row=db.execute('SELECT * FROM pdf_artifacts WHERE id=?',(identifier,)).fetchone()
        if not row:raise AppError(404,'PDF_NOT_FOUND','找不到 PDF 產物。')
        report_id=row['report_id']
    with lease(report_id):
        with store.transaction() as db:
            row=db.execute('SELECT * FROM pdf_artifacts WHERE id=?',(identifier,)).fetchone()
            source(db,report_id,row['version'],write=True)
            if row['sha256']!=expected_sha:raise AppError(409,'REVISION_CONFLICT','PDF 雜湊與確認對象不同。')
            if row['status'] not in {'ready','deletion_failed'}:raise AppError(409,'PDF_NOT_DELETABLE','目前狀態不可刪除 PDF。')
            path=managed(row['path'])
            if path.is_file() and digest(path)!=expected_sha:raise AppError(409,'PDF_CHANGED','PDF 內容與紀錄不符，不刪除未知內容。')
            sidecar=path.with_suffix('.sha256')
            if sidecar.is_file() and sidecar.read_text(encoding='ascii').strip()!=expected_sha:
                raise AppError(409,'PDF_CHANGED','PDF 雜湊檔與確認對象不符，未刪除檔案。')
            operation=store.uid()
            db.execute("UPDATE pdf_artifacts SET status='deleting',error=NULL WHERE id=?",(identifier,))
            db.execute('INSERT INTO pdf_operations VALUES(?,?,\'delete\',\'pending\',?,?,?,NULL,NULL)',(operation,identifier,actor,reason,time.time()))
        try:
            path.unlink(missing_ok=True)
            path.with_suffix('.sha256').unlink(missing_ok=True)
            with store.transaction() as db:
                db.execute("UPDATE pdf_artifacts SET status='deleted',completed=? WHERE id=?",(time.time(),identifier))
                db.execute("UPDATE pdf_operations SET status='completed',completed=? WHERE id=?",(time.time(),operation))
                store.audit(db,actor,'pdf_delete',identifier)
            return {'id':identifier,'status':'deleted','recoverable':'explicit_rebuild','report_deleted':False}
        except OSError as exc:
            with store.transaction() as db:
                db.execute("UPDATE pdf_artifacts SET status='deletion_failed',error=? WHERE id=?",(type(exc).__name__,identifier))
                db.execute("UPDATE pdf_operations SET status='failed',completed=?,error=? WHERE id=?",(time.time(),type(exc).__name__,operation))
            raise AppError(409,'PDF_DELETE_FAILED','檔案刪除未完成，已保留作業紀錄；請確認檔案未被其他程式使用後重試。') from exc


def recover_and_import():
    """Startup-only registration; never render, overwrite or revive a tombstone."""
    with store.transaction() as db:
        db.execute("UPDATE pdf_artifacts SET status='interrupted',error='PROCESS_RESTARTED' WHERE status='generating'")
        db.execute("UPDATE pdf_artifacts SET status='deletion_failed',error='PROCESS_RESTARTED' WHERE status='deleting'")
        db.execute("UPDATE pdf_operations SET status='interrupted',completed=?,error='PROCESS_RESTARTED' WHERE status='pending'",(time.time(),))
        rows=db.execute('SELECT * FROM report_versions').fetchall()
        for raw in rows:
            record=store.rowdict(raw);exam=record['payload']['exam']
            for void in (False,True):
                path=reports.artifact_path(exam['kind'],exam['id'],record['report_id'],record['version'],void)
                relative=path.relative_to(get_settings().reports_dir.resolve()).as_posix()
                if not path.is_file() or db.execute('SELECT 1 FROM pdf_artifacts WHERE path=?',(relative,)).fetchone():continue
                sha=digest(path);sidecar=path.with_suffix('.sha256')
                if sidecar.is_file() and sidecar.read_text(encoding='ascii').strip()!=sha:
                    raise AppError(409,'LEGACY_PDF_CHANGED','既有 PDF 與雜湊檔不符，停止登錄，請檢查備份。')
                identifier=store.uid();now=time.time()
                db.execute('INSERT INTO pdf_artifacts VALUES(?,?,?,?,?,?,?, ?,\'ready\',NULL,?,?,NULL)',(identifier,record['report_id'],record['version'],record['payload'].get('template_version',1),'void' if void else 'original',relative,sha,hashlib.sha256(store.dumps(record['payload']).encode()).hexdigest(),now,now))
                db.execute('INSERT INTO pdf_operations VALUES(?,?,\'import\',\'completed\',NULL,?,?,?,NULL)',(store.uid(),identifier,'既有 PDF 原樣登錄，未重新渲染',now,now))
