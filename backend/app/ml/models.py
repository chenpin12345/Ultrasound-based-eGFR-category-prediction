"""Lazy PyTorch classification models compatible with legacy state dictionaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .contracts import CLASS_COUNT, METADATA_FIELDS


class MLDependencyError(RuntimeError):
    pass


class ModelCompatibilityError(RuntimeError):
    pass


def _runtime():
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as functional
        import torchvision.models as tv_models
    except ImportError as exc:
        raise MLDependencyError(
            "PyTorch 與 Torchvision 尚未安裝；API 可啟動，但模型功能目前不可用。"
        ) from exc
    return torch, nn, functional, tv_models


def canonical_architecture(value: str) -> str:
    normalized = value.lower().replace("_", "").replace("-", "")
    aliases = {
        "resnet18": "resnet18",
        "resnet": "resnet18",
        "mobilenetv2": "mobilenetv2",
        "efficientnetb3": "efficientnetb3",
        "mlpresnet18": "mlp-resnet18",
        "mlp": "mlp-resnet18",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ModelCompatibilityError(f"Unsupported architecture: {value!r}") from exc


def build_classifier(
    architecture: str,
    *,
    num_classes: int = CLASS_COUNT,
    meta_dim: int = len(METADATA_FIELDS),
    coral: bool = False,
):
    """Build an uninitialized classifier without downloading pretrained weights."""

    torch, nn, _, tv_models = _runtime()
    architecture = canonical_architecture(architecture)

    class ResNetBackbone(nn.Module):
        def __init__(self):
            super().__init__()
            backbone = tv_models.resnet18(weights=None)
            self.features = nn.Sequential(*list(backbone.children())[:-1])
            self.feature_dim = 512

        def forward(self, value):
            value = self.features(value)
            return value.view(value.size(0), -1)

    class MobileNetV2Backbone(nn.Module):
        def __init__(self):
            super().__init__()
            backbone = tv_models.mobilenet_v2(weights=None)
            self.features = backbone.features
            self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
            self.feature_dim = 1280

        def forward(self, value):
            value = self.features(value)
            value = self.avgpool(value)
            return value.view(value.size(0), -1)

    class EfficientNetB3Backbone(nn.Module):
        def __init__(self):
            super().__init__()
            backbone = tv_models.efficientnet_b3(weights=None)
            self.features = backbone.features
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.feature_dim = backbone.classifier[1].in_features

        def forward(self, value):
            value = self.features(value)
            value = self.pool(value)
            return torch.flatten(value, 1)

    def backbone_for(name: str):
        if name in {"resnet18", "mlp-resnet18"}:
            return ResNetBackbone()
        if name == "mobilenetv2":
            return MobileNetV2Backbone()
        if name == "efficientnetb3":
            return EfficientNetB3Backbone()
        raise ModelCompatibilityError(name)

    if coral:
        # Keep the legacy CORAL state-dict names: features, feature_mlp,
        # meta_mlp and coral_classifier.fc.
        class CoralClassifier(nn.Module):
            def __init__(self, in_features: int):
                super().__init__()
                self.fc = nn.Linear(in_features, num_classes - 1)

            def forward(self, value):
                return self.fc(value)

        if architecture == "mlp-resnet18":
            class CoralMLPClassifier(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.num_classes = num_classes
                    self.meta_dim = meta_dim
                    backbone = tv_models.resnet18(weights=None)
                    self.features = nn.Sequential(*list(backbone.children())[:-1])
                    self.feature_dim = 512
                    self.feature_mlp = nn.Sequential(
                        nn.Linear(512, 128), nn.ReLU(), nn.Dropout(0.3)
                    )
                    self.meta_mlp = nn.Sequential(
                        nn.Linear(meta_dim, 64), nn.ReLU(), nn.Dropout(0.05)
                    )
                    self.coral_classifier = CoralClassifier(128 + 64)

                def forward(self, image, metadata):
                    features = self.features(image).view(image.size(0), -1)
                    features = self.feature_mlp(features)
                    metadata = self.meta_mlp(metadata)
                    return self.coral_classifier(torch.cat([features, metadata], dim=1))

            return CoralMLPClassifier()

        if architecture != "resnet18":
            raise ModelCompatibilityError("Legacy CORAL supports ResNet18 or MLP-ResNet18 only.")

        class CoralResNetClassifier(nn.Module):
            def __init__(self):
                super().__init__()
                self.num_classes = num_classes
                backbone = tv_models.resnet18(weights=None)
                self.features = nn.Sequential(*list(backbone.children())[:-1])
                self.feature_dim = 512
                self.feature_mlp = nn.Sequential(
                    nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.3)
                )
                self.coral_classifier = CoralClassifier(256)

            def forward(self, image):
                features = self.features(image).view(image.size(0), -1)
                return self.coral_classifier(self.feature_mlp(features))

        return CoralResNetClassifier()

    if architecture == "mlp-resnet18":
        class MLPClassifier(nn.Module):
            def __init__(self):
                super().__init__()
                self.num_classes = num_classes
                self.meta_dim = meta_dim
                self.backbone = ResNetBackbone()
                self.feature_mlp = nn.Sequential(
                    nn.Linear(512, 256),
                    nn.ReLU(),
                    nn.BatchNorm1d(256),
                    nn.Dropout(0.5),
                )
                self.meta_mlp = nn.Sequential(
                    nn.Linear(meta_dim, 32),
                    nn.ReLU(),
                    nn.BatchNorm1d(32),
                    nn.Dropout(0.3),
                )
                self.classifier = nn.Linear(288, num_classes)

            def forward(self, image, metadata):
                image_features = self.feature_mlp(self.backbone(image))
                metadata_features = self.meta_mlp(metadata)
                return self.classifier(torch.cat([image_features, metadata_features], dim=1))

        return MLPClassifier()

    class BasicResNetClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.num_classes = num_classes
            self.backbone = backbone_for(architecture)
            self.classifier = nn.Sequential(
                nn.Linear(self.backbone.feature_dim, 256),
                nn.ReLU(),
                nn.BatchNorm1d(256),
                nn.Dropout(0.5),
                nn.Linear(256, num_classes),
            )

        def forward(self, image):
            return self.classifier(self.backbone(image))

    return BasicResNetClassifier()


def extract_state_dict(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ModelCompatibilityError("The .pth file does not contain a state dictionary.")
    for key in ("state_dict", "model_state_dict", "model"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            payload = nested
            break
    if not payload or not all(isinstance(key, str) for key in payload):
        raise ModelCompatibilityError("Invalid model state dictionary.")
    if all(key.startswith("module.") for key in payload):
        return {key[7:]: value for key, value in payload.items()}
    return payload


def load_state_dict_file(path: str | Path, device: Any = "cpu") -> Mapping[str, Any]:
    """Load tensors with PyTorch's restricted weights-only unpickler.

    Untrusted web uploads never fall back to unrestricted pickle loading.
    """

    torch, _, _, _ = _runtime()
    try:
        payload = torch.load(str(path), map_location=device, weights_only=True)
    except TypeError as exc:
        raise ModelCompatibilityError(
            "This PyTorch version lacks safe weights_only loading; upgrade PyTorch."
        ) from exc
    except Exception as exc:
        raise ModelCompatibilityError(f"Unable to load model weights: {Path(path).name}") from exc
    return extract_state_dict(payload)


def load_classifier(
    path: str | Path,
    architecture: str,
    *,
    device: Any = "cpu",
    coral: bool = False,
):
    model = build_classifier(architecture, coral=coral)
    state = load_state_dict_file(path, device)
    try:
        model.load_state_dict(state, strict=True)
    except Exception as exc:
        raise ModelCompatibilityError(
            f"Weights do not match architecture={architecture!r}, coral={coral}."
        ) from exc
    model.to(device)
    model.eval()
    return model


def coral_logits_to_probs(logits: Any, num_classes: int = CLASS_COUNT):
    torch, _, _, _ = _runtime()
    cumulative = torch.sigmoid(logits)
    ones = torch.ones(logits.size(0), 1, device=logits.device)
    zeros = torch.zeros(logits.size(0), 1, device=logits.device)
    cumulative = torch.cat([ones, cumulative, zeros], dim=1)
    return cumulative[:, :-1] - cumulative[:, 1:]


def image_transform():
    try:
        from torchvision import transforms
    except ImportError as exc:
        raise MLDependencyError("Torchvision is required for inference.") from exc
    from .contracts import IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD

    return transforms.Compose(
        [
            transforms.Resize(IMAGE_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )

