"""v065 — fix audit_logs uuid columns (text -> uuid).

The live DB has ``audit_logs.tenant_id`` / ``actor_id`` / ``request_id`` as
``text``, but ``AuditLogModel`` declares them ``GUID()`` (UUID on Postgres).
Every ORM query therefore emits ``WHERE tenant_id = $1::uuid``, which
Postgres rejects with ``operator does not exist: text = uuid``. The
tamper-evident chain ``SELECT integrity_hash ... ORDER BY id DESC`` in
``AuditLogger._get_prev_hash`` fires this error on every audited request,
silently dropping audit rows and (when the failure propagates across a
pooled connection) aborting the next transaction that touches the same
session.

Evidence of the drift:
- V30 Flyway created the columns as ``UUID NOT NULL`` — the intended shape.
- v056 RLS hardening is the only migration in the project that uses
  ``tenant_id::uuid = get_tenant_context()`` (explicit cast), and only for
  ``audit_logs``. Every sibling RLS table uses plain ``tenant_id =
  get_tenant_context()``. That cast is a workaround, not a design choice.
- Runtime logs show ``operator does not exist: text = uuid`` against the
  ``audit_logs.tenant_id = $1::UUID`` predicate.

This migration:
- Drops the v056 ``tenant_isolation_audit`` policy BEFORE altering column
  types, because Postgres rejects ``ALTER COLUMN TYPE`` on a column
  referenced by an active policy definition (``cannot alter type of a
  column used in a policy definition``). This was the bug originally
  fixed in PR #1955 and is preserved here.
- Scrubs any non-UUID-castable values out of ``tenant_id`` / ``actor_id`` /
  ``request_id`` before each ALTER. Without this, ``ALTER COLUMN ... USING
  col::uuid`` aborts on the first row whose text payload is not parseable
  as a UUID (e.g. empty string, the literal ``"system"``, an old internal
  sentinel). The deploy logs from prod show exactly this failure mode in
  the ``audit_logs.tenant_id`` ALTER step. See FIX history below.
- ALTERs ``tenant_id``, ``actor_id``, ``request_id`` from ``text`` to
  ``uuid``.
- Re-issues the v056 RLS policy for ``audit_logs`` without the now-
  redundant ``::uuid`` cast, so it matches the sibling tables.
- Each ALTER is guarded by an ``information_schema`` check so the migration
  is idempotent on environments where the column is already ``uuid``.

FIX (2026-04-25): The previous v065 (after #1955 corrected the policy
ordering) attempted a bare ``ALTER COLUMN tenant_id TYPE uuid USING
tenant_id::uuid``. Production contained at least one row whose
``tenant_id`` payload was not UUID-castable, which aborted the ALTER,
which aborted the deploy, which failed the Railway healthcheck. This
revision adds a pre-ALTER scrub step that:
  * NULLs out non-UUID-castable values in nullable columns
    (``actor_id``, ``request_id``).
  * DELETEs rows whose ``tenant_id`` cannot be cast — those rows are
    already broken (no ORM query can read them, the RLS policy in v056
    casts ``tenant_id::uuid`` and would fault on them, and the integrity
    hash chain has no way to attribute them). Deletion happens here,
    BEFORE the v066 append-only trigger is installed, so the table is
    still mutable.
  * Counts and ``RAISE NOTICE``s the scrub volume so operators see what
    was removed at deploy time.

Production note: ``ALTER COLUMN TYPE text -> uuid`` rewrites the table and
holds ``ACCESS EXCLUSIVE`` until the scan+cast completes. ``audit_logs`` is
append-only (no UPDATE / DELETE by design after v066), so the lock window
is bounded by row count. Operators should sample ``pg_class.reltuples``
for ``audit_logs`` and a trial run on a staging snapshot before rolling
this to prod. If the table is large enough that the lock window is
unacceptable, the alternative is a dual-write migration (add new uuid
column, backfill, swap) — not in scope here.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c7d8e9f0a1b2"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (column, is_nullable). ``tenant_id`` is NOT NULL per the ORM model,
# so non-castable rows must be deleted rather than NULLed.
_COLUMNS_TO_FIX = (
    ("tenant_id", False),
    ("actor_id", True),
    ("request_id", True),
)


_CREATE_IS_VALID_UUID_FN = """
    -- Session-local helper: returns TRUE iff ``val`` casts cleanly to uuid.
    -- Wraps the cast in an exception block so we can test castability in a
    -- pure SQL predicate. Lives in ``pg_temp`` so it disappears with the
    -- session and never collides with anything else.
    CREATE OR REPLACE FUNCTION pg_temp.audit_logs_is_valid_uuid(val text)
    RETURNS boolean
    LANGUAGE plpgsql
    IMMUTABLE
    AS $fn$
    BEGIN
        IF val IS NULL THEN
            RETURN TRUE;  -- NULL is fine for nullable columns; caller
                          -- handles the NOT NULL case separately.
        END IF;
        PERFORM val::uuid;
        RETURN TRUE;
    EXCEPTION
        WHEN invalid_text_representation THEN
            RETURN FALSE;
    END;
    $fn$;
