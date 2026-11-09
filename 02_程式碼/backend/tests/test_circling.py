"""M2.5 階段 B：醫師圈選（建立批次、匯出、比對差異法轉遮罩、檢查、匯入）與一併修正的項目。只用合成影像。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tests.conftest import wait_job

COLORS = [{'color': '#ff0000', 'structure': 'kidney'}, {'color': '#00ff00', 'structure': 'sinus'}, {'color': '#0000ff', 'structure': 'liver'}]


def _setup(client) -> dict[str, list[str]]:
    """8 張合成影像分給 4 位病人（每人左右各 1 張）；P-0001 在測試集，其餘在各折；設為主切分。"""
    from app.db.models_research import Image, Patient, Split, SplitEntry
    from app.db.session import session_scope

    groups = {'P-0001': 'test', 'P-0002': 'fold-1', 'P-0003': 'fold-2', 'P-0004': 'fold-1'}
    with session_scope('research') as db:
        for n, pid in enumerate(groups):
            db.add(Patient(id=pid, source_ref=pid, sex='F', age=60 + n, has_diabetes=False, egfr=[20, 45, 75, 95][n], created_at='2026-10-29'))
        db.add(Split(id='split-0001', method='stratified', seed=42, folds=2, test_ratio=0.25, stratify_by='egfr_group', sha256='x', created_at='2026-10-29'))
    with session_scope('research') as db:
        for pid, group in groups.items():
            db.add(SplitEntry(split_id='split-0001', patient_id=pid, group=group))
        images = db.query(Image).order_by(Image.id).all()
        by_patient: dict[str, list[str]] = {}
        for n, img in enumerate(images):
            pid = list(groups)[n // 2]
            img.patient_id, img.side, img.status, img.view = pid, 'right' if n % 2 == 0 else 'left', 'usable', 'long'
            by_patient.setdefault(pid, []).append(img.id)
    assert client.put('/api/settings', json={'primary_split_id': 'split-0001'}).status_code == 200
    return by_patient


def _model_bgr(image_id: str) -> np.ndarray:
    from app.data import storage

    gray = cv2.imdecode(np.fromfile(str(storage.image_path(image_id, 'model')), np.uint8), cv2.IMREAD_GRAYSCALE)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _draw(image_id: str, closed: bool = True) -> tuple[np.ndarray, tuple[int, int], tuple[int, int]]:
    img = _model_bgr(image_id)
    h, w = img.shape[:2]
    c = (w // 2, int(h * 0.55))
    axes = (int(w * 0.16), int(h * 0.09))
    thick = max(2, w // 300)
    if closed:
        cv2.ellipse(img, c, axes, 0, 0, 360, (0, 0, 255), thick)  # 紅：腎臟外框
    else:
        cv2.ellipse(img, c, axes, 0, 200, 340, (0, 0, 255), thick)  # 沒有封閉的弧線
    cv2.ellipse(img, c, (axes[0] // 3, axes[1] // 3), 0, 0, 360, (0, 255, 0), thick)  # 綠：腎竇
    liver = (c[0], c[1] - int(axes[1] * 1.9))
    cv2.ellipse(img, liver, (axes[0], axes[1] // 2), 0, 0, 360, (255, 0, 0), thick)  # 藍：肝
    return img, c, axes


def _write(folder: Path, name: str, img: np.ndarray) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(Path(name).suffix, img)
    buf.tofile(str(folder / name))


def test_batches_select_test_sides_and_stratified_train(imported_client):
    ids = _setup(imported_client)
    test = imported_client.post('/api/circling/batches', json={'kind': 'test'}).json()
    assert test['count'] == 2  # 測試病人左右各 1 張
    detail = imported_client.get(f"/api/circling/batches/{test['id']}").json()
    assert {i['image_id'] for i in detail['items']} == set(ids['P-0001'])
    assert imported_client.post('/api/circling/batches', json={'kind': 'test'}).status_code == 409  # 每側已在批次中
    train = imported_client.post('/api/circling/batches', json={'kind': 'train', 'size': 10}).json()
    items = imported_client.get(f"/api/circling/batches/{train['id']}").json()['items']
    assert len(items) == 6 and not ({i['image_id'] for i in items} & set(ids['P-0001']))  # 不含測試病人
    assert imported_client.post('/api/circling/batches', json={'kind': 'train', 'size': 10}).status_code == 409


def test_export_deidentified_and_original_needs_confirm(imported_client, workspace):
    _setup(imported_client)
    batch = imported_client.post('/api/circling/batches', json={'kind': 'test'}).json()['id']
    job = imported_client.post(f'/api/circling/batches/{batch}/export', json={}).json()['job_id']
    wait_job(job)
    result = imported_client.get(f'/api/jobs/{job}').json()
    assert result['status'] == 'completed', result
    folder = workspace / result['result']['folder']
    pngs = sorted(p.name for p in (folder / '影像').glob('*.png'))
    assert len(pngs) == 2 and all(p.startswith('IMG-') for p in pngs)
    assert (workspace / result['result']['zip']).exists() and (folder / '圈選說明.txt').exists()
    rows = list(csv.reader((folder / '清單.csv').open(encoding='utf-8-sig')))
    assert rows[0][1] == '影像ID' and {r[1] for r in rows[1:]} == {p[:-4] for p in pngs}
    assert all(i['status'] == 'exported' for i in imported_client.get(f'/api/circling/batches/{batch}').json()['items'])
    # 原始影像：沒有輸入確認文字時拒絕；有的話存到受限區，檔名改成影像 ID
    assert imported_client.post(f'/api/circling/batches/{batch}/export', json={'include_original': True}).status_code == 422
    from app.annotation.circling import ORIGINAL_CONFIRM

    job = imported_client.post(f'/api/circling/batches/{batch}/export', json={'include_original': True, 'confirm': ORIGINAL_CONFIRM}).json()['job_id']
    wait_job(job)
    r = imported_client.get(f'/api/jobs/{job}').json()['result']
    raw = workspace / r['original_folder']
    assert raw.is_relative_to(workspace / '03_資料' / '01_原始封存')
    assert sorted(p.stem for p in raw.glob('IMG-*')) == [p[:-4] for p in pngs]
    log = imported_client.get('/api/audit').json()['entries']
    assert any('含原始影像' in e['action'] for e in log)


def test_color_drawing_parsed_reviewed_and_imported(imported_client, workspace):
    ids = _setup(imported_client)
    batch = imported_client.post('/api/circling/batches', json={'kind': 'test'}).json()['id']
    wait_job(imported_client.post(f'/api/circling/batches/{batch}/export', json={}).json()['job_id'])
    right, left = ids['P-0001']
    returned = workspace / 'returned'
    img, center, axes = _draw(right)
    _write(returned, f'{right}.png', img)
    small = cv2.resize(_draw(left)[0], None, fx=0.5, fy=0.5)
    _write(returned, f'{left}.png', small)  # 被縮放過：尺寸不符
    _write(returned, 'note.png', img)  # 對不到影像 ID
    # 還沒設定顏色對照：彩色圈選不能轉換
    wait_job(imported_client.post(f'/api/circling/batches/{batch}/upload', json={'folder': str(returned)}).json()['job_id'])
    item = next(i for i in imported_client.get(f'/api/circling/batches/{batch}').json()['items'] if i['image_id'] == right)
    assert any('顏色對照' in e for e in item['parse']['errors'])
    assert imported_client.put('/api/settings', json={'circling_colors': COLORS}).status_code == 200
    job = imported_client.post(f'/api/circling/batches/{batch}/upload', json={'folder': str(returned), 'circler': '醫師A'}).json()['job_id']
    wait_job(job)
    summary = imported_client.get(f'/api/jobs/{job}').json()['result']
    assert summary['parsed'] == 1 and summary['errors'] == 1 and summary['not_in_batch_count'] == 1
    items = {i['image_id']: i for i in imported_client.get(f'/api/circling/batches/{batch}').json()['items']}
    ok, bad = items[right], items[left]
    assert ok['status'] == 'parsed' and ok['parse']['reference'] == 'deid' and ok['circler'] == '醫師A'
    assert ok['parse']['areas']['parenchyma'] > 0 and ok['parse']['areas']['sinus'] > 0 and ok['parse']['areas']['liver'] > 0
    assert ok['structures'] == {'kidney': 'drawn', 'sinus': 'drawn', 'liver': 'drawn', 'spleen': 'absent'}  # 右腎：脾自動「不在影像中」
    assert any('尺寸' in e for e in bad['parse']['errors'])
    png = imported_client.get(f"/api/circling/items/{ok['id']}/overlay")
    assert png.status_code == 200 and png.content[:4] == b'\x89PNG'
    result = imported_client.post(f'/api/circling/batches/{batch}/import', json={}).json()
    assert result['imported'] == 1
    from app.annotation.drafts import mask_label
    from app.data.versions import mask_verified
    from app.db.models_research import MaskAnnotation
    from app.db.session import session_scope

    with session_scope('research') as db:
        m = db.get(MaskAnnotation, result['mask_ids'][0])
        assert m.source == 'physician_upload' and m.status == 'done' and mask_verified(m)
        flags = json.loads(m.flags_json)
        assert flags['labeled'] == ['parenchyma', 'sinus', 'liver', 'spleen'] and flags['circler'] == '醫師A'
        label = mask_label(m)
        assert 'physician_upload' in m.relpath
    assert label[center[1], center[0]] == 2  # 腎竇蓋在腎實質上
    assert label[center[1], center[0] + int(axes[0] * 0.7)] == 1  # 腎外框內、腎竇外＝腎實質
    assert label[center[1] - int(axes[1] * 1.9), center[0]] == 3
    assert imported_client.get(f'/api/circling/batches/{batch}').json()['counts']['imported'] == 1


def test_unclosed_outline_and_label_png(imported_client, workspace):
    ids = _setup(imported_client)
    batch = imported_client.post('/api/circling/batches', json={'kind': 'test'}).json()['id']
    imported_client.put('/api/settings', json={'circling_colors': COLORS})
    right, left = ids['P-0001']
    returned = workspace / 'returned2'
    _write(returned, f'{right}.png', _draw(right, closed=False)[0])
    h, w = _model_bgr(left).shape[:2]
    label = np.zeros((h, w), np.uint8)
    cv2.ellipse(label, (w // 2, h // 2), (w // 6, h // 10), 0, 0, 360, 1, -1)
    cv2.ellipse(label, (w // 2, h // 2), (w // 18, h // 30), 0, 0, 360, 2, -1)
    _write(returned, f'{left}_done.png', label)  # 檔名有其他文字也能對應；標籤 PNG 不需要顏色對照
    wait_job(imported_client.post(f'/api/circling/batches/{batch}/upload', json={'folder': str(returned)}).json()['job_id'])
    items = {i['image_id']: i for i in imported_client.get(f'/api/circling/batches/{batch}').json()['items']}
    assert any('沒有封閉' in w for w in items[right]['parse']['warnings'])
    assert items[right]['structures']['kidney'] == 'unlabeled'
    assert items[left]['return_kind'] == 'label' and items[left]['status'] == 'parsed'
    assert items[left]['structures'] == {'kidney': 'drawn', 'sinus': 'drawn', 'liver': 'absent', 'spleen': 'unlabeled'}
    r = imported_client.patch(f"/api/circling/items/{items[left]['id']}", json={'structures': {'spleen': 'absent'}})
    assert r.status_code == 200 and r.json()['structures']['spleen'] == 'absent'
    assert imported_client.patch(f"/api/circling/items/{items[left]['id']}", json={'structures': {'kidney': 'absent'}}).status_code == 422
    rej = imported_client.post(f"/api/circling/items/{items[right]['id']}/reject", json={'reason': '腎臟外框沒有封閉'}).json()
    assert rej['status'] == 'needs_redraw'


def test_detect_colors_reports_only_colors(imported_client, workspace):
    ids = _setup(imported_client)
    right = ids['P-0001'][0]
    _write(workspace / 'probe', f'{right}.png', _draw(right)[0])
    found = imported_client.post('/api/circling/colors/detect', json={'path': str(workspace / 'probe' / f'{right}.png')}).json()
    assert found['compared'] is True
    hexes = {c['color'] for c in found['colors']}
    assert any(h.startswith('#f') and h.endswith('0000') or h in ('#ff0000', '#fe0000') for h in hexes)
    assert set(found) == {'colors', 'compared'}


def test_bad_color_settings_rejected(client):
    assert client.put('/api/settings', json={'circling_colors': [{'color': 'red', 'structure': 'kidney'}]}).status_code == 422
    assert client.put('/api/settings', json={'circling_colors': [{'color': '#ff0000', 'structure': 'kidney'}, {'color': '#FF0000', 'structure': 'sinus'}]}).status_code == 422
    assert client.put('/api/settings', json={'circling_color_tolerance': 500}).status_code == 422


def test_labeled_from_structures():
    from app.annotation.circling import labeled_from_structures
    from app.ml.data import class_groups

    assert labeled_from_structures({'kidney': 'drawn', 'sinus': 'unlabeled', 'liver': 'drawn', 'spleen': 'absent'}) == ['kidney', 'liver', 'spleen']
    groups = class_groups({'labeled': ['kidney', 'liver', 'spleen']}, np.zeros((2, 2), np.uint8))
    assert [1, 2] in groups and [3] in groups and [4] in groups and groups[0] == [0]


def test_rasterize_fixed_order_and_editor_keeps_structures(imported_client):
    from app.annotation.service import rasterize

    sinus = {'structure': 'sinus', 'kind': 'polygon', 'points': [[40, 40], [60, 40], [60, 60], [40, 60]]}
    kidney = {'structure': 'parenchyma', 'kind': 'polygon', 'points': [[10, 10], [90, 10], [90, 90], [10, 90]]}
    label = rasterize([sinus, kidney], 100, 100)  # 先畫腎竇、後畫腎外框
    assert label[50, 50] == 2 and label[20, 20] == 1


def test_drafts_skip_protected_test_and_split_guard(imported_client):
    ids = _setup(imported_client)
    from app.annotation.drafts import save_draft
    from app.core.errors import AppError
    from app.db.models_research import Split, SplitEntry
    from app.db.session import session_scope
    from app.ml.data import _check_protected_test

    label = np.zeros((50, 50), np.uint8)
    assert save_draft(ids['P-0001'][0], label, 'rule', {})['skipped'] == 'protected_test'
    with session_scope('research') as db:
        db.add(Split(id='split-0002', method='stratified', seed=1, folds=2, test_ratio=0.25, stratify_by='egfr_group', sha256='y', created_at='2026-10-29'))
    with session_scope('research') as db:
        db.add(SplitEntry(split_id='split-0002', patient_id='P-0001', group='fold-1'))
    from app.ml.data import split_groups

    with pytest.raises(AppError) as err:
        _check_protected_test(split_groups('split-0002'))
    assert err.value.code == 'SPLIT_CONFLICTS_PROTECTED_TEST'
    _check_protected_test(split_groups('split-0001'))  # 主切分本身沒問題
