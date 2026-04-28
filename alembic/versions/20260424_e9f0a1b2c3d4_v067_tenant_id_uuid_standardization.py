"""v067 — standardize tenant_id columns to UUID across fsma.* outliers.

Most tenant-carrying tables in RegEngine use ``tenant_id UUID`` (the
canonical type). Five outliers were created with ``TEXT`` or
``VARCHAR(36)`` instead, which silently breaks every RLS policy that
does ``tenant_id = get_tenant_context()`` because ``get_tenant_context()``
returns ``UUID`` — Postgres rejects the comparison with ``operator does
not exist: text = uuid``. The same drift hit ``audit_logs`` and was
fixed by v065 (``20260423_c7d8e9f0a1b2``); this migration applies the
same fix to the remaining four tables.

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
four tables are tenant-scoped audit / queue / metadata surfaces — no
heavy row counts expected. If sampling shows a particular table has
grown unexpectedly large in prod, run the dual-write migration pattern
instead (add new uuid column, backfill, swap) — out of scope here.

FIX (2026-04-25): The original v067 attempted bare ``ALTER COLUMN TYPE
... USING ::uuid`` casts. Production hit two compounding failures
analogous to the v065 incident (#1955, #1960):

1. The ALTER is rejected for ``fsma.fsma_audit_trail`` and
   ``fsma.task_queue`` because Postgres refuses ``ALTER COLUMN TYPE``
   on a column referenced by an active RLS policy
   (``tenant_isolation_audit`` from v049, ``tenant_isolation_tasks``
   from v050 / recreated by v063). Each policy is dropped before the
   ALTER and re-created afterward with the original predicate
   preserved — including the ``::text`` cast, which becomes a no-op
   cast on the new UUID column and keeps the RLS comparison against
   ``current_setting('app.tenant_id', true)`` (a text GUC) intact.
2. Even after the policy block is removed, ``USING col::uuid`` aborts
   on any row whose payload doesn't parse as a UUID (empty string,
   stale sentinel, etc.). The deploy logs from prod show
   ``alembic upgrade head`` exiting non-zero on this exact migration
   after the v065 fix unblocked everything before it.

This revision adds, for each of the four tables:

  * A drop-policy step (only for the two tables that have one).
  * A pre-ALTER scrub:
      - Nullable columns (``fsma_audit_trail``, ``task_queue``,
        ``dlq_replay``) — NULL out non-castable rows.
      - NOT NULL columns (``transformation_links``) — DELETE
        offending rows. ``transformation_links`` rows that don't
        carry a parseable UUID tenant cannot be associated with any
        tenant and would never match an RLS policy anyway; deletion
        is the only path forward without a separate manual cleanup
        task.
  * The original ALTER, unchanged.
  * A re-create-policy step (only for the two tables we dropped one
    on).
  * ``RAISE NOTICE`` / ``RAISE WARNING`` so the deploy log records
    how many rows were scrubbed in each table.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-04-24
"""
from typing import Optional, Sequence, Tuple, Union

from alembic import op

revision: str = "e9f0a1b2c3d4"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Per-table fix descriptor.
#
# Fields:
#   schema, table, column     — the column being retyped.
#   is_nullable               — drives scrub semantics: nullable → NULL
#                               offending rows; NOT NULL → DELETE them.
#   policy_name               — name of the RLS policy that references
#                               this column and must be dropped before
#                               the ALTER. None if there is no such
#                               policy.
#   policy_using_clause       — the USING expression to recreate the
#                               policy with after the ALTER, preserved
#                               verbatim from the originating migration
#                               so RLS semantics don't shift here.
#                               None when ``policy_name`` is None.
_FIXES: Tuple[Tuple[str, str, str, bool, Optional[str], Optional[str]], ...] = (
    # fsma_audit_trail — origin v049, has tenant_isolation_audit.
    (
        "fsma",
        "fsma_audit_trail",
        "tenant_id",
        True,
        "tenant_isolation_audit",
        "(tenant_id::text = current_setting('app.tenant_id', true))",
    ),
    # task_queue — origin v050, recreated v063, has tenant_isolation_tasks.
    (
        "fsma",
        "task_queue",
        "tenant_id",
        True,
        "tenant_isolation_tasks",
        "(tenant_id::text = current_setting('app.tenant_id', true) "
        "OR current_setting('app.tenant_id', true) = '')",
    ),
    # transformation_links — origin v057, NOT NULL, RLS policy is
    # created later by v068 (so v067 has nothing to drop here).
    (
        "fsma",
        "transformation_links",
        "tenant_id",
        False,
        None,
        None,
    ),
    # dlq_replay — origin v060, VARCHAR(36), no RLS policy referencing
    # tenant_id at this point in the chain.
    (
        "fsma",
        "dlq_replay",
        "tenant_id",
        True,
        None,
        None,
    ),
)


_CREATE_IS_VALID_UUID_FN = """
    -- Session-local helper: TRUE iff ``val`` casts cleanly to uuid.
    -- Wraps the cast in an exception block so castability can be
    -- tested in a pure SQL predicate. Lives in ``pg_temp`` so it
    -- disappears with the session and can't collide with anything.
    CREATE OR REPLACE FUNCTION pg_temp.is_valid_uuid_v067(val text)
    RETURNS boolean
    LANGUAGE plpgsql
    IMMUTABLE
    AS $fn$
    BEGIN
        IF val IS NULL THEN
            RETURN TRUE;
        END IF;
        PERFORM val::uuid;
        RETURN TRUE;
    EXCEPTION
        WHEN invalid_text_representation THEN
            RETURN FALSE;
    END;
    $fn$;
"""


