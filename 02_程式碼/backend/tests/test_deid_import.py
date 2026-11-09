"""去識別化與匯入（只用程式產生的假影像）。"""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from tests import synthetic
from tests.conftest import wait_job


@pytest.mark.parametrize(
    'template_id,make',
    [
        ('TPL-T622', lambda: synthetic.toshiba(622, 500, 0, 'left')),
        ('TPL-T1493', lambda: synthetic.toshiba(1493, 1200, 1, 'right')),
        ('TPL-C1600', lambda: synthetic.canon(1600, 1200, 0)),
        ('TPL-C666', lambda: synthetic.canon(666, 500, 1)),
    ],
)
def test_deid_reads_fields_and_removes_text(template_id, make):
    from app.data import deid, templates

    img, truth = make()
    t = next(d for d in templates.DEFAULTS if d['id'] == template_id)
    r = deid.process(img, t['regions'], t['readers'])
    assert (r.age, r.sex) == (truth.age, truth.sex)
    assert r.dist_a_mm == pytest.approx(truth.dist_a)
    assert r.dist_b_mm == pytest.approx(truth.dist_b)
    assert r.pixel_spacing_mm == pytest.approx(10 / truth.px_per_cm, rel=0.03)
    if truth.side != 'unknown':
        assert r.side == truth.side
    if truth.gain:
        assert r.scan_params['gain'] == truth.gain
    assert r.caliper_pixels > 0
    # 去識別化後不能再讀到任何個資格式的文字
    assert deid.residual_check(r.model_image) == []
    # 標頭區全黑
    h = img.shape[0]
    assert int(r.model_image[: int(0.07 * h)].max()) == 0
    # 灰階計算版：caliper 位置標為無效
    assert (r.calc_valid == 0).sum() > r.caliper_pixels


def test_phash_detects_near_duplicates():
    from app.data import deid

    img, _ = synthetic.toshiba(622, 500, 7)
    gray = img[:, :, 0]
    noisy = np.clip(gray.astype(int) + np.random.default_rng(1).integers(-3, 4, gray.shape), 0, 255).astype(np.uint8)
    other, _ = synthetic.canon(666, 500, 9)
    assert deid.hamming(deid.phash(gray), deid.phash(noisy)) <= 6
    assert deid.hamming(deid.phash(gray), deid.phash(other[:, :, 0])) > 6


def test_import_original_is_idempotent_and_hides_filenames(client, synthetic_original, workspace):
    client.put('/api/settings', json={'residual_check': False})  # 殘留檢查已在 imported_template 驗證過，這裡省時間
    preview = client.post('/api/imports/preview', json={'source': 'original'}).json()
    assert preview['total'] == 8 and preview['new'] == 8 and preview['duplicates'] == 0
    before = sorted(p.name for p in (workspace / 'IMG_original').iterdir())

    r = client.post('/api/imports', json={'source': 'original'})
    assert r.status_code == 202
    assert r.json()['batch_id'] == 'B0000'
    wait_job(r.json()['job_id'])
    job = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job['status'] == 'completed', job
    assert job['result']['imported'] == 8

    images = client.get('/api/images?limit=50').json()
    assert images['total'] == 8
    body = json.dumps(images, ensure_ascii=False)
    for name, _ in synthetic_original:
        assert name not in body  # 原始檔名（含 eGFR）不會出現在 API 回應
    one = images['images'][0]
    for kind in ('model', 'calc', 'thumb'):
        assert client.get(f"/api/images/{one['id']}/file?kind={kind}").status_code == 200

    # 原始資料夾沒有被修改
    assert sorted(p.name for p in (workspace / 'IMG_original').iterdir()) == before

    # 再匯入一次：全部是重複，不會多出影像
    r2 = client.post('/api/imports', json={'source': 'original'})
    wait_job(r2.json()['job_id'])
    assert client.get(f"/api/jobs/{r2.json()['job_id']}").json()['result']['duplicates'] == 8
    assert client.get('/api/images').json()['total'] == 8

    report = client.get('/api/imports/B0000').json()
    assert report['status'] == 'completed'


def test_import_from_inbox_archives_and_moves_folder(client, workspace):
    client.put('/api/settings', json={'residual_check': False})
    inbox = workspace / '06_匯入區' / '待匯入' / '新收案一'
    names = [name for name, _ in synthetic.make_dataset(inbox)]
    # 附上病人表：前 4 張用檔名欄對到同一位病人，後 4 張不在表裡
    table = inbox / '病人表' / 'patients.csv'
    table.parent.mkdir()
    table.write_text('patient_id,性別,年齡,eGFR,影像檔名\n' + ''.join(f'NEW-1,F,61,45.2,{n}\n' for n in names[:4]), encoding='utf-8')
    folders = client.get('/api/inbox').json()['folders']
    assert folders[0]['name'] == '新收案一' and folders[0]['images'] == 8 and folders[0]['tables'] == ['patients.csv']
    r = client.post('/api/imports', json={'source': 'inbox', 'folder': '新收案一'})
    batch = r.json()['batch_id']
    assert batch.startswith('B')
    wait_job(r.json()['job_id'])
    assert not inbox.exists()
    assert (workspace / '06_匯入區' / '已完成' / f'{batch}_新收案一').is_dir()
    archive = workspace / '03_資料' / '01_原始封存' / batch
    assert len(list(archive.rglob('*.jpg'))) == 8
    assert (archive / '病人表' / 'patients.csv').exists()

    tables = client.get(f'/api/imports/{batch}').json()['report']['patient_tables']
    assert tables == [{'name': 'patients.csv', 'table_id': tables[0]['table_id'], 'rows': 4, 'matched_images': 4, 'ambiguous_groups': 0, 'unmatched_images': 4, 'updated_patients': 0}]
    images = client.get('/api/images', params={'limit': 50}).json()['images']
    mine = [i for i in images if i['batch_id'] == batch]
    assert sum(1 for i in mine if i['patient_id']) == 4 and len({i['patient_id'] for i in mine if i['patient_id']}) == 1


