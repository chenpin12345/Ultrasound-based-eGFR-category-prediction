"""Physician default plans, versioned case data and transfer protocol 2.

Additive only: existing sessions, items, runs and reports keep their meaning. Legacy
demo sessions have NULL plan_mode and keep the plan they were created with.
"""
import hashlib

from alembic import op
revision='0011'
down_revision='0010'
branch_labels=None
depends_on=None


def immutable(table,label):
    op.execute(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'immutable {label}'); END")
    op.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'immutable {label}'); END")


def upgrade():
    op.execute('''CREATE TABLE clinical_default_plans(
        id TEXT PRIMARY KEY,source TEXT NOT NULL CHECK(source IN('network_demo','capture')),
        mode TEXT NOT NULL CHECK(mode IN('plan','preview_only')),plan_id TEXT REFERENCES plans(id),
        evidence TEXT NOT NULL,actor TEXT NOT NULL REFERENCES users(id),created REAL NOT NULL,
        CHECK((mode='plan' AND plan_id IS NOT NULL) OR (mode='preview_only' AND plan_id IS NULL)))''')
    op.execute('CREATE INDEX clinical_default_plans_source ON clinical_default_plans(source,created)')
    immutable('clinical_default_plans','default plan history')
    op.execute('''CREATE TABLE exam_basic_versions(
        exam_id TEXT NOT NULL REFERENCES exams(id),revision INTEGER NOT NULL,title TEXT NOT NULL,side TEXT NOT NULL,
        payload TEXT NOT NULL,payload_sha256 TEXT NOT NULL,
        source TEXT NOT NULL CHECK(source IN('transfer','manual','legacy')),actor TEXT,created REAL NOT NULL,
        PRIMARY KEY(exam_id,revision))''')
    op.execute("CREATE TRIGGER exam_basic_versions_no_update BEFORE UPDATE ON exam_basic_versions BEGIN SELECT RAISE(ABORT,'immutable case data version'); END")
    # The creation version of a never-edited, empty exam may go only together with
    # that exam (lifecycle "delete empty"); any edited history is permanent.
    op.execute('''CREATE TRIGGER exam_basic_versions_no_delete BEFORE DELETE ON exam_basic_versions
        WHEN (SELECT COUNT(*) FROM exam_basic_versions WHERE exam_id=OLD.exam_id)>1
          OR EXISTS(SELECT 1 FROM frames WHERE exam_id=OLD.exam_id)
          OR EXISTS(SELECT 1 FROM reports WHERE exam_id=OLD.exam_id)
        BEGIN SELECT RAISE(ABORT,'immutable case data version'); END''')
    # The current state of each existing exam becomes its recorded version; no
    # earlier revision is invented.
    bind=op.get_bind()
    for row in bind.exec_driver_sql('SELECT id,revision,title,side,payload,created FROM exams').fetchall():
        bind.exec_driver_sql("INSERT INTO exam_basic_versions VALUES(?,?,?,?,?,?,'legacy',NULL,?)",
                             (row[0],row[1],row[2],row[3],row[4],hashlib.sha256(row[4].encode()).hexdigest(),row[5]))
    op.execute('''CREATE TABLE receiver_settings(
        id INTEGER PRIMARY KEY CHECK(id=1),mode TEXT NOT NULL CHECK(mode IN('auto','manual')),
        host TEXT NOT NULL,port INTEGER,updated REAL NOT NULL)''')
    for column in ('plan_mode TEXT','default_setting_id TEXT REFERENCES clinical_default_plans(id)',
                   'protocol INTEGER','host TEXT','port INTEGER'):
        op.execute('ALTER TABLE demo_sessions ADD COLUMN '+column)
    op.execute("CREATE TRIGGER demo_session_plan_locked BEFORE UPDATE OF plan_id,plan_mode,default_setting_id,protocol ON demo_sessions BEGIN SELECT RAISE(ABORT,'session plan is locked'); END")
    for column in ('exam_id TEXT REFERENCES exams(id)','case_code TEXT','case_sha256 TEXT','case_payload TEXT',
                   'staging_frame_id TEXT','missing_fields TEXT'):
        op.execute('ALTER TABLE items ADD COLUMN '+column)
    op.execute("CREATE TRIGGER items_case_identity BEFORE UPDATE OF case_sha256,sha256 ON items BEGIN SELECT RAISE(ABORT,'immutable item identity'); END")
    op.execute('CREATE INDEX items_exam ON items(exam_id,status)')


def downgrade():
    raise RuntimeError('Restore a matched backup; default plan and case version history cannot be discarded.')
