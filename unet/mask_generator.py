from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from UNet import UNet


def refine_mask(mask):
    mask = (mask > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num_labels <= 1:
        return mask

    largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    mask = (labels == largest_label).astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (10, 10))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    h, w = mask.shape[:2]
    mask_copy = mask.copy()
    floodfill_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(mask_copy, floodfill_mask, (0, 0), 1)
    holes = (mask_copy == 0).astype(np.uint8)
    mask = mask | holes

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (50, 50))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    blurred = cv2.GaussianBlur(mask.astype(np.float32), (25, 25), 0)
    _, smoothed = cv2.threshold(blurred, 0.5, 1, cv2.THRESH_BINARY)
    return smoothed.astype(np.uint8)


def _load_state_dict(model_path, device):
    try:
        state = torch.load(model_path, map_location=device, weights_only=True)
    except TypeError:
        state = torch.load(model_path, map_location=device)
    if isinstance(state, dict):
        for key in ("state_dict", "model_state_dict", "model"):
            if key in state and isinstance(state[key], dict):
                return state[key]
    return state


def load_unet_model(model_path, device=None):
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = UNet(in_channels=3, num_classes=2, bilinear=True, base_c=32).to(device)
    model.load_state_dict(_load_state_dict(model_path, device))
    model.eval()
    return model, device


def _output_tensor(output):
    if isinstance(output, dict):
        if "out" in output:
            return output["out"]
        if "mask" in output:
            return output["mask"]
        raise ValueError("Model output dict does not contain 'out' or 'mask'.")
    return output


def generate_masks(image_paths, source_dir, output_dir, model_path, progress=None, refine=True):
    image_paths = [Path(p) for p in image_paths]
    if not image_paths:
        raise ValueError("No images found for mask generation.")

    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model, device = load_unet_model(model_path)
    transform = transforms.Compose(
        [
            transforms.Resize((512, 512)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )

    with torch.no_grad():
        for index, image_path in enumerate(image_paths, 1):
            if progress:
                progress(index - 1, len(image_paths), f"Generating mask {index}/{len(image_paths)}")

            image = Image.open(image_path).convert("RGB")
            tensor = transform(image).unsqueeze(0).to(device)
            output = _output_tensor(model(tensor))
            mask = torch.argmax(output, dim=1).squeeze().cpu().numpy().astype(np.uint8)
            if refine:
                mask = refine_mask(mask)

            relative = image_path.relative_to(source_dir)
            target = (output_dir / relative).with_suffix(".png")
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray((mask * 255).astype(np.uint8)).save(target)

            if progress:
                progress(index, len(image_paths), f"Generated mask {index}/{len(image_paths)}")

    return len(image_paths)
