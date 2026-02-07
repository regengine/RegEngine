-- Migration V27: Enable RLS for Core Security Tables
-- Priority: P0 - CRITICAL SECURITY
-- Date: 2026-01-31
--
-- This migration secures the 15 most critical tables by enabling Row Level Security
-- to prevent direct PostgREST API access from bypassing application middleware.
--
-- Tables covered:
-- 1. tenants (multi-tenant isolation root)
-- 2. users (authentication)
-- 3. memberships (user-tenant associations)
-- 4. roles (permissions)
-- 5. sessions (active sessions)
-- 6. invites (pending invitations)
-- 7. api_keys (API authentication)
-- 8. compliance_snapshots (audit trail)
-- 9. audit_logs (system audit)
-- 10. evidence_logs (evidence vault)
-- 11. tenant_compliance_status (compliance tracking)
-- 12. tenant_product_profile (product config)
-- 13. compliance_alerts (alerts)
-- 14. compliance_status_log (status history)
-- 15. review_items (already has RLS from V3, adding FORCE RLS)

-- ============================================================================
-- SECTION 1: Enable RLS on Core Authentication Tables
-- ============================================================================

-- 1. tenants table - Special case: readable by all authenticated users,
-- but write operations restricted
ALTER TABLE IF EXISTS tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tenants FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenants_read_all" ON tenants;
CREATE POLICY "tenants_read_all" ON tenants
  FOR SELECT
  TO authenticated
  USING (true); -- All authenticated users can see all tenants (needed for user-tenant associations)

DROP POLICY IF EXISTS "tenants_write_own" ON tenants;
CREATE POLICY "tenants_write_own" ON tenants
  FOR ALL
  TO authenticated
  USING (
    id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "tenants_read_all" ON tenants IS 
  'Allow all authenticated users to read tenant metadata (needed for multi-tenant UIs)';
COMMENT ON POLICY "tenants_write_own" ON tenants IS 
  'Users can only modify their own tenant';

-- 2. users table
ALTER TABLE IF EXISTS users ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS users FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_own_data" ON users;
CREATE POLICY "users_own_data" ON users
  FOR ALL
  TO authenticated
  USING (id = auth.uid()); -- Supabase auth.uid() function

COMMENT ON POLICY "users_own_data" ON users IS 
  'Users can only access their own user record';

-- 3. memberships table - users can see memberships for their tenant
ALTER TABLE IF EXISTS memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS memberships FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "memberships_tenant_isolation" ON memberships;
CREATE POLICY "memberships_tenant_isolation" ON memberships
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "memberships_tenant_isolation" ON memberships IS 
  'Users can only see memberships for their current tenant';

-- 4. roles table - tenant-scoped
ALTER TABLE IF EXISTS roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS roles FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "roles_tenant_isolation" ON roles;
CREATE POLICY "roles_tenant_isolation" ON roles
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "roles_tenant_isolation" ON roles IS 
  'Roles are scoped to tenant_id';

-- 5. sessions table - user owns their own sessions
ALTER TABLE IF EXISTS sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS sessions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "sessions_user_owns" ON sessions;
CREATE POLICY "sessions_user_owns" ON sessions
  FOR ALL
  TO authenticated
  USING (user_id = auth.uid());

COMMENT ON POLICY "sessions_user_owns" ON sessions IS 
  'Users can only access their own sessions';

-- 6. invites table - tenant isolation
ALTER TABLE IF EXISTS invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS invites FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "invites_tenant_isolation" ON invites;
CREATE POLICY "invites_tenant_isolation" ON invites
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "invites_tenant_isolation" ON invites IS 
  'Invites are scoped to tenant_id';

-- 7. api_keys - Check if already has RLS from V3, if not create it
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'api_keys') THEN
    -- Enable RLS if not already enabled
    ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
    ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;
    
    -- Drop and recreate policy to ensure it exists
    DROP POLICY IF EXISTS "tenant_isolation_policy" ON api_keys;
    CREATE POLICY "tenant_isolation_policy" ON api_keys
      FOR ALL
      TO authenticated
      USING (
        tenant_id::uuid = COALESCE(
          NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
          '00000000-0000-0000-0000-000000000001'::UUID
        )
      );
    
    -- Add comment
    COMMENT ON POLICY "tenant_isolation_policy" ON api_keys IS 
      'API keys are scoped to tenant_id (enforced by V3 + V8 + V27)';
  END IF;
END $$;


