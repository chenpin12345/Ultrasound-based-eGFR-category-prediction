"""M2：遮罩來源與人工確認、脂肪肝欄位，以及訓練、模型庫、評估、特徵、實驗資料表。

r0001 用目前的模型 create_all，所以全新的資料庫在 r0001 就已經有這些欄位；
這裡逐一檢查，只補舊資料庫缺少的欄位與資料表（可重複執行）。
"""
import sqlalchemy as sa
from alembic import op

revision = 'r0002'
down_revision = 'r0001'

COLUMNS = {
    'mask_annotations': [
        sa.Column('source', sa.String(16), nullable=False, server_default='manual'),
        sa.Column('verified_by', sa.String(80), nullable=True),
        sa.Column('verified_at', sa.String(32), nullable=True),
    ],
    'patients': [sa.Column('has_fatty_liver', sa.Boolean(), nullable=True)],
}


def upgrade():
    from app.db import models_research  # noqa: F401
    from app.db.base import ResearchBase

    bind = op.get_bind()
    ResearchBase.metadata.create_all(bind=bind, checkfirst=True)
    inspector = sa.inspect(bind)
    for table, columns in COLUMNS.items():
        existing = {c['name'] for c in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)


def downgrade():
    raise RuntimeError('不支援降版')
