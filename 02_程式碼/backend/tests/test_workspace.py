"""M2.5 階段 A：移除影像品質、索引、說明檔、遮罩分桶、空資料夾清理、依任務搬移資料夾、開啟資料夾。"""

from __future__ import annotations

import csv
import json

import pytest


def test_quality_task_removed(client):
    tasks = [t['id'] for t in client.get('/api/training/tasks').json()['tasks']]
    assert tasks == ['segmentation', 'egfr', 'grade']
    assert [t['id'] for t in client.get('/api/annotation/tasks').json()['tasks']] == ['mask', 'grade', 'side']
    r = client.post('/api/training/runs', json={'task': 'quality', 'dataset_version_id': 'x', 'split_id': 'y', 'start': False})
    assert r.status_code == 422


def test_quality_label_rejected(imported_client):
    image_id = imported_client.get('/api/images').json()['images'][0]['id']
    r = imported_client.put(f'/api/annotation/labels/{image_id}', json={'kind': 'quality', 'value': {'quality': '可用'}})
    assert r.status_code == 422
    ok = imported_client.put(f'/api/annotation/labels/{image_id}', json={'kind': 'side', 'value': {'side': 'left', 'view': 'long'}})
    assert ok.status_code == 200


def test_mask_files_sharded_without_names(imported_client, workspace):
    image_id = imported_client.get('/api/images').json()['images'][0]['id']
    shapes = [{'structure': 'parenchyma', 'type': 'polygon', 'points': [[10, 10], [60, 10], [60, 60], [10, 60]]}]
    assert imported_client.put(f'/api/annotation/masks/{image_id}', json={'shapes': shapes, 'flags': {}, 'status': 'done'}).status_code == 200
    files = list((workspace / '03_資料' / '03_人工標註' / '遮罩').rglob('*.png'))
    assert len(files) == 1
    assert files[0].parent.parent.name == image_id.split('-', 1)[1][:2]  # 分桶
    assert files[0].name == 'v001_manual.png'  # 檔名不含操作者姓名


def test_index_has_no_phi_and_readmes(imported_client, workspace):
    from app.data.patients import egfr_group
    from app.db.models_research import Image, Patient
    from app.db.session import session_scope
    from app.services import index, workspace as ws

    with session_scope('research') as db:
        db.add(Patient(id='P-0001', source_ref='r1', sex='F', age=70, has_diabetes=True, egfr=47.3, created_at='2026-10-29'))
    with session_scope('research') as db:
        img = db.query(Image).first()
        img.patient_id = 'P-0001'
        image_id = img.id
    result = index.refresh()
    assert '影像索引.csv' in result['written'] and not result['skipped']
    folder = workspace / '03_資料' / '09_索引'
    rows = list(csv.reader((folder / '影像索引.csv').open(encoding='utf-8-sig')))
    row = next(r for r in rows if r[0] == image_id)
    assert row[1] == 'P-0001' and row[2] == egfr_group(47.3)
    text = '\n'.join((folder / name).read_text(encoding='utf-8-sig') for name in result['written'])
    assert '47.3' not in text  # 不寫 eGFR 數值
    for name in ('eGFR訓練索引.csv', '分割訓練索引.csv', '回音分級訓練索引.csv', '遮罩索引.csv', '評估索引.csv'):
        assert (folder / name).exists()
    ws.ensure_readmes()
    assert (folder / '說明.txt').exists()
    assert (workspace / '03_資料' / '01_原始封存' / '說明.txt').read_text(encoding='utf-8').startswith('受限區')


def test_cleanup_only_removes_empty_mask_dirs(workspace, client):
    from app.services.workspace import cleanup_empty_mask_dirs

    root = workspace / '03_資料' / '03_人工標註' / '遮罩'
    (root / 'IMG-AAAA').mkdir(parents=True)
    (root / 'AB' / 'IMG-ABCD').mkdir(parents=True)
    keep = root / 'CD' / 'IMG-CDEF'
    keep.mkdir(parents=True)
    (keep / 'v001_manual.png').write_bytes(b'x')
    assert cleanup_empty_mask_dirs() == 3  # IMG-AAAA、IMG-ABCD、AB
    assert keep.exists() and (keep / 'v001_manual.png').exists()
    assert not (root / 'IMG-AAAA').exists() and not (root / 'AB').exists()


