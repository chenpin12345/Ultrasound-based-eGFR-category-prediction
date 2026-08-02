"""Legacy-compatible two-class UNet construction and mask generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

from .models import MLDependencyError, ModelCompatibilityError, load_state_dict_file


UNET_IMAGE_SIZE = (512, 512)


def build_unet(*, in_channels: int = 3, num_classes: int = 2, bilinear: bool = True, base_c: int = 32):
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as functional
    except ImportError as exc:
        raise MLDependencyError("PyTorch is required for UNet masks.") from exc

    class DoubleConv(nn.Sequential):
        def __init__(self, input_channels, output_channels, mid_channels=None):
            mid_channels = mid_channels or output_channels
            super().__init__(
                nn.Conv2d(input_channels, mid_channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(mid_channels),
                nn.ReLU(inplace=True),
                nn.Conv2d(mid_channels, output_channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(output_channels),
                nn.ReLU(inplace=True),
            )

    class Down(nn.Sequential):
        def __init__(self, input_channels, output_channels):
            super().__init__(nn.MaxPool2d(2, stride=2), DoubleConv(input_channels, output_channels))

    class Up(nn.Module):
        def __init__(self, input_channels, output_channels):
            super().__init__()
            if bilinear:
                self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=True)
                self.conv = DoubleConv(input_channels, output_channels, input_channels // 2)
            else:
                self.up = nn.ConvTranspose2d(input_channels, input_channels // 2, 2, stride=2)
                self.conv = DoubleConv(input_channels, output_channels)

        def forward(self, decoder, encoder):
            decoder = self.up(decoder)
            diff_y = encoder.size(2) - decoder.size(2)
            diff_x = encoder.size(3) - decoder.size(3)
            decoder = functional.pad(
                decoder,
                [diff_x // 2, diff_x - diff_x // 2, diff_y // 2, diff_y - diff_y // 2],
            )
            return self.conv(torch.cat([encoder, decoder], dim=1))

    class UNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.in_channels = in_channels
            self.num_classes = num_classes
            self.bilinear = bilinear
            factor = 2 if bilinear else 1
            self.in_conv = DoubleConv(in_channels, base_c)
            self.down1 = Down(base_c, base_c * 2)
            self.down2 = Down(base_c * 2, base_c * 4)
            self.down3 = Down(base_c * 4, base_c * 8)
            self.down4 = Down(base_c * 8, base_c * 16 // factor)
            self.up1 = Up(base_c * 16, base_c * 8 // factor)
            self.up2 = Up(base_c * 8, base_c * 4 // factor)
            self.up3 = Up(base_c * 4, base_c * 2 // factor)
            self.up4 = Up(base_c * 2, base_c)
            self.out_conv = nn.Sequential(nn.Conv2d(base_c, num_classes, 1))

        def forward(self, value):
            height, width = value.size(2), value.size(3)
            value = functional.interpolate(value, scale_factor=0.5, mode="bilinear", align_corners=True)
            x1 = self.in_conv(value)
            x2 = self.down1(x1)
            x3 = self.down2(x2)
            x4 = self.down3(x3)
            x5 = self.down4(x4)
            value = self.up1(x5, x4)
            value = self.up2(value, x3)
            value = self.up3(value, x2)
            value = self.up4(value, x1)
            logits = self.out_conv(value)
            logits = functional.interpolate(logits, size=(height, width), mode="bilinear", align_corners=True)
            return {"out": logits}

    return UNet()


def load_unet(path: str | Path, device: Any = "cpu"):
    model = build_unet()
    try:
        model.load_state_dict(load_state_dict_file(path, device), strict=True)
    except Exception as exc:
        if isinstance(exc, ModelCompatibilityError):
            raise
        raise ModelCompatibilityError("UNet weights do not match base_c=32, two-class architecture.") from exc
    model.to(device)
    model.eval()
    return model


def refine_mask(mask: Any):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise MLDependencyError("OpenCV and NumPy are required for mask refinement.") from exc

    mask = (mask > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return mask
    largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    mask = (labels == largest).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (10, 10))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    height, width = mask.shape[:2]
    filled = mask.copy()
    flood_mask = np.zeros((height + 2, width + 2), np.uint8)
    cv2.floodFill(filled, flood_mask, (0, 0), 1)
    mask |= (filled == 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (50, 50))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    blurred = cv2.GaussianBlur(mask.astype(np.float32), (25, 25), 0)
    return (blurred > 0.5).astype(np.uint8)


def generate_masks(
    image_paths: Iterable[str | Path],
    *,
    source_root: str | Path,
    output_root: str | Path,
    model_path: str | Path,
    device: Any = None,
    refine: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    try:
        import torch
        from PIL import Image
        from torchvision import transforms
    except ImportError as exc:
        raise MLDependencyError("PyTorch, Torchvision and Pillow are required for masks.") from exc
    from .contracts import IMAGENET_MEAN, IMAGENET_STD

    paths = [Path(item) for item in image_paths]
    if not paths:
        raise ValueError("No images supplied for mask generation.")
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if device is None or str(device).lower() == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable.")
    model = load_unet(model_path, device)
    transform = transforms.Compose(
        [
            transforms.Resize(UNET_IMAGE_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )
    outputs: list[Path] = []
    try:
        with torch.inference_mode():
            for index, path in enumerate(paths, 1):
                resolved = path.resolve()
                try:
                    relative = resolved.relative_to(source_root)
                except ValueError as exc:
                    raise ValueError("Mask input must stay inside source_root.") from exc
                with Image.open(resolved) as source:
                    tensor = transform(source.convert("RGB")).unsqueeze(0).to(device)
                logits = model(tensor)["out"]
                mask = torch.argmax(logits, dim=1).squeeze().cpu().numpy()
                if refine:
                    mask = refine_mask(mask)
                target = (output_root / relative).with_suffix(".png")
                target.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray((mask * 255).astype("uint8")).save(target)
                outputs.append(target)
                if progress:
                    progress(index, len(paths), f"mask {index}/{len(paths)}")
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise RuntimeError("CUDA 記憶體不足，請改用 CPU 後重試。") from exc
    return outputs
