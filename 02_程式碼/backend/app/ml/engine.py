"""通用訓練引擎（改寫自訓練網站 ml/training.py，修正其中的問題）。

- 固定的外部病人層級切分（不再每次重新切分、不以影像雜湊分組）。
- checkpoint 存完整狀態：模型、最佳化器、學習率排程、AMP、patience、所有亂數狀態與洗牌產生器，
  停止後恢復的結果與不中斷相同。
- 各折回報「最佳 epoch」的指標（不是最後一個 epoch）。
- CUDA 上使用自動混合精度（AMP）與梯度累積，配合 8 GB 顯示記憶體。
- 儲存 out-of-fold 預測：分類存機率，分割存預測遮罩（給交叉擬合特徵使用）。
- 在安全的位置檢查停止要求；停止時保留上一個完成的 epoch。
"""

from __future__ import annotations

import csv
import json
import random
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from ..core.config import get_settings
from ..core.ids import shard
from ..data import deid
from . import augment, losses, metrics
from . import data as mldata
from .models import build_classifier, build_segmentation

from .defaults import COMMON, DEFAULTS, full_config, seg_output_dir  # noqa: E402,F401  預設值放在不需要 PyTorch 的模組

SEG_NAMES = ['background', 'parenchyma', 'sinus', 'liver', 'spleen']

from .paths import run_dir  # noqa: E402,F401  訓練資料夾以資料庫的 relpath 為準


# ---------- 資料 ----------
class SegDataset(Dataset):
    def __init__(self, samples: list[mldata.Sample], cfg: dict[str, Any], train: bool):
        self.samples, self.cfg, self.train, self.epoch = samples, cfg, train, 0

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx: int):
        s = self.samples[idx]
        img, _ = augment.letterbox(mldata.load_image(s.image_id), self.cfg['img_size'])
        mask = cv2.imdecode(np.fromfile(s.target, np.uint8), cv2.IMREAD_GRAYSCALE)
        mask, _ = augment.letterbox(mask, self.cfg['img_size'], cv2.INTER_NEAREST)
        if self.train:
            img, mask = augment.augment_segmentation(img, mask, augment.sample_rng(self.cfg['seed'], self.epoch, idx), flip=bool(self.cfg.get('flip', False)))
        return torch.from_numpy(augment.to_tensor_array(img, self.cfg['init'])), torch.from_numpy(mask.astype(np.int64)), idx


class ClsDataset(Dataset):
    def __init__(self, samples: list[mldata.Sample], cfg: dict[str, Any], train: bool, features: dict[str, list[float]] | None):
        self.samples, self.cfg, self.train, self.epoch, self.features = samples, cfg, train, 0, features

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx: int):
        s = self.samples[idx]
        feats = torch.tensor(self.features[s.image_id], dtype=torch.float32) if self.features else torch.zeros(0)
        if 'mask_channels' in (self.cfg.get('inputs') or []):  # ④：以腎臟為中心 160 mm 裁切，加上 3 個遮罩通道
            x = mask_channel_input(s.image_id, self.cfg, s.extra.get('spacing'), self.train, augment.sample_rng(self.cfg['seed'], self.epoch, idx))
            return torch.from_numpy(x), torch.tensor(s.target), feats, idx
        img, _ = augment.letterbox(mldata.load_image(s.image_id), self.cfg['img_size'])
        if self.train:
            img = augment.augment_classification(img, augment.sample_rng(self.cfg['seed'], self.epoch, idx))
        return torch.from_numpy(augment.to_tensor_array(img, self.cfg['init'])), torch.tensor(s.target), feats, idx


def mask_channel_input(image_id: str, cfg: dict[str, Any], spacing: float | None, train: bool, rng) -> np.ndarray:
    """④ 的輸入（4 × H × W）：灰階影像（正規化）＋腎實質、腎竇、肝或脾三個 0／1 通道；遮罩來自交叉預測遮罩組。"""
    from . import roi
    from .masksets import mask_path

    gray = mldata.load_image(image_id)
    label = cv2.imdecode(np.fromfile(str(mask_path(cfg['mask_set_id'], image_id)), np.uint8), cv2.IMREAD_GRAYSCALE)
    img, channels, _ = roi.prepare(gray, label, spacing, cfg['img_size'], float(cfg.get('roi_mm', roi.ROI_MM)))
    if train:
        img, channels = augment.augment_classification(img, rng, channels)
    return np.concatenate([augment.to_tensor_array(img, cfg['init']), channels.astype(np.float32)], 0)


