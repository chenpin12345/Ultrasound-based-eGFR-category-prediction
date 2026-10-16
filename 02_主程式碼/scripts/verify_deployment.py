"""Local deployment smoke check; no login, no writes to production databases."""
from contextlib import closing
import argparse
import json
from pathlib import Path
import re
import sqlite3
from urllib.request import urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit

CODE = Path(__file__).resolve().parents[1]
WORKSPACE = CODE.parent


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--assert-idle', action='store_true'); parser.add_argument('--output', type=Path); args = parser.parse_args()
    research = WORKSPACE / '03_模型與影像資料/research/data/isu_ai.sqlite3'
    clinical = WORKSPACE / '03_模型與影像資料/clinical/clinical.sqlite3'
    with closing(sqlite3.connect(research.as_uri() + '?mode=ro', uri=True)) as db:
        counts = {name: db.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in ('datasets', 'dataset_samples', 'model_records', 'jobs')}
        active = sum(db.execute(f"SELECT count(*) FROM {name} WHERE status IN ('queued','running','stopping')").fetchone()[0] for name in ('jobs', 'training_jobs'))
        db.row_factory = sqlite3.Row
        inventory = [dict(row) for row in db.execute('SELECT id,name,version,task,architecture,class_count,active,sha256,weights_path,metadata_path FROM model_records ORDER BY name')]
    with closing(sqlite3.connect(clinical.as_uri() + '?mode=ro', uri=True)) as db:
        counts['clinical_users'] = db.execute('SELECT count(*) FROM users').fetchone()[0]
        active_sessions = db.execute("SELECT count(*) FROM demo_sessions WHERE state='active'").fetchone()[0]
        clinical_revision = db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
    if args.assert_idle:
        assert active == active_sessions == 0, 'Do not stop active work or receiver sessions'
    record = json.loads((WORKSPACE / '03_模型與影像資料/runtime/run/server.json').read_text(encoding='utf-8'))
    assert Path(record['project_root']).resolve() == CODE
    base = record['url']
    assert urlsplit(base).hostname in {'127.0.0.1', 'localhost', '::1'}
    with urlopen(base + '/api/health', timeout=10) as response:
        health = json.load(response)
    assert health['status'] == health['database'] == 'ok'
    with urlopen(base, timeout=10) as response:
        html = response.read().decode('utf-8')
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
    assert assets
    for asset in assets:
        with urlopen(base + asset, timeout=10) as response:
            assert response.status == 200
    for route in ('/api/datasets', '/api/models', '/api/clinical/reports'):
        try:
            urlopen(base + route, timeout=10)
        except HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError('Anonymous protected API access unexpectedly succeeded')
    result = {'passed': True, 'url': base, 'active_code': '02_主程式碼', 'health': 'ok',
              'assets_served': len(assets), 'anonymous_protected_api_status': 401,
              'counts': counts, 'active_jobs': active, 'active_receiver_sessions': active_sessions,
              'clinical_schema': clinical_revision}
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'deployment.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        (args.output / 'model-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
