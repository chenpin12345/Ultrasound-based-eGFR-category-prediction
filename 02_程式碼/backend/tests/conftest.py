"""測試共用：每個測試都在暫存資料夾建立一個獨立的工作區，不會碰到真實的 IMG_original 或 03_資料。"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REAL_ROOT = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch):
    shutil.copy(REAL_ROOT / 'workspace-layout.json', tmp_path / 'workspace-layout.json')
    (tmp_path / 'IMG_original').mkdir()
    monkeypatch.setenv('KIDNEY_WORKSPACE_ROOT', str(tmp_path))
    monkeypatch.setenv('KIDNEY_TESTING', '1')
    monkeypatch.setenv('KIDNEY_SSE_POLL', '0.05')
    from app.core.config import reset_settings
    from app.db.session import dispose_all
    from app.jobs.manager import reset_manager

    reset_settings()
    dispose_all()
    reset_manager()
    from app.clinical import models_cache

    models_cache.clear()  # 醫師端的模型快取是整個程序共用的，每個測試從空的開始
    yield tmp_path
    reset_manager(wait=True)
    dispose_all()
    reset_settings()


class Client:
    """包住 TestClient：自動建立本機工作階段，寫入時帶 CSRF token 與操作者。"""

    def __init__(self, raw, csrf: str, operator: str = '測試人員'):
        self.raw, self.csrf, self.operator = raw, csrf, operator

    def _headers(self, extra=None):
        from urllib.parse import quote

        h = {'x-csrf-token': self.csrf, 'x-operator': quote(self.operator)}
        h.update(extra or {})
        return h

    def get(self, url, **kw):
        return self.raw.get(url, **kw)

    def post(self, url, **kw):
        return self.raw.post(url, headers=self._headers(kw.pop('headers', None)), **kw)

    def put(self, url, **kw):
        return self.raw.put(url, headers=self._headers(kw.pop('headers', None)), **kw)

    def patch(self, url, **kw):
        return self.raw.patch(url, headers=self._headers(kw.pop('headers', None)), **kw)


def _open_client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(testing=True)
    raw = TestClient(app)
    raw.__enter__()
    h = {'x-local-init': '1', 'origin': 'http://testserver'}
    challenge = raw.get('/api/session/challenge', headers=h).json()['challenge']
    csrf = raw.post('/api/session', json={'challenge': challenge}, headers=h).json()['csrf']
    return raw, Client(raw, csrf)


@pytest.fixture()
def client(workspace):
    raw, c = _open_client()
    yield c
    raw.__exit__(None, None, None)


IMPORTED_DIRS = ('IMG_original', '03_資料')


@pytest.fixture(scope='session')
def imported_template(tmp_path_factory):
    """整個測試只做一次真正的匯入（OCR 很慢），之後每個測試複製這份結果。"""
    from tests import synthetic

    root = tmp_path_factory.mktemp('imported')
    shutil.copy(REAL_ROOT / 'workspace-layout.json', root / 'workspace-layout.json')
    names = synthetic.make_dataset(root / 'IMG_original')
    saved = {k: os.environ.get(k) for k in ('KIDNEY_WORKSPACE_ROOT', 'KIDNEY_TESTING')}
    os.environ['KIDNEY_WORKSPACE_ROOT'], os.environ['KIDNEY_TESTING'] = str(root), '1'
    from app.core.config import reset_settings
    from app.db.session import dispose_all
    from app.jobs.manager import reset_manager

    reset_settings(), dispose_all(), reset_manager()
    raw, c = _open_client()
    job = c.post('/api/imports', json={'source': 'original'}).json()['job_id']
    wait_job(job)
    assert c.get(f'/api/jobs/{job}').json()['status'] == 'completed'
    raw.__exit__(None, None, None)
    reset_manager(wait=True), dispose_all(), reset_settings()
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return root, names


@pytest.fixture()
def imported_client(workspace, imported_template):
    """已匯入 8 張假影像（四種版面各 2 張）的工作區。"""
    template, _ = imported_template
    for name in IMPORTED_DIRS:
        shutil.rmtree(workspace / name, ignore_errors=True)
        shutil.copytree(template / name, workspace / name)
    raw, c = _open_client()
    yield c
    raw.__exit__(None, None, None)


def wait_job(job_id: str, timeout: float = 900):
    from app.jobs.manager import get_manager

    get_manager().wait(job_id, timeout)


@pytest.fixture()
def synthetic_original(workspace):
    from tests import synthetic

    return synthetic.make_dataset(workspace / 'IMG_original')


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


os.environ.setdefault('KIDNEY_TESTING', '1')
