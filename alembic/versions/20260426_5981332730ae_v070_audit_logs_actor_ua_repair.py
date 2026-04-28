"""v070 — repair audit_logs actor_ua schema drift.

Production evidence from the 2026-04-26 Railway/E2E run showed login
side-effects failing on this insert:

    column "actor_ua" of relation "audit_logs" does not exist

``AuditLogModel`` and the legacy Flyway V30 table both include
``actor_ua``. This migration closes the Alembic-managed schema gap for
Railway databases that have ``audit_logs`` but missed that column.

Revision ID: 5981332730ae
Revises: abc565b7dc47
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op


revision: str = "5981332730ae"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "abc565b7dc47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.audit_logs') IS NULL THEN
                RAISE NOTICE 'v070: public.audit_logs absent; skipping actor_ua repair';
                RETURN;
            END IF;

            ALTER TABLE public.audit_logs
                ADD COLUMN IF NOT EXISTS actor_ua TEXT;

            ALTER TABLE public.audit_logs
                ALTER COLUMN actor_ua TYPE TEXT;

            COMMENT ON COLUMN public.audit_logs.actor_ua IS
                'Bounded user-agent captured for tamper-evident audit events.';
        END$$;
        """
    )


def downgrade() -> None:
    # No-op by design. ``actor_ua`` is part of the canonical audit-log
    # schema, and dropping audit evidence columns would be destructive.
    op.execute(
        """
        DO $$ BEGIN
            RAISE NOTICE 'v070 downgrade is a no-op; actor_ua is canonical audit schema';
        END$$;
        """
    )
