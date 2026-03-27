-- ==========================================
-- RegEngine Security: RLS Sysadmin Defense-in-Depth
-- V048 — Harden sysadmin bypass against session variable leakage
-- ==========================================
--
-- VULNERABILITY: All RLS policies previously checked only
--   current_setting('regengine.is_sysadmin', true) = 'true'
-- If this session variable leaked or was set maliciously by any
-- database connection, ALL tenant data would be exposed.
--
-- FIX: Require BOTH the session variable AND the database role
-- to be 'regengine_sysadmin'. A regular 'regengine' role connection
-- can never bypass RLS even if the session variable is set.
--
-- This migration is fully idempotent — safe to re-run.

BEGIN;

-- =========================================================
-- 1. Create the dedicated sysadmin role (if not exists)
-- =========================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
        CREATE ROLE regengine_sysadmin LOGIN INHERIT;
        RAISE NOTICE 'Created role regengine_sysadmin';
    END IF;
END
$$;

-- Grant the base regengine role so regengine_sysadmin inherits table access
DO $$
BEGIN
    IF NOT pg_has_role('regengine_sysadmin', 'regengine', 'MEMBER') THEN
        EXECUTE 'GRANT regengine TO regengine_sysadmin';
        RAISE NOTICE 'Granted regengine to regengine_sysadmin';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Could not grant regengine to regengine_sysadmin: %', SQLERRM;
END
$$;

COMMENT ON ROLE regengine_sysadmin IS
    'Dedicated sysadmin role for RLS bypass. Both this role AND the '
    'regengine.is_sysadmin session variable must be present to bypass '
    'tenant isolation. Never use this role for normal application connections.';

-- =========================================================
-- 2. Create audit schema and sysadmin access log table
-- =========================================================
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.sysadmin_access_log (
    id BIGSERIAL PRIMARY KEY,
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    connection_info JSONB,
    session_user_name TEXT NOT NULL DEFAULT session_user,
    client_addr TEXT DEFAULT inet_client_addr()::TEXT
);

-- Index for time-range queries on the audit log
CREATE INDEX IF NOT EXISTS idx_sysadmin_access_log_accessed_at
    ON audit.sysadmin_access_log (accessed_at DESC);

-- Allow the sysadmin role to insert audit records
GRANT USAGE ON SCHEMA audit TO regengine_sysadmin;
GRANT INSERT, SELECT ON audit.sysadmin_access_log TO regengine_sysadmin;
GRANT USAGE, SELECT ON SEQUENCE audit.sysadmin_access_log_id_seq TO regengine_sysadmin;

-- Also allow the base regengine role to insert (the trigger runs as the
-- current user, which could be regengine_sysadmin inheriting regengine)
GRANT USAGE ON SCHEMA audit TO regengine;
GRANT INSERT ON audit.sysadmin_access_log TO regengine;
GRANT USAGE, SELECT ON SEQUENCE audit.sysadmin_access_log_id_seq TO regengine;

COMMENT ON TABLE audit.sysadmin_access_log IS
    'Records every row access that used the sysadmin RLS bypass. '
    'Captures who, when, from where, and which table/operation.';

-- =========================================================
-- 3. Create the audit trigger function
-- =========================================================
CREATE OR REPLACE FUNCTION audit.log_sysadmin_access()
RETURNS TRIGGER AS $$
BEGIN
    -- Only log when the sysadmin bypass is actually being used
    IF current_setting('regengine.is_sysadmin', true) = 'true'
       AND current_user = 'regengine_sysadmin' THEN
        INSERT INTO audit.sysadmin_access_log (table_name, operation, connection_info)
        VALUES (
            TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
            TG_OP,
            jsonb_build_object(
                'current_user', current_user,
                'session_user', session_user,
                'client_addr', inet_client_addr()::TEXT,
                'application_name', current_setting('application_name', true),
                'backend_pid', pg_backend_pid()
            )
        );
    END IF;

    -- Return the appropriate row for the trigger type
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION audit.log_sysadmin_access() IS
    'Trigger function that logs sysadmin RLS bypass usage to audit.sysadmin_access_log';

-- =========================================================
-- 4. Update the set_admin_context helper to warn on misuse
-- =========================================================
CREATE OR REPLACE FUNCTION set_admin_context(p_is_sysadmin boolean) RETURNS void AS $$
BEGIN
    -- SECURITY: Only the regengine_sysadmin role should call this with true.
    -- The RLS policies enforce both the session var AND the role check,
    -- so setting this variable alone is not sufficient for bypass.
    IF p_is_sysadmin AND current_user != 'regengine_sysadmin' THEN
        RAISE WARNING 'set_admin_context(true) called by role "%" — '
                       'RLS bypass requires regengine_sysadmin role. '
                       'The session variable will be set but RLS policies '
                       'will NOT grant sysadmin access.', current_user;
    END IF;
    PERFORM set_config('regengine.is_sysadmin', p_is_sysadmin::text, false);
END;
$$ LANGUAGE plpgsql;

-- =========================================================
-- 5. Update ALL RLS policies — require BOTH session var AND role
-- =========================================================

-- 5a. Ingestion Documents
DROP POLICY IF EXISTS tenant_isolation_docs ON ingestion.documents;
CREATE POLICY tenant_isolation_docs ON ingestion.documents
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP TRIGGER IF EXISTS trg_audit_sysadmin_docs ON ingestion.documents;
CREATE TRIGGER trg_audit_sysadmin_docs
    AFTER INSERT OR UPDATE OR DELETE ON ingestion.documents
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

-- 5b. Vertical Projects
DROP POLICY IF EXISTS tenant_isolation_projects ON vertical_projects;
CREATE POLICY tenant_isolation_projects ON vertical_projects
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP TRIGGER IF EXISTS trg_audit_sysadmin_projects ON vertical_projects;
CREATE TRIGGER trg_audit_sysadmin_projects
    AFTER INSERT OR UPDATE OR DELETE ON vertical_projects
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

-- 5c. Evidence Logs
DROP POLICY IF EXISTS tenant_isolation_evidence ON evidence_logs;
CREATE POLICY tenant_isolation_evidence ON evidence_logs
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP TRIGGER IF EXISTS trg_audit_sysadmin_evidence ON evidence_logs;
CREATE TRIGGER trg_audit_sysadmin_evidence
    AFTER INSERT OR UPDATE OR DELETE ON evidence_logs
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

-- 5d. Audit Logs
DROP POLICY IF EXISTS tenant_isolation_audit ON audit_logs;
CREATE POLICY tenant_isolation_audit ON audit_logs
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP TRIGGER IF EXISTS trg_audit_sysadmin_audit_logs ON audit_logs;
CREATE TRIGGER trg_audit_sysadmin_audit_logs
    AFTER INSERT OR UPDATE OR DELETE ON audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

-- 5e. Memberships
DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships;
CREATE POLICY tenant_isolation_memberships ON memberships
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP TRIGGER IF EXISTS trg_audit_sysadmin_memberships ON memberships;
CREATE TRIGGER trg_audit_sysadmin_memberships
    AFTER INSERT OR UPDATE OR DELETE ON memberships
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

-- 5f. Users (self-isolation + sysadmin bypass)
DROP POLICY IF EXISTS user_self_isolation ON users;
CREATE POLICY user_self_isolation ON users
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        id = current_setting('regengine.user_id', true)::uuid
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP TRIGGER IF EXISTS trg_audit_sysadmin_users ON users;
CREATE TRIGGER trg_audit_sysadmin_users
    AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

COMMIT;
