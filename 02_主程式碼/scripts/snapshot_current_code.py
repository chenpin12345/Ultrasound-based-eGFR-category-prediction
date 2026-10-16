"""Verified code/config snapshot, excluding installed dependencies and caches."""
import argparse
import os
from pathlib import Path
import shutil
import sys

CODE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CODE))
from scripts.workspace_backup import guard_operation,offline,no_links,sha,write_json
from backend.app.core.config import AppSettings


@guard_operation
def snapshot(settings,destination):
    offline(settings)
    destination=destination.resolve()
    permitted=(CODE.parent/'.maintenance/backups').resolve()
    if not destination.is_relative_to(permitted) or destination==permitted or destination.exists():
        raise ValueError('Use a new subdirectory under workspace .maintenance/backups')
    no_links(destination)
    ignored={'.venv','node_modules','__pycache__','.pytest_cache','.git','.ruff_cache'}
    paths=[]
    for parent,folders,files in os.walk(CODE):
        folders[:]=[name for name in folders if name not in ignored]
        for name in files:
            if not name.endswith(('.pyc','.pyo')):paths.append(Path(parent)/name)
    for name in ('workspace-layout.json','.env','.env.example','start.bat','stop.bat','setup.bat','README.md'):
        if (CODE.parent/name).is_file():paths.append(CODE.parent/name)
    destination.mkdir(parents=True,exist_ok=False)
    manifest={}
    for path in sorted(paths):
        no_links(path)
        relative=path.relative_to(CODE.parent)
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
        digest=sha(path);shutil.copy2(path,target)
        if sha(target)!=digest or sha(path)!=digest:raise RuntimeError('Source changed during code snapshot')
        manifest[relative.as_posix()]=digest
    write_json(destination/'source-manifest.json',manifest)
    return {'verified_code_config_files':len(manifest),'dependencies_excluded':True}


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    print(json.dumps(snapshot(AppSettings(),args.destination)))
