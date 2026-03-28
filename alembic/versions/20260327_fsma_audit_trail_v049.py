"""Add fsma_audit_trail table for persistent audit logging.

Revision ID: V049
"""
from alembic import op
import sqlalchemy as sa


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
