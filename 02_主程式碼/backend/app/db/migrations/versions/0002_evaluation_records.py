"""Append-only evaluation evidence, independent of historical training metrics."""
from alembic import op
import sqlalchemy as sa

revision = 'research_0002'
down_revision = 'research_0001'


def upgrade():
    op.create_table('evaluation_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('model_id', sa.String(36), sa.ForeignKey('model_records.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('retry_of_id', sa.String(36), sa.ForeignKey('evaluation_records.id', ondelete='RESTRICT')),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('task', sa.String(32), nullable=False),
        sa.Column('snapshot_json', sa.JSON, nullable=False),
        sa.Column('cohort_sha256', sa.String(64), nullable=False),
        sa.Column('metric_version', sa.String(64), nullable=False),
        sa.Column('sample_count', sa.Integer, nullable=False),
        sa.Column('completed_count', sa.Integer, nullable=False),
        sa.Column('result_json', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('sample_count > 0 AND completed_count >= 0 AND completed_count <= sample_count', name='ck_evaluation_counts'),
        sa.CheckConstraint("status IN ('queued','running','completed','partial','failed','stopped','interrupted')", name='ck_evaluation_status'))
    op.create_index('ix_evaluation_model', 'evaluation_records', ['model_id','created_at'])
    op.create_table('evaluation_predictions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('evaluation_id', sa.String(36), sa.ForeignKey('evaluation_records.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('sample_id', sa.String(100), nullable=False),
        sa.Column('payload_json', sa.JSON, nullable=False),
        sa.UniqueConstraint('evaluation_id','sample_id', name='uq_evaluation_sample'))
    op.create_table('mask_provenance',
        sa.Column('mask_id', sa.String(36), sa.ForeignKey('dataset_masks.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('evidence_json', sa.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('independent_reference','model_generated','unknown')", name='ck_mask_provenance_kind'))
    # Existing masks intentionally get no invented ground-truth provenance.
    for table in ('evaluation_predictions','mask_provenance'):
        for operation in ('UPDATE','DELETE'):
            op.execute(f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable evidence'); END")
    op.execute("CREATE TRIGGER evaluation_no_delete BEFORE DELETE ON evaluation_records BEGIN SELECT RAISE(ABORT,'immutable evaluation'); END")
    op.execute("""CREATE TRIGGER evaluation_terminal_immutable BEFORE UPDATE ON evaluation_records
        WHEN OLD.status IN ('completed','partial','failed','stopped','interrupted')
        BEGIN SELECT RAISE(ABORT,'immutable evaluation'); END""")
    fields=('id','model_id','job_id','dataset_id','retry_of_id','task','snapshot_json','cohort_sha256','metric_version','sample_count','created_at')
    condition=' OR '.join(f'NEW.{field} IS NOT OLD.{field}' for field in fields)
    op.execute(f"CREATE TRIGGER evaluation_input_immutable BEFORE UPDATE ON evaluation_records WHEN {condition} BEGIN SELECT RAISE(ABORT,'immutable evaluation input'); END")
    op.execute("""CREATE TRIGGER evaluation_prediction_terminal BEFORE INSERT ON evaluation_predictions
        WHEN (SELECT status FROM evaluation_records WHERE id=NEW.evaluation_id) NOT IN ('queued','running')
        BEGIN SELECT RAISE(ABORT,'evaluation already finalized'); END""")


def downgrade():
    raise RuntimeError('Restore a verified workspace backup; immutable research evidence cannot be downgraded.')