# ---------- 模型與狀態 ----------
from .tabular import input_list  # noqa: E402,F401


def build_model(cfg: dict[str, Any], n_features: int) -> torch.nn.Module:
    if cfg['task'] == 'segmentation':
        return build_segmentation(cfg['arch'], cfg['init'], mldata.NUM_SEG_CLASSES)
    in_channels = 4 if 'mask_channels' in (cfg.get('inputs') or []) else 1
    return build_classifier(cfg['arch'], cfg['init'], cfg['head'], len(mldata.task_classes(cfg['task'], cfg)), n_features, in_channels)


def class_weights(cfg: dict[str, Any], train: list[mldata.Sample], device) -> torch.Tensor | None:
    if cfg['task'] == 'segmentation':
        return None
    k = len(mldata.task_classes(cfg['task'], cfg))
    counts = np.bincount([s.target for s in train], minlength=k).astype(float)
    w = counts.sum() / (k * np.maximum(counts, 1))
    return torch.tensor(w / w.mean(), dtype=torch.float32, device=device)


def rng_state() -> dict[str, Any]:
    return {
        'python': random.getstate(),
        'numpy': np.random.get_state(),
        'torch': torch.get_rng_state(),
        'cuda': torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def set_rng_state(state: dict[str, Any]) -> None:
    random.setstate(state['python'])
    np.random.set_state(state['numpy'])
    torch.set_rng_state(state['torch'])
    if state.get('cuda') is not None and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state['cuda'])


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ---------- 單折 ----------
def _device(cfg: dict[str, Any]) -> torch.device:
    if cfg.get('device', 'auto') == 'auto':
        return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    return torch.device(cfg['device'])


def _seg_batch_loss(model, x, y, idx, samples, device, amp) -> torch.Tensor:
    groups = [samples[i].groups for i in idx.tolist()]
    merge = losses.merge_matrix(groups, mldata.NUM_SEG_CLASSES, device)
    singles = torch.zeros(len(groups), mldata.NUM_SEG_CLASSES, device=device)
    for b, gs in enumerate(groups):
        for g in gs:
            if len(g) == 1:
                singles[b, g[0]] = 1
    with torch.autocast(device.type, enabled=amp):
        logits = model(x)
    return losses.partial_ce(logits, y, merge) + losses.partial_dice(logits, y, singles)


def _cls_forward(model, x, feats, device, amp):
    with torch.autocast(device.type, enabled=amp):
        return model(x, feats if feats.numel() else None)


