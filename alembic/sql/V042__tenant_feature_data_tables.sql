-- V042 — Tenant feature data tables (persistence for in-memory stores)
-- =====================================================================
-- 11 modules currently use in-memory dicts that lose data on restart:
--   supplier_mgmt, product_catalog, team_mgmt, notification_prefs,
--   settings, onboarding, exchange_api, supplier_portal, mock_audit,
--   recall_simulations, recall_report
--
-- This migration creates the backing tables so these modules can be
-- migrated from in-memory to Postgres incrementally.

BEGIN;

-- 1) Supplier management
CREATE TABLE IF NOT EXISTS fsma.tenant_suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    contact_email TEXT,
    portal_link_id TEXT,
    portal_status TEXT NOT NULL DEFAULT 'pending',
    submissions_count INT NOT NULL DEFAULT 0,
    last_submission TIMESTAMPTZ,
    compliance_status TEXT NOT NULL DEFAULT 'unknown',
    missing_kdes TEXT[] DEFAULT '{}',
    products TEXT[] DEFAULT '{}',
    is_sample BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tenant_suppliers_tid ON fsma.tenant_suppliers(tenant_id);

-- 2) Product catalog
CREATE TABLE IF NOT EXISTS fsma.tenant_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    ftl_covered BOOLEAN NOT NULL DEFAULT TRUE,
    sku TEXT DEFAULT '',
    gtin TEXT DEFAULT '',
    description TEXT DEFAULT '',
    suppliers TEXT[] DEFAULT '{}',
    facilities TEXT[] DEFAULT '{}',
    cte_count INT NOT NULL DEFAULT 0,
    last_cte TIMESTAMPTZ,
    is_sample BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tenant_products_tid ON fsma.tenant_products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_products_gtin ON fsma.tenant_products(gtin);

-- 3) Team members (supplements admin service users for ingestion-specific roles)
CREATE TABLE IF NOT EXISTS fsma.tenant_team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    status TEXT NOT NULL DEFAULT 'invited',
    last_active TIMESTAMPTZ,
    invited_at TIMESTAMPTZ,
    is_sample BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tenant_team_tid ON fsma.tenant_team_members(tenant_id);

-- 4) Notification preferences
CREATE TABLE IF NOT EXISTS fsma.tenant_notification_prefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE,
    prefs JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5) Tenant settings
CREATE TABLE IF NOT EXISTS fsma.tenant_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6) Onboarding state
CREATE TABLE IF NOT EXISTS fsma.tenant_onboarding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE,
    state JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7) Data exchange connections
CREATE TABLE IF NOT EXISTS fsma.tenant_exchanges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    exchange_type TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tenant_exchanges_tid ON fsma.tenant_exchanges(tenant_id);

-- 8) Supplier portal links
CREATE TABLE IF NOT EXISTS fsma.tenant_portal_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    supplier_name TEXT NOT NULL,
    link_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tenant_portal_links_tid ON fsma.tenant_portal_links(tenant_id);

COMMENT ON TABLE fsma.tenant_suppliers IS 'Persistent supplier records replacing in-memory _suppliers_store (V042)';
COMMENT ON TABLE fsma.tenant_products IS 'Persistent product catalog replacing in-memory _catalog_store (V042)';
COMMENT ON TABLE fsma.tenant_team_members IS 'Persistent team roster replacing in-memory _team_store (V042)';
COMMENT ON TABLE fsma.tenant_notification_prefs IS 'Persistent notification prefs replacing in-memory _prefs_store (V042)';
COMMENT ON TABLE fsma.tenant_settings IS 'Persistent tenant settings replacing in-memory _settings_store (V042)';
COMMENT ON TABLE fsma.tenant_onboarding IS 'Persistent onboarding state replacing in-memory _onboarding_store (V042)';
COMMENT ON TABLE fsma.tenant_exchanges IS 'Persistent exchange configs replacing in-memory _exchange_store (V042)';
COMMENT ON TABLE fsma.tenant_portal_links IS 'Persistent portal links replacing in-memory _portal_links (V042)';

COMMIT;
