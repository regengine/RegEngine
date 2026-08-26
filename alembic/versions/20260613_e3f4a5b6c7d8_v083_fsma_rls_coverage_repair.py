"""v083 -- repair FSMA RLS coverage after forward-port replay.

Revision ID: e3f4a5b6c7d8
Revises: 70d5e59e3257
Create Date: 2026-06-13

Fresh Alembic replay left several V31-era/forward-port ``fsma`` tables with
nullable tenant columns, indirect-only tenant scoping, or ENABLE-only RLS. This
migration restores the production tenant-isolation contract required by the
RLS coverage gate: tenant_id NOT NULL, FORCE RLS, and policies backed by
``get_tenant_context()``.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e3f4a5b6c7d8"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "70d5e59e3257"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $mig$
        DECLARE
            table_name text;
            null_count bigint;
        BEGIN
            FOREACH table_name IN ARRAY ARRAY[
                'products',
                'locations',
                'suppliers',
                'critical_tracking_events',
                'audit_log',
                'recall_assessments',
                'compliance_snapshots',
                'compliance_alerts'
            ]
            LOOP
                IF to_regclass('fsma.' || table_name) IS NULL THEN
                    CONTINUE;
                END IF;

                EXECUTE format(
                    'ALTER TABLE fsma.%I NO FORCE ROW LEVEL SECURITY',
                    table_name
                );
                EXECUTE format(
                    'UPDATE fsma.%I SET tenant_id = org_id WHERE tenant_id IS NULL',
                    table_name
                );
                EXECUTE format(
                    'SELECT count(*) FROM fsma.%I WHERE tenant_id IS NULL',
                    table_name
                ) INTO null_count;
                IF null_count > 0 THEN
                    RAISE EXCEPTION
                        'Cannot harden fsma.%: % rows still have NULL tenant_id',
                        table_name,
                        null_count;
                END IF;

                EXECUTE format('ALTER TABLE fsma.%I ALTER COLUMN tenant_id SET NOT NULL', table_name);
                EXECUTE format('ALTER TABLE fsma.%I ENABLE ROW LEVEL SECURITY', table_name);
                EXECUTE format('ALTER TABLE fsma.%I FORCE ROW LEVEL SECURITY', table_name);
            END LOOP;
        END;
        $mig$;
        """
    )

    op.execute(
        """
        DO $mig$
        DECLARE
            null_count bigint;
        BEGIN
            IF to_regclass('fsma.key_data_elements') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE fsma.key_data_elements
                ADD COLUMN IF NOT EXISTS tenant_id UUID;
            ALTER TABLE fsma.key_data_elements NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE fsma.critical_tracking_events NO FORCE ROW LEVEL SECURITY;

            UPDATE fsma.key_data_elements kde
            SET tenant_id = cte.tenant_id
            FROM fsma.critical_tracking_events cte
            WHERE kde.tenant_id IS NULL
              AND cte.id = kde.cte_id;

            SELECT count(*)
            INTO null_count
            FROM fsma.key_data_elements
            WHERE tenant_id IS NULL;

            IF null_count > 0 THEN
                RAISE EXCEPTION
                    'Cannot harden fsma.key_data_elements: % rows could not be assigned tenant_id',
                    null_count;
            END IF;

            ALTER TABLE fsma.key_data_elements
                ALTER COLUMN tenant_id SET NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_fsma_key_data_elements_tenant
                ON fsma.key_data_elements(tenant_id);
            ALTER TABLE fsma.key_data_elements ENABLE ROW LEVEL SECURITY;
            ALTER TABLE fsma.key_data_elements FORCE ROW LEVEL SECURITY;
            ALTER TABLE fsma.critical_tracking_events FORCE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS fsma_org_isolation_kdes ON fsma.key_data_elements;
            DROP POLICY IF EXISTS tenant_isolation_kdes ON fsma.key_data_elements;
            CREATE POLICY tenant_isolation_kdes
                ON fsma.key_data_elements
                FOR ALL
                USING (tenant_id = get_tenant_context())
                WITH CHECK (tenant_id = get_tenant_context());
        END;
        $mig$;
        """
    )

    op.execute(
        """
        DO $mig$
        DECLARE
            null_count bigint;
        BEGIN
            IF to_regclass('fsma.cte_kdes_backfill_log_v059') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE fsma.cte_kdes_backfill_log_v059
                ADD COLUMN IF NOT EXISTS tenant_id UUID;
            ALTER TABLE fsma.cte_kdes_backfill_log_v059 NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE fsma.cte_events NO FORCE ROW LEVEL SECURITY;

            UPDATE fsma.cte_kdes_backfill_log_v059 log
            SET tenant_id = cte.tenant_id
            FROM fsma.cte_events cte
            WHERE log.tenant_id IS NULL
              AND cte.id = log.cte_event_id;

            SELECT count(*)
            INTO null_count
            FROM fsma.cte_kdes_backfill_log_v059
            WHERE tenant_id IS NULL;

            IF null_count > 0 THEN
                RAISE EXCEPTION
                    'Cannot harden fsma.cte_kdes_backfill_log_v059: % rows could not be assigned tenant_id',
                    null_count;
            END IF;

            ALTER TABLE fsma.cte_kdes_backfill_log_v059
                ALTER COLUMN tenant_id SET NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_cte_kdes_backfill_log_v059_tenant
                ON fsma.cte_kdes_backfill_log_v059(tenant_id);
            ALTER TABLE fsma.cte_kdes_backfill_log_v059 ENABLE ROW LEVEL SECURITY;
            ALTER TABLE fsma.cte_kdes_backfill_log_v059 FORCE ROW LEVEL SECURITY;
            ALTER TABLE fsma.cte_events FORCE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS tenant_isolation_cte_kdes_backfill_log_v059
                ON fsma.cte_kdes_backfill_log_v059;
            CREATE POLICY tenant_isolation_cte_kdes_backfill_log_v059
                ON fsma.cte_kdes_backfill_log_v059
                FOR ALL
                USING (tenant_id = get_tenant_context())
                WITH CHECK (tenant_id = get_tenant_context());
        END;
        $mig$;
        """
    )

    op.execute(
        """
        DO $mig$
        BEGIN
            IF to_regclass('fsma.rule_rejections') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE fsma.rule_rejections ENABLE ROW LEVEL SECURITY;
            ALTER TABLE fsma.rule_rejections FORCE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS tenant_isolation_rule_rejections
                ON fsma.rule_rejections;
            CREATE POLICY tenant_isolation_rule_rejections
                ON fsma.rule_rejections
                FOR ALL
                USING (tenant_id = get_tenant_context())
                WITH CHECK (tenant_id = get_tenant_context());
        END;
        $mig$;
        """
    )


def downgrade() -> None:
    """Forward-only hardening; retain tenant columns and RLS."""
    pass
