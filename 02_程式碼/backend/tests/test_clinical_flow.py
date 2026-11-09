"""M3 階段 B–E：雙機接收（上傳小程式）、示範影像包、醫師端分析、工作區修改、報告與 PDF、轉入研究、回收桶。只用合成影像。"""

from __future__ import annotations

import hashlib
import json

import cv2
import pytest

from tests.conftest import wait_job
from tests.test_training import TINY, FakeCtx, research  # noqa: F401  6 位合成病人（含已確認遮罩）


def _png(img) -> bytes:
    return cv2.imencode('.png', img)[1].tobytes()


def _put(up, token, batch, seq, data, **headers):
    h = {'authorization': f'Bearer {token}', 'x-sha256': hashlib.sha256(data).hexdigest(), **headers}
    return up.put(f'/batches/{batch}/items/{seq}', content=data, headers=h)


def _wait_exam(client, exam_id):
    """等收圖與分析工作做完。"""
    from app.db.models_system import Job
    from app.db.session import session_scope

    for _ in range(3):
        with session_scope('system') as db:
            ids = [j.id for j in db.query(Job).filter(Job.kind.in_(('clinical_receive', 'clinical_analysis'))).all()]
        for job_id in ids:
            wait_job(job_id)
    return client.get(f'/api/clinical/exams/{exam_id}').json()


