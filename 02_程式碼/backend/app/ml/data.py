"""訓練資料：從凍結的資料集版本（manifest）與固定的病人層級切分建立樣本。

- 不從檔名讀任何資訊（舊程式的標籤洩漏），只用 manifest 與資料庫。
- 每個樣本記錄病人與組別（fold-k／test／prospective），交叉驗證只用 fold-*。
- 分割樣本記錄「這份遮罩確實標了哪些類別」，訓練時沒標的類別不算錯（部分標註）。
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from ..annotation.service import STRUCTURES
from ..core.errors import AppError
from ..data import deid, storage
from ..data.versions import load_manifest
from ..db.models_research import GradeLabel, ImageGrade, MaskAnnotation, SplitEntry
from ..db.session import session_scope

TASKS = {
    'segmentation': {'label': '分割（腎實質、腎竇、肝、脾）', 'classes': ['背景', '腎實質', '腎竇', '肝', '脾']},
    'egfr': {'label': 'eGFR（2／3／5 類）', 'classes': ['eGFR ≥ 60', 'eGFR < 60']},  # 預設 2 類；實際類別由設定 egfr_classes 決定（task_classes）
    'grade': {'label': '回音分級 Grade 0–3', 'classes': ['G0', 'G1', 'G2', 'G3']},
}
NUM_SEG_CLASSES = 5
SEG_INDEX = {'background': 0, **STRUCTURES}  # parenchyma 1, sinus 2, liver 3, spleen 4


@dataclass
class Sample:
    image_id: str
    patient_id: str
    side: str | None
    group: str
    target: Any = None  # 分類：整數；分割：遮罩檔路徑
    groups: list[list[int]] = field(default_factory=list)  # 分割：無法互相區分的類別群組（部分標註）
    verified: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def split_groups(split_id: str) -> dict[str, str]:
    with session_scope('research') as db:
        rows = db.query(SplitEntry.patient_id, SplitEntry.group).filter(SplitEntry.split_id == split_id).all()
    if not rows:
        raise AppError(404, 'SPLIT_NOT_FOUND', '找不到這個切分，或切分是空的。')
    return dict(rows)


def _check_protected_test(groups: dict[str, str]) -> None:
    """主切分測試集的病人不能出現在分割訓練的各折（決策 D20）：換一個切分也不能把測試病人拿去訓練。"""
    from ..annotation.circling import protected_test_patients

    leaked = sorted(p for p in protected_test_patients() if groups.get(p, '').startswith('fold-'))
    if leaked:
        raise AppError(409, 'SPLIT_CONFLICTS_PROTECTED_TEST', f'這個切分把主切分測試集的 {len(leaked)} 位病人放進訓練折；分割訓練請使用主切分，或換一個不包含這些病人的切分。')


def class_groups(flags: dict[str, Any], label: np.ndarray) -> list[list[int]]:
    """這份遮罩分得出哪些類別：回傳「無法互相區分的類別群組」。
    例如只有整顆腎、沒有肝脾：[[背景, 肝, 脾], [腎實質, 腎竇]]。訓練時用群組的機率總和計算 loss（部分標註）。"""
    names = flags.get('labeled')
    if names is None:  # 人工遮罩：腎實質、腎竇一定有標；有畫肝或脾才算肝脾已標（畫了肝就表示這側沒有脾）
        names = ['parenchyma', 'sinus']
        if (label == STRUCTURES['liver']).any() or (label == STRUCTURES['spleen']).any():
            names += ['liver', 'spleen']
    groups: list[list[int]] = []
    known: set[int] = set()
    if 'kidney' in names:
        groups.append([STRUCTURES['parenchyma'], STRUCTURES['sinus']])
        known |= {STRUCTURES['parenchyma'], STRUCTURES['sinus']}
    for name in ('parenchyma', 'sinus', 'liver', 'spleen'):
        value = STRUCTURES[name]
        if name in names and value not in known:
            groups.append([value])
            known.add(value)
    groups.insert(0, [0] + [c for c in range(1, NUM_SEG_CLASSES) if c not in known])
    return groups


def task_classes(task: str, cfg: dict[str, Any] | None = None) -> list[str]:
    """這個訓練的類別名稱。eGFR 依設定 egfr_classes（2／3／5，預設 2）；其他任務固定。"""
    if task == 'egfr':
        from ..data.egfr import classes

        return classes(int((cfg or {}).get('egfr_classes', 2)))
    return list(TASKS[task]['classes'])


CLINICAL_KEYS = ('age', 'sex', 'has_diabetes')


def build(task: str, dataset_version_id: str, split_id: str, *, mask_policy: str = 'verified', egfr_classes: int = 2) -> list[Sample]:
    """mask_policy（分割）：verified＝只用醫師上傳或人工確認過的遮罩（預設，M2.5）；any＝最新、未退回的遮罩（含草稿）。"""
    if task not in TASKS:
        raise AppError(422, 'BAD_TASK', '不支援的訓練任務。')
    manifest = load_manifest(dataset_version_id)
    groups = split_groups(split_id)
    patients = {p['id']: p for p in manifest.get('patients', [])}
    images = [i for i in manifest['images'] if i['patient_id'] in groups]
    samples: list[Sample] = []
    if task == 'segmentation':
        _check_protected_test(groups)
        if mask_policy == 'verified':
            images = [i for i in images if i.get('mask_verified')]  # 待確認的草稿不當訓練答案
        mask_ids = [i['mask_annotation_id'] for i in images if i.get('mask_annotation_id')]
        with session_scope('research') as db:
            masks = {m.id: (m.relpath, json.loads(m.flags_json), m.source) for m in db.query(MaskAnnotation).filter(MaskAnnotation.id.in_(mask_ids)).all()}
        for i in images:
            mid = i.get('mask_annotation_id')
            if mid not in masks:
                continue
            relpath, flags, source = masks[mid]
            path = storage.from_root(relpath)
            label = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
            samples.append(Sample(i['id'], i['patient_id'], i.get('side'), groups[i['patient_id']], str(path), class_groups(flags, label), bool(i.get('mask_verified'))))
    elif task == 'egfr':
        from ..data.egfr import egfr_class

        for i in images:
            p = patients.get(i['patient_id'], {})
            egfr = p.get('egfr')
            if egfr is None:
                continue
            clinical = {k: p.get(k) for k in CLINICAL_KEYS}  # 臨床資料（② ③ 使用）：同一位病人的每張影像都一樣
            samples.append(Sample(i['id'], i['patient_id'], i.get('side'), groups[i['patient_id']], egfr_class(egfr, egfr_classes),
                                  extra={'egfr': egfr, 'clinical': clinical, 'spacing': i.get('pixel_spacing_mm')}))
    elif task == 'grade' and manifest.get('image_grade_ids'):
        # 醫師圈選網站的每張分級：每張影像用自己的答案訓練（決策 D49）；「無法判斷」不進訓練
        with session_scope('research') as db:
            rows = db.query(ImageGrade.image_id, ImageGrade.grade).filter(ImageGrade.id.in_(manifest['image_grade_ids'])).all()
        per_image: dict[str, list[int]] = defaultdict(list)
        for image_id, grade in rows:
            if grade is not None:
                per_image[image_id].append(grade)
        for i in images:
            if per_image.get(i['id']):
                samples.append(Sample(i['id'], i['patient_id'], i.get('side'), groups[i['patient_id']], int(round(statistics.median(per_image[i['id']])))))
    elif task == 'grade':
        ids = manifest.get('grade_label_ids', [])
        with session_scope('research') as db:
            rows = db.query(GradeLabel.patient_id, GradeLabel.side, GradeLabel.grade, GradeLabel.is_consensus).filter(GradeLabel.id.in_(ids)).all()
        consensus: dict[tuple[str, str], int] = {}
        raters: dict[tuple[str, str], list[int]] = defaultdict(list)
        for pid, side, grade, is_consensus in rows:
            if grade is None:
                continue
            if is_consensus:
                consensus[(pid, side)] = grade
            else:
                raters[(pid, side)].append(grade)
        for i in images:
            key = (i['patient_id'], i.get('side'))
            grade = consensus.get(key)
            if grade is None and raters.get(key):
                grade = int(round(statistics.median(raters[key])))  # 沒有共識時取醫師分級的中位數
            if grade is not None:
                samples.append(Sample(i['id'], i['patient_id'], i.get('side'), groups[i['patient_id']], grade))
    return samples


def check_classes(task: str, samples: list[Sample], names: list[str] | None = None) -> dict[str, Any]:
    """每個類別都要有樣本，否則停下來說明（舊程式會靜默關閉類別權重，訓練出偏差的模型）。"""
    train = [s for s in samples if s.group.startswith('fold-')]
    if not train:
        raise AppError(409, 'NO_TRAINING_SAMPLES', '交叉驗證的各折裡沒有任何可用樣本，請確認資料集版本與切分。')
    if task == 'segmentation':
        # 只計算「單獨分得出來」的類別；沒有任何單獨標註的類別，模型學不到，回報給使用者
        counts = Counter(g[0] for s in train for g in s.groups if len(g) == 1)
        names = TASKS[task]['classes']
        missing = [names[c] for c in range(1, NUM_SEG_CLASSES) if counts[c] == 0]
        if counts[STRUCTURES['parenchyma']] == 0 and not any(len(g) == 2 and STRUCTURES['parenchyma'] in g for s in train for g in s.groups):
            raise AppError(409, 'CLASS_MISSING', '訓練資料裡沒有任何腎臟標註，無法訓練分割模型。')
        return {'samples': len(train), 'labeled_counts': {names[c]: counts[c] for c in range(1, NUM_SEG_CLASSES)}, 'missing': missing}
    counts = Counter(s.target for s in train)
    names = names or TASKS[task]['classes']
    missing = [names[c] for c in range(len(names)) if counts[c] == 0]
    if missing:
        raise AppError(409, 'CLASS_MISSING', '以下類別在訓練資料裡沒有任何樣本：' + '、'.join(missing) + '。請補標註或改用其他任務。')
    return {'samples': len(train), 'class_counts': {names[c]: counts[c] for c in range(len(names))}}


def load_image(image_id: str) -> np.ndarray:
    """模型用影像（去識別化、caliper 已修補）：uint8 灰階。"""
    return cv2.imdecode(np.fromfile(str(storage.image_path(image_id, 'model')), np.uint8), cv2.IMREAD_GRAYSCALE)


def load_calc(image_id: str) -> tuple[np.ndarray, np.ndarray]:
    gray, valid = deid.read_gray_alpha(storage.image_path(image_id, 'calc'))
    return gray, valid > 0
