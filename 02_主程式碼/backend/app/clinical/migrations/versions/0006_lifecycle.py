"""Non-destructive lifecycle is independent of report content state."""
from alembic import op

revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE clinical_lifecycle(
        entity TEXT NOT NULL CHECK(entity IN('patients','exams','reports')), id TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'normal' CHECK(state IN('normal','archived','trashed')),
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
        restore_state TEXT NOT NULL DEFAULT 'normal' CHECK(restore_state IN('normal','archived')),
        updated REAL NOT NULL, PRIMARY KEY(entity,id))''')
    op.execute('''CREATE TABLE clinical_lifecycle_events(
        id TEXT PRIMARY KEY, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
        action TEXT NOT NULL, actor TEXT NOT NULL REFERENCES users(id), reason TEXT NOT NULL,
        before_json TEXT NOT NULL, after_json TEXT NOT NULL, created REAL NOT NULL)''')
    for table in ('patients','exams','reports'):
        op.execute(f"INSERT INTO clinical_lifecycle(entity,id,updated) SELECT '{table}',id,created FROM {table}")
        op.execute(f"""CREATE TRIGGER {table}_lifecycle_insert AFTER INSERT ON {table}
            BEGIN INSERT INTO clinical_lifecycle(entity,id,updated) VALUES('{table}',NEW.id,NEW.created); END""")
        op.execute(f"""CREATE TRIGGER {table}_lifecycle_update AFTER UPDATE ON {table}
            BEGIN UPDATE clinical_lifecycle SET revision=revision+1 WHERE entity='{table}' AND id=NEW.id; END""")
        op.execute(f"""CREATE TRIGGER {table}_lifecycle_delete AFTER DELETE ON {table}
            BEGIN DELETE FROM clinical_lifecycle WHERE entity='{table}' AND id=OLD.id; END""")
    op.execute('CREATE INDEX clinical_lifecycle_status ON clinical_lifecycle(entity,state,id)')
    for operation in ('UPDATE','DELETE'):
        op.execute(f"CREATE TRIGGER lifecycle_events_no_{operation.lower()} BEFORE {operation} ON clinical_lifecycle_events BEGIN SELECT RAISE(ABORT,'immutable lifecycle audit'); END")


def downgrade():
    raise RuntimeError('Restore a consistent backup; lifecycle history cannot be discarded.')
