"""Recoverable temporary cleanup and explicit incomplete-report acknowledgement."""
from alembic import op

revision='0009'
down_revision='0008'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE temporary_cleanup(
        id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES demo_sessions(id),
        frame_id TEXT NOT NULL UNIQUE,exam_id TEXT NOT NULL,path TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN('pending','completed','failed','interrupted')),
        attempts INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,completed REAL,error TEXT)''')
    op.execute('''CREATE TABLE cleanup_attempts(
        id TEXT PRIMARY KEY,cleanup_id TEXT NOT NULL REFERENCES temporary_cleanup(id),
        actor TEXT,reason TEXT NOT NULL,status TEXT NOT NULL,
        created REAL NOT NULL,completed REAL,error TEXT)''')
    op.execute('''CREATE TABLE report_confirmations(
        report_id TEXT NOT NULL,version INTEGER NOT NULL,reviewed_version INTEGER NOT NULL,
        actor TEXT NOT NULL REFERENCES users(id),missing_items TEXT NOT NULL,
        acknowledged INTEGER NOT NULL CHECK(acknowledged IN(0,1)),created REAL NOT NULL,
        PRIMARY KEY(report_id,version),
        FOREIGN KEY(report_id,version) REFERENCES report_versions(report_id,version))''')
    for table in ('temporary_cleanup','cleanup_attempts','report_confirmations'):
        op.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'immutable operation evidence'); END")
    op.execute("CREATE TRIGGER report_confirmation_no_update BEFORE UPDATE ON report_confirmations BEGIN SELECT RAISE(ABORT,'immutable confirmation'); END")
    op.execute("CREATE TRIGGER cleanup_attempt_final BEFORE UPDATE ON cleanup_attempts WHEN OLD.status!='pending' BEGIN SELECT RAISE(ABORT,'final cleanup attempt'); END")
    op.execute("CREATE TRIGGER cleanup_completed BEFORE UPDATE ON temporary_cleanup WHEN OLD.status='completed' BEGIN SELECT RAISE(ABORT,'cleanup completed'); END")
    identity=' OR '.join(f'NEW.{field} IS NOT OLD.{field}' for field in ('id','session_id','frame_id','exam_id','path','created'))
    op.execute(f"CREATE TRIGGER cleanup_identity BEFORE UPDATE ON temporary_cleanup WHEN {identity} BEGIN SELECT RAISE(ABORT,'immutable cleanup target'); END")


def downgrade():
    raise RuntimeError('Restore a matched backup; operation evidence cannot be discarded.')
