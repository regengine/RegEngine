-- V053 — Standardize RLS tenant-context resolution (#1271)
-- =========================================================
-- Problem: policies inconsistently use get_tenant_context() vs
--   current_setting('app.tenant_id'). The bare current_setting() call
--   raises an error when the GUC is unset; get_tenant_context() is a
--   wrapper that is sometimes unavailable in raw DB sessions.
--
-- Fix:
--   1. Drop and recreate every policy that uses get_tenant_context()
--      to use current_setting('app.tenant_id', true) instead.
--      The `true` flag returns NULL (instead of ERROR) when the GUC
--      is not set, which is the safe fail-closed behaviour.
--   2. Add sysadmin bypass to all affected policies:
--      OR current_setting('app.is_sysadmin', true) = 'true'
--      This lets internal tooling run without setting a tenant GUC.
--   3. Enable RLS and add tenant isolation policies on V042 tables
--      (tenant_suppliers, tenant_products, tenant_team_members,
--       tenant_notification_prefs, tenant_settings, tenant_onboarding,
--       tenant_exchanges, tenant_portal_links) which had no policies.

BEGIN;

-- -------------------------------------------------------------------------
-- Helper expression used throughout (avoids repetition):
--   tenant_id = current_setting('app.tenant_id', true)::uuid
--   OR current_setting('app.is_sysadmin', true) = 'true'
-- -------------------------------------------------------------------------

-- =========================================================================
-- Section 1: Re-standardise existing get_tenant_context() policies
-- =========================================================================

-- V002 tables -----------------------------------------------------------------

DROP POLICY IF EXISTS tenant_isolation_cte ON fsma.cte_events;
CREATE POLICY tenant_isolation_cte ON fsma.cte_events
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_kdes ON fsma.cte_kdes;
CREATE POLICY tenant_isolation_kdes ON fsma.cte_kdes
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_chain ON fsma.hash_chain;
CREATE POLICY tenant_isolation_chain ON fsma.hash_chain
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_alerts ON fsma.compliance_alerts;
CREATE POLICY tenant_isolation_alerts ON fsma.compliance_alerts
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_exports ON fsma.fda_export_log;
CREATE POLICY tenant_isolation_exports ON fsma.fda_export_log
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

-- V043 tables -----------------------------------------------------------------

DROP POLICY IF EXISTS tenant_isolation_ingestion_runs ON fsma.ingestion_runs;
CREATE POLICY tenant_isolation_ingestion_runs ON fsma.ingestion_runs
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_trace_events ON fsma.traceability_events;
CREATE POLICY tenant_isolation_trace_events ON fsma.traceability_events
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_evidence ON fsma.evidence_attachments;
CREATE POLICY tenant_isolation_evidence ON fsma.evidence_attachments
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

-- V044 tables -----------------------------------------------------------------

DROP POLICY IF EXISTS tenant_isolation_rule_evals ON fsma.rule_evaluations;
CREATE POLICY tenant_isolation_rule_evals ON fsma.rule_evaluations
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

-- V045 tables -----------------------------------------------------------------

DROP POLICY IF EXISTS tenant_isolation_exception_cases ON fsma.exception_cases;
CREATE POLICY tenant_isolation_exception_cases ON fsma.exception_cases
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_exception_comments ON fsma.exception_comments;
CREATE POLICY tenant_isolation_exception_comments ON fsma.exception_comments
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_exception_attachments ON fsma.exception_attachments;
CREATE POLICY tenant_isolation_exception_attachments ON fsma.exception_attachments
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_exception_signoffs ON fsma.exception_signoffs;
CREATE POLICY tenant_isolation_exception_signoffs ON fsma.exception_signoffs
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

-- V046 tables -----------------------------------------------------------------

DROP POLICY IF EXISTS tenant_isolation_request_cases ON fsma.request_cases;
CREATE POLICY tenant_isolation_request_cases ON fsma.request_cases
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_response_packages ON fsma.response_packages;
CREATE POLICY tenant_isolation_response_packages ON fsma.response_packages
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_submission_log ON fsma.submission_log;
CREATE POLICY tenant_isolation_submission_log ON fsma.submission_log
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_request_signoffs ON fsma.request_signoffs;
CREATE POLICY tenant_isolation_request_signoffs ON fsma.request_signoffs
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

-- V047 tables -----------------------------------------------------------------

DROP POLICY IF EXISTS tenant_isolation_canonical_entities ON fsma.canonical_entities;
CREATE POLICY tenant_isolation_canonical_entities ON fsma.canonical_entities
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_entity_aliases ON fsma.entity_aliases;
CREATE POLICY tenant_isolation_entity_aliases ON fsma.entity_aliases
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_merge_history ON fsma.entity_merge_history;
CREATE POLICY tenant_isolation_merge_history ON fsma.entity_merge_history
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenant_isolation_identity_review ON fsma.identity_review_queue;
CREATE POLICY tenant_isolation_identity_review ON fsma.identity_review_queue
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

-- =========================================================================
-- Section 2: V042 tables — enable RLS + add tenant isolation policies
-- (These tables were created without any RLS in V042.)
-- =========================================================================

ALTER TABLE fsma.tenant_suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.tenant_suppliers FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_suppliers ON fsma.tenant_suppliers
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

ALTER TABLE fsma.tenant_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.tenant_products FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_products ON fsma.tenant_products
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

ALTER TABLE fsma.tenant_team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.tenant_team_members FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_team_members ON fsma.tenant_team_members
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

ALTER TABLE fsma.tenant_notification_prefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.tenant_notification_prefs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_notification_prefs ON fsma.tenant_notification_prefs
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

ALTER TABLE fsma.tenant_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.tenant_settings FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_settings ON fsma.tenant_settings
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

ALTER TABLE fsma.tenant_onboarding ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.tenant_onboarding FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_onboarding ON fsma.tenant_onboarding
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

ALTER TABLE fsma.tenant_exchanges ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.tenant_exchanges FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_exchanges ON fsma.tenant_exchanges
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

ALTER TABLE fsma.tenant_portal_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.tenant_portal_links FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_portal_links ON fsma.tenant_portal_links
    FOR ALL
    USING (
        tenant_id = current_setting('app.tenant_id', true)::uuid
        OR current_setting('app.is_sysadmin', true) = 'true'
    );

COMMIT;
