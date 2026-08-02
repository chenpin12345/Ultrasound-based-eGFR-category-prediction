from __future__ import annotations

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.db.models import Dataset, DatasetSample, Job, JobEvent


def test_schema_relationships_and_event_cursor(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'db.sqlite3').as_posix()}")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        dataset = Dataset(name="資料集", root_path="datasets/d1")
        db.add(dataset)
        db.flush()
        sample = DatasetSample(
            dataset_id=dataset.id, relative_path="images/a.jpg", display_name="a.jpg", stored_name="a.jpg",
            sha256="a" * 64, mime_type="image/jpeg", size_bytes=3, width=1, height=1,
        )
        job = Job(kind="process", workspace_path="jobs/j1")
        db.add_all([sample, job])
        db.flush()
        db.add_all([
            JobEvent(job_id=job.id, event_type="queued", data_json={}),
            JobEvent(job_id=job.id, event_type="progress", data_json={"progress": 50}),
        ])
        db.commit()
        events = db.scalars(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.id)).all()
        assert events[1].id > events[0].id
        db.delete(dataset)
        db.commit()
        assert db.get(DatasetSample, sample.id) is None
