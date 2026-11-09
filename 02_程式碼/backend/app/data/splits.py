"""病人層級切分。

- 每位病人只會在一組：固定測試集（test）、開發集各折（fold-1…k），或前瞻驗證集（prospective）。
- 依 eGFR 分組分層，讓各組的病人組成接近。
- 增量分配：以既有切分為基礎產生新版本，舊病人的組別完全不變，只分配新病人。
  （改進：腎超新的切分在新增資料時會整個重排，持續收案後舊實驗就無法比較。）
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from typing import Any

import cv2
import numpy as np

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_sequential, now_iso
from ..db.models_research import Image, Patient, Split, SplitEntry
from ..db.session import session_scope
from . import storage
from .patients import egfr_group


def _eligible(db) -> dict[str, dict[str, Any]]:
    """有可用影像且已對到病人的病人。"""
    patients = {p.id: p for p in db.query(Patient).all()}
    out: dict[str, dict[str, Any]] = {}
    for pid, machine in db.query(Image.patient_id, Image.machine).filter(Image.patient_id.isnot(None), Image.status == 'usable').all():
        info = out.setdefault(pid, {'images': 0, 'toshiba': 0, 'stratum': egfr_group(patients[pid].egfr) if pid in patients else '未知'})
        info['images'] += 1
        info['toshiba'] += int(machine == 'Toshiba')
    return out


def _seeded(seed: int, label: str) -> random.Random:
    return random.Random(int(hashlib.sha256(f'{seed}:{label}'.encode()).hexdigest()[:16], 16))


def assign(patients: dict[str, dict[str, Any]], *, seed: int, folds: int, test_ratio: float) -> dict[str, str]:
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for pid, info in patients.items():
        by_stratum[info['stratum']].append(pid)
    # 每層的測試集人數用「最大餘數法」分配，讓總數等於 round(全部病人 × 比例)；
    # 每層各自四捨五入會讓總數偏離（例如 5 層各 12 人、20% → 每層 2 人，總共 10 而不是 12）。
    total = sum(len(v) for v in by_stratum.values())
    target = int(round(total * test_ratio))
    exact = {s: len(v) * test_ratio for s, v in by_stratum.items()}
    quota = {s: int(exact[s]) for s in by_stratum}
    for s in sorted(by_stratum, key=lambda s: (-(exact[s] - quota[s]), s))[: max(0, target - sum(quota.values()))]:
        quota[s] += 1
    groups: dict[str, str] = {}
    for offset, stratum in enumerate(sorted(by_stratum)):
        members = sorted(by_stratum[stratum])
        _seeded(seed, stratum).shuffle(members)
        n_test = quota[stratum]
        for pid in members[:n_test]:
            groups[pid] = 'test'
        for i, pid in enumerate(members[n_test:]):
            groups[pid] = f'fold-{(i + offset) % folds + 1}'
    return groups


def _summary(groups: dict[str, str], patients: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    order = sorted(set(groups.values()), key=lambda g: (g != 'test', g != 'prospective', g))
    out = []
    for group in order:
        members = [p for p, g in groups.items() if g == group]
        images = sum(patients[p]['images'] for p in members if p in patients)
        toshiba = sum(patients[p]['toshiba'] for p in members if p in patients)
        strata = Counter(patients[p]['stratum'] for p in members if p in patients)
        out.append({'group': group, 'patients': len(members), 'images': images, 'toshiba_ratio': round(toshiba / images, 3) if images else None, 'strata': dict(strata)})
    return out


def _sha(groups: dict[str, str]) -> str:
    payload = json.dumps(sorted(groups.items()), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def preview(seed: int, folds: int, test_ratio: float) -> dict[str, Any]:
    with session_scope('research') as db:
        patients = _eligible(db)
    if not patients:
        raise AppError(409, 'NO_PATIENTS', '還沒有可切分的病人：請先匯入影像並完成病人對照。')
    groups = assign(patients, seed=seed, folds=folds, test_ratio=test_ratio)
    return {'groups': _summary(groups, patients), 'patients': len(patients)}


def _write(split: Split, groups: dict[str, str]) -> None:
    path = get_settings().path('splits') / f'{split.id}.json'
    path.write_text(
        json.dumps(
            {
                'id': split.id,
                'parent_id': split.parent_id,
                'method': split.method,
                'seed': split.seed,
                'folds': split.folds,
                'test_ratio': split.test_ratio,
                'sha256': split.sha256,
                'created_at': split.created_at,
                'assignments': dict(sorted(groups.items())),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )


def create(seed: int, folds: int, test_ratio: float, note: str, operator: str) -> dict[str, Any]:
    if not 2 <= folds <= 10:
        raise AppError(422, 'BAD_FOLDS', '折數必須在 2 到 10 之間。')
    if not 0.05 <= test_ratio <= 0.4:
        raise AppError(422, 'BAD_TEST_RATIO', '測試集比例必須在 5% 到 40% 之間。')
    with session_scope('research') as db:
        patients = _eligible(db)
        if not patients:
            raise AppError(409, 'NO_PATIENTS', '還沒有可切分的病人：請先匯入影像並完成病人對照。')
        groups = assign(patients, seed=seed, folds=folds, test_ratio=test_ratio)
        split = Split(
            id=next_sequential('split-', [r[0] for r in db.query(Split.id).all()]),
            method='病人層級分層 K-fold＋固定測試集',
            seed=seed,
            folds=folds,
            test_ratio=test_ratio,
            stratify_by='egfr_group',
            sha256=_sha(groups),
            note=note,
            created_by=operator,
            created_at=now_iso(),
        )
        db.add(split)
        db.flush()
        db.add_all(SplitEntry(split_id=split.id, patient_id=p, group=g) for p, g in groups.items())
        _write(split, groups)
        return {'id': split.id, 'groups': _summary(groups, patients)}


def extend(parent_id: str, mode: str, note: str, operator: str) -> dict[str, Any]:
    """增量分配：舊病人不動；新病人分到各折（mode=folds）或全部放進前瞻驗證集（mode=prospective）。"""
    if mode not in {'folds', 'prospective'}:
        raise AppError(422, 'BAD_MODE', '分配方式只能是 folds 或 prospective。')
    with session_scope('research') as db:
        parent = db.get(Split, parent_id)
        if parent is None or parent.trashed_at:
            raise AppError(404, 'SPLIT_NOT_FOUND', '找不到這個切分。')
        old = {e.patient_id: e.group for e in db.query(SplitEntry).filter(SplitEntry.split_id == parent_id).all()}
        patients = _eligible(db)
        new = sorted(p for p in patients if p not in old)
        if not new:
            raise AppError(409, 'NO_NEW_PATIENTS', '沒有新的病人需要分配。')
        groups = dict(old)
        if mode == 'prospective':
            for p in new:
                groups[p] = 'prospective'
        else:
            fold_names = [f'fold-{i + 1}' for i in range(parent.folds)]
            per_stratum: dict[str, Counter] = defaultdict(Counter)
            for p, g in old.items():
                if g in fold_names and p in patients:
                    per_stratum[patients[p]['stratum']][g] += 1
            for p in new:
                counts = per_stratum[patients[p]['stratum']]
                target = min(fold_names, key=lambda f: (counts[f], f))
                groups[p] = target
                counts[target] += 1
        split = Split(
            id=next_sequential('split-', [r[0] for r in db.query(Split.id).all()]),
            parent_id=parent_id,
            method=f'增量分配（{"前瞻驗證集" if mode == "prospective" else "分到各折"}）',
            seed=parent.seed,
            folds=parent.folds,
            test_ratio=parent.test_ratio,
            stratify_by=parent.stratify_by,
            sha256=_sha(groups),
            note=note,
            created_by=operator,
            created_at=now_iso(),
        )
        db.add(split)
        db.flush()
        db.add_all(SplitEntry(split_id=split.id, patient_id=p, group=g) for p, g in groups.items())
        _write(split, groups)
        return {'id': split.id, 'new_patients': len(new), 'groups': _summary(groups, patients)}


def list_splits() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        out = []
        for s in db.query(Split).filter(Split.trashed_at.is_(None)).order_by(Split.id.desc()).all():
            counts = Counter(g for (g,) in db.query(SplitEntry.group).filter(SplitEntry.split_id == s.id).all())
            out.append(
                {
                    'id': s.id,
                    'parent_id': s.parent_id,
                    'method': s.method,
                    'seed': s.seed,
                    'folds': s.folds,
                    'test_ratio': s.test_ratio,
                    'sha256': s.sha256,
                    'note': s.note,
                    'created_by': s.created_by,
                    'created_at': s.created_at,
                    'counts': dict(counts),
                }
            )
        return out


def detail(split_id: str) -> dict[str, Any]:
    with session_scope('research') as db:
        s = db.get(Split, split_id)
        if s is None or s.trashed_at:
            raise AppError(404, 'SPLIT_NOT_FOUND', '找不到這個切分。')
        groups = {e.patient_id: e.group for e in db.query(SplitEntry).filter(SplitEntry.split_id == split_id).all()}
        patients = _eligible(db)
    return {'id': split_id, 'sha256': s.sha256, 'groups': _summary(groups, patients)}


def _content_vector(image_id: str) -> np.ndarray | None:
    """超音波內容的特徵：縮圖中央區域（避開標頭、刻度、示意圖等版面），縮成 48×48 後標準化。"""
    path = storage.image_path(image_id, 'thumb')
    if not path.exists():
        return None
    gray = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return None
    h, w = gray.shape
    center = gray[int(0.2 * h):int(0.85 * h), int(0.2 * w):int(0.8 * w)]
    v = cv2.resize(center, (48, 48), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    v -= v.mean()
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 1e-6 else None


def leakage(split_id: str, min_similarity: float = 0.95) -> dict[str, Any]:
    """洩漏檢查：
    1. 同一位病人只出現在一組（資料表結構保證，這裡再驗證一次）。
    2. 近似重複影像（超音波內容的相關係數 ≥ min_similarity）是否分屬不同組。
       只比較超音波內容：整張畫面的感知雜湊會被版面（黑底、標頭、扇形）主導，
       真實資料中 651 對不同病人的影像距離 ≤ 6，多數是誤報；內容相關係數在不同病人間最高 0.92。
    3. 有可用影像但沒有分組的病人（訓練時會被排除）。
    """
    with session_scope('research') as db:
        entries = db.query(SplitEntry.patient_id, SplitEntry.group).filter(SplitEntry.split_id == split_id).all()
        if not entries:
            raise AppError(404, 'SPLIT_NOT_FOUND', '找不到這個切分。')
        group_of: dict[str, str] = {}
        duplicates = 0
        for pid, g in entries:
            if pid in group_of:
                duplicates += 1
            group_of[pid] = g
        images = db.query(Image.id, Image.patient_id).filter(Image.status == 'usable', Image.patient_id.isnot(None)).all()
    unassigned = sorted({pid for _, pid in images if pid not in group_of})
    vectors = [(i, p, v) for i, p in images if p in group_of and (v := _content_vector(i)) is not None]
    cross: list[dict[str, Any]] = []
    if len(vectors) > 1:
        sim = np.stack([v for *_, v in vectors]) @ np.stack([v for *_, v in vectors]).T
        groups = np.array([group_of[p] for _, p, _ in vectors])
        for a, b in zip(*np.nonzero(np.triu(sim >= min_similarity, 1) & (groups[:, None] != groups[None, :]))):
            cross.append({'image_a': vectors[a][0], 'image_b': vectors[b][0], 'similarity': round(float(sim[a, b]), 3), 'groups': [groups[a], groups[b]]})
    return {
        'split_id': split_id,
        'patient_in_multiple_groups': duplicates,
        'near_duplicates_across_groups': cross[:200],
        'near_duplicates_count': len(cross),
        'unassigned_patients': unassigned,
        'passed': duplicates == 0 and not cross,
    }
