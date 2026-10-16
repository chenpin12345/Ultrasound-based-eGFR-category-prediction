from __future__ import annotations

import sys
from pathlib import Path

import pytest


pytest.importorskip("torch")
pytest.importorskip("torchvision")


def _same_state_contract(legacy, web):
    legacy_state = legacy.state_dict()
    web_state = web.state_dict()
    assert list(legacy_state) == list(web_state)
    assert all(legacy_state[key].shape == web_state[key].shape for key in legacy_state)


def test_classifier_state_dicts_match_legacy_classes():
    project = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project / "resnet"))
    try:
        from base_models import BasicResNetClassifier, MLPClassifier
        from coral import CoralMLPClassifier, CoralResNetClassifier
        from backend.app.ml.models import build_classifier

        pairs = (
            (BasicResNetClassifier(num_classes=5, weights=None), build_classifier("resnet18")),
            (
                BasicResNetClassifier(num_classes=5, weights=None, backbone_type="mobilenetv2"),
                build_classifier("mobilenetv2"),
            ),
            (
                BasicResNetClassifier(num_classes=5, weights=None, backbone_type="efficientnet_b3"),
                build_classifier("efficientnet_b3"),
            ),
            (
                MLPClassifier(num_classes=5, meta_dim=4, weights=None),
                build_classifier("mlp-resnet18"),
            ),
            (
                CoralResNetClassifier(num_classes=5, weights=None),
                build_classifier("resnet18", coral=True),
            ),
            (
                CoralMLPClassifier(num_classes=5, meta_dim=4, weights=None),
                build_classifier("mlp-resnet18", coral=True),
            ),
        )
        for legacy, web in pairs:
            _same_state_contract(legacy, web)
    finally:
        sys.path.remove(str(project / "resnet"))


def test_unet_state_dict_matches_legacy_class():
    project = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project / "unet"))
    try:
        from UNet import UNet
        from backend.app.ml.segmentation import build_unet

        _same_state_contract(
            UNet(in_channels=3, num_classes=2, bilinear=True, base_c=32),
            build_unet(in_channels=3, num_classes=2, bilinear=True, base_c=32),
        )
    finally:
        sys.path.remove(str(project / "unet"))
