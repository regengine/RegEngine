"""v074 — supplier self-service integration profiles.

Adds tenant-scoped saved mapping profiles for supplier/source onboarding and
extends portal links so a buyer can attach one reusable profile to a supplier
self-service link.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c9d0e1f2a3b4"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TENANT_POLICY = """\
tenant_id = get_tenant_context()
OR (current_setting('regengine.is_sysadmin', true) = 'true'
    AND current_user = 'regengine_sysadmin')"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.prevent_inflow_workbench_evidence_update()
        RETURNS TRIGGER AS $fn$
        BEGIN
            RAISE EXCEPTION 'Inflow workbench run and commit-decision records are append-only';
        END;
        $fn$ LANGUAGE plpgsql
        """
    )
    for table, trigger in (
        ("inflow_workbench_runs", "trg_inflow_runs_no_truncate"),
        ("inflow_workbench_commit_decisions", "trg_inflow_commit_decisions_no_truncate"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON fsma.{table}")
        op.execute(
            f"""
            CREATE TRIGGER {trigger}
                BEFORE TRUNCATE ON fsma.{table}
                FOR EACH STATEMENT EXECUTE FUNCTION fsma.prevent_inflow_workbench_evidence_update()
            """
        )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.supplier_integration_profiles (
            profile_id TEXT NOT NULL,
            tenant_id UUID NOT NULL,
            display_name TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'csv',
            field_mapping JSONB NOT NULL DEFAULT '{}'::jsonb,
            default_cte_type TEXT NOT NULL DEFAULT 'shipping',
            status TEXT NOT NULL DEFAULT 'draft',
            confidence NUMERIC(4,3) NOT NULL DEFAULT 0.750,
            supplier_id TEXT,
            supplier_name TEXT,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at TIMESTAMPTZ,
            PRIMARY KEY (tenant_id, profile_id),
            CONSTRAINT chk_supplier_profile_source
                CHECK (source_type IN ('csv', 'edi', 'epcis', 'api', 'webhook', 'spreadsheet', 'supplier_portal')),
            CONSTRAINT chk_supplier_profile_status
                CHECK (status IN ('draft', 'active', 'archived')),
            CONSTRAINT chk_supplier_profile_confidence
                CHECK (confidence >= 0 AND confidence <= 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_supplier_profiles_tenant_status "
        "ON fsma.supplier_integration_profiles (tenant_id, status, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_supplier_profiles_supplier "
        "ON fsma.supplier_integration_profiles (tenant_id, supplier_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.tenant_portal_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            supplier_name TEXT NOT NULL,
            link_token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenant_portal_links_tid "
        "ON fsma.tenant_portal_links (tenant_id)"
    )
    op.execute("ALTER TABLE fsma.tenant_portal_links ADD COLUMN IF NOT EXISTS supplier_email TEXT")
    op.execute("ALTER TABLE fsma.tenant_portal_links ADD COLUMN IF NOT EXISTS allowed_cte_types TEXT[] NOT NULL DEFAULT ARRAY['shipping']::TEXT[]")
    op.execute("ALTER TABLE fsma.tenant_portal_links ADD COLUMN IF NOT EXISTS integration_profile_id TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenant_portal_links_profile "
        "ON fsma.tenant_portal_links (tenant_id, integration_profile_id)"
    )
    op.execute("ALTER TABLE fsma.tenant_portal_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.tenant_portal_links FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_portal_links ON fsma.tenant_portal_links")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_portal_links
            ON fsma.tenant_portal_links
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_TENANT_POLICY})
            WITH CHECK ({_TENANT_POLICY})
        """
    )

    op.execute("ALTER TABLE fsma.supplier_integration_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.supplier_integration_profiles FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_supplier_integration_profiles ON fsma.supplier_integration_profiles")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_supplier_integration_profiles
            ON fsma.supplier_integration_profiles
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_TENANT_POLICY})
            WITH CHECK ({_TENANT_POLICY})
        """
    )

    op.execute(
        """
        COMMENT ON TABLE fsma.supplier_integration_profiles IS
            'Tenant-scoped reusable field mapping profiles for supplier self-service and source onboarding.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN fsma.tenant_portal_links.integration_profile_id IS
            'Optional saved integration profile attached to a supplier self-service portal link.'
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_inflow_commit_decisions_no_truncate ON fsma.inflow_workbench_commit_decisions")
    op.execute("DROP TRIGGER IF EXISTS trg_inflow_runs_no_truncate ON fsma.inflow_workbench_runs")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_supplier_integration_profiles ON fsma.supplier_integration_profiles")
    op.execute("DROP TABLE IF EXISTS fsma.supplier_integration_profiles")
    op.execute("DROP INDEX IF EXISTS fsma.idx_tenant_portal_links_profile")
    op.execute("ALTER TABLE fsma.tenant_portal_links DROP COLUMN IF EXISTS integration_profile_id")
    op.execute("ALTER TABLE fsma.tenant_portal_links DROP COLUMN IF EXISTS allowed_cte_types")
    op.execute("ALTER TABLE fsma.tenant_portal_links DROP COLUMN IF EXISTS supplier_email")
