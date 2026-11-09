"""訓練移入回收桶與永久刪除（M2.5 #109）：資料列、檔案、空資料夾都要清掉。只用合成資料。"""

from __future__ import annotations

from tests.test_egfr import _run, cohort  # noqa: F401  共用 20 位合成病人
from tests.test_training import TINY, research  # noqa: F401  分割訓練用（含已確認的遮罩）


def test_trash_restore_and_purge_runs_with_models_and_files(cohort, workspace):  # noqa: F811
    from app.core.config import get_settings
    from app.db.models_research import Evaluation, ModelEntry, TrainingRun
    from app.db.session import session_scope
    from app.ml.paths import eval_dir, run_dir

    client = cohort['client']
    cnn, _ = _run(cohort, {**TINY, 'epochs': 1}, name='影像')
    base, _ = _run(cohort, {'arch': 'logreg', 'inputs': ['clinical'], 'egfr_classes': 2}, name='純臨床')
    ev = client.post(f'/api/training/runs/{cnn}/evaluate').json()['id']
    model = client.post('/api/models', json={'run_id': cnn, 'name': 'trash-test', 'version': '1.0.0'}).json()['id']
    group = client.post('/api/egfr/comparisons', json={'dataset_version_id': cohort['version'], 'split_id': cohort['split'], 'inputs': ['clinical'], 'classes': [2], 'start': False}).json()
    assert group['members'][0]['run_id'] == base  # 沿用
    root = get_settings().root
    with session_scope('research') as db:
        model_dir = root / db.get(ModelEntry, model).relpath
    folders = [run_dir(cnn), run_dir(base), eval_dir(ev), model_dir]
    assert all(f.exists() for f in folders)

    # 移入回收桶：訓練與註冊的模型同一組；清單、詳細頁都看不到；比較組顯示找不到
    moved = client.post('/api/training/runs/trash', json={'run_ids': [cnn, base], 'reason': '測試'})
    assert moved.status_code == 201 and moved.json()['models'] == [model]
    assert {r['id'] for r in client.get('/api/training/runs?task=egfr').json()['runs']}.isdisjoint({cnn, base})
    assert client.get(f'/api/training/runs/{cnn}').status_code == 404
    assert model not in {m['id'] for m in client.get('/api/models?task=egfr').json()['models']}
    assert client.get(f"/api/egfr/comparisons/{group['id']}").status_code == 404  # 比較組的訓練都移入了：比較組也一起移入
    assert all(f.exists() for f in folders)  # 回收桶裡檔案都還在
    groups = client.get('/api/trash?kind=run').json()['groups']
    assert len(groups) == 1 and '含註冊的模型 1 個' in groups[0]['label']

    # 還原後全部回來，再移入一次後永久刪除
    assert client.post(f"/api/trash/{groups[0]['id']}/restore").json()['ok']
    assert client.get(f'/api/training/runs/{cnn}').status_code == 200 and client.get(f'/api/models/{model}').status_code == 200
    assert client.get(f"/api/egfr/comparisons/{group['id']}").status_code == 200
    gid = client.post('/api/training/runs/trash', json={'run_ids': [cnn, base]}).json()['group_id']
    out = client.post(f'/api/trash/{gid}/purge', json={'confirm': '永久刪除'}).json()
    assert out['ok'] and len(out['removed']) >= 4
    assert not any(f.exists() for f in folders)
    assert all(f.parent.exists() for f in folders)  # 只刪物件自己的資料夾；01_訓練紀錄/eGFR 等標準資料夾保留（開啟資料夾按鈕會用到）
    with session_scope('research') as db:
        assert db.get(TrainingRun, cnn) is None and db.get(TrainingRun, base) is None and db.get(ModelEntry, model) is None
        assert db.query(Evaluation).filter(Evaluation.id == ev).count() == 0
        from app.db.models_research import Experiment

        assert db.get(Experiment, group['id']) is None  # 比較組的訓練都刪了：比較組也刪除


def test_trash_runs_refuses_active_runs_and_purges_split_files_only_when_unused(cohort, workspace):  # noqa: F811
    from app.core.config import get_settings
    from app.db.models_research import TrainingRun
    from app.db.session import session_scope

    client = cohort['client']
    run, _ = _run(cohort, {'arch': 'logreg', 'inputs': ['clinical'], 'egfr_classes': 2})
    with session_scope('research') as db:
        db.get(TrainingRun, run).status = 'running'
    assert client.post('/api/training/runs/trash', json={'run_ids': [run]}).json()['error']['code'] == 'RUN_ACTIVE'
    assert client.post('/api/training/runs/trash', json={'run_ids': []}).status_code == 422
    with session_scope('research') as db:
        db.get(TrainingRun, run).status = 'completed'

    # 切分與資料集版本：還有訓練使用時不能永久刪除；訓練刪掉後，永久刪除會連檔案一起刪
    settings = get_settings()
    split_file = settings.path('splits') / f"{cohort['split']}.json"
    version_dir = settings.path('dataset_versions') / cohort['version']
    assert split_file.exists() and version_dir.exists()
    split_group = client.post('/api/trash', json={'kind': 'split', 'id': cohort['split']}).json()['group_id']
    blocked = client.post(f'/api/trash/{split_group}/purge', json={'confirm': '永久刪除'}).json()
    assert blocked['error']['code'] == 'IN_USE' and split_file.exists()
    run_group = client.post('/api/training/runs/trash', json={'run_ids': [run]}).json()['group_id']
    client.post(f'/api/trash/{run_group}/purge', json={'confirm': '永久刪除'})
    assert client.post(f'/api/trash/{split_group}/purge', json={'confirm': '永久刪除'}).json()['ok']
    assert not split_file.exists()
    version_group = client.post('/api/trash', json={'kind': 'dataset_version', 'id': cohort['version']}).json()['group_id']
    assert client.post(f'/api/trash/{version_group}/purge', json={'confirm': '永久刪除'}).json()['ok']
    assert not version_dir.exists()


