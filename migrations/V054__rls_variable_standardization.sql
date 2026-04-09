-- ============================================================================
-- V054: RLS Variable Standardization
-- Priority: P0 - CRITICAL TENANT ISOLATION FIX
-- Date: 2026-04-08
-- ============================================================================
-- Problem: The codebase has 4 different PostgreSQL session variable names
-- for tenant context. Only `app.tenant_id` is actually set by the
-- application. Policies using other variable names silently fail,
-- leaving tables unprotected by RLS.
--
-- This migration:
-- 1. Replaces get_tenant_context() with a fail-hard definition
--    (no COALESCE fallback to default UUID)
-- 2. Fixes V19 PCOS table policies (were using app.current_tenant_id)
-- 3. Fixes V20 PCOS table policy  (was using app.current_tenant_id)
-- 4. Drops stale memberships policy (was using regengine.tenant_id)
--
-- After this migration, ALL RLS policies use either:
-- - get_tenant_context() which reads app.tenant_id (preferred)
-- - NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID (direct)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Replace get_tenant_context() with FAIL-HARD definition
-- ============================================================================
-- The V3 and V29 versions fall back to '00000000-0000-0000-0000-000000000001'
-- when app.tenant_id is not set. This silently returns the wrong tenant's
-- data instead of failing. The database.py init_db() version raises an
-- exception, but only wins if it runs after migrations. This migration
-- makes the fail-hard version authoritative in the migration chain.

CREATE OR REPLACE FUNCTION get_tenant_context()
RETURNS UUID AS $$
DECLARE
    tid TEXT;
BEGIN
    tid := NULLIF(current_setting('app.tenant_id', TRUE), '');
    IF tid IS NULL THEN
        RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS';
    END IF;
    RETURN tid::UUID;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_tenant_context() IS
    'Returns current tenant UUID from session variable app.tenant_id. '
    'RAISES EXCEPTION if not set. No fallback - fail closed by design.';

-- ============================================================================
-- 2. Fix V19 PCOS tables (were using app.current_tenant_id)
-- ============================================================================
-- These 3 tables had RLS policies referencing app.current_tenant_id which
-- is NEVER set by the application. Replacing with get_tenant_context().

-- pcos_authority_documents
DROP POLICY IF EXISTS pcos_authority_documents_tenant_isolation ON pcos_authority_documents;
CREATE POLICY pcos_authority_documents_tenant_isolation ON pcos_authority_documents
    FOR ALL USING (tenant_id = get_tenant_context());

-- pcos_extracted_facts
DROP POLICY IF EXISTS pcos_extracted_facts_tenant_isolation ON pcos_extracted_facts;
CREATE POLICY pcos_extracted_facts_tenant_isolation ON pcos_extracted_facts
    FOR ALL USING (tenant_id = get_tenant_context());

-- pcos_fact_citations
DROP POLICY IF EXISTS pcos_fact_citations_tenant_isolation ON pcos_fact_citations;
CREATE POLICY pcos_fact_citations_tenant_isolation ON pcos_fact_citations
    FOR ALL USING (tenant_id = get_tenant_context());

-- ============================================================================
-- 3. Fix V20 pcos_analysis_runs (was using app.current_tenant_id)
-- ============================================================================

DROP POLICY IF EXISTS pcos_analysis_runs_tenant_isolation ON pcos_analysis_runs;
CREATE POLICY pcos_analysis_runs_tenant_isolation ON pcos_analysis_runs
    FOR ALL USING (tenant_id = get_tenant_context());

-- ============================================================================
-- 4. Drop stale memberships policy from rls_migration_v1.sql
-- ============================================================================
-- rls_migration_v1.sql created tenant_isolation_memberships using
-- regengine.tenant_id (never set). V28_5 already created the correct
-- memberships_tenant_isolation using app.tenant_id. The old policy is
-- dead weight but could confuse auditors.

DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships;

-- ============================================================================
-- 5. Ensure FORCE ROW LEVEL SECURITY on PCOS tables
-- ============================================================================
-- V19/V20 enabled RLS but did not FORCE it. Without FORCE, table owners
-- bypass RLS. FORCE ensures even the table owner is subject to policies.

ALTER TABLE pcos_authority_documents FORCE ROW LEVEL SECURITY;
ALTER TABLE pcos_extracted_facts FORCE ROW LEVEL SECURITY;
ALTER TABLE pcos_fact_citations FORCE ROW LEVEL SECURITY;
ALTER TABLE pcos_analysis_runs FORCE ROW LEVEL SECURITY;

COMMIT;