@torch.no_grad()
def evaluate(model, loader, cfg, samples, device) -> tuple[float, dict[str, Any], list[dict[str, Any]]]:
    """回傳（監控指標，越大越好；指標；逐張預測）。"""
    model.eval()
    amp = cfg['amp'] and device.type == 'cuda'
    rows: list[dict[str, Any]] = []
    if cfg['task'] == 'segmentation':
        dices: list[float] = []
        for x, y, idx in loader:
            with torch.autocast(device.type, enabled=amp):
                pred = model(x.to(device)).argmax(1).cpu()
            for b, i in enumerate(idx.tolist()):
                s = samples[i]
                row: dict[str, Any] = {'image_id': s.image_id, 'patient_id': s.patient_id, 'side': s.side}
                per = []
                for g in s.groups:
                    if len(g) == 1 and g[0] != 0:
                        d = losses.dice_per_class(pred[b], y[b], g[0])
                        if d is not None:
                            row[f'dice_{SEG_NAMES[g[0]]}'] = round(d, 4)
                            per.append(d)
                row['dice_mean'] = round(float(np.mean(per)), 4) if per else None
                if per:
                    dices.append(float(np.mean(per)))
                rows.append(row)
        score = float(np.mean(dices)) if dices else 0.0
        return score, {'dice': score, 'n': len(rows)}, rows
    logits_all, ys = [], []
    for x, y, feats, idx in loader:
        logits = _cls_forward(model, x.to(device), feats.to(device), device, amp).float().cpu()
        logits_all.append(logits)
        ys.append(y)
        for b, i in enumerate(idx.tolist()):
            s = samples[i]
            rows.append({'image_id': s.image_id, 'patient_id': s.patient_id, 'side': s.side, 'target': int(y[b]), 'logits': logits[b].tolist()})
    logits = torch.cat(logits_all)
    y = torch.cat(ys)
    probs = losses.class_probs(cfg['head'], logits).numpy()
    for r, p in zip(rows, probs):
        r['probs'] = [round(float(v), 5) for v in p]
    vloss = float(losses.classification_loss(cfg['head'], logits, y, None))
    if cfg['task'] == 'grade':
        m = metrics.ordinal_metrics(y.numpy(), probs)
        score = m['qwk'] if m['qwk'] is not None else -vloss
    else:  # eGFR：不論 2／3／5 類，早停一律看 AUC(<60)，各模型挑最佳 epoch 的標準相同
        m = metrics.egfr_metrics(y.numpy(), probs, probs.shape[1])
        score = m['auc_lt60'] if m['auc_lt60'] is not None else -vloss
    m['loss'] = vloss
    return float(score), m, rows


