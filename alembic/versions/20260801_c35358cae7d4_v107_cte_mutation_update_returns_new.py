"""v107 — authorized CTE corrections: BEFORE UPDATE trigger must RETURN NEW.

``fsma.prevent_cte_mutation()`` (v078) returns ``OLD`` whenever
``fsma.allow_mutation = 'true'``. For the DELETE half of the
``BEFORE UPDATE OR DELETE`` triggers that is correct (returning OLD lets
the delete proceed — the scheduler's retention purge relies on it), but
for UPDATE it makes PostgreSQL proceed with the *old* row values: the
statement reports ``UPDATE n`` while silently discarding every change.
The break-glass path documented in the exception message ("Set
fsma.allow_mutation=true for authorized corrections") has therefore
never been able to correct a row on ``fsma.cte_events`` or
``fsma.hash_chain`` — it succeeds as a no-op.

Fix: return ``NEW`` for UPDATE, ``OLD`` for DELETE. Unauthorized
mutations still raise (FDA 21 CFR 1.1455 append-only guard unchanged).

Revision ID: c35358cae7d4
Revises: 8633e0a7a84e
Create Date: 2026-08-01
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c35358cae7d4"  # pragma: allowlist secret
down_revision = "8633e0a7a84e"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.prevent_cte_mutation()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('fsma.allow_mutation', true) = 'true' THEN
                IF TG_OP = 'UPDATE' THEN
                    RETURN NEW;
                END IF;
                RETURN OLD;
            END IF;
            RAISE EXCEPTION
                'CTE records are append-only (FDA 21 CFR 1.1455). Set fsma.allow_mutation=true for authorized corrections. Table: %, Operation: %',
                TG_TABLE_NAME, TG_OP;
        END;
        $$;
        """
    )


def downgrade() -> None:
    # Restore the v078 body (authorized UPDATEs silently no-op again).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.prevent_cte_mutation()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('fsma.allow_mutation', true) = 'true' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION
                'CTE records are append-only (FDA 21 CFR 1.1455). Set fsma.allow_mutation=true for authorized corrections. Table: %, Operation: %',
                TG_TABLE_NAME, TG_OP;
        END;
        $$;
        """
    )
