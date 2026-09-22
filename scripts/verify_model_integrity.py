"""Compare protected numerical code and dependency pins with the pre-integration backup."""
import hashlib
import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
backup = root.parents[1] / 'integration-backup-20260913'
protected_dirs = ['backend/app/ml', 'resnet', 'unet', 'features', 'photo_process']
protected_files = ['backend/app/core/splitting.py', 'backend/app/services/training_service.py',
                   'backend/app/workers/runner.py', 'backend/app/services/analysis_service.py',
                   'backend/requirements.txt', 'backend/requirements-ml.txt', 'backend/requirements-test.txt',
                   'frontend/package.json', 'frontend/pnpm-lock.yaml']
files = list(protected_files)
for folder in protected_dirs:
    files.extend(str(p.relative_to(backup)).replace('\\', '/') for p in (backup / folder).rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
items = [{'file': f, 'baseline': digest(backup / f), 'current': digest(root / f)} for f in sorted(set(files))]
changed = [i['file'] for i in items if not i['baseline'] or i['baseline'] != i['current']]
def training_defaults(base):
    text = (base / 'frontend/src/pages/TrainingPage.tsx').read_text(encoding='utf-8')
    match = re.search(r'const DEFAULT_CONFIG: TrainingConfig = \{.*?\n\}', text, re.S)
    return match.group() if match else None

defaults = training_defaults(root)
defaults_equal = defaults is not None and defaults == training_defaults(backup)
report = {'checked': len(items), 'changed': changed, 'files': items,
          'frontend_training_defaults_equal': defaults_equal,
          'original_weights_test': 'pending_user_weights'}
if len(sys.argv) > 1:
    output = Path(sys.argv[1]); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checked': len(items), 'changed': changed, 'frontend_training_defaults_equal': defaults_equal}, ensure_ascii=False))
raise SystemExit(bool(changed) or not defaults_equal)
