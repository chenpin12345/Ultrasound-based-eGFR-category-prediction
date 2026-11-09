"""M2.5：訓練與模型可以移入回收桶（models 新增 trashed_at；training_runs 原本就有）。可重複執行。"""
import sqlalchemy as sa
from alembic import op

revision = 'r0004'
down_revision = 'r0003'


def upgrade():
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('models')}
    if 'trashed_at' not in existing:
        op.add_column('models', sa.Column('trashed_at', sa.String(32), nullable=True))


def downgrade():
    raise RuntimeError('不支援降版')
