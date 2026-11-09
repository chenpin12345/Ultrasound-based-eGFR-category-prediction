"""M1 基準：建立 system 資料表。之後的變更用新的 revision，不修改這個檔案。"""
from alembic import op

revision = 's0001'
down_revision = None


def upgrade():
    from app.db import models_system  # noqa: F401
    from app.db.base import SystemBase

    SystemBase.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('不支援降版')
