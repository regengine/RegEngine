# ============================================================================
# OPERATIONAL HARDENING — V048
# ============================================================================
# Adds tables for:
#   - FDA SLA request tracking (24-hour response mandate)
#   - Chain verification audit log
#
# These tables back the in-memory fallback stores in sla_tracking.py and
# chain_verification_job.py, ensuring data survives process restarts.
#
# For existing databases:
#     alembic upgrade head
# ============================================================================

"""operational hardening — V048: SLA tracking + chain verification log

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-27 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET search_path TO fsma, public;")

    # --- FDA SLA Request Tracking ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS fsma.fda_sla_requests (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL,
            request_type    TEXT NOT NULL DEFAULT 'records_request',
            status          TEXT NOT NULL DEFAULT 'open',
            requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            deadline_at     TIMESTAMPTZ NOT NULL,
            completed_at    TIMESTAMPTZ,
            export_ids      TEXT,
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT fda_sla_requests_status_check
                CHECK (status IN ('open', 'in_progress', 'completed', 'overdue')),
            CONSTRAINT fda_sla_requests_type_check
                CHECK (request_type IN ('records_request', 'inspection', 'recall'))
        );

        CREATE INDEX IF NOT EXISTS idx_fda_sla_requests_tenant
            ON fsma.fda_sla_requests (tenant_id);
        CREATE INDEX IF NOT EXISTS idx_fda_sla_requests_status
            ON fsma.fda_sla_requests (tenant_id, status);
        CREATE INDEX IF NOT EXISTS idx_fda_sla_requests_deadline
            ON fsma.fda_sla_requests (deadline_at)
            WHERE status IN ('open', 'in_progress');
    """)

    # --- Chain Verification Audit Log ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS fsma.chain_verification_log (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL,
            job_id          TEXT NOT NULL,
            chain_valid     BOOLEAN NOT NULL,
            chain_length    INTEGER NOT NULL DEFAULT 0,
            errors          JSONB DEFAULT '[]',
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT chain_verification_log_unique_job
                UNIQUE (job_id)
        );

        CREATE INDEX IF NOT EXISTS idx_chain_verification_log_tenant
            ON fsma.chain_verification_log (tenant_id);
        CREATE INDEX IF NOT EXISTS idx_chain_verification_log_completed
            ON fsma.chain_verification_log (tenant_id, completed_at DESC);
    """)

    # --- RLS policies ---
    op.execute("""
        ALTER TABLE fsma.fda_sla_requests ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fsma.fda_sla_requests FORCE ROW LEVEL SECURITY;
        ALTER TABLE fsma.chain_verification_log ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fsma.chain_verification_log FORCE ROW LEVEL SECURITY;

        DO $$ BEGIN
            CREATE POLICY tenant_isolation_sla ON fsma.fda_sla_requests
                USING (tenant_id::text = current_setting('app.tenant_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;

        DO $$ BEGIN
            CREATE POLICY tenant_isolation_chain_log ON fsma.chain_verification_log
                USING (tenant_id::text = current_setting('app.tenant_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    op.execute("SET search_path TO fsma, public;")
    op.execute("DROP TABLE IF EXISTS fsma.chain_verification_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.fda_sla_requests CASCADE;")