def _scrub_drop_alter_recreate(
    schema: str,
    table: str,
    column: str,
    is_nullable: bool,
    policy_name: Optional[str],
    policy_using_clause: Optional[str],
) -> str:
    """Build the per-table DO block: drop policy → scrub → ALTER → recreate policy.

    Idempotent: if the column is already ``uuid`` the entire body
    short-circuits so re-running the migration on a healthy DB is a
    no-op. Survives missing source tables (fresh bootstrap) and
    missing policies (env that never ran v049 / v050).
    """
    fq_table = f"{schema}.{table}"

    if is_nullable:
        scrub_sql = f"""
                EXECUTE format(
                    'UPDATE {fq_table} '
                    'SET {column} = NULL '
                    'WHERE {column} IS NOT NULL '
                    '  AND NOT pg_temp.is_valid_uuid_v067({column}::text)'
                );
                GET DIAGNOSTICS scrub_count = ROW_COUNT;
                IF scrub_count > 0 THEN
                    RAISE NOTICE
                        'v067 scrub: nulled % non-UUID rows in {fq_table}.{column}',
                        scrub_count;
                END IF;
        """
    else:
        scrub_sql = f"""
                EXECUTE format(
                    'DELETE FROM {fq_table} '
                    'WHERE {column} IS NULL '
                    '   OR NOT pg_temp.is_valid_uuid_v067({column}::text)'
                );
                GET DIAGNOSTICS scrub_count = ROW_COUNT;
                IF scrub_count > 0 THEN
                    RAISE WARNING
                        'v067 scrub: deleted % rows from {fq_table} with '
                        'non-UUID {column} (rows are unreachable under '
                        'tenant-scoped RLS and cannot be retained)',
                        scrub_count;
                END IF;
        """

    if policy_name and policy_using_clause:
        # Escape single quotes — the USING clause embeds ``current_setting(
        # 'app.tenant_id', true)`` whose apostrophes would otherwise close
        # the outer EXECUTE string literal early. Doubling them is the
        # standard PL/pgSQL escape inside a single-quoted SQL string.
        escaped_using = policy_using_clause.replace("'", "''")
        drop_policy_sql = (
            f"EXECUTE 'DROP POLICY IF EXISTS {policy_name} ON {fq_table}';"
        )
        recreate_policy_sql = (
            f"EXECUTE 'CREATE POLICY {policy_name} ON {fq_table} "
            f"USING {escaped_using}';"
        )
    else:
        drop_policy_sql = "-- no RLS policy on this column at v067 time"
        recreate_policy_sql = "-- no RLS policy to recreate"

    return f"""
        DO $$
        DECLARE
            scrub_count bigint := 0;
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
                {drop_policy_sql}

                {scrub_sql}

                EXECUTE
                    'ALTER TABLE {fq_table} '
                    'ALTER COLUMN {column} TYPE uuid USING {column}::uuid';

                {recreate_policy_sql}
            END IF;
        END$$;
    """


def _alter_uuid_to_text(
    schema: str,
    table: str,
    column: str,
    policy_name: Optional[str],
    policy_using_clause: Optional[str],
) -> str:
    """Reverse: idempotent DO block converting ``schema.table.column``
    from uuid back to text. Mirrors the upgrade's policy-drop /
    recreate handshake so the downgrade is symmetric.
    """
    fq_table = f"{schema}.{table}"

    if policy_name and policy_using_clause:
        # Same single-quote escape as ``_scrub_drop_alter_recreate`` — the
        # USING clause apostrophes must be doubled so they survive
        # embedding inside the outer EXECUTE string literal.
        escaped_using = policy_using_clause.replace("'", "''")
        drop_policy_sql = (
            f"EXECUTE 'DROP POLICY IF EXISTS {policy_name} ON {fq_table}';"
        )
        recreate_policy_sql = (
            f"EXECUTE 'CREATE POLICY {policy_name} ON {fq_table} "
            f"USING {escaped_using}';"
        )
    else:
        drop_policy_sql = "-- no RLS policy on this column at v067 time"
        recreate_policy_sql = "-- no RLS policy to recreate"

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
                {drop_policy_sql}

                EXECUTE
                    'ALTER TABLE {fq_table} '
                    'ALTER COLUMN {column} TYPE text USING {column}::text';

                {recreate_policy_sql}
            END IF;
        END$$;
    """


def upgrade() -> None:
    op.execute(_CREATE_IS_VALID_UUID_FN)
    for fix in _FIXES:
        op.execute(_scrub_drop_alter_recreate(*fix))


def downgrade() -> None:
    # Reverse in reverse order purely for symmetry; the ALTERs are
    # independent so order doesn't actually matter here.
    for schema, table, column, _, policy_name, policy_using in reversed(_FIXES):
        op.execute(
            _alter_uuid_to_text(schema, table, column, policy_name, policy_using)
        )
