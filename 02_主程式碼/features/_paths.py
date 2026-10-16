"""Path-only compatibility for explicitly run legacy feature utilities."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.core.config import AppSettings


def reference(name):
    path = AppSettings().reference_features_dir / name
    if not path.is_file():
        raise FileNotFoundError('Legacy utility requires this reference input; no substitute is selected: ' + str(path))
    return str(path)


def output(name):
    folder = AppSettings().runtime_dir / 'legacy_features'
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / name)
