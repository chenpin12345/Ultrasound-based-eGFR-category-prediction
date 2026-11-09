"""物件編號。格式與 01_計畫與文件/資料庫與檔案設計.md 第 2.3 節一致。"""

from __future__ import annotations

import secrets
from datetime import datetime


def image_id() -> str:
    return f'IMG-{secrets.token_hex(6).upper()}'


def shard(identifier: str) -> str:
    """影像 ID 的前兩碼，用來分桶存放。"""
    return identifier.split('-', 1)[-1][:2]


def short_uid() -> str:
    return secrets.token_hex(8)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def today_compact() -> str:
    return datetime.now().strftime('%Y%m%d')


def next_sequential(prefix: str, existing: list[str], width: int = 4) -> str:
    """dsv-0001、split-0001、P-0001 這類流水號。"""
    numbers = []
    for item in existing:
        tail = item.removeprefix(prefix)
        if tail.isdigit():
            numbers.append(int(tail))
    return f'{prefix}{(max(numbers) + 1) if numbers else 1:0{width}d}'


def next_dated(prefix: str, existing: list[str], width: int = 2) -> str:
    """B20261105-01、RUN-20261110-004 這類以日期分組的流水號。"""
    stem = f'{prefix}{today_compact()}-'
    numbers = [int(i.removeprefix(stem)) for i in existing if i.startswith(stem) and i.removeprefix(stem).isdigit()]
    return f'{stem}{(max(numbers) + 1) if numbers else 1:0{width}d}'
