"""MedSAM（wanglab/medsam-vit-base，Apache 2.0）：只當標註工具，用框提示重畫腎臟，不放進最後的模型。

權重放在 04_模型/04_預訓練權重/medsam-vit-base/，由「下載預訓練權重」工作下載一次，之後離線使用。
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import now_iso

REPO_ID = 'wanglab/medsam-vit-base'
NAME = 'medsam-vit-base'
_lock = threading.Lock()
_cache: dict[str, object] = {}


def weights_dir(name: str = NAME) -> Path:
    return get_settings().path('models') / '04_預訓練權重' / name


def output_dir() -> Path:
    return get_settings().path('model_outputs') / '預測遮罩' / 'medsam-vit-b'


def is_downloaded(name: str = NAME) -> bool:
    return (weights_dir(name) / 'download.json').exists()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def download() -> dict:
    """從 Hugging Face 下載 MedSAM 權重，記錄每個檔案的 sha256。"""
    import os

    # xet 下載器在含中文的路徑會回報完成卻沒有寫出檔案；改用一般 HTTPS 下載
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    from huggingface_hub import snapshot_download

    target = weights_dir()
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=REPO_ID, local_dir=str(target), allow_patterns=['*.json', '*.safetensors', '*.bin', '*.txt', '*.md'])
    if not any((target / f).exists() for f in ('model.safetensors', 'pytorch_model.bin')):
        raise AppError(502, 'MEDSAM_DOWNLOAD_INCOMPLETE', '下載不完整：沒有取得 MedSAM 權重檔，請稍後再試。')
    files = {p.name: sha256_file(p) for p in sorted(target.iterdir()) if p.is_file() and p.name != 'download.json'}
    info = {'repo': REPO_ID, 'license': 'Apache-2.0', 'downloaded_at': now_iso(), 'sha256': files}
    (target / 'download.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    return info


def _load():
    with _lock:
        if 'model' not in _cache:
            if not is_downloaded():
                raise AppError(409, 'MEDSAM_NOT_DOWNLOADED', '還沒有下載 MedSAM 權重，請先到「訓練 › 預訓練權重」下載。')
            import torch
            from transformers import SamModel, SamProcessor

            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            model = SamModel.from_pretrained(str(weights_dir())).to(device).eval()
            _cache.update(model=model, processor=SamProcessor.from_pretrained(str(weights_dir())), device=device)
        return _cache['model'], _cache['processor'], _cache['device']


def segment(gray: np.ndarray, boxes: list[tuple[int, int, int, int]], normalize: bool = True) -> np.ndarray:
    """灰階影像＋多個框 → 平均後的機率圖（0–1，原圖大小）。影像只編碼一次。"""
    import torch

    model, processor, device = _load()
    # MedSAM 訓練時每張影像先做最小–最大值正規化到 0–255；去識別化後的影像沒有白色文字，
    # 最亮處常只有 170 左右，不拉伸的話整張偏暗，圈出的範圍會明顯縮小
    g = gray.astype(np.float32)
    lo, hi = float(g.min()), float(g.max())
    stretched = ((g - lo) / max(hi - lo, 1e-6) * 255).astype(np.uint8) if normalize else gray
    rgb = np.repeat(stretched[:, :, None], 3, axis=2)
    inputs = processor(rgb, input_boxes=[[list(map(float, b)) for b in boxes]], return_tensors='pt')
    with torch.no_grad():
        embeddings = model.get_image_embeddings(inputs['pixel_values'].to(device))
        outputs = model(image_embeddings=embeddings, input_boxes=inputs['input_boxes'].to(device), multimask_output=False)
    probs = processor.image_processor.post_process_masks(
        outputs.pred_masks.sigmoid().cpu(), inputs['original_sizes'], inputs['reshaped_input_sizes'], binarize=False
    )[0]
    return probs[:, 0].mean(dim=0).numpy()


def get_segmenter() -> Callable[[np.ndarray, list[tuple[int, int, int, int]]], np.ndarray]:
    """測試時可以換成替身（monkeypatch 這個函式），不必載入真的權重。"""
    return segment
