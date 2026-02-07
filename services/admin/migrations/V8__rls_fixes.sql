-- Migration V6: Fix RLS Defaults and Enforcement

-- 1. Set DEFAULT tenant_id from context
ALTER TABLE review_items ALTER COLUMN tenant_id SET DEFAULT get_tenant_context();
ALTER TABLE api_keys ALTER COLUMN tenant_id SET DEFAULT get_tenant_context();

-- 2. Force RLS (applies to table owner 'regengine')
ALTER TABLE review_items FORCE ROW LEVEL SECURITY;
ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;

-- 3. Also fix tenants table RLS? (Tenants table is shared, likely readable by all but write protected?)
-- For now, tenants table usually needs global visibility or specific policy.
-- Keeping it open for now.
