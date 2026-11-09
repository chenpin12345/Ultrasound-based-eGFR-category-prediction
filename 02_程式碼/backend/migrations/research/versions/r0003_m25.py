"""M2.5：醫師圈選批次與項目、交叉預測遮罩組、依任務的測試鎖。

和 r0002 一樣：先 create_all（只建立缺少的資料表），再逐欄補上缺少的欄位（可重複執行）。
舊的 test_locked=1（整個切分共用的鎖）轉成 {"*": …}，表示所有任務都已鎖定。
"""
import json

import sqlalchemy as sa
from alembic import op

revision = 'r0003'
down_revision = 'r0002'

COLUMNS = {
    'splits': [sa.Column('test_locks_json', sa.Text(), nullable=False, server_default='{}')],
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
    locked = bind.execute(sa.text("SELECT id FROM splits WHERE test_locked = 1 AND (test_locks_json IS NULL OR test_locks_json = '{}')")).fetchall()
    for (split_id,) in locked:
        value = json.dumps({'*': {'by': 'r0003', 'note': '舊版整個切分共用的鎖'}}, ensure_ascii=False)
        bind.execute(sa.text('UPDATE splits SET test_locks_json = :v WHERE id = :i'), {'v': value, 'i': split_id})


def downgrade():
    raise RuntimeError('不支援降版')
