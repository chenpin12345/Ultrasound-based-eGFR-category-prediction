"""Protect immutable identities and report snapshots at the storage boundary."""
from alembic import op
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    for table in ('plans','report_versions'):
        for operation in ('UPDATE','DELETE'):
            op.execute(f"CREATE TRIGGER {table}_{operation.lower()}_immutable BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable snapshot'); END")
    op.execute("CREATE TRIGGER frame_identity_immutable BEFORE UPDATE OF exam_id,sha256,path,source ON frames BEGIN SELECT RAISE(ABORT,'immutable frame identity'); END")
    op.execute('ALTER TABLE items ADD COLUMN verification_ms REAL')
    op.execute('ALTER TABLE items ADD COLUMN analysis_ms REAL')

def downgrade():
    raise RuntimeError('Restore a clinical backup instead of destructive downgrade.')
