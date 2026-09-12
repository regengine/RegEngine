"""v121 -- fsma.label_charges (per-label Stripe billing).

RegEngine has never actually priced FSMA 204 traceability output per
label/unit -- Stripe billing (services/ingestion/app/stripe_billing/) only
ever sold flat-rate monthly/annual plans (PLANS in plans.py). This adds the
persistence for a real per-label charge, one row per traceable unit
(fsma.cte_events.id) actually billed.

The row IS the idempotency guarantee: UNIQUE(tenant_id, cte_event_id) means
a retried ingest of the same label can claim the row at most once (INSERT
... ON CONFLICT DO NOTHING, mirrored in
services/ingestion/app/stripe_billing/label_billing.py), so a label is
never charged twice regardless of how many times ingestion re-processes it.

RLS follows the v095/v103 pattern: tenant_id UUID NOT NULL, ENABLE + FORCE
ROW LEVEL SECURITY, fail-closed ``tenant_id = get_tenant_context()`` policy.
Client-role lockdown mirrors v092/v098/v103: REVOKE from PUBLIC/anon/
authenticated, DML grants to the regengine app roles only.

Revision ID: 7551be5c64ac (random hex, not a credential)
Revises: c6a120b4e901
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "7551be5c64ac"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c6a120b4e901"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "fsma.label_charges"
_POLICY = "tenant_isolation_label_charges"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id               UUID NOT NULL,
            cte_event_id            UUID NOT NULL,
            amount_cents            INTEGER NOT NULL CHECK (amount_cents >= 0),
            currency                TEXT NOT NULL DEFAULT 'usd',
            status                  TEXT NOT NULL DEFAULT 'pending',
            stripe_customer_id      TEXT,
            stripe_invoice_item_id  TEXT,
            error_message           TEXT,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            charged_at              TIMESTAMPTZ,
            CONSTRAINT uq_label_charges_tenant_event UNIQUE (tenant_id, cte_event_id)
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_label_charges_tenant_created
            ON {_TABLE} (tenant_id, created_at DESC)
        """
    )

    # Fail-closed tenant isolation (v095 pattern): uuid = uuid predicate,
    # FORCE so even the table owner cannot bypass.
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON {_TABLE}
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context())
        """
    )

    # Client-role lockdown + app-role grants (v092/v098/v103 pattern). Role
    # creation is guarded for environments provisioned without them.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                CREATE ROLE regengine LOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin LOGIN INHERIT;
            END IF;

            EXECUTE 'REVOKE ALL ON {_TABLE} FROM PUBLIC';
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON {_TABLE} FROM anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON {_TABLE} FROM authenticated';
            END IF;

            EXECUTE 'GRANT USAGE ON SCHEMA fsma TO regengine, regengine_sysadmin';
            -- No DELETE: this table is the idempotency/audit claim for
            -- per-label billing. A runtime role that could delete a claim
            -- row could let a retry mint a fresh one and double-charge
            -- Stripe, and would let it erase billing history.
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON {_TABLE} '
                 || 'TO regengine, regengine_sysadmin';
        END $$;
        """
    )


def downgrade() -> None:
    # This migration is the table's only owner and the feature is new --
    # a real drop is the correct downgrade (no pre-existing data to keep).
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