def test_folder_migration_moves_old_runs(client, workspace):
    from app.db.models_research import DatasetVersion, Evaluation, Split, TrainingRun
    from app.db.session import session_scope

    old = workspace / '04_模型' / '01_訓練紀錄' / 'RUN-20261024-001'
    (old / 'fold-1').mkdir(parents=True)
    (old / 'summary.json').write_text('{}', encoding='utf-8')
    old_eval = workspace / '04_模型' / '03_評估' / 'EVAL-20261024-001'
    old_eval.mkdir(parents=True)
    (old_eval / 'report.json').write_text('{}', encoding='utf-8')
    with session_scope('research') as db:
        db.add(Split(id='split-0001', method='stratified', seed=42, folds=5, test_ratio=0.2, stratify_by='egfr_group', sha256='x', created_at='2026-10-24'))
        db.add(DatasetVersion(id='dsv-0001', image_count=0, patient_count=0, manifest_sha256='x', created_at='2026-10-24'))
    with session_scope('research') as db:
        db.add(TrainingRun(id='RUN-20261024-001', task='egfr', name='R18 random', split_id='split-0001', dataset_version_id='dsv-0001',
                           config_json=json.dumps({'arch': 'resnet18'}), status='completed', summary_json=json.dumps({'mean_best_score': 0.75}),
                           relpath='04_模型/01_訓練紀錄/RUN-20261024-001', created_by='t', created_at='2026-10-24'))
    with session_scope('research') as db:
        db.add(Evaluation(id='EVAL-20261024-001', run_id='RUN-20261024-001', target='oof', metrics_json=json.dumps({'task': 'egfr'}),
                          relpath='04_模型/03_評估/EVAL-20261024-001', created_by='t', created_at='2026-10-24'))
    preview = client.get('/api/system/folder-migration').json()
    targets = {p['id']: p['to'] for p in preview['items']}
    assert targets['RUN-20261024-001'] == '04_模型/01_訓練紀錄/eGFR/RUN-20261024-001_R18_random'
    assert targets['EVAL-20261024-001'] == '04_模型/03_評估/eGFR/EVAL-20261024-001_RUN-20261024-001'
    result = client.post('/api/system/folder-migration').json()
    assert result['moved'] == 2 and not result['skipped']
    new = workspace / '04_模型' / '01_訓練紀錄' / 'eGFR' / 'RUN-20261024-001_R18_random'
    assert (new / 'fold-1').is_dir() and (new / '摘要.txt').exists() and not old.exists()
    with session_scope('research') as db:
        assert db.get(TrainingRun, 'RUN-20261024-001').relpath.endswith('eGFR/RUN-20261024-001_R18_random')
    from app.ml.paths import eval_dir, run_dir

    assert run_dir('RUN-20261024-001') == new
    assert (eval_dir('EVAL-20261024-001') / 'report.json').exists()
    assert client.get('/api/system/folder-migration').json()['count'] == 0


def test_new_runs_use_task_folders(workspace):
    from app.ml.paths import model_dir, new_eval_dir, new_run_dir

    assert new_run_dir('RUN-20261101-001', 'segmentation', '第一輪 100 張').as_posix().endswith('01_訓練紀錄/分割/RUN-20261101-001_第一輪_100_張')
    assert model_dir('egfr', 'r34', '1.0.0').as_posix().endswith('02_模型庫/eGFR/r34@1.0.0')
    assert new_eval_dir('EVAL-1', 'grade', 'grade-corn@1.0.0').as_posix().endswith('03_評估/回音分級/EVAL-1_grade-corn@1.0.0')


@pytest.mark.parametrize('kind,obj,status', [('relpath', '03_資料/01_原始封存', 403), ('relpath', '07_備份', 403), ('relpath', '../', 403), ('index', '', 200), ('run', 'RUN-NONE', 404)])
def test_open_folder_rules(client, workspace, kind, obj, status):
    (workspace / '03_資料' / '01_原始封存').mkdir(parents=True, exist_ok=True)
    (workspace / '03_資料' / '09_索引').mkdir(parents=True, exist_ok=True)
    (workspace / '07_備份').mkdir(parents=True, exist_ok=True)
    r = client.post('/api/system/open-folder', json={'kind': kind, 'id': obj})
    assert r.status_code == status, r.text
