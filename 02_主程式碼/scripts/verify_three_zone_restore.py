"""Full isolated restore: all backup bytes, paired code/config and DB upgrade.

Never targets live roots. Refuses an existing output directory and does not
start an application or mutate the verified source backups.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

CODE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CODE))
from workspace_backup import restore,verify,sha,roots
from verify_local_upgrade import inventory,assert_preserved
from backend.app.core.config import AppSettings


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--code-backup',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New scratch directory for the isolated restore (outside live data and code)')
    parser.add_argument('--summary',type=Path,help='Where to keep summary.json (e.g. under 01_Codex/驗證報告)')
    parser.add_argument('--discard',action='store_true',help='Delete the restored scratch copy after a passing check')
    args=parser.parse_args()
    destination=args.output.resolve()
    live=[p.resolve() for p in roots(AppSettings()).values()]+[CODE.resolve()]
    # Full restored copies never live in the documentation folder or near live roots.
    evidence=(CODE.parent/'01_Codex').resolve()
    if destination.exists() or any(destination.is_relative_to(p) or p.is_relative_to(destination) for p in live+[evidence]):
        raise ValueError('Use a new scratch directory outside live data, code and 01_Codex')
    backup=args.backup.resolve();source_code=args.code_backup.resolve()
    manifest=verify(backup)
    if manifest['scope']!='full':raise ValueError('Full backup required')
    source_manifest=json.loads((source_code/'source-manifest.json').read_text(encoding='utf-8'))
    for relative,digest in source_manifest.items():
        path=(source_code/relative).resolve()
        if not path.is_relative_to(source_code) or sha(path)!=digest:raise ValueError('Code backup integrity mismatch')
    required=sum(item['size'] for item in manifest['files'].values())+sum((source_code/p).stat().st_size for p in source_manifest)
    if shutil.disk_usage(destination.parent).free<required+5*1024**3:raise RuntimeError('Insufficient safe free space for restore')
    destination.mkdir(parents=True,exist_ok=False)
    kwargs={name:destination/key for name,key in [('data_dir','research'),('models_dir','models'),('clinical_dir','clinical'),
        ('reports_dir','reports'),('reference_features_dir','reference_features'),('runtime_dir','runtime')]}
    if any(not p.resolve().is_relative_to(destination) for p in kwargs.values()):raise ValueError('Invalid isolated roots')
    settings=AppSettings(_env_file=None,**kwargs,database_url='sqlite:///'+(destination/'research/isu_ai.sqlite3').as_posix())
    print(json.dumps({'phase':'restoring','files':len(manifest['files']),'bytes':required}),flush=True)
    restored=restore(backup,settings)
    for relative,item in manifest['files'].items():
        if sha(destination/relative)!=item['sha256']:raise ValueError('Restored artifact mismatch: '+relative)
    paired=destination/'paired-code-config'
    for relative,digest in source_manifest.items():
        target=paired/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source_code/relative,target)
        if sha(target)!=digest:raise ValueError('Restored code/config mismatch')
    print(json.dumps({'phase':'all_bytes_verified','data_files':len(manifest['files']),'code_files':len(source_manifest)}),flush=True)
    # Upgrade only the restored copies, then prove historical rows and non-DB bytes survive.
    paths={'research':destination/'research/isu_ai.sqlite3','clinical':destination/'clinical/clinical.sqlite3'}
    before={key:inventory(path) for key,path in paths.items()}
    for field,path in kwargs.items():os.environ['ISU_AI_'+field.upper()]=str(path)
    os.environ['ISU_AI_DATABASE_URL']=settings.database_url
    os.environ['ISU_AI_REQUIRE_EXISTING_DATABASES']='true'
    from backend.app.core.config import get_settings
    from backend.app.db.session import init_db,reset_engine_cache
    from backend.app.clinical import store
    get_settings.cache_clear();reset_engine_cache()
    init_db();store.migrate();init_db();store.migrate()
    for key,path in paths.items():assert_preserved(path,before[key])
    with store.read_transaction() as db:clinical_revision=db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
    reset_engine_cache()
    non_db=0
    for relative,item in manifest['files'].items():
        if relative in {'research/isu_ai.sqlite3','clinical/clinical.sqlite3'}:continue
        if sha(destination/relative)!=item['sha256']:raise ValueError('Upgrade changed an artifact: '+relative)
        non_db+=1
    verify(backup)
    summary={'passed':True,'scope':'full isolated file/DB restore and repeatable upgrade; not live deployment or hardware validation',
        **restored,'data_files_byte_identical_before_upgrade':len(manifest['files']),
        'paired_code_config_files_identical':len(source_manifest),'non_database_artifacts_unchanged_after_upgrade':non_db,
        'historical_tables_preserved':{key:len(value) for key,value in before.items()},
        'source_backup_reverified':True,'clinical_revision':clinical_revision,
        'new_post_upgrade_pdf_tombstones_and_analysis_runs':'separate regression tests required'}
    (destination/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.summary:
        args.summary.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(destination/'summary.json',args.summary)
    if args.discard:
        from workspace_backup import no_links,io_path
        no_links(destination);shutil.rmtree(io_path(destination))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
