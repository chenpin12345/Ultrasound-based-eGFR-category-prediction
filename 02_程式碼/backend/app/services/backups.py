"""備份：每日資料庫快照（線上、不停機）與完整備份紀錄。

完整備份（含影像）由 scripts/full_backup.py 在停止服務後執行，這裡只負責列出紀錄。
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any

from ..core.config import get_settings
from ..db.session import DATABASES

KEEP_DAYS = 14


def daily_snapshot(force: bool = False) -> dict[str, Any]:
    settings = get_settings()
    folder = settings.path('backups') / '每日資料庫' / datetime.now().strftime('%Y-%m-%d')
    if folder.exists() and not force:
        return {'folder': folder.name, 'created': False}
    tmp = folder.with_name(folder.name + '.part')
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    sizes = {}
    for name in DATABASES:
        src = settings.database_file(name)
        if not src.exists():
            continue
        dst = tmp / src.name
        # 要明確關閉連線：sqlite3 的 with 只負責 commit，不會關檔；Windows 上開著的檔案會讓下面的資料夾改名失敗
        with closing(sqlite3.connect(src)) as source, closing(sqlite3.connect(dst)) as target:
            source.backup(target)
            ok = target.execute('PRAGMA integrity_check').fetchone()[0]
        sizes[name] = {'bytes': dst.stat().st_size, 'integrity': ok}
    (tmp / 'manifest.json').write_text(json.dumps({'created_at': datetime.now().isoformat(timespec='seconds'), 'databases': sizes}, ensure_ascii=False, indent=2), encoding='utf-8')
    if folder.exists():
        shutil.rmtree(folder)
    tmp.rename(folder)
    prune()
    return {'folder': folder.name, 'created': True, 'databases': sizes}


def prune() -> None:
    root = get_settings().path('backups') / '每日資料庫'
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    for folder in root.iterdir() if root.exists() else []:
        try:
            day = datetime.strptime(folder.name, '%Y-%m-%d')
        except ValueError:
            continue
        if day < cutoff:
            shutil.rmtree(folder, ignore_errors=True)


def list_backups() -> list[dict[str, Any]]:
    root = get_settings().path('backups')
    out = []
    daily = root / '每日資料庫'
    for folder in sorted(daily.iterdir(), reverse=True) if daily.exists() else []:
        if folder.is_dir() and not folder.name.endswith('.part'):
            size = sum(p.stat().st_size for p in folder.glob('*.sqlite3'))
            out.append({'time': folder.name, 'kind': '每日資料庫快照', 'size_bytes': size, 'status': '完成'})
    records = root / '完整備份紀錄'
    for record in sorted(records.glob('*.json'), reverse=True) if records.exists() else []:
        info = json.loads(record.read_text(encoding='utf-8'))
        out.append({'time': info.get('created_at', record.stem), 'kind': '完整備份', 'size_bytes': info.get('bytes', 0), 'status': info.get('status', '完成'), 'target': info.get('target_label', '')})
    return out
