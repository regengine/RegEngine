"""cte_events append-only DB trigger (#1334).

Creates a BEFORE UPDATE OR DELETE trigger on ``fsma.cte_events`` that raises
an exception for any attempt to mutate or delete an existing row. This is the
database-layer enforcement of the append-only constraint documented in #1334.

The application layer (``cte_persistence.core._assert_not_exists``) provides
the primary enforcement and surfaces a typed ``DuplicateEventError``; this
trigger is the second layer that protects against callers that bypass Python
and write SQL directly (e.g. ad-hoc psql sessions, DB migration scripts,
compromised service accounts).

Revision ID: v073
Revises: v072
Create Date: 2026-04-20
"""

from alembic import op

# Revision identifiers, used by Alembic.
revision = "v073"
down_revision = "v072"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Trigger SQL
# ---------------------------------------------------------------------------

# The trigger function raises SQLSTATE P0001 (raise_exception) so callers
# receive a clear message rather than a generic constraint violation.  The
# function is created with CREATE OR REPLACE so re-running the migration is
# idempotent.  Both the function and the trigger live in the ``fsma`` schema
# alongside the table they protect.

_CREATE_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION fsma.cte_events_enforce_append_only()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = fsma, pg_catalog
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION
            'fsma.cte_events is append-only (#1334): UPDATE is not permitted '
            '(event_id=%, tenant_id=%)',
            OLD.id, OLD.tenant_id
            USING ERRCODE = 'P0001';
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'fsma.cte_events is append-only (#1334): DELETE is not permitted '
            '(event_id=%, tenant_id=%)',
            OLD.id, OLD.tenant_id
            USING ERRCODE = 'P0001';
    END IF;
    -- BEFORE trigger: returning OLD (unreachable, but required by plpgsql)
    RETURN OLD;
END;
$$;
"""

_CREATE_TRIGGER = """
DO $$
BEGIN
    -- Drop any stale copy so the migration is re-runnable without error.
    DROP TRIGGER IF EXISTS cte_events_no_update_delete ON fsma.cte_events;

    CREATE TRIGGER cte_events_no_update_delete
        BEFORE UPDATE OR DELETE
        ON fsma.cte_events
        FOR EACH ROW
        EXECUTE FUNCTION fsma.cte_events_enforce_append_only();
END;
$$;
"""

_DROP_TRIGGER = """
DROP TRIGGER IF EXISTS cte_events_no_update_delete ON fsma.cte_events;
"""

_DROP_TRIGGER_FN = """
DROP FUNCTION IF EXISTS fsma.cte_events_enforce_append_only();
"""


def upgrade() -> None:
    """Install the append-only trigger on fsma.cte_events."""
    op.execute(_CREATE_TRIGGER_FN)
    op.execute(_CREATE_TRIGGER)


def downgrade() -> None:
    """Remove the append-only trigger (restores mutability — use with care)."""
    op.execute(_DROP_TRIGGER)
    op.execute(_DROP_TRIGGER_FN)
