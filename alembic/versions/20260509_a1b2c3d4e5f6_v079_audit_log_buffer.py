"""v079 -- audit_log_buffer durable buffer for KDE_READ failure policy.

Revision ID: a1b2c3d4e5f6
Revises: 5ac9e7b1d402
Create Date: 2026-05-09

Adds the ``audit_log_buffer`` table that backs the buffered failure policy
for KDE_READ audit events (RE-SEC-006). When the primary audit-log backend
is unavailable and policy=buffered, events are inserted here. A separate
reconciliation job (out of scope for this migration) replays them against
the primary backend and stamps ``replayed_at``.

Additive only: no existing table is modified.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "5ac9e7b1d402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.audit_log_buffer (
            id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id            text NOT NULL,
            actor                text NOT NULL,
            event_type           text NOT NULL,
            payload              jsonb NOT NULL,
            originally_failed_at timestamptz NOT NULL,
            primary_error        text,
            replayed_at          timestamptz NULL,
            replay_attempts      integer NOT NULL DEFAULT 0,
            created_at           timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_log_buffer_unreplayed
            ON public.audit_log_buffer (created_at)
            WHERE replayed_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_log_buffer_tenant
            ON public.audit_log_buffer (tenant_id, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.idx_audit_log_buffer_tenant")
    op.execute("DROP INDEX IF EXISTS public.idx_audit_log_buffer_unreplayed")
    op.execute("DROP TABLE IF EXISTS public.audit_log_buffer")
