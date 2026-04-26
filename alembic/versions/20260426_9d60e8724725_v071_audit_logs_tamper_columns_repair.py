"""v071 — repair remaining audit_logs tamper-evidence columns.

V070 restored ``actor_ua`` after Railway logs showed that column missing.
The next production login audit insert then advanced to the next missing
column, ``severity``. A direct production schema inspection confirmed the
legacy ``audit_logs`` table also lacks ``endpoint``, ``request_id``, and
``prev_hash``.

This migration is intentionally additive only. ``audit_logs`` is
append-only, so we avoid historical row rewrites and simply make the live
table accept the ORM insert shape used by ``AuditLogger``.

Revision ID: 9d60e8724725
Revises: 5981332730ae
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op


revision: str = "9d60e8724725"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "5981332730ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_REPAIR_SQL = """
DO $$
BEGIN
    IF to_regclass('public.audit_logs') IS NULL THEN
        RAISE NOTICE 'v071: public.audit_logs absent; skipping tamper-column repair';
        RETURN;
    END IF;

    ALTER TABLE public.audit_logs
        ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'info',
        ADD COLUMN IF NOT EXISTS endpoint TEXT,
        ADD COLUMN IF NOT EXISTS request_id UUID,
        ADD COLUMN IF NOT EXISTS prev_hash TEXT;

    ALTER TABLE public.audit_logs
        ALTER COLUMN severity SET DEFAULT 'info';

    COMMENT ON COLUMN public.audit_logs.severity IS
        'Audit event severity; defaults to info for compatibility with legacy rows.';
    COMMENT ON COLUMN public.audit_logs.endpoint IS
        'HTTP method and route captured for request-scoped audit events.';
    COMMENT ON COLUMN public.audit_logs.request_id IS
        'Request correlation id captured for request-scoped audit events.';
    COMMENT ON COLUMN public.audit_logs.prev_hash IS
        'Previous audit-row integrity hash for tamper-evident hash chaining.';
END$$;
"""


def upgrade() -> None:
    op.execute(_REPAIR_SQL)


def downgrade() -> None:
    # No-op by design. These columns are part of the canonical audit-log
    # schema, and dropping audit evidence columns would be destructive.
    op.execute(
        """
        DO $$ BEGIN
            RAISE NOTICE 'v071 downgrade is a no-op; tamper-evidence columns are canonical audit schema';
        END$$;
        """
    )
