"""Add append-only triggers on fsma.cte_events and fsma.hash_chain (#1334).

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
Create Date: 2026-04-20

Why
---
FDA 21 CFR 1.1455 requires traceability records be preserved for 2 years.
``fsma.cte_events`` and ``fsma.hash_chain`` are written by
``services/shared/cte_persistence/core.py`` but nothing previously prevented
UPDATE or DELETE on those rows. A bug or malicious query could silently
mutate FSMA evidence without detection. Auditors expect append-only records.

Fix
---
A BEFORE UPDATE OR DELETE trigger on each table raises an exception unless
the break-glass GUC ``fsma.allow_mutation`` is set to ``true`` in the current
transaction. Even when break-glass is active, a NOTICE is raised so every
mutation surfaces in Postgres logs.

Break-glass procedure
---------------------
Only a superuser or an application role with SET privilege on ``fsma.*`` GUCs
can bypass the guard. To perform a corrective mutation:

    -- 1. Open a transaction
    BEGIN;

    -- 2. Activate break-glass for this transaction only
    --    (SET LOCAL is rolled back automatically on COMMIT/ROLLBACK)
    SET LOCAL fsma.allow_mutation = 'true';

    -- 3. Perform the corrective DML
    UPDATE fsma.cte_events SET ... WHERE ...;

    -- 4. Commit — the NOTICE("fsma.cte_events mutation allowed via break-glass")
    --    will appear in the Postgres log and should be captured in your
    --    incident ticket.
    COMMIT;

A NOTICE is emitted for every row touched even when break-glass is active,
so the Postgres log retains a durable record of every mutation. Application-
level audit should capture this in your SIEM alongside the incident ticket.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # Trigger function — shared by both tables
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.enforce_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            _allow boolean;
        BEGIN
            -- Check break-glass GUC; default is FALSE (append-only enforced)
            BEGIN
                _allow := current_setting('fsma.allow_mutation', true)::boolean;
            EXCEPTION WHEN OTHERS THEN
                _allow := false;
            END;

            IF _allow THEN
                -- Break-glass active: allow the mutation but surface a NOTICE
                -- in the Postgres log so every mutation is traceable.
                RAISE NOTICE
                    'fsma.% mutation allowed via break-glass (op=%, tenant_id=%)',
                    TG_TABLE_NAME,
                    TG_OP,
                    COALESCE(
                        (CASE WHEN TG_OP = 'DELETE' THEN OLD.tenant_id::text
                              ELSE NEW.tenant_id::text END),
                        '<unknown>'
                    );
                -- For DELETE, OLD is the relevant row; return it to proceed.
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;

            -- Default path: block the mutation.
            RAISE EXCEPTION
                'fsma.% is append-only (FSMA 21 CFR 1.1455 — 2-year retention). '
                'Set LOCAL fsma.allow_mutation = true to bypass (break-glass). '
                'Op: %, table: fsma.%',
                TG_TABLE_NAME, TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END;
        $$;
        """
    )

    # -----------------------------------------------------------------
    # Trigger on fsma.cte_events
    # -----------------------------------------------------------------
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_cte_events_append_only ON fsma.cte_events;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_cte_events_append_only
        BEFORE UPDATE OR DELETE ON fsma.cte_events
        FOR EACH ROW EXECUTE FUNCTION fsma.enforce_append_only();
        """
    )

    # -----------------------------------------------------------------
    # Trigger on fsma.hash_chain
    # -----------------------------------------------------------------
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_hash_chain_append_only ON fsma.hash_chain;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_hash_chain_append_only
        BEFORE UPDATE OR DELETE ON fsma.hash_chain
        FOR EACH ROW EXECUTE FUNCTION fsma.enforce_append_only();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_hash_chain_append_only ON fsma.hash_chain;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_cte_events_append_only ON fsma.cte_events;"
    )
    op.execute("DROP FUNCTION IF EXISTS fsma.enforce_append_only();")
