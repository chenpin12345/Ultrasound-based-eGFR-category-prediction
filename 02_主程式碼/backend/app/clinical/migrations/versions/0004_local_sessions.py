"""Local operator identities are not login-capable human accounts."""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN actor_kind TEXT NOT NULL DEFAULT 'human' CHECK(actor_kind IN ('human','local_system'))")
    op.execute("CREATE UNIQUE INDEX one_local_actor ON users(actor_kind) WHERE actor_kind='local_system'")
    op.execute('''CREATE TABLE local_sessions(
        id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
        actor_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL,
        capabilities TEXT NOT NULL, boot_id TEXT NOT NULL,
        created REAL NOT NULL, expires REAL NOT NULL, revoked REAL)''')
    op.execute('CREATE INDEX local_session_expiry ON local_sessions(expires)')


def downgrade():
    raise RuntimeError('Restore matched code/data backup; historical actors must not be dropped.')
