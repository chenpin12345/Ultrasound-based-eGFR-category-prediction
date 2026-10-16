"""Only unsaved, unreferenced receiver frames; journal precedes filesystem work.

The SQLite write transaction serializes saving/analysis against cleanup. A failed
attempt keeps the frame and a blocking journal. No error is treated as success,
and retry cannot expand the originally recorded target.
"""
from __future__ import annotations

import re
import shutil
import stat
import threading
import time

from ..core.errors import AppError
from . import store

_lock=threading.Lock()


def eligible(db,frame_id,session_id):
    row=db.execute('''SELECT f.* FROM frames f JOIN exams e ON e.id=f.exam_id
        JOIN demo_sessions s ON s.id=e.demo_session_id
        WHERE f.id=? AND e.demo_session_id=? AND e.kind='demo'
        AND s.state!='active' AND f.saved=0 AND f.source='network_demo'
        AND f.status!='analyzing'
        AND NOT EXISTS(SELECT 1 FROM clinical_operations o WHERE o.frame_id=f.id)
        AND NOT EXISTS(SELECT 1 FROM analysis_runs a WHERE a.frame_id=f.id)
        AND NOT EXISTS(SELECT 1 FROM analysis_publications a WHERE a.frame_id=f.id)
        AND NOT EXISTS(SELECT 1 FROM reports r WHERE r.exam_id=e.id)
        AND NOT EXISTS(SELECT 1 FROM clinical_lifecycle l
            WHERE l.entity='exams' AND l.id=e.id AND l.state!='normal')''',(frame_id,session_id)).fetchone()
    return row


def folder_for(record):
    identifier=record['frame_id']
    if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Invalid frame directory identity')
    root=store.root().resolve()
    expected=root/'frames'/identifier
    folder=store.managed(record['path']).parent
    # Check resolved paths AND reparse points; never follow a junction during deletion.
    if folder!=expected or expected.resolve()!=expected:raise ValueError('Cleanup target escaped its frame directory')
    for parent in (root/'frames',expected):
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(),'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('Cleanup target is a link')
    if expected.exists():
        for child in expected.rglob('*'):
            if child.is_symlink() or getattr(child.lstat(),'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('Linked cleanup content is not permitted')
    return expected


def run(identifier,*,actor=None,reason='接收結束後清理未保存暫存影像'):
    with _lock:
        with store.transaction() as db:
            row=db.execute('SELECT * FROM temporary_cleanup WHERE id=?',(identifier,)).fetchone()
            if not row:raise AppError(404,'NOT_FOUND','找不到暫存清理作業。')
            if row['status']=='completed':return {'id':identifier,'status':'completed'}
            frame=eligible(db,row['frame_id'],row['session_id'])
            if not frame or frame['path']!=row['path']:
                raise AppError(409,'CLEANUP_REFERENCED','暫存影像已不符合清理條件；未刪除任何檔案。')
            attempt=store.uid()
            db.execute('INSERT INTO cleanup_attempts VALUES(?,?,?,?,?,?,NULL,NULL)',(attempt,identifier,actor,reason,'pending',time.time()))
            db.execute("UPDATE temporary_cleanup SET status='pending',attempts=attempts+1,error=NULL WHERE id=?",(identifier,))
        try:
            with store.transaction() as db:
                row=db.execute('SELECT * FROM temporary_cleanup WHERE id=?',(identifier,)).fetchone()
                frame=eligible(db,row['frame_id'],row['session_id'])
                if not frame or frame['path']!=row['path']:raise ValueError('Cleanup eligibility changed')
                folder=folder_for(row)
                if folder.exists():shutil.rmtree(folder)  # exact validated, exclusively temporary frame directory
                db.execute('UPDATE items SET frame_id=NULL WHERE frame_id=?',(row['frame_id'],))
                db.execute('DELETE FROM frames WHERE id=?',(row['frame_id'],))
                # Keep the exam/session history; temporary cleanup is not lifecycle deletion.
                db.execute("UPDATE temporary_cleanup SET status='completed',completed=?,error=NULL WHERE id=?",(time.time(),identifier))
                db.execute("UPDATE cleanup_attempts SET status='completed',completed=? WHERE id=?",(time.time(),attempt))
                local=db.execute("SELECT id FROM users WHERE actor_kind='local_system'").fetchone()
                store.audit(db,actor or (local['id'] if local else 'system:temporary_cleanup'),'temporary_cleanup_completed',identifier)
        except Exception as exc:
            # Persist a bounded non-path diagnostic. A partial filesystem operation
            # remains explicitly blocked until an authorized retry completes it.
            error=f'{type(exc).__name__}: 暫存清理未完成；原作業與影像識別仍保留，請檢查檔案占用及路徑。'
            with store.transaction() as db:
                db.execute("UPDATE temporary_cleanup SET status='failed',error=? WHERE id=?",(error,identifier))
                db.execute("UPDATE cleanup_attempts SET status='failed',completed=?,error=? WHERE id=?",(time.time(),error,attempt))
            return {'id':identifier,'status':'failed','error':error}
        return {'id':identifier,'status':'completed'}


def cleanup_session(session_id):
    with store.transaction() as db:
        rows=db.execute('''SELECT f.id FROM frames f JOIN exams e ON e.id=f.exam_id
            WHERE e.demo_session_id=? AND NOT EXISTS(SELECT 1 FROM temporary_cleanup c WHERE c.frame_id=f.id)''',(session_id,)).fetchall()
        jobs=[]
        for candidate in rows:
            row=eligible(db,candidate['id'],session_id)
            if row is None:continue
            identifier=store.uid()
            db.execute('INSERT INTO temporary_cleanup VALUES(?,?,?,?,?,?,0,?,NULL,NULL)',
                       (identifier,session_id,row['id'],row['exam_id'],row['path'],'pending',time.time()))
            jobs.append(identifier)
    for identifier in jobs:run(identifier)


def recover():
    with store.transaction() as db:
        db.execute("UPDATE temporary_cleanup SET status='interrupted',error='主程式中斷；請由作業監控明確重試。' WHERE status='pending'")
        db.execute("UPDATE cleanup_attempts SET status='interrupted',completed=?,error='主程式中斷；未自動重試。' WHERE status='pending'",(time.time(),))
