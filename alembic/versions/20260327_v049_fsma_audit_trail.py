"""Add fsma_audit_trail table for persistent audit logging.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-27 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute("""
        CREATE TABLE IF NOT EXISTS fsma.fsma_audit_trail (
            id              BIGSERIAL PRIMARY KEY,
            event_id        TEXT NOT NULL,
            actor           TEXT NOT NULL,
            actor_type      TEXT NOT NULL,
            action          TEXT NOT NULL,
            target_type     TEXT,
            target_id       TEXT,
            tenant_id       TEXT,
            correlation_id  TEXT,
            confidence      DOUBLE PRECISION,
            evidence_link   TEXT,
            checksum        TEXT NOT NULL,
            previous_checksum TEXT,
            diff_json       JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_trail_tenant_time
        ON fsma.fsma_audit_trail (tenant_id, created_at)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_trail_event_id
        ON fsma.fsma_audit_trail (event_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_trail_target
        ON fsma.fsma_audit_trail (target_type, target_id)
    """)

    # Enable RLS for tenant isolation
    op.execute("ALTER TABLE fsma.fsma_audit_trail ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_audit ON fsma.fsma_audit_trail
        USING (tenant_id::text = current_setting('app.tenant_id', true))
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fsma.fsma_audit_trail CASCADE")
