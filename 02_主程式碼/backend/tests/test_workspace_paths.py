from pathlib import Path

import pytest

from backend.app.core.config import AppSettings
from workspace_paths import WORKSPACE_ROOT


def test_default_layout_does_not_depend_on_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = AppSettings(_env_file=None)
    assert settings.project_root == WORKSPACE_ROOT / '02_主程式碼'
    assert settings.data_dir == WORKSPACE_ROOT / '03_模型與影像資料/research/data'
    assert settings.clinical_dir == WORKSPACE_ROOT / '03_模型與影像資料/clinical'
    assert settings.reports_dir == WORKSPACE_ROOT / '04_醫師報告'


def test_explicit_legacy_data_override_keeps_test_clinical_isolated(tmp_path):
    settings = AppSettings(data_dir=tmp_path / 'data', _env_file=None)
    assert settings.clinical_dir == tmp_path / 'data/clinical'
    assert settings.reports_dir == tmp_path / 'data/clinical/reports'
    assert settings.runtime_dir == tmp_path / 'data/runtime'
    assert not settings.require_existing_databases


def test_relative_override_is_workspace_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = AppSettings(data_dir='relative-data', _env_file=None)
    assert settings.data_dir == WORKSPACE_ROOT / 'relative-data'


def test_missing_existing_database_is_not_silently_initialized(tmp_path, monkeypatch):
    # The production migration lock is deliberately active during development.
    # This test owns a separate workspace and must not consume that lock.
    monkeypatch.setattr('backend.app.core.config.WORKSPACE_ROOT', tmp_path)
    settings = AppSettings(data_dir=tmp_path / 'missing', require_existing_databases=True, _env_file=None)
    with pytest.raises(RuntimeError, match='refusing empty initialization'):
        settings.ensure_directories()
    assert not (tmp_path / 'missing').exists()


def test_migration_lock_blocks_new_installation(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.app.core.config.WORKSPACE_ROOT', tmp_path)
    marker = tmp_path / '.maintenance/migration-in-progress.json'
    marker.parent.mkdir(); marker.write_text('{}')
    settings = AppSettings(data_dir=tmp_path / 'data', require_existing_databases=True, _env_file=None)
    with pytest.raises(RuntimeError, match='migration is not yet validated'):
        settings.ensure_directories()


@pytest.mark.parametrize('kind,exam,report,version', [
    ('other', 'abc', 'def', 1), ('demo', '../escape', 'def', 1),
    ('demo', 'abc', 'C:/secret', 1), ('demo', 'abc', 'def', 0),
    ('patient', 'abc', 'def', True),
])
def test_report_resolver_rejects_unsafe_identifiers(kind, exam, report, version):
    from backend.app.clinical.reports import artifact_path
    from backend.app.core.errors import AppError
    with pytest.raises(AppError):
        artifact_path(kind, exam, report, version)


def test_pdf_root_is_separate_and_not_public(client):
    from backend.app.clinical.reports import artifact_path
    from backend.app.core.config import get_settings
    path = artifact_path('demo', 'exam1', 'report1', 2)
    assert path == get_settings().reports_dir / 'demo/exam1/report1/v2.pdf'
    assert artifact_path('demo', 'exam1', 'report1', 2, True) != path
    assert client.get('/api/clinical/reports/report1/versions/2/pdf').status_code == 404
    assert client.get('/reports/demo/exam1/report1/v2.pdf').status_code == 404
