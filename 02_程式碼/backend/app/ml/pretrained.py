"""預訓練權重（D2）：下載一次存在 04_模型/04_預訓練權重/{名稱}/，附 sha256 與授權，之後離線使用。

- medsam-vit-base：只當標註工具。
- ImageNet 權重：訓練時可選「隨機初始化」或「ImageNet」，由消融實驗比較兩者。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.errors import AppError
from ..core.ids import now_iso
from ..jobs.manager import JobContext, register
from . import medsam

# torchvision 的 ImageNet 權重（BSD-3-Clause）
TORCHVISION = {
    'resnet18-imagenet': ('resnet18', 'ResNet18_Weights', 'IMAGENET1K_V1', '分類骨幹（小）'),
    'resnet34-imagenet': ('resnet34', 'ResNet34_Weights', 'IMAGENET1K_V1', '分類骨幹、UNet 編碼器'),
}
CATALOG: dict[str, dict[str, str]] = {
    'medsam-vit-base': {'label': 'MedSAM（標註工具）', 'license': 'Apache-2.0', 'size': '約 375 MB', 'use': '用舊遮罩當框重畫腎臟；不放進最後的模型'},
    **{k: {'label': v[0], 'license': 'BSD-3-Clause', 'size': '約 45–85 MB', 'use': v[3]} for k, v in TORCHVISION.items()},
}


def spec(name: str) -> dict[str, str]:
    if name not in CATALOG:
        raise AppError(404, 'WEIGHTS_NOT_FOUND', '不認識這個預訓練權重。')
    return CATALOG[name]


def path_of(name: str) -> Path:
    return medsam.weights_dir(name)


def info(name: str) -> dict[str, Any] | None:
    f = path_of(name) / 'download.json'
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else None


def list_weights() -> list[dict[str, Any]]:
    return [{'name': k, **v, 'downloaded': info(k)} for k, v in CATALOG.items()]


def torchvision_state(name: str):
    """訓練時載入 ImageNet 權重（必須先下載）。"""
    import torch

    record = info(name)
    if record is None:
        raise AppError(409, 'WEIGHTS_NOT_DOWNLOADED', f'還沒有下載 {name}，請先到「訓練 › 預訓練權重」下載。')
    return torch.load(path_of(name) / record['file'], map_location='cpu', weights_only=True)


def _fetch(url: str, dest: Path, ctx: JobContext) -> None:
    """分段下載：顯示真正的進度、可以隨時停止、中斷後從已下載的位置接續（.part 檔）。"""
    import urllib.request

    tmp = dest.with_name(dest.name + '.part')
    have = tmp.stat().st_size if tmp.exists() else 0
    request = urllib.request.Request(url, headers={'Range': f'bytes={have}-'} if have else {})
    with urllib.request.urlopen(request, timeout=60) as resp:
        if have and resp.status != 206:  # 伺服器不支援接續，從頭下載
            have = 0
        total = have + int(resp.headers.get('Content-Length') or 0)
        with tmp.open('ab' if have else 'wb') as fh:
            while chunk := resp.read(1 << 18):
                fh.write(chunk)
                have += len(chunk)
                ctx.check_stop()  # 停止時保留 .part，下次接續
                if total:
                    ctx.progress(5 + 90 * have / total, f'{have / 2**20:.1f}／{total / 2**20:.1f} MB')
    tmp.replace(dest)


def _download_torchvision(name: str, ctx: JobContext) -> dict[str, Any]:
    import torchvision.models as tvm

    arch, enum_name, member, _ = TORCHVISION[name]
    weights = getattr(getattr(tvm, enum_name), member)
    target = path_of(name)
    target.mkdir(parents=True, exist_ok=True)
    file = target / f'{arch}.pth'
    _fetch(weights.url, file, ctx)
    digest = medsam.sha256_file(file)
    expected = weights.url.rsplit('-', 1)[-1].split('.')[0]  # torchvision 檔名內含 sha256 的前 8 碼
    if not digest.startswith(expected):
        file.unlink()
        raise AppError(502, 'WEIGHTS_CORRUPT', '下載的檔案雜湊不符（可能下載不完整），已刪除，請重新下載。')
    record = {'name': name, 'source': weights.url, 'license': 'BSD-3-Clause', 'file': file.name, 'sha256': {file.name: digest}, 'downloaded_at': now_iso()}
    (target / 'download.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


@register('download_pretrained', label='下載預訓練權重')
def download_job(ctx: JobContext) -> dict[str, Any]:
    name = ctx.config['name']
    spec(name)
    ctx.progress(5, f'下載 {name}')
    record = medsam.download() if name == 'medsam-vit-base' else _download_torchvision(name, ctx)
    ctx.progress(100, '完成')
    return {'name': name, 'files': list(record.get('sha256', {}).keys())}
