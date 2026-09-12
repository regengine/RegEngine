"""v121 — billing usage counters for per-label metered billing (DESIGN_metering-billing.md).

Revision ID: ceb552c6d36d
Revises: c6a120b4e901
Create Date: 2026-09-12

Adds the first Postgres-durable billing state in the repo, under a new
``billing`` schema (Stripe subscription/customer state today lives entirely
in Redis — ``services/ingestion/app/stripe_billing/state.py`` — so this is
additive, not a migration off Redis):

1. ``billing.tenant_usage_event_ledger`` — one row per **counted** accepted
   label event (``fsma.traceability_events.event_id``). The idempotency
   guard for ``increment_usage_for_event``: ``PRIMARY KEY (tenant_id,
   event_id)`` with ``ON CONFLICT ... DO NOTHING`` at the call site makes
   counting a given event twice (e.g. a retried webhook) a guaranteed
   no-op. Same idiom the canonical writer already uses for the events table
   itself (``writer.py::_insert_canonical_event``).
2. ``billing.tenant_usage_counters`` — per tenant, per UTC-calendar-month
   billing period, the running ``unit_count`` (ground truth for
   ``GET /api/v1/billing/usage``) plus ``last_reported_count`` /
   ``last_reported_at``, the high-water mark of what has already been
   pushed to Stripe's Billing Meters API so ``report_tenant_usage_to_stripe``
   sends only the delta and is safe to re-run.

Both tables: ``tenant_id UUID NOT NULL`` + ENABLE/FORCE ROW LEVEL SECURITY
with the ``get_tenant_context()`` predicate, via the same ``_tenant_rls``
helper as the v095 supplier remediation slice
(``20260716_c7a1e5f2b9d4_v095_supplier_remediation_slice.py``), reused
verbatim here.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "ceb552c6d36d"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c6a120b4e901"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_rls(table: str, column: str, policy: str) -> None:
    schema, table_name = table.split(".", 1)
    op.execute(
        f"""
        DO $$
        DECLARE
            column_type text;
            predicate text;
        BEGIN
            IF to_regclass('{table}') IS NULL THEN
                RETURN;
            END IF;
            SELECT data_type INTO column_type
            FROM information_schema.columns
            WHERE table_schema = '{schema}'
              AND table_name = '{table_name}'
              AND column_name = '{column}';
            IF column_type IS NULL THEN
                RETURN;
            END IF;
            IF column_type IN ('text', 'character varying') THEN
                predicate := '{column} = get_tenant_context()::text';
            ELSE
                predicate := '{column} = get_tenant_context()';
            END IF;
            EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE {table} FORCE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS {policy} ON {table}';
            EXECUTE format(
                'CREATE POLICY {policy} ON {table}
                    FOR ALL
                    USING (%s)
                    WITH CHECK (%s)',
                predicate,
                predicate
            );
        END $$;
        """
    )


def _create_tables() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS billing")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing.tenant_usage_event_ledger (
            tenant_id            UUID NOT NULL,
            event_id             UUID NOT NULL,
            billing_period_start DATE NOT NULL,
            counted_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_usage_event_ledger_period
            ON billing.tenant_usage_event_ledger (tenant_id, billing_period_start);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing.tenant_usage_counters (
            tenant_id            UUID NOT NULL,
            billing_period_start DATE NOT NULL,
            billing_period_end   DATE NOT NULL,
            unit_count           BIGINT NOT NULL DEFAULT 0,
            last_reported_count  BIGINT NOT NULL DEFAULT 0,
            last_reported_at     TIMESTAMPTZ,
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, billing_period_start)
        );
        """
    )


def upgrade() -> None:
    _create_tables()
    _tenant_rls(
        "billing.tenant_usage_event_ledger",
        "tenant_id",
        "tenant_isolation_tenant_usage_event_ledger",
    )
    _tenant_rls(
        "billing.tenant_usage_counters",
        "tenant_id",
        "tenant_isolation_tenant_usage_counters",
    )


def downgrade() -> None:
    # Schema is left in place (matches every prior "CREATE SCHEMA IF NOT
    # EXISTS" migration in this repo other than the two `audit` schema
    # CASCADE drops, which v056's own comments note ran into ordering
    # trouble) — dropping the two tables is a complete, non-destructive
    # reversal of what upgrade() added.
    op.execute("DROP TABLE IF EXISTS billing.tenant_usage_counters")
    op.execute("DROP TABLE IF EXISTS billing.tenant_usage_event_ledger")
