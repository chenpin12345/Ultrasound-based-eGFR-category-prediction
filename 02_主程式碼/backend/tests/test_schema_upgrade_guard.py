import json
import pytest


@pytest.fixture
def layout(tmp_path,monkeypatch):
    from backend.app.core.config import get_settings
    from backend.app.db.session import init_db,reset_engine_cache
    from backend.app.clinical import store
    for field in ('data','models','clinical','reports','runtime','reference_features'):
        monkeypatch.setenv('ISU_AI_'+field.upper()+'_DIR',str(tmp_path/field))
    monkeypatch.setenv('ISU_AI_DATABASE_URL','sqlite:///'+(tmp_path/'data/isu_ai.sqlite3').as_posix())
    monkeypatch.setenv('ISU_AI_REQUIRE_EXISTING_DATABASES','false')
    get_settings.cache_clear();reset_engine_cache()
    init_db();store.migrate()
    yield get_settings()
    reset_engine_cache();get_settings.cache_clear()


def prepare(settings,tmp_path,monkeypatch):
    from scripts import workspace_backup as backup,upgrade_three_zones as upgrade
    monkeypatch.setattr(backup,'offline',lambda settings:None)
    monkeypatch.setattr(upgrade,'offline',lambda settings:None)
    # Isolated database roots, with no server or production data.
    source=tmp_path/'source-backup';backup.backup(source,settings,'full')
    code=tmp_path/'paired-code';code.mkdir()
    (code/'sentinel.py').write_text('# isolated code backup\n',encoding='utf-8')
    (code/'source-manifest.json').write_text(json.dumps({'sentinel.py':backup.sha(code/'sentinel.py')}))
    return settings,source,code,upgrade


def test_verified_upgrade_is_repeatable_and_preserves_rows(layout,tmp_path,monkeypatch):
    settings,source,code,upgrade=prepare(layout,tmp_path,monkeypatch)
    first=upgrade.upgrade(settings,source,code,tmp_path/'first')
    assert first['passed'] and first['revisions']['clinical']=='0011'  # current head (0011: default plans, case versions)
    assert upgrade.upgrade(settings,source,code,tmp_path/'second')['passed']
    assert not (settings.runtime_dir/'schema-upgrade-journal.json').exists()
    assert not (settings.runtime_dir/'maintenance-operation.json').exists()


def test_upgrade_failure_leaves_marker_that_blocks_new_startup(layout,tmp_path,monkeypatch):
    settings,source,code,upgrade=prepare(layout,tmp_path,monkeypatch)
    def fail():raise RuntimeError('injected migration failure')
    monkeypatch.setattr(upgrade,'migrate_databases',fail)
    with pytest.raises(RuntimeError,match='injected'):upgrade.upgrade(settings,source,code,tmp_path/'failed')
    assert json.loads((settings.runtime_dir/'schema-upgrade-journal.json').read_text(encoding='utf-8'))['phase']=='failed'
    with pytest.raises(RuntimeError,match='upgrade is incomplete'):settings.ensure_directories()


def test_changed_live_data_requires_new_backup(layout,tmp_path,monkeypatch):
    settings,source,code,upgrade=prepare(layout,tmp_path,monkeypatch)
    (settings.models_dir/'new-artifact.bin').write_bytes(b'new data')
    with pytest.raises(ValueError,match='inventory differs'):upgrade.upgrade(settings,source,code,tmp_path/'rejected')
    assert not (settings.runtime_dir/'schema-upgrade-journal.json').exists()
