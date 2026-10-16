"""Managed PDF artifacts and recoverable file-operation journal."""
from alembic import op
revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE pdf_artifacts(
        id TEXT PRIMARY KEY,report_id TEXT NOT NULL,version INTEGER NOT NULL,
        template_version INTEGER NOT NULL,variant TEXT NOT NULL CHECK(variant IN('original','void')),
        path TEXT NOT NULL UNIQUE,sha256 TEXT,source_sha256 TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN('generating','ready','deleting','deleted','failed','interrupted','deletion_failed')),
        actor TEXT REFERENCES users(id),created REAL NOT NULL,completed REAL,error TEXT,
        FOREIGN KEY(report_id,version) REFERENCES report_versions(report_id,version))''')
    op.execute('CREATE INDEX pdf_artifacts_version ON pdf_artifacts(report_id,version,created,id)')
    op.execute('''CREATE TABLE pdf_operations(
        id TEXT PRIMARY KEY,artifact_id TEXT NOT NULL REFERENCES pdf_artifacts(id),
        action TEXT NOT NULL CHECK(action IN('generate','delete','import')),
        status TEXT NOT NULL CHECK(status IN('pending','completed','failed','interrupted')),
        actor TEXT REFERENCES users(id),reason TEXT NOT NULL,created REAL NOT NULL,completed REAL,error TEXT)''')
    for table in ('pdf_artifacts','pdf_operations'):
        op.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'PDF evidence cannot be deleted'); END")
    identity=' OR '.join(f'NEW.{field} IS NOT OLD.{field}' for field in ('id','report_id','version','template_version','variant','path','source_sha256','actor','created'))
    op.execute(f"CREATE TRIGGER pdf_artifact_identity BEFORE UPDATE ON pdf_artifacts WHEN {identity} OR (OLD.sha256 IS NOT NULL AND NEW.sha256 IS NOT OLD.sha256) BEGIN SELECT RAISE(ABORT,'immutable PDF identity'); END")
    op.execute("CREATE TRIGGER pdf_artifact_tombstone BEFORE UPDATE ON pdf_artifacts WHEN OLD.status='deleted' BEGIN SELECT RAISE(ABORT,'PDF tombstone is final'); END")
    op.execute("CREATE TRIGGER pdf_operation_final BEFORE UPDATE ON pdf_operations WHEN OLD.status!='pending' BEGIN SELECT RAISE(ABORT,'PDF operation finalized'); END")


def downgrade():
    raise RuntimeError('Restore a matched backup; PDF tombstones cannot be discarded.')
