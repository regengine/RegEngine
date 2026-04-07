# ============================================================================
# AUDIT INDEXES + SLA OPTIMISTIC LOCKING — V052
# ============================================================================
# 1. Composite indexes on audit_logs for filtered queries:
#      (tenant_id, timestamp DESC) — time-range scans
#      (tenant_id, event_category) — category filter
#
# 2. Optimistic locking column on fda_sla_requests:
#      version INTEGER NOT NULL DEFAULT 1
#      Prevents silent overwrites on concurrent status updates.
#
# For existing databases:
#     alembic upgrade head
# ============================================================================

"""audit indexes + SLA optimistic locking — V052

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Composite indexes on audit_logs ---
    # These cover the two hot query patterns in audit_routes.py:
    #   1. Filter by tenant + time range (every export query)
    #   2. Filter by tenant + event_category (optional filter)
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_tenant_timestamp
            ON audit_logs (tenant_id, "timestamp" DESC);
    """)
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_tenant_category
            ON audit_logs (tenant_id, event_category);
    """)

    # --- Optimistic locking on fda_sla_requests ---
    # Adds a version column so concurrent updates can detect conflicts:
    #   UPDATE ... SET status = :s, version = version + 1
    #   WHERE id = :id AND version = :expected_version
    op.execute("""
        ALTER TABLE fsma.fda_sla_requests
            ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE fsma.fda_sla_requests DROP COLUMN IF EXISTS version;")
    op.execute("DROP INDEX IF EXISTS idx_audit_logs_tenant_category;")
    op.execute("DROP INDEX IF EXISTS idx_audit_logs_tenant_timestamp;")