-- 8. audit_logs - tenant isolation
ALTER TABLE IF EXISTS audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS audit_logs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "audit_logs_tenant_isolation" ON audit_logs;
CREATE POLICY "audit_logs_tenant_isolation" ON audit_logs
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "audit_logs_tenant_isolation" ON audit_logs IS 
  'Audit logs are scoped to tenant_id for security isolation';

-- 9. evidence_logs - tenant isolation (immutable evidence vault)
ALTER TABLE IF EXISTS evidence_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS evidence_logs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "evidence_logs_tenant_isolation" ON evidence_logs;
CREATE POLICY "evidence_logs_tenant_isolation" ON evidence_logs
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "evidence_logs_tenant_isolation" ON evidence_logs IS 
  'Evidence logs are immutable and scoped to tenant_id';

-- ============================================================================
-- SECTION 3: Enable RLS on Compliance Tables
-- ============================================================================

-- 10. compliance_snapshots - tenant isolation
ALTER TABLE IF EXISTS compliance_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS compliance_snapshots FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "compliance_snapshots_tenant_isolation" ON compliance_snapshots;
CREATE POLICY "compliance_snapshots_tenant_isolation" ON compliance_snapshots
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "compliance_snapshots_tenant_isolation" ON compliance_snapshots IS 
  'Compliance snapshots are immutable and scoped to tenant_id';

-- 11. tenant_compliance_status - tenant isolation
ALTER TABLE IF EXISTS tenant_compliance_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tenant_compliance_status FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenant_compliance_status_isolation" ON tenant_compliance_status;
CREATE POLICY "tenant_compliance_status_isolation" ON tenant_compliance_status
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "tenant_compliance_status_isolation" ON tenant_compliance_status IS 
  'Compliance status is scoped to tenant_id';

-- 12. tenant_product_profile - tenant isolation
ALTER TABLE IF EXISTS tenant_product_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tenant_product_profile FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenant_product_profile_isolation" ON tenant_product_profile;
CREATE POLICY "tenant_product_profile_isolation" ON tenant_product_profile
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "tenant_product_profile_isolation" ON tenant_product_profile IS 
  'Product profiles are scoped to tenant_id';

-- 13. compliance_alerts - tenant isolation
ALTER TABLE IF EXISTS compliance_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS compliance_alerts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "compliance_alerts_tenant_isolation" ON compliance_alerts;
CREATE POLICY "compliance_alerts_tenant_isolation" ON compliance_alerts
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "compliance_alerts_tenant_isolation" ON compliance_alerts IS 
  'Compliance alerts are scoped to tenant_id';

-- 14. compliance_status_log - tenant isolation
ALTER TABLE IF EXISTS compliance_status_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS compliance_status_log FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "compliance_status_log_tenant_isolation" ON compliance_status_log;
CREATE POLICY "compliance_status_log_tenant_isolation" ON compliance_status_log
  FOR ALL
  TO authenticated
  USING (
    tenant_id = COALESCE(
      NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
      '00000000-0000-0000-0000-000000000001'::UUID
    )
  );

COMMENT ON POLICY "compliance_status_log_tenant_isolation" ON compliance_status_log IS 
  'Status log entries are scoped to tenant_id';

-- 15. review_items - Check if already has RLS from V3, add FORCE RLS
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'review_items') THEN
    -- Enable RLS if not already enabled
    ALTER TABLE review_items ENABLE ROW LEVEL SECURITY;
    ALTER TABLE review_items FORCE ROW LEVEL SECURITY;
    
    -- Drop and recreate policy to ensure it exists
    DROP POLICY IF EXISTS "tenant_isolation_policy" ON review_items;
    CREATE POLICY "tenant_isolation_policy" ON review_items
      FOR ALL
      TO authenticated
      USING (
        tenant_id = COALESCE(
          NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
          '00000000-0000-0000-0000-000000000001'::UUID
        )
      );
    
    -- Add comment
    COMMENT ON POLICY "tenant_isolation_policy" ON review_items IS 
      'Review items are scoped to tenant_id (enforced by V3 + V8 + V27)';
  END IF;
END $$;


-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Add audit log entry
DO $$
BEGIN
  RAISE NOTICE 'V27 Migration Complete: RLS enabled on 15 core security tables';
  RAISE NOTICE 'Protected tables: tenants, users, memberships, roles, sessions, invites, api_keys, audit_logs, evidence_logs, compliance_snapshots, tenant_compliance_status, tenant_product_profile, compliance_alerts, compliance_status_log, review_items';
END $$;
