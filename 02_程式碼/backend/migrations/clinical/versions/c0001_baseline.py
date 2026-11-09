"""M1 基準：臨床資料庫先建立空的版本紀錄，M3 加入資料表。"""

revision = 'c0001'
down_revision = None


def upgrade():
    pass


def downgrade():
    raise RuntimeError('不支援降版')
