-- V052 — Safety-net: ensure all tenant feature tables exist
-- ============================================================
-- V042 creates these tables, but if the baseline migration path
-- was interrupted or partially applied, the tables may be missing.
-- All statements are IF NOT EXISTS — idempotent and safe to re-run.

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

-- 3) Team members
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

-- 4) Notification preferences (JSONB)
CREATE TABLE IF NOT EXISTS fsma.tenant_notification_prefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE,
    prefs JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5) Tenant settings (JSONB)
CREATE TABLE IF NOT EXISTS fsma.tenant_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6) Onboarding state (JSONB)
CREATE TABLE IF NOT EXISTS fsma.tenant_onboarding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE,
    state JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7) Data exchanges
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

-- 9) Generic tenant JSONB store (for recall_simulations, supplier_validation, etc.)
CREATE TABLE IF NOT EXISTS fsma.tenant_data (
    tenant_id UUID NOT NULL,
    namespace VARCHAR(64) NOT NULL,
    key VARCHAR(255) NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, namespace, key)
);
CREATE INDEX IF NOT EXISTS idx_tenant_data_ns ON fsma.tenant_data(tenant_id, namespace);

-- RLS on tenant_data
ALTER TABLE fsma.tenant_data ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS tenant_data_isolation ON fsma.tenant_data
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
