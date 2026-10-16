from __future__ import annotations

import csv
import zipfile

import pytest

from backend.app.ml.contracts import FEATURE_CSV_FIELDS, INFERENCE_CSV_FIELDS
from backend.app.ml.features import write_feature_csv
from backend.app.ml.inference import InferenceItem, write_inference_csv
from backend.app.ml.processing import ProcessingPlanError, validate_processing_order
from backend.app.services.artifact_service import ArtifactError, create_result_archive


def _header(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def test_feature_csv_is_utf8_bom_with_exact_legacy_order(tmp_path):
    path = write_feature_csv(tmp_path / "features.csv", [{"image_name": "腎臟.jpg"}])
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert tuple(_header(path)) == FEATURE_CSV_FIELDS


def test_inference_csv_is_utf8_bom_with_stable_schema(tmp_path):
    item = InferenceItem("a.jpg", 2, "eGFR 30–59", 0.8, [0.0, 0.1, 0.8, 0.1, 0.0])
    path = write_inference_csv(tmp_path / "inference.csv", [item])
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert tuple(_header(path)) == INFERENCE_CSV_FIELDS


def test_processing_plan_rejects_unknown_and_warns_for_custom_order():
    with pytest.raises(ProcessingPlanError):
        validate_processing_order(["crop", "unknown"])
    plan = validate_processing_order(["rb", "crop"])
    assert plan.steps == ("rb", "crop")
    assert plan.warnings


def test_result_archive_is_atomic_and_workspace_contained(tmp_path):
    workspace = tmp_path / "job"
    output = workspace / "output"
    output.mkdir(parents=True)
    (output / "result.txt").write_text("ok", encoding="utf-8")
    archive = create_result_archive(workspace, [output])
    with zipfile.ZipFile(archive) as handle:
        assert handle.namelist() == ["output/result.txt"]
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(ArtifactError):
        create_result_archive(workspace, [outside])
