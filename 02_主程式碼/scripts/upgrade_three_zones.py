"""Offline, backup-verified, fail-closed upgrade of the two database chains.

No service is stopped by this tool. Failure retains the journal and prevents
startup; recovery is a matched backup restore, never a destructive downgrade.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

CODE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CODE))
from scripts.workspace_backup import guard_operation,offline,verify,roots,entries,sha,write_json
from scripts.verify_local_upgrade import inventory,assert_preserved


def verify_live_backup(settings,source):
    manifest=verify(source)
    if manifest['scope']!='full':raise ValueError('A verified full backup is required')
    mapping=roots(settings)
    databases={'research':'isu_ai.sqlite3','clinical':'clinical.sqlite3'}
    actual={}
    for key,folder in mapping.items():
        if not folder.exists():continue  # Empty optional roots are omitted by backup as well.
        for path in entries(folder):
            relative=path.relative_to(folder).as_posix()
            if key in databases and relative in {databases[key]+'-wal',databases[key]+'-shm'}:continue
            actual[key+'/'+relative]=path
    if set(actual)!=set(manifest['files']):raise ValueError('Live file inventory differs from backup; create a fresh backup')
    for relative,path in actual.items():
        key,name=relative.split('/',1)
        if databases.get(key)==name:
            if inventory(path)!=inventory(source/relative):raise ValueError('Live database differs from backup; create a fresh backup')
        elif sha(path)!=manifest['files'][relative]['sha256']:
            raise ValueError('Live artifact differs from backup; create a fresh backup')
    return manifest


def migrate_databases():
    from backend.app.db.session import init_db,reset_engine_cache
    from backend.app.clinical.store import migrate
    try:init_db();migrate()
    finally:reset_engine_cache()


@guard_operation
def upgrade(settings,backup,code_backup,evidence):
    offline(settings)
    journal=settings.runtime_dir/'schema-upgrade-journal.json'
    if journal.exists():raise RuntimeError('An upgrade journal already exists; do not overwrite it')
    if evidence.exists():raise ValueError('Use a new evidence directory')
    manifest=verify_live_backup(settings,backup)
    code_manifest=json.loads((code_backup/'source-manifest.json').read_text(encoding='utf-8'))
    for relative,digest in code_manifest.items():
        path=(code_backup/relative).resolve()
        if not path.is_relative_to(code_backup.resolve()) or sha(path)!=digest:
            raise ValueError('Code/config backup integrity mismatch')
    before={'research':inventory(settings.sqlite_path),'clinical':inventory(settings.clinical_dir/'clinical.sqlite3')}
    evidence.mkdir(parents=True,exist_ok=False)
    state={'version':1,'started':time.time(),'phase':'upgrading','backup':str(backup.resolve()),
           'code_backup':str(code_backup.resolve()),'evidence':str(evidence.resolve())}
    # Exclusive publication avoids replacing another upgrade's recovery marker.
    with journal.open('x',encoding='utf-8') as stream:
        json.dump(state,stream,ensure_ascii=False,indent=2)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    try:
        migrate_databases()
        assert_preserved(settings.sqlite_path,before['research'])
        assert_preserved(settings.clinical_dir/'clinical.sqlite3',before['clinical'])
        for relative,item in manifest['files'].items():
            if relative in {'research/isu_ai.sqlite3','clinical/clinical.sqlite3'}:continue
            key,name=relative.split('/',1)
            if sha(roots(settings)[key]/name)!=item['sha256']:raise ValueError('Artifact changed during upgrade')
        import sqlite3
        from contextlib import closing
        revisions={}
        for key,path in {'research':settings.sqlite_path,'clinical':settings.clinical_dir/'clinical.sqlite3'}.items():
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                revisions[key]=db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        result={'passed':True,'scope':'offline database upgrade only; startup/browser/restart acceptance is separate',
                'backup_files_verified':len(manifest['files']),'code_config_backup_files_verified':len(code_manifest),
                'historical_tables_preserved':{key:len(value) for key,value in before.items()},'revisions':revisions}
        write_json(evidence/'summary.json',result)
        state.update(phase='completed',completed=time.time(),revisions=revisions)
        write_json(journal,state)
        journal.rename(evidence/'completed-journal.json')
        return result
    except BaseException as exc:
        state.update(phase='failed',error_type=type(exc).__name__,failed=time.time())
        write_json(journal,state)
        raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--code-backup',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--apply',action='store_true',required=True)
    args=parser.parse_args()
    from backend.app.core.config import get_settings
    # Populate the process-local configuration before acquiring the startup
    # interlock. Other processes still reject maintenance/journal markers.
    settings=get_settings()
    print(json.dumps(upgrade(settings,args.backup.resolve(),args.code_backup.resolve(),args.evidence.resolve())))


if __name__=='__main__':main()
