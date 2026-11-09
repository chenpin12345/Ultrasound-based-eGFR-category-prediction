"""M3：檢查的醫師修改（腎長、分級）存在 clinical_exams.overrides_json。可重複執行。"""
import sqlalchemy as sa
from alembic import op

revision = 'c0003'
down_revision = 'c0002'


def upgrade():
    bind = op.get_bind()
    if 'overrides_json' not in {c['name'] for c in sa.inspect(bind).get_columns('clinical_exams')}:
        op.add_column('clinical_exams', sa.Column('overrides_json', sa.Text(), nullable=False, server_default='{}'))


def downgrade():
    raise RuntimeError('不支援降版')
