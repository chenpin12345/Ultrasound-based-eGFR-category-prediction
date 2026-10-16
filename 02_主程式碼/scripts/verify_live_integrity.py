"""Read-only integrity inventory of the live workspace (no backups needed).

Checks both SQLite databases (integrity + foreign keys), and that every file the
databases reference exists with the recorded SHA-256: research images, model
weights/manifests, clinical originals, sealed plan bundles, analysis artifacts and
ready PDFs. Use before/after maintenance:

  python scripts/verify_live_integrity.py out.json [--compare before.json]

--compare requires every record and file recorded before to still be present and
unchanged (new clinical rows are allowed and listed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workspace_paths import default_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def connect(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def check_db(db):
    return {'integrity': db.execute('PRAGMA integrity_check').fetchone()[0],
            'foreign_key_violations': len(db.execute('PRAGMA foreign_key_check').fetchall()),
            'tables': {r[0]: db.execute(f'SELECT COUNT(*) FROM "{r[0]}"').fetchone()[0]
                       for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}}


def file_entry(path, expected, problems, label):
    if not path.is_file():
        problems.append(f'{label}: missing'); return None
    actual = sha(path)
    if expected and actual != expected: problems.append(f'{label}: sha mismatch')
    return actual


def inventory():
    research_dir = default_path('research_data', ROOT / 'data')
    models_dir = default_path('models', ROOT / 'models')
    clinical_dir = default_path('clinical', ROOT / 'clinical')
    reports_dir = default_path('reports', clinical_dir / 'reports')
    problems, files = [], {}
    with closing(connect(research_dir / 'isu_ai.sqlite3')) as db:
        research = check_db(db)
        for row in db.execute('SELECT s.id,s.relative_path,s.sha256,d.root_path FROM dataset_samples s JOIN datasets d ON d.id=s.dataset_id'):
            files['sample:' + row['id']] = file_entry(research_dir / row['root_path'] / row['relative_path'], row['sha256'], problems, 'sample ' + row['id'])
        for row in db.execute('SELECT id,weights_path,metadata_path,sha256 FROM model_records'):
            files['weights:' + row['id']] = file_entry(models_dir / row['weights_path'], row['sha256'], problems, 'weights ' + row['id'])
            files['manifest:' + row['id']] = file_entry(models_dir / row['metadata_path'], None, problems, 'manifest ' + row['id'])
    with closing(connect(clinical_dir / 'clinical.sqlite3')) as db:
        clinical = check_db(db)
        for row in db.execute('SELECT id,path,sha256 FROM frames'):
            files['frame:' + row['id']] = file_entry(clinical_dir / row['path'], row['sha256'], problems, 'frame ' + row['id'])
        for row in db.execute('SELECT id,snapshot FROM plans'):
            for role, model in json.loads(row['snapshot'])['models'].items():
                files[f'plan:{row["id"]}:{role}'] = file_entry(clinical_dir / model['path'], model['sha256'], problems, f'plan {row["id"]} {role}')
        for row in db.execute("SELECT id,snapshot FROM analysis_runs WHERE evidence='verified'"):
            for name, item in json.loads(row['snapshot']).get('artifacts', {}).items():
                files[f'run:{row["id"]}:{name}'] = file_entry(clinical_dir / item['path'], item['sha256'], problems, f'run {row["id"]} {name}')
        for row in db.execute("SELECT id,path,sha256 FROM pdf_artifacts WHERE status='ready'"):
            files['pdf:' + row['id']] = file_entry(reports_dir / row['path'], row['sha256'], problems, 'pdf ' + row['id'])
    for name, value in (('research', research), ('clinical', clinical)):
        if value['integrity'] != 'ok' or value['foreign_key_violations']:
            problems.append(f'{name} database integrity failed')
    return {'research': research, 'clinical': clinical, 'files': files, 'file_count': len(files), 'problems': problems}


def compare(before, after):
    problems = []
    for key, value in before['files'].items():
        if after['files'].get(key) != value: problems.append(f'changed or missing: {key}')
    for db in ('research', 'clinical'):
        for table, count in before[db]['tables'].items():
            now = after[db]['tables'].get(table)
            if now is None or now < count: problems.append(f'{db}.{table}: {count} -> {now}')
    added = sorted(set(after['files']) - set(before['files']))
    return problems, added


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    report = inventory()
    if args.compare:
        problems, added = compare(json.loads(args.compare.read_text(encoding='utf-8')), report)
        report['comparison'] = {'against': str(args.compare), 'problems': problems, 'added_files': added}
        report['problems'] += problems
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'file_count': report['file_count'], 'problems': report['problems'][:20],
                      'research_tables': report['research']['tables'], 'clinical_tables': report['clinical']['tables']}, ensure_ascii=False))
    raise SystemExit(bool(report['problems']))
