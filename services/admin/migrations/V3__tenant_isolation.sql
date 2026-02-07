-- Migration V3: Add tenant isolation with Row-Level Security (RLS)
--
-- This migration implements multi-tenant data isolation by:
-- 1. Adding tenant_id column to all tenant-specific tables
-- 2. Enabling PostgreSQL Row-Level Security (RLS)
-- 3. Creating RLS policies to enforce tenant isolation
--
-- Phase: 2.2 Postgres Row-Level Security
-- Date: 2025-11-22

-- ============================================================================
-- STEP 1: Add tenant_id column to tenant-specific tables
-- ============================================================================

-- Note: In a real migration, you would need to handle existing data.
-- For now, we'll assume this is applied to a fresh database or that
-- existing data should be migrated to a default tenant.

-- Create a default tenant ID for existing data (if any)
DO $$
DECLARE
    default_tenant_id UUID := '00000000-0000-0000-0000-000000000001';
BEGIN
    -- review_items table (if it exists)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'review_items') THEN
        -- Add column with temporary default
        ALTER TABLE review_items
        ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';

        -- Remove default after backfilling
        ALTER TABLE review_items ALTER COLUMN tenant_id DROP DEFAULT;

        -- Make it NOT NULL
        ALTER TABLE review_items ALTER COLUMN tenant_id SET NOT NULL;

        -- Create index for performance
        CREATE INDEX IF NOT EXISTS idx_review_items_tenant_id ON review_items(tenant_id);
    END IF;

    -- api_keys table (if it exists)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'api_keys') THEN
        ALTER TABLE api_keys
        ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';

        ALTER TABLE api_keys ALTER COLUMN tenant_id DROP DEFAULT;
        ALTER TABLE api_keys ALTER COLUMN tenant_id SET NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_api_keys_tenant_id ON api_keys(tenant_id);
    END IF;

    -- assessment_results table (if it exists)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'assessment_results') THEN
        ALTER TABLE assessment_results
        ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';

        ALTER TABLE assessment_results ALTER COLUMN tenant_id DROP DEFAULT;
        ALTER TABLE assessment_results ALTER COLUMN tenant_id SET NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_assessment_results_tenant_id ON assessment_results(tenant_id);
    END IF;

    -- tenant_overrides table (if it exists)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenant_overrides') THEN
        ALTER TABLE tenant_overrides
        ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';

        ALTER TABLE tenant_overrides ALTER COLUMN tenant_id DROP DEFAULT;
        ALTER TABLE tenant_overrides ALTER COLUMN tenant_id SET NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_tenant_overrides_tenant_id ON tenant_overrides(tenant_id);
    END IF;

    -- customer_configs table (if it exists)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'customer_configs') THEN
        ALTER TABLE customer_configs
        ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';

        ALTER TABLE customer_configs ALTER COLUMN tenant_id DROP DEFAULT;
        ALTER TABLE customer_configs ALTER COLUMN tenant_id SET NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_customer_configs_tenant_id ON customer_configs(tenant_id);
    END IF;
END $$;

-- ============================================================================
-- STEP 2: Create tenants table to manage tenant metadata
-- ============================================================================

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);

-- Insert default tenant
INSERT INTO tenants (id, name, slug, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'Default Tenant', 'default', 'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- STEP 3: Enable Row-Level Security (RLS) on tenant tables
-- ============================================================================

-- Enable RLS on review_items
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'review_items') THEN
        ALTER TABLE review_items ENABLE ROW LEVEL SECURITY;
    END IF;
END $$;

-- Enable RLS on api_keys
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'api_keys') THEN
        ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
    END IF;
END $$;

-- Enable RLS on assessment_results
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'assessment_results') THEN
        ALTER TABLE assessment_results ENABLE ROW LEVEL SECURITY;
    END IF;
END $$;

-- Enable RLS on tenant_overrides
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenant_overrides') THEN
        ALTER TABLE tenant_overrides ENABLE ROW LEVEL SECURITY;
    END IF;
END $$;

