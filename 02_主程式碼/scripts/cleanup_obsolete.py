"""One-time removal of obsolete backups, restore copies and superseded evidence (2026-10-13).

Only the exact paths listed in TARGETS (relative to the workspace root) are touched.
Live data roots, code dependencies and anything not listed are never deleted; unknown
siblings are reported and skipped. Links/junctions are removed as links, never followed.

  python scripts/cleanup_obsolete.py plan  <receipt.json>            # dry run: sizes, evidence, preconditions
  python scripts/cleanup_obsolete.py apply <receipt.json> [--final]  # delete; --final also removes the
                                                                     # temporary rollback pair kept during this change
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path

CODE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CODE))
from workspace_paths import WORKSPACE_ROOT  # noqa: E402

EVIDENCE='01_Codex/驗證報告/20261008-three-zones/'
B='.maintenance/backups/'
# (action, relative path, purpose, why it is safe to remove)
TARGETS=[
    ('delete',B+'20261007-original','10/07 目錄重構前完整快照（資料、模型、程式）','重構已驗收；唯一程式依賴 verify_model_integrity／verify_workspace_data 已改寫或退役'),
    ('delete',B+'20261008-three-zones-data','未完成的 10/08 資料備份','文件明定不得用於還原'),
    ('delete',B+'20261008-three-zones-data-v2','10/08 已驗證完整資料備份','已被後續備份取代；使用者已另存 10/11 版本'),
    ('delete',B+'20261008-three-zones-code','10/08 程式快照','僅供已退役的交付收據腳本計算差異'),
    ('delete',B+'20261010-three-zones-current-data','10/10 升級前資料備份','升級已完成並驗收；已被後續備份取代'),
    ('delete',B+'20261010-three-zones-current-code','10/10 程式快照','已被後續快照取代'),
    ('delete',B+'20261011-three-zones-current-code','10/11 程式快照','無任何引用'),
    ('delete',B+'formal-browser-1011b-clinical-before-restart','10/11 重啟前醫師資料單區備份','已被後續備份取代'),
    ('delete',B+'formal-browser-1011l-clinical-before-restart','10/11 最終重啟前醫師資料單區備份','重啟驗收已完成'),
    ('delete',B+'ui-full','失敗的 UI 測試備份','文件明定不得用於還原'),
    ('delete',B+'ui-full-verified','合成 UI 測試備份','唯一依賴 verify_restored_clinical.py（使用已停用登入）已退役'),
    ('final',B+'formal-browser-1011h-full-before-restart','10/11 最後已驗證完整資料備份（本次改版期間的本機回退點）','使用者已自行另存此版本；本次改版驗收通過後才刪除'),
    ('final',B+'formal-browser-1011h-code','配對 10/11 程式快照（本次改版期間的本機回退點）','同上'),
    ('final','.maintenance/pre-0011-clinical','0011 遷移前醫師資料範圍短期備份','遷移與冷啟動驗收通過後刪除'),
    ('delete','.maintenance/archives/20261007-original-install','10/07 前整套舊安裝（含 .venv、資料、模型、前端）','已遷移並驗收；資料與模型由現行 03 區保存；回退流程已退役'),
    ('delete','.maintenance/archives/historical-workspace','舊測試資料夾與 09 月整合備份','無程式引用；歷史整合紀錄不作為現行依據'),
    ('delete','.maintenance/migrations/20261007','10/07 遷移計畫與日誌','遷移已完成（validated-and-cut-over）；workspace_migrate.py 已退役'),
    *[('delete','.maintenance/'+name,'pytest 暫存資料夾','測試暫存，無引用') for name in ('b0','n0','n1','n3','n5','n6','n7','n8','n9','tests','test-evaluation-stop-1010q','test-final-backend-1010q','test-final-backend-1011a','test-long-path-1011a')],
    ('delete','.maintenance/portable-relocated','傳送工具搬移測試副本','與 delivery 同雜湊的舊版，已重新封裝'),
    ('delete','.maintenance/portable-selftest.json','舊版傳送工具自我測試結果','已被新封裝的自我測試取代'),
    ('delete','.maintenance/prediction-before','10/07 數值比較暫存','已由 prediction-after-1009 證據與 scripts/fixtures 基準取代'),
    ('delete','.maintenance/prediction-after','10/07 數值比較暫存','同上'),
    ('delete','.maintenance/prediction-after-verified','10/07 數值比較暫存','同上'),
    ('delete','.maintenance/real-transfer-d060d3b5','舊端到端腳本殘留暫存','腳本已改用系統暫存並自動清理'),
    ('delete','.maintenance/u1','10/07 隔離 UI 測試伺服器資料','一次性測試'),
    ('delete','.maintenance/u2','10/07 隔離還原目標','唯一依賴 verify_restored_clinical.py 已退役'),
    ('delete','.maintenance/tools','10/07 一次性工具舊副本','原工具已退役'),
    ('delete','.pnpm-store','舊前端套件快取（未使用）','frontend 使用 AppData 的 pnpm store；與舊安裝 hardlink'),
    ('delete','ISU_AI_KUA-main (3)','舊捷徑相容入口（4 個轉址 bat）','無捷徑或程式引用；使用根目錄 start.bat'),
    *[('delete',EVIDENCE+name,'完整還原副本／失敗或被取代的驗收批次','結果已記錄於 STATUS 與交付收據；不保留整套資料副本') for name in (
        'full-restore-1010','evaluation-ui-1011a','evaluation-ui-1011b','evaluation-ui-1011c','real-evaluation-1010m','real-evaluation-1010n','real-evaluation-1010o',
        'browser-1009a','browser-1009b','browser-1009c','browser-1009d','browser-1009e','browser-1009f','browser-1009g','browser-1009h','browser-1009k','browser-1009l','browser-1010','browser-1010b','browser-1010g',
        'formal-browser-1011a','formal-browser-1011b','formal-browser-1011h','formal-browser-1011j','formal-browser-1011k','formal-start-1011a','formal-upgrade-1010l',
        'isolated-upgrade-1009','isolated-upgrade-1009f','isolated-upgrade-1009j','isolated-upgrade-1010','isolated-upgrade-1010d','isolated-upgrade-1010f',
        'pdf-v2-1009','pdf-v2-1009b','prediction-before-1009','full-975-before-1009','full-restore-1010b','full-restore-1010l')],
    # Keep only the top-level summaries hashed by delivery-1011; drop the bulky copies under them.
    *[('prune',EVIDENCE+name,'交付收據引用的驗收證據','保留頂層摘要檔；移除其下的完整資料／影像副本') for name in (
        'full-restore-1011j','full-975-after-1010','evaluation-ui-1011g','real-evaluation-1010p','isolated-upgrade-1011i','prediction-after-1009','browser-1010h','pdf-v2-1009c','formal-browser-1011l')],
    *[('delete',EVIDENCE+name,'歷史測試 XML／延續筆記／一次性檢查腳本','被最終 1011a／1011f 結果取代，或綁定已刪除目錄') for name in (
        'baseline-backend.xml','baseline-frontend.json','catalog-backend.xml','continuation-1010-backend.xml','continuation-1010-frontend.xml','continuation-1010c-backend.xml',
        'continuation-1010c-frontend.xml','continuation-1010d-backend.xml','continuation-1010e-backend.xml','continuation-1010f-frontend.xml','continuation-1010g-backend.xml',
        'continuation-1010g-frontend.xml','continuation-1010j-backend.xml','continuation-1010k-backend.xml','continuation-1010l-frontend.xml','continuation-1010q-backend.xml',
        'continuation-1011d-frontend.xml','continuation-1011e-frontend.xml','continuation-backend.xml','continuation-e-backend.xml','continuation-f-backend.xml',
        'continuation-f-frontend.xml','continuation-i-backend.xml','continuation-j-backend.xml','continuation-l-frontend.xml','CONTINUATION_20261009_F.md','CONTINUATION_20261010.md',
        'evaluation-stop-1010q.xml','local-backend.xml','long-path-1011a.xml','receiver-race-1010h.xml','schema-upgrade-1010k.xml',
        'build_delivery_receipt.py','real_evaluation_check.py','evaluation_ui_check.py','evaluation_ui_check.cjs','formal_browser_check.cjs')],
]
# Parents whose children must all be accounted for; anything else is reported, never deleted.
WATCHED=['.maintenance','.maintenance/backups','.maintenance/archives',EVIDENCE.rstrip('/')]
KEPT={'.maintenance/backups','.maintenance/archives','.maintenance/migrations',EVIDENCE+'STATUS.md',EVIDENCE+'delivery-1011',
      EVIDENCE+'continuation-1011a-backend.xml',EVIDENCE+'continuation-1011f-frontend.xml'}


def long(path):
    value=str(path)
    return value if os.name!='nt' or value.startswith('\\\\?\\') else '\\\\?\\'+value


def is_link(path):
    info=os.lstat(long(path))
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT)


def measure(path):
    size=files=links=errors=0
    if is_link(path): return {'bytes':0,'files':0,'links':1,'errors':0}
    if os.path.isfile(long(path)): return {'bytes':os.path.getsize(long(path)),'files':1,'links':0,'errors':0}
    stack=[path]
    while stack:
        folder=stack.pop()
        try: entries=list(os.scandir(long(folder)))
        except OSError: errors+=1; continue
        for entry in entries:
            child=Path(folder)/entry.name
            try:
                if is_link(child): links+=1
                elif entry.is_dir(follow_symlinks=False): stack.append(child)
                else: size+=entry.stat(follow_symlinks=False).st_size; files+=1
            except OSError: errors+=1
    return {'bytes':size,'files':files,'links':links,'errors':errors}


def remove(path,failures):
    """Bottom-up deletion; links are unlinked (never traversed); read-only bits cleared."""
    def unlink(target):
        info=os.lstat(long(target))
        if getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_READONLY or not info.st_mode&stat.S_IWRITE:
            try: os.chmod(long(target),stat.S_IWRITE,follow_symlinks=False)
            except (OSError,NotImplementedError): pass
        # A directory junction/symlink is removed with rmdir: only the link goes, never its target.
        directory=getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_DIRECTORY
        (os.rmdir if directory else os.unlink)(long(target))
    if is_link(path) or os.path.isfile(long(path)):
        try: unlink(path)
        except OSError as exc: failures.append({'path':str(path),'error':type(exc).__name__})
        return
    try: entries=list(os.scandir(long(path)))
    except OSError as exc:
        # e.g. an ACL this account cannot read: report it; never change permissions.
        failures.append({'path':str(path),'error':type(exc).__name__}); return
    for entry in entries:
        child=Path(path)/entry.name
        if is_link(child) or not entry.is_dir(follow_symlinks=False):
            try: unlink(child)
            except OSError as exc: failures.append({'path':str(child),'error':type(exc).__name__})
        else: remove(child,failures)
    try: os.rmdir(long(path))
    except OSError as exc: failures.append({'path':str(path),'error':type(exc).__name__})


def preconditions():
    from backend.app.core.config import AppSettings
    from scripts.workspace_backup import offline,roots
    import sqlite3
    settings=AppSettings()
    problems=[]
    try: offline(settings)
    except RuntimeError as exc: problems.append(str(exc))
    for marker in ('maintenance-operation.json','restore-journal.json','schema-upgrade-journal.json'):
        if (settings.runtime_dir/marker).exists(): problems.append('進行中的維護作業標記：'+marker)
    if (WORKSPACE_ROOT/'.maintenance/migration-in-progress.json').exists(): problems.append('遷移進行中')
    with sqlite3.connect(settings.sqlite_path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running','stopping')").fetchone()[0]: problems.append('研究工作仍在執行')
    with sqlite3.connect((settings.clinical_dir/'clinical.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute("SELECT COUNT(*) FROM demo_sessions WHERE state='active'").fetchone()[0]: problems.append('雙機接收會話仍開啟')
    live=[p.resolve() for p in roots(settings).values()]+[CODE.resolve()]
    return problems,live


def resolve(relative,live):
    path=(WORKSPACE_ROOT/relative)
    absolute=Path(os.path.abspath(path))
    if not absolute.is_relative_to(WORKSPACE_ROOT) or absolute==WORKSPACE_ROOT: raise ValueError('越界目標：'+relative)
    for root in live:
        if absolute.is_relative_to(root) or root.is_relative_to(absolute): raise ValueError('目標與現行資料或程式重疊：'+relative)
    return absolute


def unknown_children():
    listed={t[1].rstrip('/') for t in TARGETS}|KEPT
    found=[]
    for parent in WATCHED:
        folder=WORKSPACE_ROOT/parent
        if folder.is_dir():
            found+=[f'{parent}/{c.name}' for c in folder.iterdir() if f'{parent}/{c.name}' not in listed]
    return sorted(found)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['plan','apply']);parser.add_argument('receipt',type=Path);parser.add_argument('--final',action='store_true')
    args=parser.parse_args()
    problems,live=preconditions()
    selected=[t for t in TARGETS if t[0]!='final' or args.final]
    rows=[];total=0
    for action,relative,purpose,reason in selected:
        path=resolve(relative,live)
        if not os.path.lexists(long(path)): rows.append({'path':relative,'action':action,'purpose':purpose,'evidence':reason,'state':'absent'}); continue
        if action=='prune':
            parts=[Path(path)/e.name for e in os.scandir(long(path)) if e.is_dir(follow_symlinks=False) or is_link(Path(path)/e.name)]
            measured=[measure(p) for p in parts]
        else: parts=[path]; measured=[measure(path)]
        size=sum(m['bytes'] for m in measured);total+=size
        rows.append({'path':relative,'action':action,'purpose':purpose,'evidence':reason,'bytes':size,'files':sum(m['files'] for m in measured),
                     'links_not_followed':sum(m['links'] for m in measured),'read_errors':sum(m['errors'] for m in measured),'parts':[str(p.relative_to(WORKSPACE_ROOT)) for p in parts] if action=='prune' else None})
    receipt={'mode':args.mode,'final':args.final,'created':time.strftime('%Y-%m-%dT%H:%M:%S'),'workspace':str(WORKSPACE_ROOT),
             'preconditions_ok':not problems,'precondition_problems':problems,'unknown_not_touched':unknown_children(),
             'total_bytes_listed':total,'targets':rows}
    if args.mode=='apply':
        if problems: raise SystemExit('前置條件未通過，未刪除任何檔案：'+'；'.join(problems))
        free_before=shutil.disk_usage(WORKSPACE_ROOT).free;failures=[]
        for row in rows:
            if row.get('state')=='absent': continue
            # A prune touches only its listed subfolders (possibly none); never the folder itself.
            for part in (row['parts'] if row['action']=='prune' else [row['path']]):
                remove(WORKSPACE_ROOT/part,failures)
            row['state']='removed' if not any(f['path'].startswith(str(WORKSPACE_ROOT/row['path'])) for f in failures) else 'partial'
        receipt.update(failures=failures,free_bytes_before=free_before,free_bytes_after=shutil.disk_usage(WORKSPACE_ROOT).free)
        receipt['freed_bytes_measured']=receipt['free_bytes_after']-free_before
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in receipt if k not in ('targets',)},ensure_ascii=False)[:3000])
    if args.mode=='apply' and receipt['failures']: raise SystemExit(1)


if __name__=='__main__':main()
