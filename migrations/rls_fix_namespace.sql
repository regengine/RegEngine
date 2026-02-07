-- ==========================================
-- RegEngine Hardening: Fix RLS Policy Namespace
-- ==========================================
-- This script aligns policies with the existing 'app.tenant_id' session variable.

BEGIN;

-- 1. Ingestion Documents
DROP POLICY IF EXISTS tenant_isolation_docs ON ingestion.documents;
CREATE POLICY tenant_isolation_docs ON ingestion.documents
    FOR ALL
    TO regengine
    USING (
        tenant_id = get_tenant_context()
        OR current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- 2. Vertical Projects
DROP POLICY IF EXISTS tenant_isolation_projects ON vertical_projects;
CREATE POLICY tenant_isolation_projects ON vertical_projects
    FOR ALL
    TO regengine
    USING (
        tenant_id = get_tenant_context()
        OR current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- 3. Evidence Logs
DROP POLICY IF EXISTS tenant_isolation_evidence ON evidence_logs;
CREATE POLICY tenant_isolation_evidence ON evidence_logs
    FOR ALL
    TO regengine
    USING (
        tenant_id = get_tenant_context()
        OR current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- 4. Audit Logs
DROP POLICY IF EXISTS tenant_isolation_audit ON audit_logs;
CREATE POLICY tenant_isolation_audit ON audit_logs
    FOR ALL
    TO regengine
    USING (
        tenant_id = get_tenant_context()
        OR current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- 5. Memberships
DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships;
CREATE POLICY tenant_isolation_memberships ON memberships
    FOR ALL
    TO regengine
    USING (
        tenant_id = get_tenant_context()
        OR current_setting('regengine.is_sysadmin', true) = 'true'
    );

COMMIT;
