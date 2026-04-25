"""v067 — standardize tenant_id columns to UUID across fsma.* outliers.

Most tenant-carrying tables in RegEngine use ``tenant_id UUID`` (the
canonical type). Five outliers were created with ``TEXT`` or
``VARCHAR(36)`` instead, which silently breaks every RLS policy that
does ``tenant_id = get_tenant_context()`` because ``get_tenant_context()``
returns ``UUID`` — Postgres rejects the comparison with ``operator does
not exist: text = uuid``. The same drift hit ``audit_logs`` and was
fixed by v065 (``20260423_c7d8e9f0a1b2``); this migration applies the
same fix to the remaining five tables.

Tables fixed:

  * ``fsma.fsma_audit_trail.tenant_id``      TEXT       → UUID  (origin: v049)
  * ``fsma.task_queue.tenant_id``            TEXT       → UUID  (origin: v050, recreated v063)
  * ``fsma.transformation_links.tenant_id``  TEXT NOT NULL → UUID NOT NULL  (origin: v057)
  * ``fsma.dlq_replay.tenant_id``            VARCHAR(36) → UUID  (origin: v060)

Each ALTER is guarded by an ``information_schema`` check so the
migration is idempotent on environments where the column may already
be ``uuid`` (fresh CI, dev DBs that ran a different migration order).

Production note: ``ALTER COLUMN TYPE TEXT -> UUID`` rewrites the table
and holds ``ACCESS EXCLUSIVE`` until the scan + cast completes. All
five tables are tenant-scoped audit / queue / metadata surfaces — no
heavy row counts expected. If sampling shows a particular table has
grown unexpectedly large in prod, run the dual-write migration pattern
instead (add new uuid column, backfill, swap) — out of scope here.

Failure mode: if any existing row in any of these tables holds a value
that doesn't parse as a UUID (e.g. an empty string, a non-UUID literal
inserted by a buggy older path), ``::uuid`` cast raises and the whole
migration aborts. The DB is left at its prior state with no partial
type change. To recover: run a SELECT to find the offending rows, fix
or delete them, retry the migration.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-04-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e9f0a1b2c3d4"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Each tuple: (schema_qualified_table, full_table_for_DO, column_name,
#              source_data_type_label_in_information_schema)
# The ``data_type`` value in ``information_schema.columns`` for
# ``VARCHAR(36)`` is ``character varying``; for ``TEXT`` it's ``text``.
# Listing both so the guard works regardless of which the table started
# with — including an env that already partially migrated.
_COLUMNS_TO_FIX = [
    ("fsma", "fsma_audit_trail", "tenant_id"),
    ("fsma", "task_queue",       "tenant_id"),
    ("fsma", "transformation_links", "tenant_id"),
    ("fsma", "dlq_replay",       "tenant_id"),
]


def _alter_text_or_varchar_to_uuid(schema: str, table: str, column: str) -> str:
    """Return an idempotent DO block converting ``schema.table.column``
    from text/character varying to uuid.

    Skips the ALTER if the table doesn't exist (fresh DB where the
    upstream creation migration hasn't run) or if the column is already
    ``uuid`` (re-running the migration).
    """
    fq_table = f"{schema}.{table}"
    return f"""
        DO $$
        BEGIN
            IF to_regclass('{fq_table}') IS NULL THEN
                RETURN;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = '{schema}'
                  AND table_name = '{table}'
                  AND column_name = '{column}'
                  AND data_type IN ('text', 'character varying')
            ) THEN
                EXECUTE
                    'ALTER TABLE {fq_table} '
                    'ALTER COLUMN {column} TYPE uuid USING {column}::uuid';
            END IF;
        END$$;
    """


def _alter_uuid_to_text(schema: str, table: str, column: str) -> str:
    """Reverse: idempotent DO block converting ``schema.table.column``
    from uuid back to text.  Only used by ``downgrade()`` — the live
    schema after upgrade should always be uuid.
    """
    fq_table = f"{schema}.{table}"
    return f"""
        DO $$
        BEGIN
            IF to_regclass('{fq_table}') IS NULL THEN
                RETURN;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = '{schema}'
                  AND table_name = '{table}'
                  AND column_name = '{column}'
                  AND data_type = 'uuid'
            ) THEN
                EXECUTE
                    'ALTER TABLE {fq_table} '
                    'ALTER COLUMN {column} TYPE text USING {column}::text';
            END IF;
        END$$;
    """


def upgrade() -> None:
    for schema, table, column in _COLUMNS_TO_FIX:
        op.execute(_alter_text_or_varchar_to_uuid(schema, table, column))


def downgrade() -> None:
    # Reverse in reverse order purely for symmetry; the ALTERs are
    # independent so order doesn't actually matter here.
    for schema, table, column in reversed(_COLUMNS_TO_FIX):
        op.execute(_alter_uuid_to_text(schema, table, column))
