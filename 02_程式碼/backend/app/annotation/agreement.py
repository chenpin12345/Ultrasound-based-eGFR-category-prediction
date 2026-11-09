"""標註一致性：醫師分級的 weighted kappa、遮罩的 Dice。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

import numpy as np

from ..core.config import get_settings
from ..core.ids import now_iso, short_uid
from ..data.deid import read_image
from ..data.storage import from_root
from ..db.models_research import AgreementReport, GradeLabel, MaskAnnotation
from ..db.session import session_scope
from .service import STRUCTURES


def weighted_kappa(a: list[int], b: list[int], k: int = 4, power: int = 2) -> float | None:
    """有序分級的加權 kappa（power=2 即 quadratic weighted kappa）。"""
    if len(a) != len(b) or len(a) < 2:
        return None
    observed = np.zeros((k, k))
    for x, y in zip(a, b):
        observed[x, y] += 1
    observed /= observed.sum()
    expected = np.outer(observed.sum(1), observed.sum(0))
    idx = np.arange(k)
    weights = np.abs(idx[:, None] - idx[None, :]) ** power / (k - 1) ** power
    denom = (weights * expected).sum()
    if denom == 0:
        return 1.0
    return float(1 - (weights * observed).sum() / denom)


def dice(a: np.ndarray, b: np.ndarray) -> float | None:
    total = int(a.sum() + b.sum())
    if total == 0:
        return None
    return float(2 * np.logical_and(a, b).sum() / total)


def grade_agreement() -> dict[str, Any]:
    with session_scope('research') as db:
        rows = db.query(GradeLabel).filter(GradeLabel.is_consensus.is_(False)).all()
    by_key: dict[tuple[str, str], dict[str, int | None]] = defaultdict(dict)
    for r in rows:
        by_key[(r.patient_id, r.side)][r.rater] = r.grade
    pair_counts = Counter()
    for raters in by_key.values():
        for pair in combinations(sorted(raters), 2):
            pair_counts[pair] += 1
    pairs = []
    for (r1, r2), _ in pair_counts.most_common():
        a, b, disagreements, unsure = [], [], [], 0
        for (pid, side), raters in by_key.items():
            if r1 in raters and r2 in raters:
                g1, g2 = raters[r1], raters[r2]
                if g1 is None or g2 is None:
                    unsure += 1
                    continue
                a.append(g1)
                b.append(g2)
                if abs(g1 - g2) >= 2:
                    disagreements.append({'patient_id': pid, 'side': side, 'grades': [g1, g2]})
        exact = float(np.mean([x == y for x, y in zip(a, b)])) if a else None
        pairs.append(
            {
                'raters': [r1, r2],
                'n': len(a),
                'unsure': unsure,
                'weighted_kappa': weighted_kappa(a, b),
                'exact_agreement': exact,
                'differ_by_2_or_more': disagreements,
            }
        )
    return {'kind': 'grade', 'pairs': pairs}


def mask_agreement() -> dict[str, Any]:
    with session_scope('research') as db:
        rows = db.query(MaskAnnotation).filter(MaskAnnotation.status != 'draft', MaskAnnotation.trashed_at.is_(None)).order_by(MaskAnnotation.version).all()
    latest: dict[str, dict[str, MaskAnnotation]] = defaultdict(dict)
    for r in rows:
        latest[r.image_id][r.annotator] = r
    per_structure: dict[str, list[float]] = defaultdict(list)
    images = 0
    for annotators in latest.values():
        if len(annotators) < 2:
            continue
        a, b = list(annotators.values())[:2]
        la = read_image(from_root(a.relpath))[:, :, 0]
        lb = read_image(from_root(b.relpath))[:, :, 0]
        images += 1
        for name, value in STRUCTURES.items():
            d = dice(la == value, lb == value)
            if d is not None:
                per_structure[name].append(d)
    return {
        'kind': 'mask',
        'images': images,
        'dice': {name: {'mean': float(np.mean(v)), 'n': len(v)} for name, v in per_structure.items()},
    }


def compute_and_save() -> dict[str, Any]:
    result = {'grade': grade_agreement(), 'mask': mask_agreement(), 'created_at': now_iso()}
    report_id = f'AGR-{short_uid()}'
    folder = get_settings().path('annotations') / '一致性報告'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{report_id}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with session_scope('research') as db:
        db.add(AgreementReport(id=report_id, kind='all', raters_json='[]', metrics_json=json.dumps(result, ensure_ascii=False), created_at=result['created_at']))
    return {'id': report_id, **result}


def latest_report() -> dict[str, Any] | None:
    with session_scope('research') as db:
        row = db.query(AgreementReport).order_by(AgreementReport.created_at.desc()).first()
        return {'id': row.id, **json.loads(row.metrics_json)} if row else None
