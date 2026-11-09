"""M3：醫師端資料表（病人、檢查、影像、分析、修改紀錄、報告與版本、接收）。只建立缺少的表，可重複執行。"""

revision = 'c0002'
down_revision = 'c0001'


def upgrade():
    from alembic import op

    from app.db import models_clinical  # noqa: F401
    from app.db.base import ClinicalBase

    ClinicalBase.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('不支援降版')
