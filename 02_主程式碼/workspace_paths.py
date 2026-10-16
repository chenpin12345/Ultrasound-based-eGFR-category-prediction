"""Pure path discovery shared by launchers and application; no mkdir/import ML."""
from __future__ import annotations

import json
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
LAYOUT_FILE = CODE_ROOT.parent / 'workspace-layout.json'


def read_layout():
    if not LAYOUT_FILE.is_file():
        return CODE_ROOT, {}
    root = LAYOUT_FILE.parent.resolve()
    layout = json.loads(LAYOUT_FILE.read_text(encoding='utf-8-sig'))
    if layout.get('version') != 1:
        raise ValueError('Unsupported workspace layout version')
    for key in ('code', 'research_data', 'models', 'reference_features', 'clinical', 'reports', 'runtime'):
        value = Path(layout[key])
        if value.is_absolute() or not (root / value).resolve().is_relative_to(root):
            raise ValueError('Layout paths must remain within the workspace: ' + key)
    if (root / layout['code']).resolve() != CODE_ROOT:
        raise ValueError('Layout points to a different code installation')
    return root, layout


WORKSPACE_ROOT, LAYOUT = read_layout()
ENV_FILE = WORKSPACE_ROOT / '.env'


def default_path(key: str, fallback: Path) -> Path:
    return (WORKSPACE_ROOT / LAYOUT[key]).resolve() if key in LAYOUT else fallback
