"""Explicit demo-session ownership supports crash recovery without touching manual cases."""
from alembic import op
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('ALTER TABLE exams ADD COLUMN demo_session_id TEXT REFERENCES demo_sessions(id)')
    op.execute("CREATE TRIGGER demo_session_immutable BEFORE UPDATE OF demo_session_id ON exams BEGIN SELECT RAISE(ABORT,'immutable demo session'); END")
    op.execute("CREATE TRIGGER patient_demo_session_forbidden BEFORE INSERT ON exams WHEN NEW.kind='patient' AND NEW.demo_session_id IS NOT NULL BEGIN SELECT RAISE(ABORT,'domain mismatch'); END")

def downgrade():
    raise RuntimeError('Restore a clinical backup instead of destructive downgrade.')
