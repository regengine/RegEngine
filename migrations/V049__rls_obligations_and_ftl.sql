-- ==========================================
-- RegEngine Security: Enable RLS on obligations and food_traceability_list
-- V049 — Close the last two RLS gaps identified in code review audit
-- ==========================================
--
-- FINDING: obligations (78 rows, tenant-scoped) and food_traceability_list
-- (15 rows, global reference data) were created without RLS in V001/V036.
-- Application-layer filtering exists but database-level RLS was missing.
--
-- obligations: tenant-scoped → standard tenant isolation policy
-- food_traceability_list: global FDA reference data (no tenant_id column)
--   → read-only policy for all authenticated roles, no writes via RLS
--
-- This migration is fully idempotent — safe to re-run.

BEGIN;

-- =========================================================
-- 1. obligations — enable RLS with tenant isolation
-- =========================================================
ALTER TABLE obligations ENABLE ROW LEVEL SECURITY;

-- Allow normal tenant-scoped access + sysadmin bypass (matches V048 pattern)
DROP POLICY IF EXISTS tenant_isolation_obligations ON obligations;
CREATE POLICY tenant_isolation_obligations ON obligations
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

-- Audit trigger for sysadmin bypass tracking
DROP TRIGGER IF EXISTS trg_audit_sysadmin_obligations ON obligations;
CREATE TRIGGER trg_audit_sysadmin_obligations
    AFTER INSERT OR UPDATE OR DELETE ON obligations
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

-- Also protect the controls table (child of obligations, same gap)
ALTER TABLE controls ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_controls ON controls;
CREATE POLICY tenant_isolation_controls ON controls
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP TRIGGER IF EXISTS trg_audit_sysadmin_controls ON controls;
CREATE TRIGGER trg_audit_sysadmin_controls
    AFTER INSERT OR UPDATE OR DELETE ON controls
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

-- =========================================================
-- 2. food_traceability_list — read-only access for all roles
-- =========================================================
-- This table has NO tenant_id column — it's the FDA Food Traceability List,
-- identical for all tenants (federal regulation). See V036 for seed data.
-- RLS policy: allow SELECT for all application roles, block INSERT/UPDATE/DELETE.

ALTER TABLE food_traceability_list ENABLE ROW LEVEL SECURITY;

-- Read-only: any authenticated application role can SELECT
DROP POLICY IF EXISTS ftl_read_only ON food_traceability_list;
CREATE POLICY ftl_read_only ON food_traceability_list
    FOR SELECT
    TO regengine, regengine_sysadmin
    USING (true);

-- Write access: sysadmin only (for seeding/updating reference data)
DROP POLICY IF EXISTS ftl_sysadmin_write ON food_traceability_list;
CREATE POLICY ftl_sysadmin_write ON food_traceability_list
    FOR ALL
    TO regengine_sysadmin
    USING (true)
    WITH CHECK (true);

COMMENT ON TABLE food_traceability_list IS
    'FDA FSMA 204 Food Traceability List — global reference data (no tenant_id). '
    'RLS: read-only for all roles, writes restricted to regengine_sysadmin. '
    'See V036 for seed data, V049 for RLS enablement.';

-- =========================================================
-- 3. regulations table — also missing RLS (parent of obligations)
-- =========================================================
ALTER TABLE regulations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_regulations ON regulations;
CREATE POLICY tenant_isolation_regulations ON regulations
    FOR ALL
    TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP TRIGGER IF EXISTS trg_audit_sysadmin_regulations ON regulations;
CREATE TRIGGER trg_audit_sysadmin_regulations
    AFTER INSERT OR UPDATE OR DELETE ON regulations
    FOR EACH ROW
    EXECUTE FUNCTION audit.log_sysadmin_access();

COMMIT;
