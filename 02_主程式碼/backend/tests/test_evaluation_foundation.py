import importlib

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from backend.app.services.evaluation_metrics import classification_metrics,evaluation_label,foreground_counts,segmentation_metrics


def upgrade(engine):
    from pathlib import Path
    cfg=Config()
    cfg.set_main_option('script_location',str(Path(__file__).parents[1]/'app/db/migrations'))
    with engine.begin() as connection:
        cfg.attributes['connection']=connection
        command.upgrade(cfg,'head')


@pytest.mark.parametrize('legacy',[False,True])
def test_research_upgrade_new_or_validated_legacy_is_repeatable(tmp_path,legacy):
    from backend.app.db.migrations.legacy_schema import Base
    engine=create_engine(f'sqlite:///{tmp_path / "research.sqlite3"}')
    if legacy:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO settings(key,value_json,updated_at) VALUES('preserve','123','2020-01-01')"))
    upgrade(engine)
    upgrade(engine)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version'))=='research_0002'
        if legacy: assert connection.scalar(text("SELECT value_json FROM settings WHERE key='preserve'"))==123
        triggers=set(connection.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger'")))
        assert {'evaluation_input_immutable','evaluation_terminal_immutable','evaluation_prediction_terminal'}<=triggers
    # ORM schema and migration schema stay synchronized, including constraints.
    from backend.app.db.models import Base as CurrentBase
    reference=create_engine('sqlite://')
    CurrentBase.metadata.create_all(reference)
    signature=importlib.import_module('backend.app.db.migrations.versions.0001_research_baseline').signature
    for table in CurrentBase.metadata.tables:
        assert signature(engine,table)==signature(reference,table),table
    reference.dispose();engine.dispose()


def test_unrecognized_research_schema_is_not_blindly_stamped(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path / "bad.sqlite3"}')
    with engine.begin() as db: db.execute(text('CREATE TABLE datasets (id TEXT PRIMARY KEY)'))
    with pytest.raises(RuntimeError,match='baseline mismatch'): upgrade(engine)
    assert 'evaluation_records' not in inspect(engine).get_table_names()
    with engine.connect() as db:
        assert not db.scalar(text('SELECT version_num FROM alembic_version'))
    engine.dispose()


def test_dynamic_classification_metrics_defined_and_undefined():
    result=classification_metrics([0,0,1,2],[0,1,1,2],3)
    assert result['accuracy']==0.75
    assert result['confusion_matrix']==[[1,1,0],[0,1,0],[0,0,1]]
    assert result['macro_f1']==pytest.approx((2/3+2/3+1)/3)
    sparse=classification_metrics([0],[0],5)
    assert sparse['per_class'][4]['f1'] is None
    assert sparse['macro_defined_class_count']==1
    empty=classification_metrics([],[],2)
    assert empty['accuracy'] is None and empty['macro_f1'] is None
    assert [evaluation_label(index,2) for index in range(5)]==[0,0,0,1,1]
    assert [evaluation_label(index,3) for index in range(5)]==[0,0,1,2,2]
    assert [evaluation_label(index,5) for index in range(5)]==list(range(5))
    with pytest.raises(ValueError): classification_metrics([2],[0],2)


def test_foreground_metrics_empty_rules_and_no_silent_resize():
    empty=foreground_counts([[0,0]],[[0,0]])
    partial=foreground_counts([[1,1]],[[1,0]])
    result=segmentation_metrics([empty,partial])
    assert result['per_image']==[{'dice':1.0,'iou':1.0},{'dice':2/3,'iou':0.5}]
    assert result['micro_pixel_counts']=={'dice':2/3,'iou':0.5}
    assert segmentation_metrics([])['micro_pixel_counts']['dice'] is None
    with pytest.raises(ValueError,match='resizing'): foreground_counts([[0]],[[0,0]])
    with pytest.raises(ValueError,match='binary'): foreground_counts([[255]],[[1]])
