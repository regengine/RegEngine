"""v090 -- add per-tenant audit_logs.sequence_num + UNIQUE constraint.

Revision ID: 44225a26ed58
Revises: 38e02636e340
Create Date: 2026-06-29

#2513: The admin tamper-evident audit chain had no per-tenant sequence
column and no UNIQUE (tenant_id, sequence_num) constraint, so concurrent
``log_event`` writers could fork the chain off a shared prev_hash and a
removed middle row left no gap signal. This migration adds a contiguous
per-tenant ``sequence_num``, backfills existing rows in (tenant_id, id)
order, and adds UNIQUE (tenant_id, sequence_num) so a forked chain
surfaces as an IntegrityError and verify_chain can detect gaps.

Additive change (new nullable column + UNIQUE constraint). Idempotent and
safe to re-run. The application computes ``sequence_num`` under a
per-tenant advisory lock so the constraint is never the primary
serialization mechanism — it is defense-in-depth.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "44225a26ed58"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "38e02636e340"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the nullable column (idempotent).
    op.execute("ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS sequence_num BIGINT;")

    # 2. Backfill contiguous per-tenant sequences ordered by id. Only
    #    touch rows that have not been assigned yet so re-runs are cheap
    #    and never renumber an already-sequenced chain.
    #
    #    The v066 ``audit_append_only`` trigger rejects every UPDATE on
    #    audit_logs, including this backfill, on any database that already
    #    has rows (CI migrates empty databases, so only live databases hit
    #    it). Disable it for the backfill and re-enable afterwards; both
    #    ALTERs and the UPDATE share this migration's transaction and the
    #    ACCESS EXCLUSIVE lock, so no concurrent writer ever sees the
    #    trigger disabled.
    #
    # The migration credential is NOBYPASSRLS and audit_logs is FORCE-RLS.
    # Temporarily restore owner access in the same transaction; FORCE is
    # reinstated before the migration returns.
    op.execute("ALTER TABLE public.audit_logs NO FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'audit_append_only'
                  AND tgrelid = 'public.audit_logs'::regclass
            ) THEN
                EXECUTE 'ALTER TABLE public.audit_logs DISABLE TRIGGER audit_append_only';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY id ASC) AS seq
            FROM public.audit_logs
        )
        UPDATE public.audit_logs AS a
        SET sequence_num = numbered.seq
        FROM numbered
        WHERE a.id = numbered.id
          AND a.sequence_num IS NULL;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'audit_append_only'
                  AND tgrelid = 'public.audit_logs'::regclass
            ) THEN
                EXECUTE 'ALTER TABLE public.audit_logs ENABLE TRIGGER audit_append_only';
            END IF;
        END
        $$;
        """
    )
    op.execute("ALTER TABLE public.audit_logs FORCE ROW LEVEL SECURITY;")

    # 3. Enforce per-tenant uniqueness. NULLs are distinct in Postgres, so
    #    any future legacy/NULL rows do not collide. Idempotent via the
    #    pg_constraint guard.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_audit_tenant_sequence'
            ) THEN
                ALTER TABLE public.audit_logs
                    ADD CONSTRAINT uq_audit_tenant_sequence UNIQUE (tenant_id, sequence_num);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public.audit_logs DROP CONSTRAINT IF EXISTS uq_audit_tenant_sequence;")
    op.execute("ALTER TABLE public.audit_logs DROP COLUMN IF EXISTS sequence_num;")