def test_seg_run_takes_mask_sets_and_feature_sets_and_locked_files_stop_purge(research, workspace):  # noqa: F811
    """分割訓練連同遮罩組、特徵集一起刪；用到它們的訓練要一起勾；有檔案被開著時什麼都不刪（2026-11-09）。"""
    from app.db.models_research import FeatureSet, MaskSet, TrainingRun
    from app.db.session import session_scope
    from app.features.service import folder as feature_folder
    from app.ml import masksets
    from app.ml.defaults import seg_output_dir
    from app.ml.paths import run_dir
    from app.ml.runs import create
    from tests.conftest import wait_job
    from tests.test_masksets import _seg_run

    client = research['client']
    seg = _seg_run(research)
    created = client.post('/api/mask-sets', json={'seg_run_id': seg}).json()
    wait_job(created['job_id'])
    ms = created['id']
    fs = client.get(f"/api/jobs/{created['job_id']}").json()['result']['feature_set_id']
    with session_scope('research') as db:
        wait_job(db.get(FeatureSet, fs).job_id)
    egfr = create('egfr', '遮罩通道', research['version'], research['split'], {**TINY, 'epochs': 1, 'inputs': ['image', 'mask_channels'], 'mask_set_id': ms},
                  '測試', start=False)['id']
    folders = [run_dir(seg), masksets.folder(ms), feature_folder(fs), run_dir(egfr)]
    assert all(f.exists() for f in folders)
    folders.append(seg_output_dir(seg))  # OOF 預測遮罩（有產生時）也要刪掉

    blocked = client.post('/api/training/runs/trash', json={'run_ids': [seg]}).json()
    assert blocked['error']['code'] == 'RUN_IN_USE' and egfr in blocked['error']['message']
    moved = client.post('/api/training/runs/trash', json={'run_ids': [seg, egfr]}).json()
    assert moved['mask_sets'] == [ms] and moved['feature_sets'] == [fs]
    assert ms not in {m['id'] for m in client.get('/api/mask-sets').json()['mask_sets']}
    assert fs not in {f['id'] for f in client.get('/api/features').json()['feature_sets']}
    assert client.get(f'/api/features/{fs}').status_code == 404

    # 還原：遮罩組、特徵集一起回來
    assert client.post(f"/api/trash/{moved['group_id']}/restore").json()['ok']
    assert ms in {m['id'] for m in client.get('/api/mask-sets').json()['mask_sets']}
    gid = client.post('/api/training/runs/trash', json={'run_ids': [seg, egfr]}).json()['group_id']

    # 有檔案被開著：什麼都不刪（資料庫和檔案都還在）
    locked = next(masksets.folder(ms).rglob('*.png'))
    handle = locked.open('rb')
    try:
        out = client.post(f'/api/trash/{gid}/purge', json={'confirm': '永久刪除'}).json()
    finally:
        handle.close()
    assert out['error']['code'] == 'FILE_IN_USE'
    assert all(f.exists() for f in folders[:4])
    with session_scope('research') as db:
        assert db.get(MaskSet, ms) is not None and db.get(TrainingRun, seg) is not None

    out = client.post(f'/api/trash/{gid}/purge', json={'confirm': '永久刪除'}).json()
    assert out['ok'] and not any(f.exists() for f in folders)
    assert not any('.deleting-' in p.name for p in workspace.rglob('*'))  # 沒有留下改名中的暫存
    with session_scope('research') as db:
        assert db.get(MaskSet, ms) is None and db.get(FeatureSet, fs) is None and db.get(TrainingRun, seg) is None and db.get(TrainingRun, egfr) is None


def test_purging_primary_split_clears_setting(cohort, workspace):  # noqa: F811
    client = cohort['client']
    extra = client.post('/api/splits', json={'seed': 9, 'folds': 2, 'test_ratio': 0.2}).json()['id']
    assert client.put('/api/settings', json={'primary_split_id': extra}).status_code == 200
    client.post('/api/trash', json={'kind': 'split', 'id': extra, 'reason': ''})
    gid = next(g['id'] for g in client.get('/api/trash?kind=split').json()['groups'])
    assert client.post(f'/api/trash/{gid}/purge', json={'confirm': '永久刪除'}).json()['ok']
    assert client.get('/api/settings').json()['primary_split_id'] is None
