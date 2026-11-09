"""M3：臨床回饋加上修改種類、側別、影像、原因、模型（研究端審核時看得懂是哪一項）。可重複執行。"""
import sqlalchemy as sa
from alembic import op

revision = 'r0005'
down_revision = 'r0004'

COLUMNS = [
    sa.Column('kind', sa.String(32), nullable=False, server_default=''),
    sa.Column('side', sa.String(8), nullable=True),
    sa.Column('image_id', sa.String(24), nullable=True),
    sa.Column('reason', sa.String(200), nullable=False, server_default=''),
    sa.Column('model_id', sa.String(120), nullable=True),
]


def upgrade():
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('clinical_feedback')}
    for column in COLUMNS:
        if column.name not in existing:
            op.add_column('clinical_feedback', column)


def downgrade():
    raise RuntimeError('不支援降版')