-- Enable RLS on customer_configs
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'customer_configs') THEN
        ALTER TABLE customer_configs ENABLE ROW LEVEL SECURITY;
    END IF;
END $$;

-- ============================================================================
-- STEP 4: Create RLS policies for tenant isolation
-- ============================================================================

-- Helper function to get current tenant from session variable
-- This will be set by the application layer on each request

-- RLS Policy for review_items
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'review_items') THEN
        DROP POLICY IF EXISTS tenant_isolation_policy ON review_items;
        CREATE POLICY tenant_isolation_policy ON review_items
            USING (
                tenant_id = COALESCE(
                    NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
                    '00000000-0000-0000-0000-000000000001'::UUID
                )
            );
    END IF;
END $$;

-- RLS Policy for api_keys (tenant_id is VARCHAR, need cast)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'api_keys') THEN
        DROP POLICY IF EXISTS tenant_isolation_policy ON api_keys;
        CREATE POLICY tenant_isolation_policy ON api_keys
            USING (
                tenant_id::uuid = COALESCE(
                    NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
                    '00000000-0000-0000-0000-000000000001'::UUID
                )
            );
    END IF;
END $$;

-- RLS Policy for assessment_results
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'assessment_results') THEN
        DROP POLICY IF EXISTS tenant_isolation_policy ON assessment_results;
        CREATE POLICY tenant_isolation_policy ON assessment_results
            USING (
                tenant_id = COALESCE(
                    NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
                    '00000000-0000-0000-0000-000000000001'::UUID
                )
            );
    END IF;
END $$;

-- RLS Policy for tenant_overrides
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenant_overrides') THEN
        DROP POLICY IF EXISTS tenant_isolation_policy ON tenant_overrides;
        CREATE POLICY tenant_isolation_policy ON tenant_overrides
            USING (
                tenant_id = COALESCE(
                    NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
                    '00000000-0000-0000-0000-000000000001'::UUID
                )
            );
    END IF;
END $$;

-- RLS Policy for customer_configs
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'customer_configs') THEN
        DROP POLICY IF EXISTS tenant_isolation_policy ON customer_configs;
        CREATE POLICY tenant_isolation_policy ON customer_configs
            USING (
                tenant_id = COALESCE(
                    NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
                    '00000000-0000-0000-0000-000000000001'::UUID
                )
            );
    END IF;
END $$;

-- ============================================================================
-- STEP 5: Create helper functions for tenant management
-- ============================================================================

-- Function to set tenant context for a session
CREATE OR REPLACE FUNCTION set_tenant_context(p_tenant_id UUID)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.tenant_id', p_tenant_id::TEXT, FALSE);
END;
$$ LANGUAGE plpgsql;

-- Function to get current tenant context
CREATE OR REPLACE FUNCTION get_tenant_context()
RETURNS UUID AS $$
BEGIN
    RETURN COALESCE(
        NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
        '00000000-0000-0000-0000-000000000001'::UUID
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- VERIFICATION QUERIES (for testing)
-- ============================================================================

-- To verify RLS is working:
--
-- 1. Set tenant context:
--    SELECT set_tenant_context('00000000-0000-0000-0000-000000000001');
--
-- 2. Query should only return tenant's data:
--    SELECT * FROM review_items;
--
-- 3. Change tenant context:
--    SELECT set_tenant_context('11111111-1111-1111-1111-111111111111');
--
-- 4. Query should return different tenant's data:
--    SELECT * FROM review_items;

-- ============================================================================
-- NOTES
-- ============================================================================
--
-- 1. The application MUST call set_tenant_context() at the start of each
--    request/session to enforce tenant isolation.
--
-- 2. RLS policies use COALESCE to fall back to default tenant if no context
--    is set, preventing accidental data exposure.
--
-- 3. All new tenant-specific tables should:
--    - Include tenant_id UUID NOT NULL column
--    - Have an index on tenant_id
--    - Enable ROW LEVEL SECURITY
--    - Have a tenant_isolation_policy
--
-- 4. For multi-tenant queries across all tenants (admin operations),
--    use a superuser connection or temporarily disable RLS.
--
-- ============================================================================
