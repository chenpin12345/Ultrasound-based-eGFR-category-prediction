"""${message}"""
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}


def upgrade():
    pass


def downgrade():
    raise RuntimeError('不支援降版')