"""


_DROP_POLICY_SQL = """
    DO $$
    BEGIN
        IF to_regclass('public.audit_logs') IS NULL THEN
            RETURN;
        END IF;
        DROP POLICY IF EXISTS tenant_isolation_audit ON public.audit_logs;
    END$$;
"""


_CREATE_POLICY_NO_CAST_SQL = """
    DO $$
    BEGIN
        IF to_regclass('public.audit_logs') IS NULL THEN
            RETURN;
        END IF;
        CREATE POLICY tenant_isolation_audit ON public.audit_logs
            FOR ALL USING (tenant_id = get_tenant_context());
    END$$;
"""


def _scrub_and_alter_text_to_uuid(column: str, is_nullable: bool) -> str:
    """Return an idempotent DO block that scrubs bad rows then ALTERs.

    No-op if the column is already uuid or the table is absent (e.g. fresh
    bootstrap where the baseline has not run yet for some reason).

    Scrub semantics:
        * Nullable columns -> set offending rows to NULL.
        * NOT NULL columns -> DELETE offending rows (audit_logs is
          append-only AFTER v066; v065 runs before that trigger exists).
    """
    if is_nullable:
        scrub_sql = f"""
                EXECUTE format(
                    'UPDATE public.audit_logs '
                    'SET {column} = NULL '
                    'WHERE {column} IS NOT NULL '
                    '  AND NOT pg_temp.audit_logs_is_valid_uuid({column})'
                );
                GET DIAGNOSTICS scrub_count = ROW_COUNT;
                IF scrub_count > 0 THEN
                    RAISE NOTICE
                        'v065 scrub: nulled % non-UUID rows in audit_logs.{column}',
                        scrub_count;
                END IF;
        """
    else:
        scrub_sql = f"""
                EXECUTE format(
                    'DELETE FROM public.audit_logs '
                    'WHERE {column} IS NULL '
                    '   OR NOT pg_temp.audit_logs_is_valid_uuid({column})'
                );
                GET DIAGNOSTICS scrub_count = ROW_COUNT;
                IF scrub_count > 0 THEN
                    RAISE WARNING
                        'v065 scrub: deleted % audit_logs rows with '
                        'non-UUID {column} (pre-v066, append-only trigger '
                        'not yet installed)', scrub_count;
                END IF;
        """

    return f"""
        DO $$
        DECLARE
            scrub_count bigint := 0;
        BEGIN
            IF to_regclass('public.audit_logs') IS NULL THEN
                RETURN;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'audit_logs'
                  AND column_name = '{column}'
                  AND data_type = 'text'
            ) THEN
                {scrub_sql}
                EXECUTE
                    'ALTER TABLE public.audit_logs '
                    'ALTER COLUMN {column} TYPE uuid USING {column}::uuid';
            END IF;
        END$$;
    """


def _alter_column_uuid_to_text(column: str) -> str:
    """Return an idempotent DO block that reverts a uuid column to text."""
    return f"""
        DO $$
        BEGIN
            IF to_regclass('public.audit_logs') IS NULL THEN
                RETURN;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'audit_logs'
                  AND column_name = '{column}'
                  AND data_type = 'uuid'
            ) THEN
                EXECUTE
                    'ALTER TABLE public.audit_logs '
                    'ALTER COLUMN {column} TYPE text USING {column}::text';
            END IF;
        END$$;
    """


def upgrade() -> None:
    # The scrub helper is created once at the start of the upgrade and
    # reused for each column. ``pg_temp`` keeps it out of the global
    # namespace and lets it die with the session.
    op.execute(_CREATE_IS_VALID_UUID_FN)

    # Drop the RLS policy BEFORE altering column types. PostgreSQL rejects
    # ALTER COLUMN TYPE on a column referenced by an active policy
    # definition: "cannot alter type of a column used in a policy
    # definition". This is the ordering originally fixed in PR #1955 and
    # is preserved here while the scrub step is layered on top.
    op.execute(_DROP_POLICY_SQL)

    for column, is_nullable in _COLUMNS_TO_FIX:
        op.execute(_scrub_and_alter_text_to_uuid(column, is_nullable))

    # Re-issue the v056 RLS policy for audit_logs without the ``::uuid``
    # workaround cast. With tenant_id now typed as uuid, the cast is
    # redundant and masks future drift if it sneaks back in.
    op.execute(_CREATE_POLICY_NO_CAST_SQL)


def downgrade() -> None:
    # Drop the no-cast policy first so the column type can change.
    op.execute(_DROP_POLICY_SQL)
    for column, _ in _COLUMNS_TO_FIX:
        op.execute(_alter_column_uuid_to_text(column))
    # Re-issue the v056 policy with the ``::uuid`` cast for the now-text
    # columns.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.audit_logs') IS NULL THEN
                RETURN;
            END IF;
            CREATE POLICY tenant_isolation_audit ON public.audit_logs
                FOR ALL USING (tenant_id::uuid = get_tenant_context());
        END$$;
        """
    )