def train_fold(cfg: dict[str, Any], fold: str, samples: list[mldata.Sample], fold_dir: Path, ctx, progress: tuple[int, int], features) -> dict[str, Any]:
    device = _device(cfg)
    amp = bool(cfg['amp']) and device.type == 'cuda'
    train = [s for s in samples if s.group.startswith('fold-') and s.group != fold]
    val = [s for s in samples if s.group == fold]
    if not train or not val:
        return {'fold': fold, 'skipped': '這一折沒有訓練或驗證資料'}
    fold_index, n_folds = progress
    seed = int(cfg['seed']) + fold_index
    n_feat = len(next(iter(features.values()))) if features else 0
    seed_everything(seed)
    model = build_model(cfg, n_feat).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg['lr'], weight_decay=cfg['weight_decay'])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, cfg['epochs']))
    scaler = torch.amp.GradScaler(device.type, enabled=amp)
    gen = torch.Generator().manual_seed(seed)
    weights = class_weights(cfg, train, device)
    if cfg['task'] == 'segmentation':
        train_ds, val_ds = SegDataset(train, cfg, True), SegDataset(val, cfg, False)
    else:
        train_ds, val_ds = ClsDataset(train, cfg, True, features), ClsDataset(val, cfg, False, features)
    workers = int(cfg['num_workers'])
    train_loader = DataLoader(train_ds, batch_size=cfg['batch_size'], shuffle=True, generator=gen, num_workers=workers, drop_last=len(train) > cfg['batch_size'])
    val_loader = DataLoader(val_ds, batch_size=cfg['batch_size'], shuffle=False, num_workers=workers)

    state = {'epoch': 0, 'best': -float('inf'), 'best_epoch': None, 'patience_left': cfg['patience'], 'best_metrics': None}
    last = fold_dir / 'last.pth'
    if last.exists():  # 恢復：從上一個完成的 epoch 接續
        ck = torch.load(last, map_location=device, weights_only=False)
        model.load_state_dict(ck['model'])
        opt.load_state_dict(ck['optimizer'])
        sched.load_state_dict(ck['scheduler'])
        scaler.load_state_dict(ck['scaler'])
        gen.set_state(ck['generator'])
        set_rng_state(ck['rng'])
        state = ck['state']
    history = fold_dir / 'history.csv'
    accum = max(1, int(cfg['accum_steps']))
    while state['epoch'] < cfg['epochs'] and state['patience_left'] > 0:
        epoch = state['epoch']
        ctx.check_stop()
        train_ds.epoch = epoch
        model.train()
        started = time.time()
        total, count = 0.0, 0
        opt.zero_grad(set_to_none=True)
        for step, batch in enumerate(train_loader):
            if step % 10 == 0:
                ctx.check_stop()  # 停在 epoch 中間時，捨棄這個 epoch，從上一個 checkpoint 恢復
            if cfg['task'] == 'segmentation':
                x, y, idx = batch
                loss = _seg_batch_loss(model, x.to(device), y.to(device), idx, train, device, amp)
            else:
                x, y, feats, idx = batch
                logits = _cls_forward(model, x.to(device), feats.to(device), device, amp)
                loss = losses.classification_loss(cfg['head'], logits, y.to(device), weights)
            scaler.scale(loss / accum).backward()
            if (step + 1) % accum == 0 or step + 1 == len(train_loader):
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
            total += float(loss.detach()) * x.shape[0]
            count += x.shape[0]
        sched.step()
        score, m, _ = evaluate(model, val_loader, cfg, val, device)
        improved = score > state['best']
        if improved:
            state.update(best=score, best_epoch=epoch + 1, patience_left=cfg['patience'], best_metrics=m)
            torch.save({'model': model.state_dict(), 'epoch': epoch + 1, 'metrics': m}, fold_dir / 'best.pth')
        else:
            state['patience_left'] -= 1
        state['epoch'] = epoch + 1
        torch.save(
            {'model': model.state_dict(), 'optimizer': opt.state_dict(), 'scheduler': sched.state_dict(), 'scaler': scaler.state_dict(), 'generator': gen.get_state(), 'rng': rng_state(), 'state': state},
            last,
        )
        row = {'epoch': epoch + 1, 'train_loss': round(total / max(1, count), 5), 'val_score': round(score, 5), 'val_loss': round(m.get('loss', 0.0), 5) if 'loss' in m else '', 'lr': opt.param_groups[0]['lr'], 'seconds': round(time.time() - started, 1)}
        new = not history.exists()
        with history.open('a', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)
        ctx.event('epoch', {'fold': fold, **row, 'best': round(state['best'], 5), 'improved': improved})
        ctx.progress((fold_index + (epoch + 1) / cfg['epochs']) / n_folds * 100, f'{fold} 第 {epoch + 1}／{cfg["epochs"]} epoch')

    # 用最佳 epoch 的模型預測這一折（out-of-fold）
    ck = torch.load(fold_dir / 'best.pth', map_location=device, weights_only=False)
    model.load_state_dict(ck['model'])
    _, m, rows = evaluate(model, val_loader, cfg, val, device)
    for r in rows:
        r['fold'] = fold
    if cfg['task'] == 'segmentation':
        _write_seg_predictions(model, val, cfg, device, ctx.run_id if hasattr(ctx, 'run_id') else fold_dir.parent.name)
    result = {'fold': fold, 'best_epoch': state['best_epoch'], 'best_score': state['best'], 'metrics': m, 'epochs_run': state['epoch'], 'train_images': len(train), 'val_images': len(val)}
    (fold_dir / 'oof.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    (fold_dir / 'done.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


@torch.no_grad()
def _write_seg_predictions(model, samples: list[mldata.Sample], cfg, device, run_id: str) -> None:
    """out-of-fold 預測遮罩存成原尺寸 PNG：交叉擬合特徵用這些遮罩，不用人工遮罩。"""
    model.eval()
    out = seg_output_dir(run_id)
    amp = cfg['amp'] and device.type == 'cuda'
    for s in samples:
        img = mldata.load_image(s.image_id)
        boxed, box = augment.letterbox(img, cfg['img_size'])
        x = torch.from_numpy(augment.to_tensor_array(boxed, cfg['init']))[None].to(device)
        with torch.autocast(device.type, enabled=amp):
            pred = model(x).argmax(1)[0].cpu().numpy().astype(np.uint8)
        deid.write_png(out / shard(s.image_id) / f'{s.image_id}.png', augment.unletterbox(pred, box))


# ---------- 整個訓練 ----------
def train_run(run_id: str, task: str, cfg_overrides: dict[str, Any], dataset_version_id: str, split_id: str, ctx) -> dict[str, Any]:
    cfg = full_config(task, cfg_overrides)
    folder = run_dir(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'config.json').write_text(json.dumps({**cfg, 'dataset_version_id': dataset_version_id, 'split_id': split_id}, ensure_ascii=False, indent=2), encoding='utf-8')
    samples = mldata.build(task, dataset_version_id, split_id, mask_policy=cfg.get('mask_policy', 'verified'), egfr_classes=int(cfg.get('egfr_classes', 2)))
    if cfg.get('max_images'):
        samples = samples[: int(cfg['max_images'])]
    check = mldata.check_classes(task, samples, mldata.task_classes(task, cfg))
    ctx.event('data', check)
    features, feature_stats = tabular_features(cfg, samples)
    if features is not None:
        samples = [s for s in samples if s.image_id in features]
    if 'mask_channels' in (cfg.get('inputs') or []):
        from .masksets import mask_path

        before = len(samples)
        samples = [s for s in samples if mask_path(cfg['mask_set_id'], s.image_id).exists()]
        ctx.event('data', {**check, 'mask_set_id': cfg['mask_set_id'], 'without_mask': before - len(samples)})
    folds = sorted({s.group for s in samples if s.group.startswith('fold-')})
    if cfg.get('folds'):
        folds = [f for f in folds if f in set(cfg['folds'])]
    results = []
    for k, fold in enumerate(folds):
        fold_dir = folder / fold
        fold_dir.mkdir(exist_ok=True)
        done = fold_dir / 'done.json'
        if done.exists():
            results.append(json.loads(done.read_text(encoding='utf-8')))
            continue
        results.append(train_fold(cfg, fold, samples, fold_dir, ctx, (k, len(folds)), features))
    summary = summarize(run_id, cfg, results, check)
    if feature_stats:  # 推論時要用同樣的平均與標準差標準化
        summary['feature_stats'] = feature_stats
        (folder / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


from .tabular import clinical_features, load_features, tabular_features  # noqa: E402,F401  表格特徵（不需要 PyTorch，基準模型也用）


def summarize(run_id: str, cfg: dict[str, Any], results: list[dict[str, Any]], check: dict[str, Any]) -> dict[str, Any]:
    folder = run_dir(run_id)
    done = [r for r in results if 'best_score' in r]
    oof: list[dict[str, Any]] = []
    for r in done:
        oof += json.loads((folder / r['fold'] / 'oof.json').read_text(encoding='utf-8'))
    summary: dict[str, Any] = {
        'task': cfg['task'],
        'folds': results,
        'mean_best_score': float(np.mean([r['best_score'] for r in done])) if done else None,
        'std_best_score': float(np.std([r['best_score'] for r in done])) if done else None,
        'data': check,
    }
    if cfg['task'] != 'segmentation' and oof:
        logits = np.array([r['logits'] for r in oof], float)
        y = np.array([r['target'] for r in oof], int)

        def to_probs(lg: np.ndarray, t: float) -> np.ndarray:
            return losses.class_probs(cfg['head'], torch.tensor(lg), t).numpy()

        temperature = metrics.fit_temperature(logits, y, to_probs)
        calibrated = to_probs(logits, temperature)
        for r, p in zip(oof, calibrated):
            r['calibrated'] = [round(float(v), 5) for v in p]
        summary['temperature'] = temperature
        if cfg['task'] == 'grade':
            summary['oof'] = metrics.ordinal_metrics(y, calibrated)
        else:
            from ..data import egfr as E

            raw = to_probs(logits, 1.0)
            k = calibrated.shape[1]
            summary['egfr_classes'] = k
            summary['oof'] = metrics.egfr_metrics(y, calibrated, k)
            summary['oof']['ece_before_calibration'] = metrics.ece(E.y_lt(y, k, 60), E.p_lt(raw, k, 60))
    elif oof:
        values = [r['dice_mean'] for r in oof if r.get('dice_mean') is not None]
        summary['oof'] = {'dice': float(np.mean(values)) if values else None, 'n': len(values)}
        for name in SEG_NAMES[1:]:
            vals = [r[f'dice_{name}'] for r in oof if f'dice_{name}' in r]
            summary['oof'][f'dice_{name}'] = float(np.mean(vals)) if vals else None
    (folder / 'oof_predictions.json').write_text(json.dumps(oof, ensure_ascii=False), encoding='utf-8')
    (folder / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary
