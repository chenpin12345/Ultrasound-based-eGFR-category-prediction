from __future__ import annotations

import hashlib
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePath
from typing import Iterable


CLASS_NAMES = (
    "eGFR -15",
    "eGFR 15-29",
    "eGFR 30-59",
    "eGFR 60-89",
    "eGFR 90-",
)
CLASS_TO_INDEX = {name: index for index, name in enumerate(CLASS_NAMES)}


def class_for_egfr(value: float) -> tuple[int, str]:
    if value < 15:
        index = 0
    elif value < 30:
        index = 1
    elif value < 60:
        index = 2
    elif value < 90:
        index = 3
    else:
        index = 4
    return index, CLASS_NAMES[index]


def parse_egfr(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def detect_label(path: str, metadata: dict[str, object] | None = None) -> tuple[int | None, str | None, float | None]:
    parts = PurePath(path.replace("\\", "/")).parts
    for part in parts[:-1]:
        if part in CLASS_TO_INDEX:
            return CLASS_TO_INDEX[part], part, None

    metadata = metadata or {}
    for key in ("eGFR", "egfr", "matched_eGFR", "matched_egfr"):
        egfr = parse_egfr(metadata.get(key))
        if egfr is not None:
            index, name = class_for_egfr(egfr)
            return index, name, egfr

    basename = parts[-1] if parts else path
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)_", basename)
    egfr = parse_egfr(match.group(1)) if match else None
    if egfr is not None:
        index, name = class_for_egfr(egfr)
        return index, name, egfr
    return None, None, None


@dataclass(frozen=True)
class SplitAssignment:
    sample_id: str
    split: str
    fold: int | None


def _stable_seed(seed: int, label: int | None) -> int:
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def deterministic_stratified_split(
    samples: Iterable[tuple[str, int | None] | tuple[str, int | None, str]],
    *,
    train_ratio: float = 0.7,
    val_ratio: float = 0.2,
    test_ratio: float = 0.1,
    seed: int = 42,
    k_folds: int = 5,
) -> list[SplitAssignment]:
    ratios = (train_ratio, val_ratio, test_ratio)
    if any(r < 0 for r in ratios) or abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError("train/validation/test 比例總和必須為 1。")
    if k_folds < 0 or k_folds == 1:
        raise ValueError("K-fold 必須為 0 或至少 2。")

    # A group is indivisible. Importers pass SHA-256 here, preventing identical
    # images from leaking across train/validation/test or K-fold boundaries.
    grouped_samples: dict[str, list[tuple[str, int | None]]] = defaultdict(list)
    for sample in samples:
        sample_id, label = sample[0], sample[1]
        group_id = sample[2] if len(sample) == 3 else sample_id
        grouped_samples[str(group_id)].append((sample_id, label))

    grouped: dict[int | None, list[tuple[str, list[str]]]] = defaultdict(list)
    for group_id, members in grouped_samples.items():
        label_counts: dict[int | None, int] = defaultdict(int)
        for _sample_id, label in members:
            label_counts[label] += 1
        group_label = sorted(label_counts, key=lambda value: (-label_counts[value], -1 if value is None else value))[0]
        grouped[group_label].append((group_id, sorted(sample_id for sample_id, _label in members)))

    assignments: list[SplitAssignment] = []
    for label in sorted(grouped, key=lambda value: (-1 if value is None else value)):
        groups = sorted(grouped[label], key=lambda item: item[0])
        random.Random(_stable_seed(seed, label)).shuffle(groups)
        total_samples = sum(len(ids) for _group_id, ids in groups)
        targets = [total_samples * ratio for ratio in ratios]
        assigned = [0, 0, 0]
        for position, (_group_id, ids) in enumerate(groups):
            split_index = max(range(3), key=lambda index: (targets[index] - assigned[index], ratios[index], -index))
            assigned[split_index] += len(ids)
            split = ("train", "validation", "test")[split_index]
            fold = position % k_folds if k_folds >= 2 else None
            assignments.extend(SplitAssignment(sample_id, split, fold) for sample_id in ids)
    return sorted(assignments, key=lambda item: item.sample_id)
