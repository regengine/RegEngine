-- V040 — Document obligation_cte_rules as intentionally global (no RLS)
-- ======================================================================
-- The obligation_cte_rules table maps FSMA 204 regulatory obligations to
-- CTE types and required KDEs.  These rules are **federal regulations** —
-- they apply identically to all tenants.  There is no tenant_id column
-- because the data is system-wide reference data, not tenant-specific.
--
-- Tenant scoping happens at query time via JOINs:
--   WHERE o.tenant_id = CAST(:tid AS uuid)
-- This JOIN to the obligations table (which IS tenant-scoped) ensures
-- only the requesting tenant's obligations are returned.
--
-- This migration adds an explicit COMMENT documenting this design decision
-- so future developers don't add RLS by mistake.

BEGIN;

COMMENT ON TABLE obligation_cte_rules IS
    'FSMA 204 obligation-to-CTE mapping rules. INTENTIONALLY GLOBAL (no RLS, no tenant_id). '
    'These are federal regulatory rules that apply identically to all tenants. '
    'Tenant scoping is enforced via JOIN to the tenant-scoped obligations table. '
    'See V037 for the initial seed data (82 rules).';

COMMIT;
