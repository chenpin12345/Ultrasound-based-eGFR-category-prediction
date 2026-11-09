"""醫師圈選網站接回主系統：全部影像批次、圈選結果.json、每張回音分級。只用合成影像。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from tests.conftest import wait_job
from tests.test_circling import _model_bgr, _setup, _write


def _site_result(folder: Path, entries: list[dict]) -> None:
    (folder / '圈選結果.json').write_text(json.dumps({'schema': 'kidney-circling-result', 'version': 1, 'images': entries}, ensure_ascii=False), encoding='utf-8')


def _site_entry(image_id: str, **extra) -> dict:
    return {'image_id': image_id, 'status': 'done', 'side': 'right', 'label_file': f'標籤/{image_id}.png', 'states': {'kidney': 'drawn', 'sinus': 'drawn', 'liver': 'unlabeled', 'spleen': 'absent', 'cyst': 'drawn'},
            'shapes': [], 'grade': 2, 'grade_unsure': False, 'grade_reason': '', 'note': '備註', 'discuss': True, 'circler': 'A', 'seconds': 90, **extra}


def _label_for(image_id: str) -> np.ndarray:
    h, w = _model_bgr(image_id).shape[:2]
    label = np.zeros((h, w), np.uint8)
    cv2.ellipse(label, (w // 2, h // 2), (w // 6, h // 10), 0, 0, 360, 1, -1)
    cv2.ellipse(label, (w // 2, h // 2), (w // 18, h // 30), 0, 0, 360, 2, -1)
    return label


def test_all_batch_covers_every_image_and_puts_test_first(imported_client):
    from app.db.models_research import Image
    from app.db.session import session_scope

    ids = _setup(imported_client)
    excluded = ids['P-0003'][0]
    with session_scope('research') as db:
        db.get(Image, excluded).status = 'excluded'
    batch = imported_client.post('/api/circling/batches', json={'kind': 'all'}).json()
    detail = imported_client.get(f"/api/circling/batches/{batch['id']}").json()
    order = [i['image_id'] for i in detail['items']]
    assert batch['count'] == 7 and excluded not in order
    assert set(order[:2]) == set(ids['P-0001'])  # 測試集在最前面


def test_site_result_sets_states_grades_and_keeps_extras(imported_client, workspace, tmp_path):
    from app.core.config import get_settings
    from app.db.models_research import ImageGrade, MaskAnnotation
    from app.db.session import session_scope

    ids = _setup(imported_client)
    batch = imported_client.post('/api/circling/batches', json={'kind': 'test'}).json()
    right, left = ids['P-0001']
    root = tmp_path / '2026-11-06_圈選結果'
    _write(root / '標籤', f'{right}.png', _label_for(right))
    _write(root / '標籤', f'{left}.png', _label_for(left))
    left_states = {'kidney': 'drawn', 'sinus': 'drawn', 'liver': 'absent', 'spleen': 'absent'}
    _site_result(root, [_site_entry(right), _site_entry(left, grade=None, grade_unsure=True, grade_reason='看不到脾', circler='B', side='left', states=left_states)])
    response = imported_client.post(f"/api/circling/batches/{batch['id']}/upload", json={'folder': str(root), 'circler': ''})
    job = response.json()['job_id']
    wait_job(job)
    assert imported_client.get(f'/api/jobs/{job}').json()['status'] == 'completed'
    detail = imported_client.get(f"/api/circling/batches/{batch['id']}").json()
    items = {i['image_id']: i for i in detail['items']}
    assert items[right]['structures'] == {'kidney': 'drawn', 'sinus': 'drawn', 'liver': 'unlabeled', 'spleen': 'absent'}
    assert items[left]['structures']['spleen'] == 'absent' and items[left]['circler'] == 'B'
    assert imported_client.post(f"/api/circling/batches/{batch['id']}/import", json={}).status_code == 200
    with session_scope('research') as db:
        grades = {g.image_id: (g.grade, g.rater, g.unsure_reason) for g in db.query(ImageGrade).all()}
        flags = json.loads(db.query(MaskAnnotation).filter(MaskAnnotation.image_id == right).one().flags_json)
    assert grades == {right: (2, 'A', None), left: (None, 'B', '看不到脾')}
    assert flags['site']['note'] == '備註' and flags['labeled'] == ['parenchyma', 'sinus', 'spleen']
    assert (get_settings().path('annotations') / '醫師圈選回傳' / batch['id'] / '圈選結果.json').is_file()


def test_bad_site_result_stops_upload(imported_client, workspace, tmp_path):
    ids = _setup(imported_client)
    batch = imported_client.post('/api/circling/batches', json={'kind': 'test'}).json()
    root = tmp_path / 'bad'
    _write(root / '標籤', f"{ids['P-0001'][0]}.png", _label_for(ids['P-0001'][0]))
    (root / '圈選結果.json').write_text('{"schema": "other"}', encoding='utf-8')
    response = imported_client.post(f"/api/circling/batches/{batch['id']}/upload", json={'folder': str(root), 'circler': ''})
    job = response.json()['job_id']
    wait_job(job)
    assert imported_client.get(f'/api/jobs/{job}').json()['status'] == 'failed'


def test_grade_training_uses_each_image_grade_and_test_stays_out(imported_client):
    from app.data.versions import load_manifest
    from app.db.models_research import ImageGrade
    from app.db.session import session_scope
    from app.ml import data as ml_data

    ids = _setup(imported_client)
    a, b = ids['P-0002']
    with session_scope('research') as db:
        db.add(ImageGrade(image_id=a, grade=1, rater='A', created_at='2026-11-06'))
        db.add(ImageGrade(image_id=b, grade=3, rater='A', created_at='2026-11-06'))
        db.add(ImageGrade(image_id=ids['P-0003'][0], grade=None, unsure_reason='看不到', rater='A', created_at='2026-11-06'))
        db.add(ImageGrade(image_id=ids['P-0001'][0], grade=2, rater='A', created_at='2026-11-06'))
    from app.data.versions import create

    version = create('', 'tester')
    manifest = load_manifest(version['id'])
    assert len(manifest['image_grade_ids']) == 3
    samples = ml_data.build('grade', version['id'], 'split-0001')
    targets = {s.image_id: s.target for s in samples}
    assert targets[a] == 1 and targets[b] == 3 and ids['P-0003'][0] not in targets
    assert ids['P-0001'][0] not in {s.image_id for s in samples if s.group.startswith('fold-')}


def test_capsule_line_does_not_brighten_cortex():
    from app.annotation.service import STRUCTURES
    from app.features.service import measure

    h, w = 400, 500
    label = np.zeros((h, w), np.uint8)
    cv2.ellipse(label, (300, 200), (120, 60), 0, 0, 360, STRUCTURES['parenchyma'], -1)
    cv2.ellipse(label, (300, 200), (60, 20), 0, 0, 360, STRUCTURES['sinus'], -1)
    gray = np.full((h, w), 30, np.uint8)
    gray[label == STRUCTURES['parenchyma']] = 60
    cv2.ellipse(gray, (300, 200), (120, 60), 0, 0, 360, 200, 3)
    out = measure(label, gray, np.ones((h, w), bool), 'right', 0.2)
    assert out['cortex_mean'] == 60


SITE_PYTHON = Path(__file__).resolve().parents[3] / '醫師圈選網站' / 'backend' / '.venv' / 'Scripts' / 'python.exe'
SITE_FILL = SITE_PYTHON.parents[2] / 'tests' / 'e2e_fill.py'


def _site(*args: str) -> Path:
    done = subprocess.run([str(SITE_PYTHON), str(SITE_FILL), *args], capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    assert done.returncode == 0, done.stderr
    return Path(done.stdout.strip().splitlines()[-1])


def _expected_label(shapes: list[dict], w: int, h: int) -> np.ndarray:
    """和網站無關的獨立算法：每個像素中心 (i+0.5, j+0.5) 用射線法判斷是否在多邊形內（奇偶規則）。"""
    xs, ys = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    label = np.zeros((h, w), np.uint8)
    for code, value in (('liver', 3), ('spleen', 4), ('kidney', 1), ('sinus', 2)):
        for shape in shapes:
            if shape['structure'] != code:
                continue
            pts = np.array(shape['points'], float)
            inside = np.zeros((h, w), bool)
            for (x0, y0), (x1, y1) in zip(pts, np.roll(pts, -1, axis=0)):
                crosses = (y0 <= ys) != (y1 <= ys)
                with np.errstate(divide='ignore', invalid='ignore'):
                    x_at = x0 + (ys - y0) * (x1 - x0) / (y1 - y0)
                inside ^= crosses & (xs < x_at)
            label[inside] = value
    return label


def _upload(client, batch_id: str, folder: Path) -> dict:
    job = client.post(f'/api/circling/batches/{batch_id}/upload', json={'folder': str(folder), 'circler': ''}).json()['job_id']
    wait_job(job)
    result = client.get(f'/api/jobs/{job}').json()
    assert result['status'] == 'completed', result
    return result['result']


@pytest.mark.skipif(not SITE_PYTHON.exists(), reason='圈選網站還沒建立虛擬環境')
def test_end_to_end_masks_match_physician_drawing_pixel_for_pixel(imported_client, workspace, tmp_path):
    """主系統匯出原始影像 → 網站圈選、輸出 → 主系統上傳、匯入：遮罩逐像素等於醫師畫的多邊形，尺寸、狀態、分級、其他項目都對得上。"""
    from app.annotation.circling import ORIGINAL_CONFIRM
    from app.data import storage
    from app.db.models_research import Image, ImageGrade, MaskAnnotation
    from app.db.session import session_scope

    _setup(imported_client)
    batch = imported_client.post('/api/circling/batches', json={'kind': 'all'}).json()
    job = imported_client.post(f"/api/circling/batches/{batch['id']}/export", json={'include_original': True, 'confirm': ORIGINAL_CONFIRM}).json()['job_id']
    wait_job(job)
    original = workspace / imported_client.get(f'/api/jobs/{job}').json()['result']['original_folder']
    site_root = tmp_path / 'site'
    result = _site(str(original), str(site_root))
    assert not [p for p in result.rglob('*') if p.suffix.lower() in {'.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}]  # 不含影像內容
    site = {i['image_id']: i for i in json.loads((result / '圈選結果.json').read_text(encoding='utf-8'))['images']}
    assert len(site) == 8

    first = _upload(imported_client, batch['id'], result)
    assert first['parsed'] == 8 and first['errors'] == 0 and first['site']['label_file_missing'] == []
    detail = imported_client.get(f"/api/circling/batches/{batch['id']}").json()
    assert imported_client.post(f"/api/circling/batches/{batch['id']}/import", json={}).json()['imported'] == 8
    with session_scope('research') as db:
        for item in detail['items']:
            image_id = item['image_id']
            entry = site[image_id]
            image = db.get(Image, image_id)
            mask = db.query(MaskAnnotation).filter(MaskAnnotation.image_id == image_id, MaskAnnotation.source == 'physician_upload').one()
            stored = cv2.imdecode(np.fromfile(str(storage.from_root(mask.relpath)), np.uint8), cv2.IMREAD_UNCHANGED)
            assert stored.ndim == 2 and stored.shape == (image.height, image.width)  # 尺寸和系統影像相同
            expected = _expected_label(entry['shapes'], image.width, image.height)
            assert np.array_equal(stored, expected), f'{image_id}：{int((stored != expected).sum())} 個像素不同'
            organ = 'liver' if entry['states'].get('liver') == 'drawn' else 'spleen'
            other = 'spleen' if organ == 'liver' else 'liver'
            assert item['structures'] == {'kidney': 'drawn', 'sinus': 'drawn', organ: 'drawn', other: 'absent'}
            flags = json.loads(mask.flags_json)
            assert flags['site']['extras']['shapes'] == [s for s in entry['shapes'] if s['structure'] in ('cyst', 'stone')]
            assert flags['site']['extras']['states']['cyst'] == 'drawn' and flags['site']['extras']['states']['shadow'] == 'not_seen'
            assert db.query(ImageGrade).filter(ImageGrade.image_id == image_id).one().grade == entry['grade']
            assert imported_client.get(f"/api/circling/items/{item['id']}/overlay").status_code == 200

    # 網站每次輸出都包含全部完成的影像：沒改過的不會重複匯入
    changed = detail['items'][0]['image_id']
    again = _upload(imported_client, batch['id'], _site('modify', str(site_root), changed))
    assert again['unchanged'] == 7 and again['parsed'] == 1
    assert imported_client.post(f"/api/circling/batches/{batch['id']}/import", json={}).json()['imported'] == 1
    with session_scope('research') as db:
        versions = db.query(MaskAnnotation).filter(MaskAnnotation.image_id == changed).order_by(MaskAnnotation.version).all()
        assert len(versions) == 2 and db.query(MaskAnnotation).count() == 9
        latest = cv2.imdecode(np.fromfile(str(storage.from_root(versions[-1].relpath)), np.uint8), cv2.IMREAD_UNCHANGED)
        image = db.get(Image, changed)
        newest = sorted((site_root / '輸出').iterdir())[-1]
        new_entry = {i['image_id']: i for i in json.loads((newest / '圈選結果.json').read_text(encoding='utf-8'))['images']}[changed]
        assert np.array_equal(latest, _expected_label(new_entry['shapes'], image.width, image.height))
        assert db.query(ImageGrade).filter(ImageGrade.image_id == changed).one().grade == 3


def test_site_side_and_usability_override_main_system(imported_client, workspace, tmp_path):
    """醫師圈選網站的側別、能否使用一律為準（2026-11-09）：不同時改成網站的值，重新去識別化也不會蓋掉。"""
    from app.db.models_research import Image
    from app.db.session import session_scope

    ids = _setup(imported_client)
    batch = imported_client.post('/api/circling/batches', json={'kind': 'all'}).json()['id']
    a, b = ids['P-0001']  # 系統：右、左
    c, d = ids['P-0002']
    with session_scope('research') as db:
        db.get(Image, c).status, db.get(Image, c).review_reasons_json = 'pending_review', '["讀不到年齡"]'
    root = tmp_path / '2026-11-09_圈選結果'
    for image_id in (a, c):
        _write(root / '標籤', f'{image_id}.png', _label_for(image_id))
    _site_result(root, [
        _site_entry(a, side='left'),  # 醫師判定是左腎
        _site_entry(c, side=None),  # 醫師判定看不出側別
        {'image_id': b, 'status': 'unusable', 'side': 'left', 'label_file': None, 'states': {}, 'shapes': [], 'grade': None, 'grade_unsure': False,
         'grade_reason': '', 'note': '', 'discuss': False, 'unusable_reason': '腎臟不完整', 'circler': 'A', 'seconds': 10},
    ])
    wait_job(imported_client.post(f'/api/circling/batches/{batch}/upload', json={'folder': str(root), 'circler': ''}).json()['job_id'])
    with session_scope('research') as db:
        got = {i: (db.get(Image, i).side, db.get(Image, i).side_source, db.get(Image, i).status, db.get(Image, i).exclude_reason) for i in (a, b, c, d)}
    assert got[a] == ('left', 'circling', 'usable', None)
    assert got[c] == (None, 'circling', 'usable', None)  # 待確認 → 可用；側別改成未知
    assert got[b] == ('left', 'circling', 'excluded', '醫師圈選：腎臟不完整')
    assert got[d][1] != 'circling'  # 沒有在圈選結果裡的影像不動
    items = {i['image_id']: i for i in imported_client.get(f'/api/circling/batches/{batch}').json()['items']}
    assert items[b]['status'] == 'unusable'
    assert any('側別 右腎 → 左腎' in w for w in items[a]['parse']['warnings'])
    counts = next(x for x in imported_client.get('/api/circling/batches').json()['batches'] if x['id'] == batch)['counts']
    assert counts['unusable'] == 1
    # 重新去識別化（重新辨識側別）不會蓋掉醫師圈選的側別
    wait_job(imported_client.post('/api/images/reread-side').json()['job_id'])
    with session_scope('research') as db:
        assert db.get(Image, a).side == 'left'


def test_purging_imported_physician_mask_returns_item_to_review(imported_client, workspace, tmp_path):
    """刪掉醫師圈選匯入的遮罩（永久刪除）：PNG 刪掉，圈選項目回到「已轉換，待檢查」，可以重新匯入。"""
    from app.data import storage
    from app.db.models_research import MaskAnnotation
    from app.db.session import session_scope

    ids = _setup(imported_client)
    batch = imported_client.post('/api/circling/batches', json={'kind': 'test'}).json()['id']
    right, _ = ids['P-0001']
    root = tmp_path / 'r'
    _write(root / '標籤', f'{right}.png', _label_for(right))
    _site_result(root, [_site_entry(right)])
    wait_job(imported_client.post(f'/api/circling/batches/{batch}/upload', json={'folder': str(root), 'circler': ''}).json()['job_id'])
    mask_id = imported_client.post(f'/api/circling/batches/{batch}/import', json={}).json()['mask_ids'][0]
    with session_scope('research') as db:
        png = storage.from_root(db.get(MaskAnnotation, mask_id).relpath)
    assert png.exists()
    imported_client.post('/api/trash', json={'kind': 'mask', 'id': str(mask_id), 'reason': '重圈'})
    gid = next(g['id'] for g in imported_client.get('/api/trash?kind=mask').json()['groups'])
    assert imported_client.post(f'/api/trash/{gid}/purge', json={'confirm': '永久刪除'}).json()['ok']
    item = next(i for i in imported_client.get(f'/api/circling/batches/{batch}').json()['items'] if i['image_id'] == right)
    assert not png.exists() and item['status'] == 'parsed'
    assert imported_client.post(f'/api/circling/batches/{batch}/import', json={}).json()['imported'] == 1
