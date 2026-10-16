"""Immutable completed analysis snapshots; legacy artifacts remain unverified."""
import json
from alembic import op

revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE analysis_runs(
        id TEXT PRIMARY KEY,frame_id TEXT NOT NULL REFERENCES frames(id),
        exam_id TEXT NOT NULL REFERENCES exams(id),plan_id TEXT REFERENCES plans(id),
        operation_id TEXT REFERENCES clinical_operations(id),actor TEXT REFERENCES users(id),
        evidence TEXT NOT NULL CHECK(evidence IN('verified','legacy_unverified')),
        snapshot TEXT NOT NULL,created REAL NOT NULL)''')
    op.execute('CREATE INDEX analysis_runs_frame ON analysis_runs(frame_id,created,id)')
    op.execute('''CREATE TABLE latest_analysis(
        frame_id TEXT PRIMARY KEY REFERENCES frames(id),run_id TEXT NOT NULL REFERENCES analysis_runs(id))''')
    op.execute('''CREATE TABLE analysis_publications(
        id TEXT PRIMARY KEY,frame_id TEXT NOT NULL REFERENCES frames(id),path TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN('staging','published','failed','interrupted')),
        created REAL NOT NULL,completed REAL,error TEXT)''')
    connection=op.get_bind()
    rows=connection.exec_driver_sql("SELECT id,exam_id,result,created FROM frames WHERE status='completed' AND result IS NOT NULL").fetchall()
    for frame_id,exam_id,result,created in rows:
        run_id='legacy-'+frame_id
        snapshot={'version':1,'result':json.loads(result),'artifacts':{},'evidence':'legacy_unverified',
                  'reason':'舊結果僅保留現存數值，無法證實共用 Mask／疊圖屬於此次分析；不補用最新產物。'}
        connection.exec_driver_sql('INSERT INTO analysis_runs VALUES(?,?,?,?,?,?,?,?,?)',
            (run_id,frame_id,exam_id,None,None,None,'legacy_unverified',json.dumps(snapshot,ensure_ascii=False),created))
        connection.exec_driver_sql('INSERT INTO latest_analysis VALUES(?,?)',(frame_id,run_id))
    for operation in ('UPDATE','DELETE'):
        op.execute(f"CREATE TRIGGER analysis_runs_no_{operation.lower()} BEFORE {operation} ON analysis_runs BEGIN SELECT RAISE(ABORT,'immutable analysis snapshot'); END")
    op.execute("CREATE TRIGGER analysis_publications_no_delete BEFORE DELETE ON analysis_publications BEGIN SELECT RAISE(ABORT,'publication journal required'); END")
    op.execute("CREATE TRIGGER analysis_publications_final BEFORE UPDATE ON analysis_publications WHEN OLD.state!='staging' BEGIN SELECT RAISE(ABORT,'publication finalized'); END")


def downgrade():
    raise RuntimeError('Restore a consistent backup; immutable analyses cannot be discarded.')
