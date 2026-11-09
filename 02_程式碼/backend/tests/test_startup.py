"""網頁請求不載入 PyTorch（M2.5 #108）：PyTorch 連同 CUDA 函式庫約 2 GB，第一次載入要很久，只有訓練與推論才需要。
在新的 Python 程序裡檢查（測試程序本身早就因為訓練測試載入過 PyTorch）。"""

from __future__ import annotations

import subprocess
import sys

from tests.conftest import BACKEND
from tests.test_egfr import cohort  # noqa: F401  共用 20 位合成病人

SCRIPT = """
import sys
from tests.conftest import _open_client

raw, c = _open_client()  # 含啟動流程：遷移、註冊背景工作、說明檔、索引
for url in ('/api/training/tasks', '/api/training/runs?task=egfr', '/api/egfr/options', '/api/egfr/comparisons', '/api/mask-sets', '/api/features', '/api/models?task=egfr', '/api/pretrained'):
    assert c.get(url).status_code == 200, url
from app.ml import baseline, egfr_compare, masksets, registry, runs  # noqa: F401
from app.ml.defaults import full_config, seg_output_dir

assert full_config('egfr', {'egfr_classes': 3})['head'] == 'corn'
seg_output_dir('RUN-x')
raw.__exit__(None, None, None)
print('torch' in sys.modules)
"""


def test_web_requests_do_not_load_torch(workspace):
    out = subprocess.run([sys.executable, '-c', SCRIPT], cwd=BACKEND, capture_output=True, text=True, encoding='utf-8', timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == 'False', out.stdout


ACTIONS = """
import sys
from tests.conftest import _open_client

version, split = sys.argv[1], sys.argv[2]
raw, c = _open_client()
group = c.post('/api/egfr/comparisons', json={'dataset_version_id': version, 'split_id': split, 'inputs': ['image', 'clinical'], 'classes': [2, 5], 'start': False}).json()
run = group['members'][0]['run_id']
seg = c.post('/api/training/runs', json={'task': 'segmentation', 'dataset_version_id': version, 'split_id': split, 'config': {}, 'start': False}).json()['id']
for url in (f"/api/egfr/comparisons/{group['id']}", f'/api/training/runs/{run}', f'/api/training/runs/{seg}', f"/api/egfr/test-readiness?experiment_ids={group['id']}",
            '/api/training/learning-curve', '/api/overview', '/api/annotation/tasks', '/api/annotation/queue/mask?rater=', '/api/images?limit=60', '/api/patients',
            '/api/circling/batches', '/api/system/folder-migration', '/api/jobs', '/api/trash'):
    assert c.get(url).status_code == 200, url
gid = c.post('/api/training/runs/trash', json={'run_ids': [seg, run]}).json()['group_id']
assert c.post(f'/api/trash/{gid}/purge', json={'confirm': '永久刪除'}).json()['ok']
raw.__exit__(None, None, None)
print('torch' in sys.modules)
"""


def test_page_actions_do_not_load_torch(cohort):  # noqa: F811
    """建立比較組與訓練草稿、開訓練詳細、測試就緒、移入回收桶與永久刪除：都不該載入 PyTorch。"""
    out = subprocess.run([sys.executable, '-c', ACTIONS, cohort['version'], cohort['split']], cwd=BACKEND, capture_output=True, text=True, encoding='utf-8', timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == 'False', out.stdout
