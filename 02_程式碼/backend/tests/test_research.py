"""病人對照、切分、資料集版本、標註、一致性、回收桶。"""

from __future__ import annotations

import io

import pytest



def _upload_table(client, rows: list[list]) -> str:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(['patient_id', '性別', '年齡', '是否有糖尿病', 'matched_eGFR', 'matched_date'])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post('/api/patients/tables', files={'file': ('add_HbA1C.xlsx', buf.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert r.status_code == 201, r.json()
    return r.json()['table_id']


def test_patient_matching_uses_egfr_then_ocr_age(imported_client):
    client = imported_client
    # 72.1 有兩位病人：OCR 讀到的年齡 67 只符合 102，所以能自動區分
    table = _upload_table(client, [['101', '女', 66, 1, 30.5, '2022-01-01'], ['102', '女', 67, 0, 72.1, '2022-02-01'], ['103', '男', 50, 0, 72.1, '2022-03-01']])
    preview = client.post('/api/patients/match-preview', json={'table_id': table}).json()
    assert preview['matched_images'] == 8 and preview['matched_patients'] == 2 and preview['ambiguous_images'] == 0
    client.post('/api/patients/match', json={'table_id': table})
    patients = client.get('/api/patients').json()['patients']
    assert [p['images'] for p in patients] == [4, 4]
    assert all('egfr' not in p for p in patients)  # 只回傳分組，不回傳數值


def test_ambiguous_patients_need_manual_review(imported_client):
    client = imported_client
    # 兩位 30.5 的病人年齡都是 66 → 無法自動區分
    table = _upload_table(client, [['201', '女', 66, 1, 30.5, None], ['202', '女', 66, 0, 30.5, None]])
    result = client.post('/api/patients/match', json={'table_id': table}).json()
    assert result['ambiguous_groups'] == 1
    group = client.get('/api/patients/review').json()['ambiguous'][0]
    assert len(group['image_ids']) == 4
    r = client.post('/api/patients/review/resolve', json={'table_id': table, 'image_ids': group['image_ids'], 'row_key': group['candidates'][0]['row_key']})
    assert r.status_code == 200
    assert client.get('/api/patients/review').json()['ambiguous'] == []


def _fake_patients(n_old: int, n_new: int = 0):
    """直接在資料庫建立假病人與影像（切分測試需要較多病人）。"""
    from app.core.ids import now_iso
    from app.db.models_research import Batch, Image, Patient
    from app.db.session import session_scope

    with session_scope('research') as db:
        if db.get(Batch, 'BTEST') is None:
            db.add(Batch(id='BTEST', source_kind='inbox', source_label='test', status='completed', created_at=now_iso()))
        start = db.query(Patient).count()
        for i in range(start, start + n_old + n_new):
            pid = f'P-{i + 1:04d}'
            db.add(Patient(id=pid, egfr=[10, 20, 45, 75, 100][i % 5], created_at=now_iso()))
            db.flush()
            for j in range(3):
                db.add(Image(id=f'IMG-T{i:04d}{j}', batch_id='BTEST', sha256=f'{i:060d}{j:04d}', phash=f'{(i * 7919 + j * 104729) % (1 << 63):016x}', patient_id=pid, machine='Toshiba' if j % 2 else 'Canon Aplio 300', width=10, height=10, status='usable', created_at=now_iso()))


def test_split_patient_level_and_incremental(client):
    _fake_patients(60)
    preview = client.post('/api/splits/preview', json={'seed': 42, 'folds': 5, 'test_ratio': 0.2}).json()
    assert preview['patients'] == 60
    created = client.post('/api/splits', json={'seed': 42, 'folds': 5, 'test_ratio': 0.2}).json()
    groups = {g['group']: g['patients'] for g in created['groups']}
    assert groups['test'] == 12 and sum(groups.values()) == 60

    from app.db.models_research import SplitEntry
    from app.db.session import session_scope

    with session_scope('research') as db:
        old = {e.patient_id: e.group for e in db.query(SplitEntry).filter(SplitEntry.split_id == created['id'])}

    _fake_patients(0, 10)
    ext = client.post(f"/api/splits/{created['id']}/extend", json={'mode': 'folds'}).json()
    assert ext['new_patients'] == 10
    with session_scope('research') as db:
        new = {e.patient_id: e.group for e in db.query(SplitEntry).filter(SplitEntry.split_id == ext['id'])}
    assert all(new[p] == g for p, g in old.items())  # 舊病人組別不變
    assert all(new[p] != 'test' for p in set(new) - set(old))  # 新病人不會進固定測試集

    pro = client.post(f"/api/splits/{created['id']}/extend", json={'mode': 'prospective'}).json()
    groups = {g['group']: g['patients'] for g in pro['groups']}
    assert groups['prospective'] == 10

    leak = client.get(f"/api/splits/{created['id']}/leakage").json()
    assert leak['patient_in_multiple_groups'] == 0


def test_leakage_finds_near_duplicates_across_groups(client):
    import cv2
    import numpy as np

    from app.data import storage
    from app.db.models_research import Image, SplitEntry
    from app.db.session import session_scope

    _fake_patients(20)
    split = client.post('/api/splits', json={'seed': 1, 'folds': 5, 'test_ratio': 0.2}).json()
    with session_scope('research') as db:
        group = dict(db.query(SplitEntry.patient_id, SplitEntry.group).filter(SplitEntry.split_id == split['id']).all())
        imgs = [(i.id, i.patient_id) for i in db.query(Image).order_by(Image.id).all()]
    rng = np.random.default_rng(0)

    def thumb(image_id, img):
        path = storage.image_path(image_id, 'thumb')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(cv2.imencode('.jpg', img)[1].tobytes())

    # 每張都有相同的版面（黑底＋標頭白框），只有超音波內容不同 → 版面相同不算重複
    contents = {}
    for image_id, _ in imgs:
        img = np.zeros((300, 400), np.uint8)
        img[:30] = 200
        img[60:270, 80:320] = cv2.GaussianBlur(rng.integers(0, 255, (210, 240), dtype=np.uint8), (9, 9), 3)
        contents[image_id] = img
        thumb(image_id, img)
    a = imgs[0]
    other = next(i for i in imgs if group[i[1]] != group[a[1]])
    same = next(i for i in imgs if i[1] == a[1] and i != a)
    thumb(other[0], contents[a[0]])  # 不同組的病人有一張幾乎一樣的影像 → 洩漏
    thumb(same[0], contents[a[0]])  # 同一位病人的重複影像在同一組 → 不算
    leak = client.get(f"/api/splits/{split['id']}/leakage").json()
    assert leak['near_duplicates_count'] == 2  # a↔other、same↔other
    assert {(d['image_a'], d['image_b']) for d in leak['near_duplicates_across_groups']} == {tuple(sorted((a[0], other[0]))), tuple(sorted((same[0], other[0])))}
    assert not leak['passed']


def test_masks_versioned_and_rasterized(imported_client):
    client = imported_client
    image = client.get('/api/images').json()['images'][0]
    shapes = [
        {'structure': 'parenchyma', 'kind': 'polygon', 'points': [[100, 100], [300, 100], [300, 250], [100, 250]]},
        {'structure': 'sinus', 'kind': 'polygon', 'points': [[150, 150], [250, 150], [250, 200], [150, 200]]},
    ]
    r1 = client.put(f"/api/annotation/masks/{image['id']}", json={'shapes': shapes}).json()
    r2 = client.put(f"/api/annotation/masks/{image['id']}", json={'shapes': shapes[:1]}).json()
    assert (r1['version'], r2['version']) == (1, 2)
    assert r1['pixels']['sinus'] > 0 and r1['pixels']['parenchyma'] > r1['pixels']['sinus']
    assert r2['pixels']['sinus'] == 0
    masks = client.get(f"/api/annotation/masks/{image['id']}").json()
    assert masks['latest']['version'] == 2 and len(masks['history']) == 2
    bad = client.put(f"/api/annotation/masks/{image['id']}", json={'shapes': [{'structure': 'tumor', 'kind': 'polygon', 'points': [[0, 0], [1, 1], [2, 0]]}]})
    assert bad.status_code == 422


def test_grades_and_agreement(client):
    from app.annotation.agreement import weighted_kappa

    assert weighted_kappa([0, 1, 2, 3], [0, 1, 2, 3]) == pytest.approx(1.0)
    assert weighted_kappa([0, 1, 2, 3, 2], [0, 1, 3, 3, 1]) < 1.0

    _fake_patients(5)
    for i, (a, b) in enumerate([(0, 0), (1, 1), (2, 3), (3, 3), (1, 3)]):
        pid = f'P-{i + 1:04d}'
        client.put('/api/annotation/grades', json={'patient_id': pid, 'side': 'right', 'grade': a, 'rater': '林醫師'})
        client.put('/api/annotation/grades', json={'patient_id': pid, 'side': 'right', 'grade': b, 'rater': '周醫師'})
    assert client.put('/api/annotation/grades', json={'patient_id': 'P-0001', 'side': 'right', 'grade': None, 'rater': '林醫師'}).status_code == 422
    report = client.post('/api/annotation/agreement').json()
    pair = report['grade']['pairs'][0]
    assert pair['n'] == 5
    assert pair['weighted_kappa'] == pytest.approx(weighted_kappa([0, 1, 2, 3, 1], [0, 1, 3, 3, 3]) if pair['raters'][0] == '林醫師' else weighted_kappa([0, 1, 3, 3, 3], [0, 1, 2, 3, 1]))
    assert len(pair['differ_by_2_or_more']) == 1


def test_annotation_queue_is_blind(imported_client):
    client = imported_client
    table = _upload_table(client, [['101', '女', 66, 1, 30.5, None], ['102', '女', 67, 0, 72.1, None]])
    client.post('/api/patients/match', json={'table_id': table})
    q = client.get('/api/annotation/queue/grade?rater=林醫師').json()
    body = str(q)
    assert 'egfr' not in body.lower() and '30.5' not in body and '72.1' not in body
    assert q['total'] >= 1


def test_dataset_version_and_trash(imported_client):
    client = imported_client
    table = _upload_table(client, [['101', '女', 66, 1, 30.5, None], ['102', '女', 67, 0, 72.1, None]])
    client.post('/api/patients/match', json={'table_id': table})
    v = client.post('/api/dataset-versions', json={'note': '第一版'}).json()
    assert v['id'] == 'dsv-0001' and v['images'] == 8 and v['patients'] == 2

    split = client.post('/api/splits', json={'seed': 3, 'folds': 2, 'test_ratio': 0.2}).json()
    group = client.post('/api/trash', json={'kind': 'split', 'id': split['id']}).json()['group_id']
    assert client.get('/api/splits').json()['splits'] == []
    client.post(f'/api/trash/{group}/restore')
    assert len(client.get('/api/splits').json()['splits']) == 1
    group = client.post('/api/trash', json={'kind': 'split', 'id': split['id']}).json()['group_id']
    assert client.post(f'/api/trash/{group}/purge', json={'confirm': '刪除'}).status_code == 422
    assert client.post(f'/api/trash/{group}/purge', json={'confirm': '永久刪除'}).status_code == 200
    assert client.get('/api/trash').json()['groups'] == []


def test_patient_table_headers_and_key_required(client, workspace):
    from app.data.patients import read_table

    ok = workspace / 'ok.csv'
    ok.write_text('patient_id,性別,年紀,是否有糖尿病,matched_eGFR\nX1,F,61,1,45.2\n', encoding='utf-8')
    row = read_table(ok)[0]
    assert row['age'] == 61 and row['sex'] == 'F' and row['egfr'] == 45.2

    xlsx = workspace / 'zero.xlsx'
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(['patient_id', '是否有糖尿病', 'matched_eGFR'])
    wb.active.append(['X2', 0, 50.1])
    wb.save(xlsx)
    assert read_table(xlsx)[0]['diabetes'] is False

    per_image = workspace / 'metadata.csv'
    per_image.write_text('image_name,age,has_diabetes\na.jpg,61,1\nb.jpg,61,0\n', encoding='utf-8')
    r = client.post('/api/patients/tables', files={'file': ('metadata.csv', per_image.read_bytes(), 'text/csv')})
    assert r.status_code == 422 and r.json()['error']['code'] == 'TABLE_NO_PATIENT_KEY'


def test_fatty_liver_column_updates_existing_patients(imported_client, workspace):
    first = workspace / 't1.csv'
    first.write_text('patient_id,性別,eGFR\nA1,F,30.5\nA2,F,72.1\n', encoding='utf-8')
    t1 = imported_client.post('/api/patients/tables', files={'file': ('t1.csv', first.read_bytes(), 'text/csv')}).json()['table_id']
    imported_client.post('/api/patients/match', json={'table_id': t1})
    second = workspace / 't2.csv'
    second.write_text('patient_id,性別,年紀,是否有糖尿病,eGFR,是否有脂肪肝\nA1,F,66,0,30.5,0\nA2,F,67,1,72.1,0.0\n', encoding='utf-8')
    t2 = imported_client.post('/api/patients/tables', files={'file': ('t2.csv', second.read_bytes(), 'text/csv')}).json()['table_id']
    assert imported_client.post('/api/patients/match', json={'table_id': t2}).json()['updated_patients'] == 2
    patients = imported_client.get('/api/patients').json()['patients']
    assert patients and all(p['has_fatty_liver'] is False for p in patients)
    # 第一份表沒有年紀與糖尿病：重新套用時補上空白欄位
    assert sorted((p['age'], p['has_diabetes']) for p in patients) == [(66, False), (67, True)]


def test_rematch_groups_same_header_number(imported_client):
    from tests.conftest import wait_job

    client = imported_client
    table = _upload_table(client, [['201', '女', 66, 1, 30.5, None], ['202', '女', 66, 0, 30.5, None]])
    client.post('/api/patients/match', json={'table_id': table})
    job = client.post('/api/patients/review/rematch').json()['job_id']
    wait_job(job)
    result = client.get(f'/api/jobs/{job}').json()['result']
    # 兩位候選年齡相同 → 不自動分配；4 張標頭病歷號相同，合成一組只需決定一次
    assert result['by_age'] == 0 and result['by_elimination'] == 0
    groups = client.get('/api/patients/review').json()['ambiguous']
    assert len(groups) == 1 and len(groups[0]['image_ids']) == 4
    assert '同一位病人' in groups[0]['note'] and '0012345' not in str(groups)


def test_rematch_assigns_by_age_then_elimination(imported_client, monkeypatch):
    from app.data import importer
    from app.db.models_research import Image
    from app.db.session import session_scope
    from tests.conftest import wait_job

    client = imported_client
    with session_scope('research') as db:
        ids = sorted(i.id for i in db.query(Image).filter(Image.ocr_age == 66).all())
        assert len(ids) == 4
        db.query(Image).filter(Image.id.in_(ids)).update({'ocr_age': None}, synchronize_session=False)
    # 沒有年齡 → 兩位 30.5 的病人分不出來
    table = _upload_table(client, [['301', '女', 66, 1, 30.5, None], ['302', '女', 50, 0, 30.5, None]])
    assert client.post('/api/patients/match', json={'table_id': table}).json()['ambiguous_groups'] == 1
    # 前兩張讀回年齡 66；標頭號碼把 4 張分成兩個人
    with session_scope('research') as db:
        db.query(Image).filter(Image.id.in_(ids[:2])).update({'ocr_age': 66}, synchronize_session=False)
    monkeypatch.setattr(importer, 'header_number', lambda image_id: 'A' if image_id in ids[:2] else 'B')
    job = client.post('/api/patients/review/rematch').json()['job_id']
    wait_job(job)
    result = client.get(f'/api/jobs/{job}').json()['result']
    assert result['by_age'] == 2 and result['by_elimination'] == 2 and result['still_ambiguous_groups'] == 0
    assert client.get('/api/patients/review').json()['ambiguous'] == []
    with session_scope('research') as db:
        owner = {i.id: i.patient_id for i in db.query(Image).filter(Image.id.in_(ids)).all()}
    assert owner[ids[0]] == owner[ids[1]] and owner[ids[2]] == owner[ids[3]] and owner[ids[0]] != owner[ids[2]]