def test_receiver_pairing_upload_rules_and_summary(client, workspace):
    from fastapi.testclient import TestClient

    from app.clinical import receiver
    from app.db.models_clinical import ReceiverBatch, ReceiverSession
    from app.db.session import session_scope
    from tests import synthetic

    assert client.post('/api/clinical/receiver/start', json={'address': '10.255.255.254'}).status_code == 422  # 不是這台電腦的位址
    started = client.post('/api/clinical/receiver/start', json={'address': '127.0.0.1'}).json()
    assert started['url'] == 'https://127.0.0.1:8443' and len(started['code']) == 6 and started['fingerprint']
    assert client.post('/api/clinical/receiver/start', json={'address': '127.0.0.1'}).json()['error']['code'] == 'RECEIVER_ACTIVE'
    up = TestClient(receiver.upload_app())
    # 只有傳送頁、配對、上傳三類路徑；主網站的 API 不存在
    assert {r.path for r in receiver.upload_app().routes} == {'/', '/pair', '/batches', '/batches/{batch_id}/items/{seq:int}', '/batches/{batch_id}/finish', '/batches/{batch_id}'}
    assert up.get('/api/overview').status_code == 404 and '配對' in up.get('/').text
    assert up.post('/batches', json={}).status_code == 401  # 沒配對
    # 配對碼錯 5 次就鎖住，換新的配對碼才解開
    for left in range(4, -1, -1):
        r = up.post('/pair', headers={'x-pair-code': '000000' if started['code'] != '000000' else '111111'})
        assert r.status_code == 401 and f'剩 {left} 次' in r.json()['error']['message']
    assert up.post('/pair', headers={'x-pair-code': started['code']}).status_code == 429
    code = client.post('/api/clinical/receiver/code').json()['code']
    with session_scope('clinical') as db:  # 資料庫只存雜湊
        s = db.query(ReceiverSession).one()
        assert code not in s.code_hash and s.code_hash == hashlib.sha256(code.encode()).hexdigest()
        s.code_expires_at = '2000-01-01T00:00:00+08:00'
    assert up.post('/pair', headers={'x-pair-code': code}).json()['error']['code'] == 'CODE_EXPIRED'
    code = client.post('/api/clinical/receiver/code').json()['code']
    token = up.post('/pair', headers={'x-pair-code': code}).json()['token']

    batch = up.post('/batches', headers={'authorization': f'Bearer {token}'}, json={'case_code': 'TEST-01', 'age': 61, 'sex': '男', 'diabetes': '無'}).json()
    img, _ = synthetic.toshiba(622, 500, 3, 'left')
    data = _png(img)
    assert _put(up, token, batch['batch_id'], 1, data).json()['status'] == 'received'
    assert _put(up, token, batch['batch_id'], 2, data).json()['status'] == 'duplicate'
    assert _put(up, token, batch['batch_id'], 3, b'not an image at all').json()['error']['code'] == 'NOT_IMAGE'
    bad = up.put(f'/batches/{batch["batch_id"]}/items/4', content=data, headers={'authorization': f'Bearer {token}', 'x-sha256': '0' * 64})
    assert bad.json()['error']['code'] == 'HASH_MISMATCH'
    assert up.put(f'/batches/{batch["batch_id"]}/items/5', content=data).status_code == 401
    finished = up.post(f'/batches/{batch["batch_id"]}/finish', headers={'authorization': f'Bearer {token}'}).json()
    assert finished['exam_id'] == batch['exam_id']
    assert _put(up, token, batch['batch_id'], 6, data).json()['error']['code'] == 'BATCH_FINISHED'
    exam = _wait_exam(client, batch['exam_id'])
    assert len(exam['images']) == 1 and exam['clinical'] == {'age': 61.0, 'sex': 'M', 'diabetes': 'no', 'source': 'upload'}
    assert exam['analysis']['status'] == 'partial' and all(s['status'] == 'not_configured' for s in exam['analysis']['steps'].values())
    # 原始檔在受限區、暫存清掉、沒有保存 A 端檔名
    assert not any((workspace / '05_醫師端' / '05_接收暫存').iterdir())
    raw_files = list((workspace / '05_醫師端' / '01_原始').rglob('CI-*'))
    assert len(raw_files) == 1 and raw_files[0].suffix == '.png'  # 依內容存成 .png，不是上傳暫存的 .part
    with session_scope('clinical') as db:
        items = json.loads(db.get(ReceiverBatch, batch['batch_id']).items_json)
    assert all('name' not in i and 'filename' not in i for i in items)
    summary = client.get(f'/api/clinical/receiver/batches/{batch["batch_id"]}/summary')
    assert 'attachment' in summary.headers['content-disposition']
    assert [i['status'] for i in summary.json()['item_list']] == ['ok', 'duplicate']
    # 去識別化影像可以看；原始檔沒有任何 API
    image_id = exam['images'][0]['id']
    assert client.get(f'/api/clinical/images/{image_id}/thumb').status_code == 200
    assert client.get(f'/api/clinical/images/{image_id}/raw').status_code == 422
    # 停止後，配對失效
    assert client.post('/api/clinical/receiver/stop').json() == {'ok': True}
    assert up.post('/batches', headers={'authorization': f'Bearer {token}'}, json={}).status_code == 401
    assert client.get('/api/clinical/receiver').json()['session'] is None


def test_layout_mismatch_and_fix(client, workspace):
    from app.clinical import exams
    from tests import synthetic

    img, _ = synthetic.toshiba(700, 520, 5, 'left')  # 沒有這個尺寸的版面範本
    ex = exams.create_exam('LAYOUT-1', {}, source='upload', batch_id='RB-TEST')
    path = workspace / 'tmp.part'
    path.write_bytes(_png(img))
    assert exams.add_image(ex['exam_id'], 'RB-TEST', 1, path, 'a' * 64, {})['status'] == 'layout_mismatch'
    assert exams.refresh_status(ex['exam_id']) == 'layout_mismatch'
    image_id = client.get(f'/api/clinical/exams/{ex["exam_id"]}').json()['images'][0]['id']
    assert client.get(f'/api/clinical/images/{image_id}/model').status_code == 403  # 沒去識別化的不顯示
    fixed = client.post(f'/api/clinical/exams/{ex["exam_id"]}/layout').json()
    assert fixed['templates'] == ['700×520'] and fixed['fixed'] == 1
    detail = client.get(f'/api/clinical/exams/{ex["exam_id"]}').json()
    assert detail['images'][0]['status'] in ('ok', 'residual') and detail['edits'][0]['kind'] == 'layout'


