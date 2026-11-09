"""回收桶補強（2026-11-09）：特徵集可以跟著分割訓練移入回收桶。可重複執行。"""
import sqlalchemy as sa
from alembic import op

revision = 'r0007'
down_revision = 'r0006'


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('feature_sets')}
    if 'trashed_at' not in existing:
        op.add_column('feature_sets', sa.Column('trashed_at', sa.String(32), nullable=True))


def downgrade():
    raise RuntimeError('不支援降版')
