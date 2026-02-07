-- ==========================================
-- RegEngine Hardening: Phase 7.1 RLS Migration
-- ==========================================
-- This script enforces the 'Double-Lock' isolation model.
-- It enables RLS and creates policies for all multi-tenant tables.

BEGIN;

-- 1. Ingestion Documents
ALTER TABLE ingestion.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion.documents FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_docs ON ingestion.documents;
CREATE POLICY tenant_isolation_docs ON ingestion.documents
    FOR ALL
    TO regengine
    USING (tenant_id = get_tenant_context());

-- 2. Vertical Projects
ALTER TABLE vertical_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE vertical_projects FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_projects ON vertical_projects;
CREATE POLICY tenant_isolation_projects ON vertical_projects
    FOR ALL
    TO regengine
    USING (tenant_id = get_tenant_context());

-- 3. Evidence Logs
ALTER TABLE evidence_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_logs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_evidence ON evidence_logs;
CREATE POLICY tenant_isolation_evidence ON evidence_logs
    FOR ALL
    TO regengine
    USING (tenant_id = get_tenant_context());

-- 4. Audit Logs
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_audit ON audit_logs;
CREATE POLICY tenant_isolation_audit ON audit_logs
    FOR ALL
    TO regengine
    USING (tenant_id = get_tenant_context());

-- 5. Memberships
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships;
CREATE POLICY tenant_isolation_memberships ON memberships
    FOR ALL
    TO regengine
    USING (tenant_id = current_setting('regengine.tenant_id')::uuid);

-- 6. User Profiles (Self-Isolation / Sysadmin)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_self_isolation ON users;
CREATE POLICY user_self_isolation ON users
    FOR ALL
    TO regengine
    USING (
        id = current_setting('regengine.user_id', true)::uuid 
        OR current_setting('regengine.is_sysadmin', true) = 'true'
    );

COMMIT;
