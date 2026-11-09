"""工作區整理（決策 D29）：說明檔、空資料夾清理、依任務搬移訓練資料夾、匯出資料夾、開啟資料夾。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.errors import AppError
from ..data.storage import slug
from ..db.models_research import Evaluation, ModelEntry, TrainingRun
from ..db.session import session_scope

# 每個資料夾的 說明.txt：位置（相對於 layout 鍵）→ 內容
README_TEXTS: dict[tuple[str, str], str] = {
    ('data', ''): '研究資料，全部由系統管理，請不要手動修改、搬移或改名。\n各子資料夾的用途見裡面的 說明.txt；完整說明見 01_計畫與文件/資料庫與檔案設計.md 第 2 節。\n想找某張影像、某位病人（P-編號）、某個訓練，請先看 09_索引 裡的 CSV（可用 Excel 開啟，不含個資）。',
    ('databases', ''): 'system、research、clinical 三個 SQLite 資料庫。系統執行中請不要複製或修改；備份見 07_備份。',
    ('raw_archive', ''): '受限區：含病人個資的原始檔。\n- {批次ID}/：匯入區批次的原始影像副本（初始資料集 B0000 不複製，指向 IMG_original）。\n- 病人表/：上傳過的病人表（T-編號）。\n- 醫師圈選匯出/、醫師圈選回傳/：勾選「原始影像」時才會有。\n不可上傳、不可外流；網頁不顯示這裡的檔案。',
    ('deid_images', ''): '去識別化影像（已遮蓋個資）。影像/ 給模型用、計算用/ 給灰階計算用、縮圖/ 給網頁顯示。\n檔名是影像 ID，依 ID 前兩碼分桶。要找影像屬於哪位病人，看 09_索引/影像索引.csv。',
    ('annotations', ''): '人工標註。\n- 遮罩/{分桶}/{影像ID}/v{版本}_{來源}.png：每次存檔都是新版本（0 背景、1 腎實質、2 腎竇、3 肝、4 脾）。\n- 醫師圈選回傳/：醫師在去識別化影像上圈選後傳回的原檔，保留以便追溯。\n- 一致性報告/。\n遮罩的來源、狀態與是否確認，看 09_索引/遮罩索引.csv。',
    ('model_outputs', ''): '模型自動產生的結果，依來源分開、不覆蓋。\n- 預測遮罩/{訓練ID}/：分割訓練的交叉驗證預測。\n- 預測遮罩組/{MS-ID}/：交叉預測遮罩組（全部影像）。\n- 特徵/{FS-ID}/：回音與形態特徵。\n- 預測結果/{工作ID}/：一鍵流程與 AI 分析。',
    ('dataset_versions', ''): '凍結的資料集版本（manifest.json）。訓練一定指定一個版本，凍結後不可修改。',
    ('splits', ''): '病人層級的資料切分（病人 → 組別）。',
    ('import_records', ''): '每一批匯入的報表（report.json）。',
    ('exports', ''): '給醫師、論文或分析用的匯出，每次一個資料夾：{日期}_{用途}/。可以自由複製帶走（內容不含個資）。',
    ('index', ''): '索引（自動產生，不含個資）：用 Excel 開啟就能查找影像、遮罩、醫師圈選批次、訓練、模型、評估。\n病人只用 P-編號，eGFR 只寫分組。系統在匯入、訓練、評估、遮罩上傳後自動更新，也可以在「設定」按「更新索引」。\n請不要在這裡存放自己的檔案，下次更新會被覆蓋。',
    ('clinical', ''): '醫師端（M3）。\n- 01_原始/：受限區，A 電腦或超音波機器傳來的原始影像（可能含個資），網頁不顯示、不可外流。\n- 02_影像/{檢查}/：去識別化後的影像與遮罩疊圖。\n- 03_報告/{病例代碼或檢查}/報告.pdf：每份報告只保留最新一份 PDF（新版覆蓋舊版，D42）；各版本內容存在資料庫。\n- 04_分析/：分析結果的圖檔。\n- 05_接收暫存/：受限區，上傳中的暫存檔。\n請不要手動修改；要刪除請用網頁的回收桶。',
    ('models', ''): '模型相關。\n- 01_訓練紀錄/{eGFR|分割|回音分級}/{訓練ID}_{名稱}/：每個訓練的設定、紀錄、各折權重；摘要.txt 是人看得懂的摘要。\n- 02_模型庫/{eGFR|分割|回音分級}/{名稱}@{版本}/：註冊的模型（註冊後不可改）。\n- 03_評估/{eGFR|分割|回音分級}/{評估ID}_{對象}/：評估報告。\n- 04_預訓練權重/：下載的公開權重。\n- nnUNet/：nnU-Net 基準實驗的資料與結果。',
}


def ensure_readmes() -> None:
    """建立缺少的 說明.txt（已存在的不覆蓋，方便你自己加註）。"""
    settings = get_settings()
    for (key, sub), text in README_TEXTS.items():
        folder = settings.path(key) / sub if sub else settings.path(key)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / '說明.txt'
            if not target.exists():
                target.write_text(text + '\n', encoding='utf-8')
        except OSError:
            continue


def remove_empty_dirs(base: Path, stop: Path) -> int:
    """往上移除變空的資料夾，直到 stop（不含）。只刪空資料夾，有檔案的不動。"""
    removed = 0
    current = base
    stop = stop.resolve()
    while current.resolve() != stop and stop in current.resolve().parents:
        try:
            current.rmdir()
        except OSError:
            break
        removed += 1
        current = current.parent
    return removed


def cleanup_legacy_clinical_dirs() -> int:
    """M3 之前建立的醫師端空資料夾（報告、接收暫存、檢查）改用 01_原始…05_接收暫存；只刪空的，有檔案的不動。"""
    removed = 0
    for name in ('報告', '接收暫存', '檢查'):
        path = get_settings().path('clinical') / name
        try:
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
                removed += 1
        except OSError:
            continue
    return removed


def cleanup_empty_mask_dirs() -> int:
    """清掉 03_人工標註/遮罩 底下的空資料夾（例如永久刪除草稿後留下的）。只刪空資料夾。"""
    root = get_settings().path('annotations') / '遮罩'
    if not root.exists():
        return 0
    removed = 0
    for dirpath, _dirnames, _files in sorted(os.walk(root), key=lambda x: -len(x[0])):
        path = Path(dirpath)
        if path == root:
            continue
        try:
            path.rmdir()
            removed += 1
        except OSError:
            continue
    return removed


# ---------- 依任務搬移訓練、模型、評估資料夾 ----------
def _expected_paths() -> list[dict[str, Any]]:
    from ..ml.paths import model_dir, new_eval_dir, new_run_dir

    root = get_settings().root
    plan: list[dict[str, Any]] = []
    with session_scope('research') as db:
        runs = {r.id: r for r in db.query(TrainingRun).all()}
        for r in runs.values():
            target = new_run_dir(r.id, r.task, '' if r.name == r.id else r.name)
            if r.config_json and '"framework": "nnunetv2"' in r.config_json:
                target = new_run_dir(r.id, r.task, 'nnU-Net')
            plan.append({'kind': 'run', 'id': r.id, 'status': r.status, 'from': r.relpath, 'to': target.relative_to(root).as_posix()})
        for m in db.query(ModelEntry).all():
            plan.append({'kind': 'model', 'id': m.id, 'status': m.stage, 'from': m.relpath, 'to': model_dir(m.task, m.name, m.version).relative_to(root).as_posix()})
        for e in db.query(Evaluation).all():
            task = runs[e.run_id].task if e.run_id in runs else ''
            if not task and e.model_id:
                task = e.model_id.split('/', 1)[0]
            subject = (e.model_id or '').replace('/', '-') or e.run_id or ''
            plan.append({'kind': 'evaluation', 'id': e.id, 'status': e.target, 'from': e.relpath, 'to': new_eval_dir(e.id, task, subject).relative_to(root).as_posix()})
    return [p for p in plan if p['from'] and p['from'] != p['to']]


def migration_preview() -> dict[str, Any]:
    root = get_settings().root
    items = []
    for p in _expected_paths():
        source, target = root / p['from'], root / p['to']
        blocked = ''
        if p['kind'] == 'run' and p['status'] in ('queued', 'running'):
            blocked = '訓練正在執行，請等它結束'
        elif not source.exists():
            blocked = '原資料夾不存在，只更新資料庫路徑'
        elif target.exists():
            blocked = '目標資料夾已存在'
        items.append({**p, 'note': blocked})
    return {'items': items, 'count': len(items)}


def migrate_folders(operator: str) -> dict[str, Any]:
    root = get_settings().root
    moved, skipped = [], []
    for p in migration_preview()['items']:
        source, target = root / p['from'], root / p['to']
        if p['kind'] == 'run' and p['status'] in ('queued', 'running'):
            skipped.append({**p, 'reason': p['note']})
            continue
        if source.exists():
            if target.exists():
                skipped.append({**p, 'reason': '目標資料夾已存在'})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            remove_empty_dirs(source.parent, get_settings().path('models'))
        model = {'run': TrainingRun, 'model': ModelEntry, 'evaluation': Evaluation}[p['kind']]
        with session_scope('research') as db:
            row = db.get(model, p['id'])
            if row is not None:
                row.relpath = p['to']
        moved.append(p)
    if any(p['kind'] == 'run' for p in moved):
        from ..ml.paths import write_run_summary

        for p in moved:
            if p['kind'] == 'run':
                write_run_summary(p['id'])
    return {'moved': len(moved), 'skipped': skipped, 'items': moved, 'operator': operator}


# ---------- 匯出資料夾 ----------
def new_export_dir(purpose: str) -> Path:
    base = get_settings().path('exports')
    name = f'{date.today().isoformat()}_{slug(purpose)}'
    folder, n = base / name, 2
    while folder.exists():
        folder, n = base / f'{name}_{n}', n + 1
    folder.mkdir(parents=True)
    return folder


# ---------- 在檔案總管開啟 ----------
RESTRICTED_KEYS = ('raw_archive', 'source_original', 'databases', 'backups')  # 備份含資料庫完整複本（M3 #113）


def resolve_folder(kind: str, object_id: str = '') -> Path:
    """把物件換成資料夾位置；只允許專案內、非受限區。"""
    settings = get_settings()
    root = settings.root
    path: Path | None = None
    if kind == 'run':
        from ..ml.paths import run_dir

        path = run_dir(object_id)
    elif kind == 'evaluation':
        from ..ml.paths import eval_dir

        path = eval_dir(object_id)
    elif kind == 'model':
        with session_scope('research') as db:
            m = db.get(ModelEntry, object_id)
            path = root / m.relpath if m else None
    elif kind in ('index', 'exports', 'models', 'annotations', 'model_outputs'):
        path = settings.path(kind) / object_id if object_id else settings.path(kind)
    elif kind == 'relpath':
        path = root / object_id
    if path is None:
        raise AppError(404, 'FOLDER_NOT_FOUND', '找不到這個資料夾。')
    path = path.resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise AppError(403, 'FOLDER_OUTSIDE', '只能開啟專案內的資料夾。')
    for key in RESTRICTED_KEYS:
        restricted = settings.path(key).resolve()
        if path == restricted or restricted in path.parents:
            raise AppError(403, 'FOLDER_RESTRICTED', '這個資料夾含個資（受限區），不提供開啟。')
    from ..core.config import CLINICAL_RESTRICTED

    for sub in CLINICAL_RESTRICTED:  # 醫師端的原始影像與接收暫存（M3-8）
        restricted = (settings.path('clinical') / sub).resolve()
        if path == restricted or restricted in path.parents:
            raise AppError(403, 'FOLDER_RESTRICTED', '這個資料夾含個資（受限區），不提供開啟。')
    if not path.exists():
        raise AppError(404, 'FOLDER_NOT_FOUND', '資料夾還不存在。')
    return path


def open_folder(kind: str, object_id: str = '') -> dict[str, Any]:
    path = resolve_folder(kind, object_id)
    rel = path.relative_to(get_settings().root.resolve()).as_posix() if path != get_settings().root.resolve() else '.'
    if not get_settings().testing:
        if sys.platform == 'win32':
            os.startfile(str(path))  # noqa: S606  只開本機專案內的資料夾
        else:
            subprocess.Popen(['xdg-open', str(path)])  # noqa: S603,S607
    return {'path': rel}
