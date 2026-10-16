"""Durable preview operation history without persisting unsaved image bytes."""
from alembic import op
revision='0010'
down_revision='0009'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE preview_operations(
        id TEXT PRIMARY KEY,operation_key TEXT NOT NULL,exam_id TEXT NOT NULL REFERENCES exams(id),
        plan_id TEXT NOT NULL REFERENCES plans(id),actor TEXT NOT NULL REFERENCES users(id),
        basic_input TEXT NOT NULL,source_sha256 TEXT,
        status TEXT NOT NULL CHECK(status IN('running','completed','failed','cancelled','interrupted')),
        created REAL NOT NULL,completed REAL,error_code TEXT,error_message TEXT,result_summary TEXT)''')
    op.execute('CREATE INDEX preview_operations_exam ON preview_operations(exam_id,status)')
    op.execute('CREATE INDEX preview_operations_order ON preview_operations(created,id)')
    op.execute("CREATE TRIGGER preview_operations_no_delete BEFORE DELETE ON preview_operations BEGIN SELECT RAISE(ABORT,'immutable preview evidence'); END")
    op.execute("CREATE TRIGGER preview_operations_final BEFORE UPDATE ON preview_operations WHEN OLD.status!='running' BEGIN SELECT RAISE(ABORT,'preview operation finalized'); END")
    fields=('id','operation_key','exam_id','plan_id','actor','basic_input','created')
    condition=' OR '.join(f'NEW.{field} IS NOT OLD.{field}' for field in fields)
    op.execute(f"CREATE TRIGGER preview_operations_identity BEFORE UPDATE ON preview_operations WHEN {condition} BEGIN SELECT RAISE(ABORT,'immutable preview identity'); END")


def downgrade():
    raise RuntimeError('Restore a matched backup; preview operation history cannot be discarded.')
