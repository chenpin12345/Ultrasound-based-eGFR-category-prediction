"""Check protected numerical code against a committed hash manifest.

The manifest replaces the old comparison against full historical backups. It only
proves that these files are byte-identical to the numerically verified version;
numerical regression itself is covered by backend/tests/test_numeric_baseline.py.

  check (default):   python scripts/verify_protected_compute.py [report.json]
  write manifest:    python scripts/verify_protected_compute.py --write --baseline <verified code root> --note <provenance>
                     (refuses unless the current files equal that verified baseline)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'scripts' / 'fixtures' / 'protected_compute_manifest.json'
PROTECTED_DIRS = ['backend/app/ml', 'resnet', 'unet', 'photo_process']
PROTECTED_FILES = ['backend/app/core/splitting.py', 'backend/app/services/training_service.py',
                   'backend/app/workers/runner.py', 'backend/app/services/analysis_service.py',
                   'backend/app/clinical/analysis.py',
                   'backend/requirements.txt', 'backend/requirements-ml.txt', 'backend/requirements-test.txt',
                   'frontend/package.json', 'frontend/pnpm-lock.yaml',
                   'features/addmore.py', 'features/train_stats.json']


def protected(base):
    files = set(PROTECTED_FILES)
    for folder in PROTECTED_DIRS:
        files.update(p.relative_to(base).as_posix() for p in (base / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    return sorted(files)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def training_defaults(base):
    path = base / 'frontend/src/pages/TrainingPage.tsx'
    match = re.search(r'const DEFAULT_CONFIG: TrainingConfig = \{.*?\n\}', path.read_text(encoding='utf-8'), re.S)
    return hashlib.sha256(match.group().encode()).hexdigest() if match else None


def write(baseline, note):
    files = protected(ROOT)
    mismatched = [f for f in files if digest(ROOT / f) != digest(baseline / f)]
    if mismatched or training_defaults(ROOT) != training_defaults(baseline):
        raise SystemExit('Current protected files differ from the verified baseline: ' + ', '.join(mismatched or ['TrainingPage defaults']))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({'version': 1, 'created': time.strftime('%Y-%m-%d'), 'provenance': note,
                                    'training_defaults_sha256': training_defaults(ROOT),
                                    'files': {f: digest(ROOT / f) for f in files}}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'written': str(MANIFEST), 'files': len(files)}, ensure_ascii=False))


def check(output=None):
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    expected = manifest['files']
    current = set(protected(ROOT))
    changed = sorted(f for f, sha in expected.items() if digest(ROOT / f) != sha)
    added = sorted(current - set(expected))
    defaults_equal = training_defaults(ROOT) == manifest['training_defaults_sha256']
    report = {'checked': len(expected), 'changed': changed, 'added': added,
              'frontend_training_defaults_equal': defaults_equal, 'provenance': manifest['provenance']}
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(bool(changed or added) or not defaults_equal)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', nargs='?')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    if args.write:
        if not args.baseline or not args.note:
            raise SystemExit('--write requires --baseline and --note')
        write(args.baseline.resolve(), args.note)
    else:
        check(args.output)
