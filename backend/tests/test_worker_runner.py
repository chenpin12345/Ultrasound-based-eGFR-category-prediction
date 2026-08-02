from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.db.models import Dataset, DatasetSample, Job, JobEvent, TrainingJob
from backend.app.workers.manager import WorkerManager
from backend.app.workers.runner import _dispatch_general, _resolve_inputs, _safe_resolve, _set_job_running


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'worker.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_runner_resolves_samples_relative_to_dataset_root(tmp_path):
    factory = _factory(tmp_path)
    data_root = tmp_path / "data"
    image = data_root / "datasets" / "d1" / "images" / "a.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    with factory() as session:
        dataset = Dataset(id="d1", name="dataset", root_path="datasets/d1")
        sample = DatasetSample(
            id="s1",
            dataset_id="d1",
            relative_path="images/a.jpg",
            display_name="a.jpg",
            stored_name="a.jpg",
            sha256="a" * 64,
            mime_type="image/jpeg",
            size_bytes=5,
            width=1,
            height=1,
        )
        session.add_all([dataset, sample])
        session.commit()
    manager = type("Manager", (), {"data_root": data_root.resolve(), "session_factory": factory})()
    assert _resolve_inputs(manager, {"dataset_id": "d1"}) == [image.resolve()]


def test_set_running_uses_job_kind_as_operation_and_persists_event(tmp_path):
    factory = _factory(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    with factory() as session:
        session.add(Job(id="j1", kind="features", status="queued", workspace_path="jobs/j1"))
        session.commit()
    manager = type("Manager", (), {"data_root": data_root.resolve(), "session_factory": factory})()
    config, workspace = _set_job_running(manager, "j1")
    assert config["operation"] == "features"
    assert workspace == (data_root / "jobs" / "j1").resolve()
    with factory() as session:
        assert session.get(Job, "j1").status == "running"
        event = session.scalar(select(JobEvent).where(JobEvent.job_id == "j1"))
        assert event.event_type == "started"
        assert event.data_json["status"] == "running"


def test_mask_dispatch_creates_workspace_scoped_preview_pairs(tmp_path, monkeypatch):
    data_root = (tmp_path / "data").resolve()
    models_root = (tmp_path / "models").resolve()
    workspace = data_root / "jobs" / "j1"
    source = workspace / "input" / "scan.jpg"
    model = models_root / "unet.pth"
    source.parent.mkdir(parents=True)
    model.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    model.write_bytes(b"weights")

    def fake_generate(inputs, **kwargs):
        assert inputs == [source]
        target = kwargs["output_root"] / "scan.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mask")
        return [target]

    import backend.app.ml.segmentation as segmentation

    monkeypatch.setattr(segmentation, "generate_masks", fake_generate)
    manager = type(
        "Manager",
        (),
        {
            "data_root": data_root,
            "models_root": models_root,
            "features_root": (tmp_path / "features").resolve(),
        },
    )()
    result = _dispatch_general(
        manager,
        "j1",
        {
            "operation": "masks",
            "input_paths": ["jobs/j1/input/scan.jpg"],
            "model_path": "unet.pth",
            "refine": False,
        },
        workspace,
    )

    assert result["previews"] == [
        {
            "name": "scan.jpg",
            "source_file": "input/scan.jpg",
            "mask_file": "masks/scan.png",
        }
    ]
    assert (workspace / result["previews"][0]["source_file"]).is_file()
    assert (workspace / result["previews"][0]["mask_file"]).is_file()


def test_worker_restart_marks_running_job_interrupted(tmp_path):
    factory = _factory(tmp_path)
    with factory() as session:
        session.add(Job(id="j1", kind="process", status="running", workspace_path="jobs/j1"))
        session.commit()
    manager = WorkerManager(
        session_factory=factory,
        data_root=tmp_path / "data",
        models_root=tmp_path / "models",
        features_root=tmp_path / "features",
        cpu_workers=1,
    )
    manager.shutdown()
    with factory() as session:
        assert session.get(Job, "j1").status == "interrupted"
        event = session.scalar(select(JobEvent).where(JobEvent.job_id == "j1"))
        assert event.event_type == "interrupted"


def test_worker_restart_recovers_kfold_checkpoint_pointer(tmp_path):
    factory = _factory(tmp_path)
    models_root = tmp_path / "models"
    checkpoint = models_root / "t1" / "folds" / "fold-2" / "last_checkpoint.pth"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"checkpoint")
    (models_root / "t1" / "kfold_state.json").write_text(
        '{"active_fold": 1}', encoding="utf-8"
    )
    with factory() as session:
        session.add(Dataset(id="d1", name="dataset", root_path="datasets/d1"))
        session.add(Job(id="j1", dataset_id="d1", kind="training", status="running", workspace_path="training/t1"))
        session.add(
            TrainingJob(
                id="t1",
                job_id="j1",
                dataset_id="d1",
                model_name="model",
                architecture="resnet18",
                status="running",
                total_epochs=3,
            )
        )
        session.commit()
    manager = WorkerManager(
        session_factory=factory,
        data_root=tmp_path / "data",
        models_root=models_root,
        features_root=tmp_path / "features",
        cpu_workers=1,
    )
    manager.shutdown()
    with factory() as session:
        training = session.get(TrainingJob, "t1")
        assert training.status == "interrupted"
        assert training.last_checkpoint_path == "t1/folds/fold-2/last_checkpoint.pth"


def test_safe_resolve_rejects_absolute_and_traversal(tmp_path):
    assert _safe_resolve(tmp_path, "inside/file.txt").is_relative_to(tmp_path)
    for unsafe in (tmp_path / "absolute.txt", "../outside.txt"):
        try:
            _safe_resolve(tmp_path, unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe path accepted: {unsafe}")