def test_unknown_template_goes_to_review(client, workspace):
    import cv2

    img = np.zeros((300, 400, 3), np.uint8)
    cv2.imencode('.jpg', img)[1].tofile(str(workspace / 'IMG_original' / '50.0_1.jpg'))
    preview = client.post('/api/imports/preview', json={'source': 'original'}).json()
    assert preview['unknown_sizes'] == [{'size': '400 × 300', 'count': 1}]


def test_template_update_and_preview(imported_client):
    client = imported_client
    t = client.get('/api/templates/TPL-T622').json()
    t['regions'][0]['h'] = 11
    r = client.put('/api/templates/TPL-T622', json={'regions': t['regions'], 'readers': t['readers']})
    assert r.json()['version'] == 2
    bad = client.put('/api/templates/TPL-T622', json={'regions': [{'name': 'x', 'x': 90, 'y': 0, 'w': 20, 'h': 5}], 'readers': t['readers']})
    assert bad.status_code == 422
    sample = client.get('/api/templates/TPL-T622/samples').json()['image_ids'][0]
    prev = client.post(f'/api/templates/TPL-T622/preview?image_id={sample}', json={'regions': t['regions'], 'readers': t['readers']})
    assert prev.status_code == 200 and prev.headers['content-type'] == 'image/jpeg'


def test_exclude_requires_reason(imported_client):
    client = imported_client
    image_id = client.get('/api/images').json()['images'][0]['id']
    assert client.patch(f'/api/images/{image_id}', json={'status': 'excluded'}).status_code == 422
    assert client.patch(f'/api/images/{image_id}', json={'status': 'excluded', 'exclude_reason': '腎臟截斷'}).status_code == 200
    assert client.get(f'/api/images/{image_id}').json()['status'] == 'excluded'


@pytest.mark.parametrize('size', [(622, 500), (1600, 1200)])
def test_bodymark_side_rules(size):
    from app.data import bodymark
    from app.data.deid import crop
    from app.data.templates import CANON_READERS, TOSHIBA_READERS

    rect = (TOSHIBA_READERS if size[0] == 622 else CANON_READERS)['bodymark']
    expected = {('front', 'viewer_left'): 'right', ('front', 'viewer_right'): 'left', ('back', 'viewer_left'): 'left', ('back', 'viewer_right'): 'right'}
    for (view, probe), side in expected.items():
        img = np.zeros((size[1], size[0], 3), np.uint8)
        synthetic.bodymark(img, rect, view, probe)
        mark = bodymark.detect(crop(img, rect)[0])
        assert (mark.view, mark.side) == (view, side), (size, view, probe, mark)
    assert bodymark.detect(crop(np.zeros((size[1], size[0], 3), np.uint8), rect)[0]).side is None


def test_reread_side_skips_manual(imported_client, workspace):
    from app.data import storage
    from app.data.templates import CANON_READERS, TOSHIBA_READERS
    from app.db.models_research import Image, SourceMap
    from app.db.session import session_scope

    with session_scope('research') as db:
        rows = db.query(Image.id, Image.machine, SourceMap.original_relpath).join(SourceMap, SourceMap.image_id == Image.id).order_by(Image.id).all()
    (auto_id, machine, rel), (manual_id, machine2, rel2) = rows[0], rows[1]
    for path, m, view in ((storage.from_root(rel), machine, 'front'), (storage.from_root(rel2), machine2, 'back')):
        img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        synthetic.bodymark(img, (TOSHIBA_READERS if m == 'Toshiba' else CANON_READERS)['bodymark'], view, 'viewer_left')
        synthetic.write(path, img)
    assert imported_client.post('/api/images/bulk-side', json={'image_ids': [manual_id], 'side': 'right'}).json() == {'updated': 1}

    job = imported_client.post('/api/images/reread-side').json()['job_id']
    wait_job(job)
    assert imported_client.get(f'/api/jobs/{job}').json()['status'] == 'completed'
    auto = imported_client.get(f'/api/images/{auto_id}').json()
    manual = imported_client.get(f'/api/images/{manual_id}').json()
    assert (auto['side'], auto['side_source']) == ('right', 'bodymark')  # 正面圖、探頭在畫面左邊 → 右腎
    assert (manual['side'], manual['side_source']) == ('right', 'manual')  # 背面圖會判成左腎，但人工設定優先


def test_redeid_keeps_ids_and_requires_scope(imported_client):
    before = {i['id'] for i in imported_client.get('/api/images', params={'limit': 50}).json()['images']}
    assert imported_client.post('/api/images/redeid', json={}).status_code == 422  # 一定要指定範圍
    job = imported_client.post('/api/images/redeid', json={'template_id': 'TPL-T622'}).json()['job_id']
    wait_job(job)
    result = imported_client.get(f'/api/jobs/{job}').json()
    assert result['status'] == 'completed' and result['result']['processed'] == 2, result
    after = {i['id'] for i in imported_client.get('/api/images', params={'limit': 50}).json()['images']}
    assert before == after  # 影像編號不變，標註與病人對照都還對得上
