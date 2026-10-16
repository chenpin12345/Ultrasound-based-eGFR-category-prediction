"""Clinical operation evidence stays in the clinical database, not research jobs."""
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE clinical_operations(
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind='frame_analysis'),
        frame_id TEXT NOT NULL REFERENCES frames(id), exam_id TEXT NOT NULL REFERENCES exams(id),
        plan_id TEXT NOT NULL REFERENCES plans(id), actor TEXT REFERENCES users(id),
        retry_of TEXT REFERENCES clinical_operations(id),
        status TEXT NOT NULL CHECK(status IN('running','completed','unavailable','failed','interrupted')),
        created REAL NOT NULL, completed REAL, error_code TEXT, error_message TEXT)''')
    op.execute('CREATE INDEX clinical_operations_order ON clinical_operations(created,id)')
    op.execute('CREATE INDEX clinical_operations_frame ON clinical_operations(frame_id,status)')
    op.execute("CREATE TRIGGER clinical_operation_no_delete BEFORE DELETE ON clinical_operations BEGIN SELECT RAISE(ABORT,'immutable operation evidence'); END")
    op.execute("CREATE TRIGGER clinical_operation_final BEFORE UPDATE ON clinical_operations WHEN OLD.status!='running' BEGIN SELECT RAISE(ABORT,'operation finalized'); END")
    fields=('id','kind','frame_id','exam_id','plan_id','actor','retry_of','created')
    condition=' OR '.join(f'NEW.{field} IS NOT OLD.{field}' for field in fields)
    op.execute(f"CREATE TRIGGER clinical_operation_identity BEFORE UPDATE ON clinical_operations WHEN {condition} BEGIN SELECT RAISE(ABORT,'immutable operation identity'); END")
    for table,column in (('exams','patient_id'),('frames','exam_id'),('reports','exam_id'),('batches','session_id')):
        op.execute(f'CREATE INDEX clinical_monitor_{table}_{column} ON {table}({column})')


def downgrade():
    raise RuntimeError('Restore the matched backup; do not discard operation history.')
