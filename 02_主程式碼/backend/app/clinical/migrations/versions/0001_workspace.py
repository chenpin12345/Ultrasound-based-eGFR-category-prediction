"""Independent clinical schema; original research database is untouched."""
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = [
    '''CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
       roles TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)))''',
    '''CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
       csrf TEXT NOT NULL, expires REAL NOT NULL)''',
    '''CREATE TABLE patients(id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
       created REAL NOT NULL)''',
    '''CREATE TABLE plans(id TEXT PRIMARY KEY, name TEXT NOT NULL, profile TEXT NOT NULL,
       snapshot TEXT NOT NULL, created REAL NOT NULL)''',
    '''CREATE TABLE exams(id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN('patient','demo')),
       patient_id TEXT REFERENCES patients(id), title TEXT NOT NULL, side TEXT NOT NULL,
       payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL,
       CHECK((kind='demo' AND patient_id IS NULL) OR (kind='patient' AND patient_id IS NOT NULL)))''',
    '''CREATE TRIGGER exam_kind_immutable BEFORE UPDATE OF kind,patient_id ON exams
       BEGIN SELECT RAISE(ABORT,'immutable exam identity'); END''',
    '''CREATE TABLE frames(id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id),
       sha256 TEXT NOT NULL, path TEXT NOT NULL, source TEXT NOT NULL,
       result TEXT, status TEXT NOT NULL, saved INTEGER NOT NULL DEFAULT 0,
       created REAL NOT NULL, UNIQUE(id,exam_id))''',
    '''CREATE TABLE reports(id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id),
       current_version INTEGER NOT NULL, state TEXT NOT NULL, created REAL NOT NULL)''',
    '''CREATE TABLE report_versions(report_id TEXT NOT NULL REFERENCES reports(id), version INTEGER NOT NULL,
       payload TEXT NOT NULL, state TEXT NOT NULL, actor TEXT NOT NULL REFERENCES users(id),
       created REAL NOT NULL, PRIMARY KEY(report_id,version))''',
    '''CREATE TABLE demo_sessions(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id),
       plan_id TEXT REFERENCES plans(id), state TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL)''',
    '''CREATE TABLE batches(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES demo_sessions(id),
       state TEXT NOT NULL, created REAL NOT NULL)''',
    '''CREATE TABLE items(id TEXT NOT NULL, batch_id TEXT NOT NULL REFERENCES batches(id), sha256 TEXT NOT NULL,
       frame_id TEXT REFERENCES frames(id), status TEXT NOT NULL, error TEXT,
       created REAL NOT NULL, PRIMARY KEY(batch_id,id))''',
    '''CREATE TABLE audit(id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
       entity TEXT NOT NULL, created REAL NOT NULL)''',
]


def upgrade():
    for statement in SCHEMA:
        op.execute(statement)


def downgrade():
    raise RuntimeError('Restore a consistent clinical backup; destructive downgrade is disabled.')
