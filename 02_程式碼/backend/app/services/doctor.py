"""系統檢查：環境、資料夾、資料庫、OCR、GPU。"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from typing import Any

from ..core.config import get_settings


def _check(name: str, ok: bool, note: str) -> dict[str, Any]:
    return {'name': name, 'ok': ok, 'note': note}


def run() -> list[dict[str, Any]]:
    settings = get_settings()
    checks = [_check('Python', sys.version_info[:2] == (3, 12), platform.python_version())]
    missing = [m for m in ('fastapi', 'sqlalchemy', 'cv2', 'skimage', 'sklearn', 'openpyxl', 'rapidocr_onnxruntime') if importlib.util.find_spec(m) is None]
    checks.append(_check('後端套件', not missing, '齊全' if not missing else '缺少：' + '、'.join(missing)))
    try:
        from ..data import ocr

        ocr._get_engine()
        checks.append(_check('OCR 引擎', True, 'RapidOCR 可用（離線）'))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check('OCR 引擎', False, f'無法載入：{type(exc).__name__}'))
    # 不在網站程序裡 import torch（會載入約 2 GB 的 CUDA 函式庫）；只讀套件版本
    from importlib import metadata

    try:
        version = metadata.version('torch')
        checks.append(_check('PyTorch', '+cu' in version, f'{version}（{"CUDA 版" if "+cu" in version else "只有 CPU，無法使用顯示卡"}）'))
    except metadata.PackageNotFoundError:
        checks.append(_check('PyTorch', False, '尚未安裝，請重新執行 setup.bat'))
    for package, label in (('transformers', 'MedSAM 載入套件'), ('nnunetv2', 'nnU-Net v2')):
        try:
            checks.append(_check(label, True, metadata.version(package)))
        except metadata.PackageNotFoundError:
            checks.append(_check(label, False, '尚未安裝，請重新執行 setup.bat'))
    from ..ml import pretrained

    medsam = pretrained.info('medsam-vit-base')
    checks.append(_check('MedSAM 權重', medsam is not None, '已下載' if medsam else '尚未下載（訓練 › 預訓練權重）'))
    gpu = '未偵測到'
    if shutil.which('nvidia-smi'):
        try:
            out = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], capture_output=True, text=True, timeout=10)
            gpu = out.stdout.strip() or gpu
        except Exception:  # noqa: BLE001
            pass
    checks.append(_check('顯示卡', gpu != '未偵測到', gpu))
    original = settings.path('source_original')
    checks.append(_check('原始影像資料夾', original.is_dir() and os.access(original, os.R_OK), '可讀取（系統只讀不寫）' if original.is_dir() else '找不到 IMG_original'))
    writable = all(os.access(settings.path(k), os.W_OK) for k in ('data', 'models', 'inbox', 'backups', 'runtime'))
    checks.append(_check('資料夾寫入權限', writable, '正常' if writable else '有資料夾無法寫入'))
    from sqlalchemy import text

    from ..db.session import DATABASES, get_engine

    versions = []
    for name in DATABASES:
        with get_engine(name).connect() as c:
            row = c.execute(text('SELECT version_num FROM alembic_version')).fetchone()
            versions.append(f'{name} {row[0] if row else "—"}')
    checks.append(_check('資料庫版本', True, '、'.join(versions)))
    dist = settings.frontend_dist / 'index.html'
    checks.append(_check('前端建置', dist.exists(), '已建置' if dist.exists() else '尚未建置（執行 setup.bat）'))
    free = shutil.disk_usage(settings.root).free / 1024**3
    checks.append(_check('磁碟空間', free > 10, f'剩餘 {free:.0f} GB'))
    return checks
