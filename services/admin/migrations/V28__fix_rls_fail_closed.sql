-- Migration V28: Fix RLS Fail-Open Logic
-- Priority: P0 - CRITICAL SECURITY REMEDIATION
-- Date: 2026-02-21
--
-- This migration removes the COALESCE fallback to the sandbox UUID
-- '00000000-0000-0000-0000-000000000001' in RLS policies.
-- Policies will now FAIL CLOSED if 'app.tenant_id' is null or empty.

-- 1. tenants
DROP POLICY IF EXISTS "tenants_write_own" ON tenants;
CREATE POLICY "tenants_write_own" ON tenants
  FOR ALL
  TO authenticated
  USING (
    id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 2. users (Already fails closed as it uses auth.uid())

-- 3. memberships
DROP POLICY IF EXISTS "memberships_tenant_isolation" ON memberships;
CREATE POLICY "memberships_tenant_isolation" ON memberships
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 4. roles
DROP POLICY IF EXISTS "roles_tenant_isolation" ON roles;
CREATE POLICY "roles_tenant_isolation" ON roles
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 6. invites
DROP POLICY IF EXISTS "invites_tenant_isolation" ON invites;
CREATE POLICY "invites_tenant_isolation" ON invites
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 7. api_keys
DROP POLICY IF EXISTS "tenant_isolation_policy" ON api_keys;
CREATE POLICY "tenant_isolation_policy" ON api_keys
  FOR ALL
  TO authenticated
  USING (
    tenant_id::uuid = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 8. audit_logs
DROP POLICY IF EXISTS "audit_logs_tenant_isolation" ON audit_logs;
CREATE POLICY "audit_logs_tenant_isolation" ON audit_logs
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 9. evidence_logs
DROP POLICY IF EXISTS "evidence_logs_tenant_isolation" ON evidence_logs;
CREATE POLICY "evidence_logs_tenant_isolation" ON evidence_logs
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 10. compliance_snapshots
DROP POLICY IF EXISTS "compliance_snapshots_tenant_isolation" ON compliance_snapshots;
CREATE POLICY "compliance_snapshots_tenant_isolation" ON compliance_snapshots
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 11. tenant_compliance_status
DROP POLICY IF EXISTS "tenant_compliance_status_isolation" ON tenant_compliance_status;
CREATE POLICY "tenant_compliance_status_isolation" ON tenant_compliance_status
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 12. tenant_product_profile
DROP POLICY IF EXISTS "tenant_product_profile_isolation" ON tenant_product_profile;
CREATE POLICY "tenant_product_profile_isolation" ON tenant_product_profile
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 13. compliance_alerts
DROP POLICY IF EXISTS "compliance_alerts_tenant_isolation" ON compliance_alerts;
CREATE POLICY "compliance_alerts_tenant_isolation" ON compliance_alerts
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 14. compliance_status_log
DROP POLICY IF EXISTS "compliance_status_log_tenant_isolation" ON compliance_status_log;
CREATE POLICY "compliance_status_log_tenant_isolation" ON compliance_status_log
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- 15. review_items
DROP POLICY IF EXISTS "tenant_isolation_policy" ON review_items;
CREATE POLICY "tenant_isolation_policy" ON review_items
  FOR ALL
  TO authenticated
  USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
  );

-- FORCE RLS on all tables to be absolutely sure
ALTER TABLE IF EXISTS tenants FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS users FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS roles FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS invites FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS api_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS audit_logs FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS evidence_logs FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS compliance_snapshots FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tenant_compliance_status FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tenant_product_profile FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS compliance_alerts FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS compliance_status_log FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS review_items FORCE ROW LEVEL SECURITY;

-- Log the remediation
DO $$
BEGIN
  RAISE NOTICE 'V28 Remediation Complete: RLS policies hardened to fail-closed state.';
END $$;
