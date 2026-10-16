from __future__ import annotations

import pytest

from backend.app.ml.contracts import (
    CLASS_NAMES,
    FEATURE_CSV_FIELDS,
    METADATA_FIELDS,
    ModelMetadata,
    class_index_from_egfr,
    normalize_metadata,
)
from backend.app.ml.training import _classification_metrics


@pytest.mark.parametrize(
    ("egfr", "expected"),
    [
        (-1, 0),
        (14.999, 0),
        (15, 1),
        (29.999, 1),
        (30, 2),
        (59.999, 2),
        (60, 3),
        (89.999, 3),
        (90, 4),
    ],
)
def test_fixed_five_class_boundaries(egfr, expected):
    assert class_index_from_egfr(egfr) == expected


def test_fixed_display_labels_and_metadata_order():
    assert list(CLASS_NAMES) == [0, 1, 2, 3, 4]
    assert CLASS_NAMES[0] == "eGFR < 15"
    assert CLASS_NAMES[4] == "eGFR ≥ 90"
    assert METADATA_FIELDS == ("age", "Length_px", "Contrast_Ratio", "has_diabetes")
    assert FEATURE_CSV_FIELDS == (
        "image_name",
        "age",
        "gender",
        "Length_px",
        "Entropy",
        "Contrast_Ratio",
        "has_diabetes",
    )


def test_metadata_normalization_is_ordered_and_mean_imputes_to_zero():
    values = normalize_metadata(
        {"age": 12, "Length_px": 22, "Contrast_Ratio": 32, "has_diabetes": 1},
        {
            "age": {"mean": 10, "std": 2},
            "Length_px": {"mean": 20, "std": 2},
            "Contrast_Ratio": {"mean": 30, "std": 2},
        },
    )
    assert values == pytest.approx([1, 1, 1, 1])
    assert normalize_metadata({}) == pytest.approx([0, 0, 0, 0])


def test_model_metadata_round_trip_preserves_integer_class_indices():
    restored = ModelMetadata.from_dict(ModelMetadata(architecture="resnet18").to_dict())
    assert restored.class_names == CLASS_NAMES
    assert tuple(restored.metadata_fields) == METADATA_FIELDS


def test_uploaded_model_manifest_shape_is_accepted_and_coral_is_inferred():
    restored = ModelMetadata.from_dict(
        {
            "architecture": "coral-mlp-resnet18",
            "version": "external-1",
            "class_names": [CLASS_NAMES[index] for index in range(5)],
            "metadata_columns": list(METADATA_FIELDS),
            "preprocessing": {
                "mode": "RGB",
                "size": [224, 224],
                "mean": [0.485, 0.456, 0.406],
                "std": [0.229, 0.224, 0.225],
            },
        }
    )
    assert restored.architecture == "mlp-resnet18"
    assert restored.coral is True
    assert restored.model_version == "external-1"


def test_metrics_include_all_classes_and_confusion_matrix():
    result = _classification_metrics([0, 1, 1, 4], [0, 2, 1, 3])
    assert result["accuracy"] == pytest.approx(0.5)
    assert len(result["per_class"]) == 5
    assert len(result["confusion_matrix"]) == 5
    assert result["confusion_matrix"][1][2] == 1