def _train(research, task, cfg, name):
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope
    from app.ml import engine
    from app.ml.runs import create

    run = create(task, name, research['version'], research['split'], cfg, '測試', start=False)['id']
    summary = engine.train_run(run, task, cfg, research['version'], research['split'], FakeCtx())
    with session_scope('research') as db:
        r = db.get(TrainingRun, run)
        r.status, r.summary_json = 'completed', json.dumps(summary)
    return run


def test_demo_flow_analysis_workspace_report_pdf_transfer_trash(research, workspace):  # noqa: F811
    from fastapi.testclient import TestClient

    from app.clinical import receiver

    client = research['client']
    seg_run = _train(research, 'segmentation', {**TINY, 'epochs': 1, 'arch': 'unet'}, 'seg')
    egfr_run = _train(research, 'egfr', {**TINY, 'epochs': 1, 'inputs': ['image', 'clinical']}, 'egfr')
    seg = client.post('/api/models', json={'run_id': seg_run, 'name': 'seg-c', 'version': '1.0.0'}).json()['id']
    egfr = client.post('/api/models', json={'run_id': egfr_run, 'name': 'egfr-c', 'version': '1.0.0'}).json()['id']
    for m in (seg, egfr):
        client.post(f'/api/models/{m}/stage', json={'stage': 'candidate'})
    assert client.put('/api/settings', json={'clinical_plan': {'segmentation': seg, 'egfr': egfr}}).status_code == 200
    home = client.get('/api/clinical/overview').json()
    assert home['candidate'] and next(c for c in home['checks'] if c['key'] == 'plan')['ok']

    # 示範影像包：只有測試集病人、每側 1 張、不含 eGFR
    pack = client.post('/api/clinical/demo-pack', json={'patients': 6}).json()
    folder = workspace / pack['folder']
    listing = json.loads((folder / '示範清單.json').read_text(encoding='utf-8'))
    from app.db.models_research import SplitEntry
    from app.db.session import session_scope

    with session_scope('research') as db:
        test_patients = {p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == research['split'], SplitEntry.group == 'test').all()}
    assert pack['patients'] == len([p for p in test_patients]) and pack['images'] == 2 * pack['patients']
    assert all('egfr' not in json.dumps(i).lower() and i['case_code'].startswith('DEMO-') for i in listing['items'])
    assert 'P-' not in json.dumps(listing['items'])

    # A 電腦匯入清單後傳送第一位
    started = client.post('/api/clinical/receiver/start', json={'address': '127.0.0.1'}).json()
    up = TestClient(receiver.upload_app())
    token = up.post('/pair', headers={'x-pair-code': started['code']}).json()['token']
    first = [i for i in listing['items'] if i['case_code'] == 'DEMO-01']
    batch = up.post('/batches', headers={'authorization': f'Bearer {token}'},
                    json={'case_code': 'DEMO-01', 'age': first[0]['age'], 'sex': first[0]['sex'], 'diabetes': first[0]['diabetes'], 'demo': True}).json()
    for n, item in enumerate(first, start=1):
        r = _put(up, token, batch['batch_id'], n, (folder / item['file']).read_bytes(), **{'x-demo': '1', 'x-side': item['side'], 'x-spacing': str(item['pixel_spacing_mm'])})
        assert r.json()['status'] == 'received', r.json()
    up.post(f'/batches/{batch["batch_id"]}/finish', headers={'authorization': f'Bearer {token}'})
    exam_id = batch['exam_id']
    exam = _wait_exam(client, exam_id)
    assert {i['side'] for i in exam['images']} == {'right', 'left'} and all(i['spacing_source'] == 'demo_list' for i in exam['images'])
    steps = exam['analysis']['steps']
    assert steps['segmentation']['status'] == 'done' and steps['grade']['status'] == 'not_configured'
    # 糖尿病不明 → 影像＋臨床的 eGFR 模型略過，檢查變成「待補資料」（其他步驟照做）
    assert steps['egfr']['status'] == 'skipped' and exam['status'] == 'needs_data' and '糖尿病' in exam['missing_clinical']
    assert exam['analysis']['candidate'] and exam['analysis']['models']['egfr']['hashes']
    worklist = client.get('/api/clinical/exams?status=needs_data').json()['items']
    assert [e['id'] for e in worklist] == [exam_id] and worklist[0]['candidate']

    # 補填資料、重新分析（新的一筆分析，舊的不變）
    old_analysis = exam['analysis']['id']
    client.patch(f'/api/clinical/exams/{exam_id}/clinical', json={'age': 61, 'sex': '女', 'diabetes': '無'})
    re = client.post(f'/api/clinical/exams/{exam_id}/reanalyze').json()
    exam = _wait_exam(client, exam_id)
    assert exam['analysis']['id'] == re['analysis_id'] != old_analysis and exam['analysis']['retry_of'] == old_analysis
    egfr_res = exam['analysis']['results']['egfr']
    assert exam['status'] == 'ready' and egfr_res['images'] == 2 and 0 <= egfr_res['p_lt60'] <= 1  # 整次檢查（兩側）整合
    right = exam['analysis']['results']['sides']['right']
    assert right['images'] == 1 and 'longest_image_id' in right
    image_id = exam['images'][0]['id']
    assert client.get(f'/api/clinical/analyses/{exam["analysis"]["id"]}/overlay/{image_id}').status_code == 200

    # 醫師修改：排除要原因；腎長修改並回饋研究端（不送臨床資料）
    assert client.patch(f'/api/clinical/exams/{exam_id}/images/{image_id}', json={'excluded': True}).json()['error']['code'] == 'REASON_REQUIRED'
    client.patch(f'/api/clinical/exams/{exam_id}/images/{image_id}', json={'excluded': True, 'reason': '切面不完整'})
    client.patch(f'/api/clinical/exams/{exam_id}/images/{image_id}', json={'excluded': False})
    detail = client.patch(f'/api/clinical/exams/{exam_id}/sides/right', json={'length_mm': 105.5}).json()
    assert detail['overrides']['right']['length_mm'] == 105.5
    assert client.patch(f'/api/clinical/exams/{exam_id}/sides/right', json={'length_mm': 400}).status_code == 422
    assert [e['kind'] for e in detail['edits']][:4] == ['length', 'include', 'exclude', 'reanalyze']
    feedback = client.get('/api/feedback').json()['items']
    assert {f['kind'] for f in feedback} == {'exclude', 'include', 'length'}
    assert next(f for f in feedback if f['kind'] == 'exclude')['reason'] == '切面不完整'
    assert all('61' not in f['doctor'] for f in feedback)

    # 報告：AI 只預填腎長與 eGFR；簽核前檢查清單；簽核要醫師名單＋輸入姓名
    report = client.post(f'/api/clinical/exams/{exam_id}/report').json()
    rid = report['id']
    assert report['payload']['sides']['right']['length_mm'] == 105.5 and report['payload']['sides']['right']['hydronephrosis'] == ''
    assert report['payload']['egfr']['p_lt60'] == egfr_res['p_lt60']
    keys = {i['key'] for i in report['checklist']}
    assert {'ai_unconfirmed', 'candidate'} <= keys
    client.put(f'/api/clinical/reports/{rid}', json={'payload': {'impression': '雙側腎臟大小正常。', 'ai_confirmed': True,
                                                               'sides': {'right': {'hydronephrosis': '無'}}}, 'submit': True})
    assert client.post(f'/api/clinical/reports/{rid}/sign', json={'physician': '林醫師', 'confirm_name': '林醫師', 'acknowledged': []}).json()['error']['code'] == 'PHYSICIAN_REQUIRED'
    client.post('/api/people', json={'name': '林醫師', 'kind': 'physician'})
    assert client.post(f'/api/clinical/reports/{rid}/sign', json={'physician': '林醫師', 'confirm_name': '林', 'acknowledged': []}).json()['error']['code'] == 'CONFIRM_MISMATCH'
    assert client.post(f'/api/clinical/reports/{rid}/sign', json={'physician': '林醫師', 'confirm_name': '林醫師', 'acknowledged': []}).json()['error']['code'] == 'CHECKLIST_REQUIRED'
    need = [i['key'] for i in client.get(f'/api/clinical/reports/{rid}').json()['checklist']]
    assert 'ai_unconfirmed' not in need
    signed = client.post(f'/api/clinical/reports/{rid}/sign', json={'physician': '林醫師', 'confirm_name': '林醫師', 'acknowledged': need}).json()
    assert signed['status'] == 'signed' and signed['versions'][0]['acknowledged'] == sorted(need)
    pdf_dir = workspace / '05_醫師端' / '03_報告' / f'DEMO-01_{exam_id}'
    first_pdf = (pdf_dir / '報告.pdf').read_bytes()
    assert first_pdf.startswith(b'%PDF') and client.get(f'/api/clinical/reports/{rid}/pdf').status_code == 200
    assert client.patch(f'/api/clinical/exams/{exam_id}/sides/left', json={'length_mm': 100}).json()['error']['code'] == 'EXAM_SIGNED'
    # 修訂 → 再簽核：資料夾裡只剩最新一份 PDF（D42），版本歷史還查得到
    client.post(f'/api/clinical/reports/{rid}/revise')
    client.put(f'/api/clinical/reports/{rid}', json={'payload': {'impression': '修訂：右腎稍小。'}})
    need = [i['key'] for i in client.get(f'/api/clinical/reports/{rid}').json()['checklist']]
    signed = client.post(f'/api/clinical/reports/{rid}/sign', json={'physician': '林醫師', 'confirm_name': '林醫師', 'acknowledged': need}).json()
    assert [p.name for p in pdf_dir.iterdir()] == ['報告.pdf'] and (pdf_dir / '報告.pdf').read_bytes() != first_pdf
    versions = signed['versions']
    assert [v['status'] for v in versions][:2] == ['signed', 'draft'] and signed['pdf']['version'] == signed['version']
    first_signed = next(v['version'] for v in reversed(versions) if v['status'] == 'signed')
    assert client.get(f'/api/clinical/reports/{rid}/versions/{first_signed}').json()['impression'] == '雙側腎臟大小正常。'
    # PDF 被外部改過：下載時發現
    (pdf_dir / '報告.pdf').write_bytes(b'%PDF-1.4 tampered')
    assert client.get(f'/api/clinical/reports/{rid}/pdf').json()['error']['code'] == 'PDF_CHANGED'
    # 已簽核報告不能移入回收桶，只能作廢；作廢覆蓋成作廢版
    assert client.post('/api/trash', json={'kind': 'clinical_exam', 'id': exam_id, 'reason': '測試'}).json()['error']['code'] == 'REPORT_SIGNED'
    assert client.post(f'/api/clinical/reports/{rid}/void', json={'reason': ''}).status_code == 422
    voided = client.post(f'/api/clinical/reports/{rid}/void', json={'reason': '病例代碼填錯'}).json()
    assert voided['status'] == 'void' and [p.name for p in pdf_dir.iterdir()] == ['報告.pdf']
    assert client.get(f'/api/clinical/reports/{rid}/pdf').status_code == 200

    # 病人趨勢與索引（不含姓名、病歷號）
    patients = client.get('/api/clinical/patients').json()['items']
    trend = client.get(f'/api/clinical/patients/{patients[0]["id"]}').json()
    assert trend['exams'][0]['sides']['right']['length_mm'] == 105.5
    from app.services import index

    assert index.refresh_clinical()
    csv_text = (workspace / '03_資料' / '09_索引' / '醫師端檢查.csv').read_text(encoding='utf-8-sig')
    assert exam_id in csv_text and 'DEMO-01' in csv_text

    # 轉入研究：人工指定 P-編號；同樣的影像不重複轉入
    assert client.post(f'/api/clinical/exams/{exam_id}/transfer', json={'patient_id': 'P-9999'}).json()['error']['code'] == 'PATIENT_REQUIRED'
    moved = client.post(f'/api/clinical/exams/{exam_id}/transfer', json={'patient_id': 'P-0001'}).json()
    from app.db.models_research import Batch, Image

    with session_scope('research') as db:
        assert db.get(Batch, moved['batch_id']).source_kind == 'clinical'
        assert db.query(Image).filter(Image.batch_id == moved['batch_id']).count() == moved['images']
    # 同樣的影像在研究端已經有了（示範影像本來就來自研究端），所以這裡是 0 張或全部略過
    assert moved['images'] + moved['skipped'] == 2

    # 回收桶：作廢後可以移入、還原、永久刪除（連檔案）
    assert client.post('/api/trash', json={'kind': 'clinical_exam', 'id': exam_id, 'reason': '展示結束'}).status_code == 201
    assert client.get(f'/api/clinical/exams/{exam_id}').status_code == 404
    assert client.get('/api/clinical/reports').json()['items'] == []
    entry = next(g for g in client.get('/api/trash').json()['groups'] if g['kind'] == 'clinical_exam')
    assert entry['kind_label'] == '醫師端檢查' and 'DEMO-01' in entry['label']
    assert client.post(f'/api/trash/{entry["id"]}/restore').status_code == 200
    assert client.get(f'/api/clinical/exams/{exam_id}').status_code == 200 and len(client.get('/api/clinical/reports').json()['items']) == 1
    client.post('/api/trash', json={'kind': 'clinical_exam', 'id': exam_id, 'reason': '展示結束'})
    entry = next(g for g in client.get('/api/trash').json()['groups'] if g['kind'] == 'clinical_exam')
    base = workspace / '05_醫師端'
    (base / '01_原始' / batch['batch_id'] / 'CI-orphan.png').write_bytes(b'x')  # 處理失敗、沒有影像紀錄的原始檔也要刪
    (base / '05_接收暫存' / batch['batch_id']).mkdir(parents=True, exist_ok=True)  # 沒傳完的暫存
    (base / '05_接收暫存' / batch['batch_id'] / '9.part').write_bytes(b'x')
    assert client.post(f'/api/trash/{entry["id"]}/purge', json={'confirm': '永久刪除'}).status_code == 200
    assert client.get('/api/clinical/patients').json()['items'] == []
    assert not (base / '05_接收暫存' / batch['batch_id']).exists()
    assert not [f for f in client.get('/api/feedback').json()['items'] if f['exam_id'] == exam_id]  # 研究端關於這筆檢查的回饋一起刪
    from app.data import storage
    from app.db.models_research import SourceMap

    with session_scope('research') as db:  # 已轉入研究的影像：原始檔在研究端的封存，醫師端刪掉也找得到
        assert all(storage.from_root(m.original_relpath).exists() for m in db.query(SourceMap).filter(SourceMap.batch_id == moved['batch_id']).all())
    assert not (base / '02_影像' / exam_id).exists() and not (base / '04_分析' / exam_id).exists() and not pdf_dir.exists()
    assert not (base / '01_原始' / batch['batch_id']).exists()
    client.post('/api/clinical/receiver/stop')


@pytest.mark.parametrize('raw,expected', [({'sex': '男', 'diabetes': '有'}, ('M', 'yes')), ({'sex': 'female', 'diabetes': None}, ('F', 'unknown'))])
def test_normalize_clinical(raw, expected):
    from app.clinical.exams import normalize_clinical

    out = normalize_clinical(**raw)
    assert (out['sex'], out['diabetes']) == expected
