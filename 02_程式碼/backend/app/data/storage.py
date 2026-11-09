"""檔案位置。所有路徑都由這裡產生，其他模組不自己拼路徑。"""

from __future__ import annotations

from pathlib import Path

from ..core.config import get_settings
from ..core.ids import shard

KINDS = {'model': ('影像', '.png'), 'calc': ('計算用', '.png'), 'thumb': ('縮圖', '.jpg')}


def image_path(image_id: str, kind: str = 'model') -> Path:
    folder, suffix = KINDS[kind]
    return get_settings().path('deid_images') / folder / shard(image_id) / f'{image_id}{suffix}'


def mask_path(image_id: str, version: int, label: str) -> Path:
    """遮罩依影像 ID 分桶；檔名用來源（manual、physician_upload…），不放人名。"""
    return get_settings().path('annotations') / '遮罩' / shard(image_id) / image_id / f'v{version:03d}_{label}.png'


def batch_archive(batch_id: str) -> Path:
    return get_settings().path('raw_archive') / batch_id


def import_record_dir(batch_id: str) -> Path:
    return get_settings().path('import_records') / batch_id


def relative_to_root(path: Path) -> str:
    return path.resolve().relative_to(get_settings().root).as_posix()


def from_root(relpath: str) -> Path:
    return get_settings().root / relpath


def slug(name: str) -> str:
    """檔名用的標註者代號（保留中文，去掉不能當檔名的字元）。"""
    import re

    cleaned = re.sub(r'[\\/:*?"<>|\s]+', '_', name).strip('_')
    return cleaned[:40] or 'unknown'
