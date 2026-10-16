"""Validate/adopt the existing research schema, or create a new installation."""
from alembic import op
from sqlalchemy import create_engine, inspect

from backend.app.db.migrations.legacy_schema import Base

revision = 'research_0001'
down_revision = None


def signature(connection, table):
    inspector = inspect(connection)
    return {
        'columns': sorted((c['name'], str(c['type']), c['nullable'], c['default']) for c in inspector.get_columns(table)),
        'pk': tuple(inspector.get_pk_constraint(table)['constrained_columns']),
        'unique': sorted(tuple(c['column_names']) for c in inspector.get_unique_constraints(table)),
        'fk': sorted((tuple(c['constrained_columns']), c['referred_table'], tuple(c['referred_columns']),
                      c.get('options', {}).get('ondelete')) for c in inspector.get_foreign_keys(table)),
        'checks': sorted(c['sqltext'].strip() for c in inspector.get_check_constraints(table)),
        'indexes': sorted((tuple(c['column_names']),bool(c['unique'])) for c in inspector.get_indexes(table)),
    }


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != 'sqlite':
        raise RuntimeError('Research migrations currently require the validated local SQLite schema.')
    actual = set(inspect(connection).get_table_names()) - {'alembic_version'}
    expected = set(Base.metadata.tables)
    if not actual:
        Base.metadata.create_all(connection)
        return
    if actual != expected:
        raise RuntimeError('Research baseline mismatch: unexpected or missing tables; no blind stamp is permitted.')
    reference = create_engine('sqlite://')
    try:
        Base.metadata.create_all(reference)
        for table in sorted(expected):
            if signature(connection, table) != signature(reference, table):
                raise RuntimeError(f'Research baseline mismatch in {table}; restore or inspect before upgrading.')
    finally:
        reference.dispose()


def downgrade():
    raise RuntimeError('Use a verified matched workspace backup; destructive downgrade is disabled.')
