"""M1 基準：建立 research 資料表。之後的變更用新的 revision，不修改這個檔案。"""
from alembic import op

revision = 'r0001'
down_revision = None


def upgrade():
    from app.db import models_research  # noqa: F401
    from app.db.base import ResearchBase

    ResearchBase.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('不支援降版')
