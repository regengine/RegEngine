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

Runtime-role grants (self-review fix): v111
(``20260803_b71d9e4c2a60_v111_runtime_role_grants.py``) put every schema the
app touches under a closed allowlist — ``regengine`` (the role
``services/shared/database.py``'s engine actually connects as, enforced by
``check_rls_posture``) has *zero* privileges on any object that migration
didn't explicitly name, "New objects are inaccessible until an audited
migration names them" per that file's own comment, and ``billing`` is a
schema created after that cutover with no prior grant of any kind. Without
an explicit grant here, ``increment_usage_for_event`` — which
``CanonicalEventStore.persist_event``/``persist_events_batch`` call for
*every* accepted label by default (``meter_usage=True``) — would fail with
``permission denied for schema billing`` on the very first accepted event
in a deployed environment, rolling back the entire canonical-event
transaction, not just the usage counter. Grants below are scoped to exactly
what the writer (INSERT, plus the implicit SELECT Postgres requires for
``RETURNING`` / the ``unit_count = unit_count + 1`` self-reference) and the
``/billing/usage`` + ``/billing/usage/report`` routes (SELECT, and the
latter's high-water-mark UPDATE) actually need — matching the
least-privilege, per-table allowlist pattern v111 established (e.g.
``fsma.traceability_events: ("SELECT", "INSERT", "UPDATE")``).
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


def _grant_runtime_role_access() -> None:
    """Grant ``regengine`` exactly the privileges the app needs on the new
    schema (see the module docstring: v111 closed every schema to an
    explicit per-table allowlist, and that allowlist does not — cannot —
    know about a schema created after it ran).

    - ``tenant_usage_event_ledger``: INSERT-only from the app's point of
      view, but the ``... RETURNING event_id`` in
      ``increment_usage_for_event`` requires SELECT on the returned column
      too (Postgres treats a RETURNING clause as a read).
    - ``tenant_usage_counters``: SELECT (the ``/billing/usage`` GET, and
      the ``unit_count = billing.tenant_usage_counters.unit_count + 1``
      self-reference in the upsert), INSERT (first upsert of a period),
      and UPDATE (the upsert's ``DO UPDATE`` branch, plus
      ``report_tenant_usage_to_stripe``'s ``last_reported_count`` advance).
    """
    op.execute("GRANT USAGE ON SCHEMA billing TO regengine")
    op.execute("GRANT SELECT, INSERT ON billing.tenant_usage_event_ledger TO regengine")
    op.execute("GRANT SELECT, INSERT, UPDATE ON billing.tenant_usage_counters TO regengine")


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
    _grant_runtime_role_access()


def downgrade() -> None:
    # Schema is left in place (matches every prior "CREATE SCHEMA IF NOT
    # EXISTS" migration in this repo other than the two `audit` schema
    # CASCADE drops, which v056's own comments note ran into ordering
    # trouble) — dropping the two tables is a complete, non-destructive
    # reversal of what upgrade() added.
    op.execute("DROP TABLE IF EXISTS billing.tenant_usage_counters")
    op.execute("DROP TABLE IF EXISTS billing.tenant_usage_event_ledger")
