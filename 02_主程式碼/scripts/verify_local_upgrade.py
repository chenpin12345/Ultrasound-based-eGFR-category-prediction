"""Isolated database upgrade and protected-numerics check; never migrate live DBs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys


def inventory(path):
    result={}
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence')"):
            columns=[row[1] for row in db.execute(f'PRAGMA table_info("{table}")')]
            rows=db.execute(f'SELECT * FROM "{table}"').fetchall()
            result[table]={'columns':columns,'rows':sorted(rows,key=repr)}
    return result


def assert_preserved(path,before):
    with sqlite3.connect(path) as db:
        for table,item in before.items():
            fields=','.join('"'+column+'"' for column in item['columns'])
            after=sorted(db.execute(f'SELECT {fields} FROM "{table}"').fetchall(),key=repr)
            assert item['rows']==after,f'Historical data changed: {table}'
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--code-backup',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    code=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(code))
    data=args.output/'research';clinical=args.output/'clinical'
    data.mkdir();clinical.mkdir()
    sources={'research':args.backup/'research/isu_ai.sqlite3','clinical':args.backup/'clinical/clinical.sqlite3'}
    targets={'research':data/'isu_ai.sqlite3','clinical':clinical/'clinical.sqlite3'}
    before={}
    source_hashes={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in sources.items()}
    for key,source in sources.items():
        shutil.copy2(source,targets[key]);before[key]=inventory(targets[key])
    os.environ.update(ISU_AI_DATA_DIR=str(data),ISU_AI_CLINICAL_DIR=str(clinical),ISU_AI_MODELS_DIR=str(args.output/'models'),
                      ISU_AI_REPORTS_DIR=str(args.output/'reports'),ISU_AI_RUNTIME_DIR=str(args.output/'runtime'),
                      ISU_AI_REFERENCE_FEATURES_DIR=str(args.output/'features'),ISU_AI_REQUIRE_EXISTING_DATABASES='false',
                      ISU_AI_DATABASE_URL='sqlite:///'+targets['research'].as_posix())
    from backend.app.db.session import init_db,reset_engine_cache
    from backend.app.clinical.store import migrate
    init_db();migrate();init_db();migrate()
    for key,target in targets.items():assert_preserved(target,before[key])
    reset_engine_cache()
    files=[]
    for folder in ('backend/app/ml','resnet','unet','photo_process'):
        files.extend(path.relative_to(args.code_backup) for path in (args.code_backup/folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc')
    files += [Path('backend/app/core/splitting.py'),Path('backend/app/services/training_service.py')]
    changed=[path.as_posix() for path in files if not (code/path).is_file() or hashlib.sha256((code/path).read_bytes()).digest()!=hashlib.sha256((args.code_backup/path).read_bytes()).digest()]
    assert not changed,changed
    for key,path in sources.items():assert hashlib.sha256(path.read_bytes()).hexdigest()==source_hashes[key]
    summary={'passed':True,'scope':'isolated database upgrade; not full artifact restore or hardware acceptance',
             'historical_tables_preserved':{key:len(value) for key,value in before.items()},
             'migration_repeatable':True,'integrity_and_foreign_keys':'ok','protected_numerical_files_identical':len(files),
             'backup_databases_unchanged':True}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':main()
