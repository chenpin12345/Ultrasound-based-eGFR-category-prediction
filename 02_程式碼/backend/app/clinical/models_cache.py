"""醫師端的模型快取與預熱（M3-3）。

第一次分析原本要等 PyTorch 載入與 5 個各約 85 MB 的模型檔；按「開始接收」時先載入（預熱），之後的分析直接用。
顯示卡正在訓練時改用 CPU（較慢），避免搶顯示卡記憶體；結果會記錄實際使用的裝置。
PyTorch 只在醫師端佇列的工作裡載入，網頁請求不載入（M2.5 #108 的原則）。
"""

from __future__ import annotations

import threading
from typing import Any

from ..db.models_system import Job
from ..db.session import session_scope
from ..jobs.manager import JobContext, register

# 用到顯示卡的研究端工作：執行中時，醫師端改用 CPU
GPU_KINDS = {'train', 'nnunet_train', 'mask_set', 'medsam_kidney', 'evaluate_test', 'evaluate_egfr_test', 'pipeline'}
_cache: dict[tuple[str, str], Any] = {}
_lock = threading.Lock()


def gpu_busy() -> bool:
    with session_scope('system') as db:
        return db.query(Job).filter(Job.kind.in_(GPU_KINDS), Job.status.in_(('running', 'stopping'))).count() > 0


def device_choice() -> tuple[str, str]:
    """回傳 (registry.load 的 device 參數, 給人看的說明)。"""
    if gpu_busy():
        return 'cpu', '顯示卡訓練中，改用 CPU，較慢'
    return 'auto', ''


def get(model_id: str, expect_task: str | None = None):
    """取得已載入的模型；沒有就載入（含合約與雜湊檢查，見 registry.load）。"""
    from ..ml import registry

    device, _ = device_choice()
    key = (model_id, device)
    with _lock:
        model = _cache.get(key)
        if model is None:
            model = registry.load(model_id, expect_task, device=device)
            _cache[key] = model
    return model


def loaded() -> list[dict[str, str]]:
    with _lock:
        return [{'model_id': k[0], 'device': str(v.device)} for k, v in _cache.items()]


def clear() -> None:
    with _lock:
        _cache.clear()


def retain(model_ids: set[str]) -> list[str]:
    """只留下分析方案裡的模型；換掉的模型從記憶體釋放（不然一直佔記憶體，也會被列成「已預先載入」）。"""
    with _lock:
        dropped = [k for k in _cache if k[0] not in model_ids]
        for k in dropped:
            del _cache[k]
    return sorted({k[0] for k in dropped})


@register('clinical_warmup', pool='clinical', label='醫師端預先載入模型')
def warmup_job(ctx: JobContext) -> dict[str, Any]:
    """把分析方案的模型先載入快取（按「開始接收」時自動執行，也可以在設定頁手動執行）。"""
    from . import plan

    zones = plan.current()['zones']
    retain({z['model_id'] for z in zones.values() if z['model_id']})
    done = []
    for n, (zone, info) in enumerate(zones.items(), start=1):
        if info['model_id']:
            ctx.check_stop()
            model = get(info['model_id'], zone)
            done.append({'zone': zone, 'model_id': info['model_id'], 'device': str(model.device)})
        ctx.progress(n / len(zones) * 100, f'{n}／{len(zones)}')
    return {'loaded': done, 'note': device_choice()[1]}
