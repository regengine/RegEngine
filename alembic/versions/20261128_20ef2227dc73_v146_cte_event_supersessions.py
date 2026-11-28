"""Let a stored EDI line be completed by a later record (v146, ADR-007 amendment).

``fsma.cte_events`` is append-only and its hash covers every KDE, so a resend
that supplies a deferred KDE is stored as a new event. This table marks the
event it replaces, so regulator-facing reads return one record for the line.
Rows are never updated or deleted; chain verification still walks both events.

``edi_line_identities.canonical_event_id`` links a line to its canonical event,
which the new event supersedes in ``fsma.traceability_events``.

Revision ID: 20ef2227dc73
Revises: 62355c37e367
"""

from alembic import op

revision = "20ef2227dc73"  # pragma: allowlist secret
down_revision = "62355c37e367"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the insert-only supersession marker and the canonical link."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS fsma.cte_event_supersessions (
            tenant_id uuid NOT NULL,
            superseded_event_id uuid NOT NULL,
            superseding_event_id uuid NOT NULL,
            superseded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (tenant_id, superseded_event_id),
            CHECK (superseded_event_id <> superseding_event_id)
        );
        ALTER TABLE fsma.cte_event_supersessions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fsma.cte_event_supersessions FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS cte_event_supersessions_tenant ON fsma.cte_event_supersessions;
        CREATE POLICY cte_event_supersessions_tenant ON fsma.cte_event_supersessions
            TO regengine
            USING (tenant_id = public.get_tenant_context())
            WITH CHECK (tenant_id = public.get_tenant_context());
        REVOKE ALL ON fsma.cte_event_supersessions FROM PUBLIC;
        GRANT SELECT, INSERT ON fsma.cte_event_supersessions TO regengine;

        ALTER TABLE fsma.edi_line_identities ADD COLUMN IF NOT EXISTS canonical_event_id uuid;
        GRANT UPDATE (canonical_event_id) ON fsma.edi_line_identities TO regengine;
    """)


def downgrade() -> None:
    """Remove both; deploy the previous application before downgrade."""
    op.execute("""
        ALTER TABLE fsma.edi_line_identities DROP COLUMN IF EXISTS canonical_event_id;
        DROP TABLE IF EXISTS fsma.cte_event_supersessions;
    """)
