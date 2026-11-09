"""訓練的預設設定（不需要 PyTorch）。

網頁的請求（訓練表單、訓練詳細、建立比較組、註冊模型、特徵擷取）只需要預設值，
放在這裡就不必載入 engine.py；engine.py 一載入就會載入 PyTorch 與 CUDA 函式庫（約 2 GB），
第一次要等很久（M2.5 #108）。真正訓練或推論時才載入 engine.py。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.config import get_settings
from .tabular import input_list

COMMON = {'seed': 42, 'num_workers': 0, 'amp': True, 'max_images': None, 'folds': None, 'features': None, 'device': 'auto'}
# eGFR 的輸入方式（決策 D23）：image＝影像；clinical＝糖尿病、年齡、性別；measures＝遮罩量測（特徵集）；mask_channels＝遮罩通道
DEFAULTS: dict[str, dict[str, Any]] = {
    'segmentation': {'arch': 'resnet34-unet', 'init': 'random', 'img_size': 512, 'epochs': 60, 'batch_size': 4, 'accum_steps': 2, 'lr': 3e-4, 'weight_decay': 1e-4, 'patience': 12, 'flip': False, 'mask_policy': 'verified'},
    'egfr': {'arch': 'resnet18', 'init': 'random', 'head': 'binary', 'img_size': 384, 'epochs': 40, 'batch_size': 16, 'accum_steps': 1, 'lr': 3e-4, 'weight_decay': 1e-4, 'patience': 10, 'egfr_classes': 2},
    'grade': {'arch': 'resnet18', 'init': 'random', 'head': 'corn', 'img_size': 384, 'epochs': 40, 'batch_size': 16, 'accum_steps': 1, 'lr': 3e-4, 'weight_decay': 1e-4, 'patience': 10},
}


def full_config(task: str, overrides: dict[str, Any] | None) -> dict[str, Any]:
    cfg = {**COMMON, **DEFAULTS[task], **(overrides or {})}
    cfg['task'] = task
    if task == 'egfr':
        if int(cfg.get('egfr_classes', 2)) > 2 and 'head' not in (overrides or {}):
            cfg['head'] = 'corn'  # 3、5 類預設 CORN（有序）；2 類維持二元
        cfg['inputs'] = input_list(cfg)
    if task == 'segmentation':
        cfg.pop('head', None)
    return cfg


def seg_output_dir(run_id: str) -> Path:
    """分割訓練的 OOF 預測遮罩資料夾。"""
    return get_settings().path('model_outputs') / '預測遮罩' / run_id
