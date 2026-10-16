from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image


def image_bytes(color=(40, 80, 120), image_format="JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, image_format)
    return buffer.getvalue()


@pytest.fixture
def make_image():
    return image_bytes


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    models_dir = tmp_path / "models"
    monkeypatch.setenv("ISU_AI_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ISU_AI_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("ISU_AI_FRONTEND_DIST", str(tmp_path / "frontend-dist"))
    monkeypatch.setenv("ISU_AI_DATABASE_URL", f"sqlite:///{(data_dir / 'test.sqlite3').as_posix()}")

    from backend.app.core.config import get_settings
    from backend.app.db.session import reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    from backend.app.main import create_app

    with TestClient(create_app(testing=True)) as test_client:
        from backend.app.clinical.auth import _attempts
        _attempts.clear()
        test_client.headers['Origin']='http://testserver'
        headers={'X-Local-Init':'1'}
        challenge=test_client.get('/api/local-session/challenge',headers=headers)
        assert challenge.status_code==200
        login=test_client.post('/api/local-session',json={'challenge':challenge.json()['challenge']},headers=headers)
        assert login.status_code==200
        test_client.headers['X-CSRF-Token']=login.json()['csrf']
        yield test_client

    reset_engine_cache()
    get_settings.cache_clear()
