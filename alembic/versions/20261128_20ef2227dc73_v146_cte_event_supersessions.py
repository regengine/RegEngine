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

from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "20ef2227dc73"  # pragma: allowlist secret
down_revision = "62355c37e367"  # pragma: allowlist secret
branch_labels = None
depends_on = None

# Fail a busy deploy fast instead of queueing ingest behind an ACCESS EXCLUSIVE wait.
_LOCK_TIMEOUT = "10s"


@contextmanager
def _bounded_lock_wait():
    """Bound lock waits for this revision only, as v126 does.

    Later revisions can run in the same transaction, so the previous value is
    restored afterwards.
    """
    conn = op.get_bind()
    previous = conn.execute(sa.text("SELECT pg_catalog.current_setting('lock_timeout')")).scalar_one()
    conn.execute(sa.text("SELECT pg_catalog.set_config('lock_timeout', :value, true)"), {"value": _LOCK_TIMEOUT})
    yield
    conn.execute(sa.text("SELECT pg_catalog.set_config('lock_timeout', :value, true)"), {"value": previous})


def upgrade() -> None:
    """Create the insert-only supersession marker and the canonical link."""
    with _bounded_lock_wait():
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
    """Remove both, refusing once they hold supersession history.

    A marker and a canonical link are the only record of which event a
    completed line replaced; dropping them would make both hashed events read
    as live again. Deploy the previous application before an empty downgrade.

    Both tables force row security and their policy names only ``regengine``,
    so the owner would see no rows. NO FORCE lifts that for this transaction
    only, as in v126: the ALTER holds its lock until commit and a refusal rolls
    it back.
    """
    with _bounded_lock_wait():
        op.execute("""
            ALTER TABLE fsma.cte_event_supersessions NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE fsma.edi_line_identities NO FORCE ROW LEVEL SECURITY;
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM fsma.cte_event_supersessions) THEN
                    RAISE EXCEPTION 'v146 downgrade refused: fsma.cte_event_supersessions holds supersession history';
                END IF;
                IF EXISTS (SELECT 1 FROM fsma.edi_line_identities WHERE canonical_event_id IS NOT NULL) THEN
                    RAISE EXCEPTION 'v146 downgrade refused: edi_line_identities holds canonical links';
                END IF;
            END $$;
            ALTER TABLE fsma.edi_line_identities DROP COLUMN IF EXISTS canonical_event_id;
            ALTER TABLE fsma.edi_line_identities FORCE ROW LEVEL SECURITY;
            DROP TABLE IF EXISTS fsma.cte_event_supersessions;
        """)
