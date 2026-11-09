"""完整備份：資料庫、資料、模型、醫師端、原始影像與文件，複製到指定資料夾（建議外接硬碟）。

用法：python full_backup.py <目標資料夾>
請先執行 stop.bat 停止服務，避免備份到寫到一半的資料。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("KIDNEY_WORKSPACE_ROOT", Path(__file__).resolve().parents[2])).resolve()
INCLUDE = ['workspace-layout.json', 'README.md', '01_計畫與文件', '03_資料', '04_模型', '05_醫師端', 'IMG_original']
RUN_FILE = ROOT / '08_系統' / 'run' / 'server.json'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if len(sys.argv) > 2:
        print('用法：python full_backup.py [目標資料夾]')
        return 2
    if RUN_FILE.exists():
        print('系統還在執行，請先執行 stop.bat 再備份。')
        return 1
    if len(sys.argv) == 2:
        target_text = sys.argv[1]
    else:
        # backup.bat 不帶參數：在這裡詢問（批次檔只放英文，中文提示由 Python 輸出）
        print('完整備份會複製資料庫、資料、模型、醫師端、原始影像與文件。')
        print('原始影像含有個資，請使用外接硬碟並妥善保管。')
        target_text = input('請輸入備份目標資料夾（例如 E:\\備份）：').strip().strip('"')
        if not target_text:
            return 1
    target_root = Path(target_text).expanduser().resolve()
    if ROOT in target_root.parents or target_root == ROOT:
        print('目標資料夾不能在工作區裡面，請選擇外接硬碟。')
        return 1
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = target_root / f'腎超備份_{stamp}'
    target.mkdir(parents=True)
    started = time.time()
    manifest: dict[str, str] = {}
    total = 0
    for item in INCLUDE:
        src = ROOT / item
        if not src.exists():
            continue
        files = [src] if src.is_file() else [p for p in src.rglob('*') if p.is_file()]
        for f in files:
            rel = f.relative_to(ROOT)
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if f.suffix == '.sqlite3':
                with closing(sqlite3.connect(f)) as s, closing(sqlite3.connect(dst)) as d:
                    s.backup(d)
            elif f.name.endswith(('-wal', '-shm')):
                continue
            else:
                shutil.copy2(f, dst)
            manifest[rel.as_posix()] = sha256(dst)
            total += dst.stat().st_size
        print(f'已備份 {item}')
    (target / 'manifest.json').write_text(json.dumps({'created_at': stamp, 'files': manifest}, ensure_ascii=False, indent=1), encoding='utf-8')
    record = ROOT / '07_備份' / '完整備份紀錄' / f'{stamp}.json'
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(
        json.dumps({'created_at': stamp, 'target_label': target.name, 'files': len(manifest), 'bytes': total, 'seconds': round(time.time() - started), 'status': '完成'}, ensure_ascii=False),
        encoding='utf-8',
    )
    print(f'完成：{len(manifest)} 個檔案，{total / 1024**3:.2f} GB，存在 {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
