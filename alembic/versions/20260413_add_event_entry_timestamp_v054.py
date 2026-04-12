"""Add event_entry_timestamp column to cte_events table

FDA 21 CFR 1.1455 requires recording when data was entered into the
traceability system, distinct from when the event occurred (event_timestamp).
Existing rows are backfilled from ingested_at as the best available proxy.

Revision ID: a8b9c0d1e2f3
Revises: 97a8b9c0d1e2
Create Date: 2026-04-13
"""
from alembic import op

# revision identifiers
revision = "a8b9c0d1e2f3"
down_revision = "97a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add event_entry_timestamp to fsma.cte_events and backfill from ingested_at."""
    op.execute("""
        ALTER TABLE fsma.cte_events
        ADD COLUMN IF NOT EXISTS event_entry_timestamp TIMESTAMPTZ;
    """)
    op.execute("""
        COMMENT ON COLUMN fsma.cte_events.event_entry_timestamp
        IS 'FDA 21 CFR 1.1455 — when the record was entered into the system (distinct from event_timestamp)';
    """)
    # Backfill: use ingested_at as best proxy for historical records
    op.execute("""
        UPDATE fsma.cte_events
        SET event_entry_timestamp = ingested_at
        WHERE event_entry_timestamp IS NULL
          AND ingested_at IS NOT NULL;
    """)


def downgrade() -> None:
    """Remove event_entry_timestamp column."""
    op.execute("ALTER TABLE fsma.cte_events DROP COLUMN IF EXISTS event_entry_timestamp;")
