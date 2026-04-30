-- V068 — Supplier self-service integration profiles
-- =================================================
-- Raw SQL companion for Alembic v074.

BEGIN;

CREATE SCHEMA IF NOT EXISTS fsma;

CREATE OR REPLACE FUNCTION fsma.prevent_inflow_workbench_evidence_update()
RETURNS TRIGGER AS $fn$
BEGIN
    RAISE EXCEPTION 'Inflow workbench run and commit-decision records are append-only';
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inflow_runs_no_truncate
    ON fsma.inflow_workbench_runs;
CREATE TRIGGER trg_inflow_runs_no_truncate
    BEFORE TRUNCATE ON fsma.inflow_workbench_runs
    FOR EACH STATEMENT EXECUTE FUNCTION fsma.prevent_inflow_workbench_evidence_update();

DROP TRIGGER IF EXISTS trg_inflow_commit_decisions_no_truncate
    ON fsma.inflow_workbench_commit_decisions;
CREATE TRIGGER trg_inflow_commit_decisions_no_truncate
    BEFORE TRUNCATE ON fsma.inflow_workbench_commit_decisions
    FOR EACH STATEMENT EXECUTE FUNCTION fsma.prevent_inflow_workbench_evidence_update();

CREATE TABLE IF NOT EXISTS fsma.supplier_integration_profiles (
    profile_id       TEXT NOT NULL,
    tenant_id        UUID NOT NULL,
    display_name     TEXT NOT NULL,
    source_type      TEXT NOT NULL DEFAULT 'csv',
    field_mapping    JSONB NOT NULL DEFAULT '{}'::jsonb,
    default_cte_type TEXT NOT NULL DEFAULT 'shipping',
    status           TEXT NOT NULL DEFAULT 'draft',
    confidence       NUMERIC(4,3) NOT NULL DEFAULT 0.750,
    supplier_id      TEXT,
    supplier_name    TEXT,
    notes            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at     TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, profile_id),
    CONSTRAINT chk_supplier_profile_source
        CHECK (source_type IN ('csv', 'edi', 'epcis', 'api', 'webhook', 'spreadsheet', 'supplier_portal')),
    CONSTRAINT chk_supplier_profile_status
        CHECK (status IN ('draft', 'active', 'archived')),
    CONSTRAINT chk_supplier_profile_confidence
        CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX IF NOT EXISTS idx_supplier_profiles_tenant_status
    ON fsma.supplier_integration_profiles (tenant_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_supplier_profiles_supplier
    ON fsma.supplier_integration_profiles (tenant_id, supplier_id);

ALTER TABLE fsma.tenant_portal_links
    ADD COLUMN IF NOT EXISTS supplier_email TEXT;
ALTER TABLE fsma.tenant_portal_links
    ADD COLUMN IF NOT EXISTS allowed_cte_types TEXT[] NOT NULL DEFAULT ARRAY['shipping']::TEXT[];
ALTER TABLE fsma.tenant_portal_links
    ADD COLUMN IF NOT EXISTS integration_profile_id TEXT;
CREATE INDEX IF NOT EXISTS idx_tenant_portal_links_profile
    ON fsma.tenant_portal_links (tenant_id, integration_profile_id);

ALTER TABLE fsma.supplier_integration_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.supplier_integration_profiles FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_supplier_integration_profiles
    ON fsma.supplier_integration_profiles;
CREATE POLICY tenant_isolation_supplier_integration_profiles
    ON fsma.supplier_integration_profiles
    FOR ALL TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    )
    WITH CHECK (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

COMMENT ON TABLE fsma.supplier_integration_profiles IS
    'Tenant-scoped reusable field mapping profiles for supplier self-service and source onboarding.';
COMMENT ON COLUMN fsma.tenant_portal_links.integration_profile_id IS
    'Optional saved integration profile attached to a supplier self-service portal link.';

COMMIT;
