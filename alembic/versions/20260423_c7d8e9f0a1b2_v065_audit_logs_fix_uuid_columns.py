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
- ALTERs ``tenant_id``, ``actor_id``, ``request_id`` from ``text`` to ``uuid``.
- Re-issues the v056 RLS policy for ``audit_logs`` without the now-redundant
  ``::uuid`` cast, so it matches the sibling tables.
- Each ALTER is guarded by an ``information_schema`` check so the migration
  is idempotent on environments where the column is already ``uuid``.

Production note: ``ALTER COLUMN TYPE text -> uuid`` rewrites the table and
holds ``ACCESS EXCLUSIVE`` until the scan+cast completes. ``audit_logs`` is
append-only (no UPDATE / DELETE by design), so the lock window is bounded
by row count. Operators should sample ``pg_class.reltuples`` for
``audit_logs`` and a trial run on a staging snapshot before rolling this
to prod. If the table is large enough that the lock window is
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


_COLUMNS_TO_FIX = ("tenant_id", "actor_id", "request_id")


def _alter_column_text_to_uuid(column: str) -> str:
    """Return an idempotent DO block that converts a text column to uuid.

    No-op if the column is already uuid or the table is absent (e.g. fresh
    bootstrap where the baseline has not run yet for some reason).
    """
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
                  AND data_type = 'text'
            ) THEN
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
    # Drop the RLS policy BEFORE altering column types. PostgreSQL does not
    # allow ``ALTER COLUMN TYPE`` on a column that is referenced by an active
    # policy definition — the ALTER fails with:
    #   "cannot alter type of a column used in a policy definition"
    # Dropping the policy first unblocks the type changes; we recreate it
    # immediately after with the corrected (cast-free) expression.
    op.execute(
        """
        DO $
        BEGIN
            IF to_regclass('public.audit_logs') IS NULL THEN
                RETURN;
            END IF;
            DROP POLICY IF EXISTS tenant_isolation_audit ON public.audit_logs;
        END$;
        """
    )

    for column in _COLUMNS_TO_FIX:
        op.execute(_alter_column_text_to_uuid(column))

    # Re-issue the v056 RLS policy for audit_logs without the ``::uuid``
    # workaround cast. With tenant_id now typed as uuid, the cast is
    # redundant and masks future drift if it sneaks back in.
    op.execute(
        """
        DO $
        BEGIN
            IF to_regclass('public.audit_logs') IS NULL THEN
                RETURN;
            END IF;
            CREATE POLICY tenant_isolation_audit ON public.audit_logs
                FOR ALL USING (tenant_id = get_tenant_context());
        END$;
        """
    )


def downgrade() -> None:
    # Reverse the policy change first — the policy references the column,
    # but re-issuing it with plain equality works against either type.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.audit_logs') IS NULL THEN
                RETURN;
            END IF;
            DROP POLICY IF EXISTS tenant_isolation_audit ON public.audit_logs;
            CREATE POLICY tenant_isolation_audit ON public.audit_logs
                FOR ALL USING (tenant_id::uuid = get_tenant_context());
        END$$;
        """
    )
    for column in _COLUMNS_TO_FIX:
        op.execute(_alter_column_uuid_to_text(column))
