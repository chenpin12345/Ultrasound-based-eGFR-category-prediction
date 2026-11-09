"""醫師圈選網站：每張影像的回音分級（決策 D49）。可重複執行。"""
import sqlalchemy as sa
from alembic import op

revision = 'r0006'
down_revision = 'r0005'


def upgrade():
    if 'image_grades' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'image_grades',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('image_id', sa.String(24), sa.ForeignKey('images.id'), nullable=False),
        sa.Column('grade', sa.Integer, nullable=True),
        sa.Column('unsure_reason', sa.String(80), nullable=True),
        sa.Column('rater', sa.String(80), nullable=False),
        sa.Column('created_at', sa.String(32), nullable=False),
        sa.UniqueConstraint('image_id', 'rater', name='uq_image_grade_rater'),
    )
    op.create_index('ix_image_grades_image_id', 'image_grades', ['image_id'])


def downgrade():
    raise RuntimeError('不支援降版')
