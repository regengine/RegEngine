-- V051 — Document developer portal schema (tables already exist in Supabase)
-- ======================================================================
-- These tables were created via Supabase dashboard and are actively used
-- by the developer portal frontend. This migration documents the schema
-- for version control and adds COMMENT annotations.
--
-- Tables: developer_invite_codes, developer_profiles, developer_api_keys,
--         developer_api_usage, assessment_submissions
--
-- All 5 tables have RLS enabled with appropriate policies:
--   - developer_profiles: SELECT/UPDATE own profile (auth_user_id = auth.uid())
--   - developer_api_keys: SELECT/INSERT/UPDATE own keys (via developer_id)
--   - developer_api_usage: SELECT own usage (via developer_id)
--   - developer_invite_codes: anon SELECT (for registration flow)
--   - assessment_submissions: anon INSERT/SELECT/UPDATE (for lead capture tools)
--
-- Tenant scoping: These tables use auth.uid()-based isolation, not tenant_id.
-- This is intentional — the developer portal is per-developer, not per-tenant.
-- If the portal goes multi-org, add tenant_id to developer_profiles and
-- cascade through the FK chain.

BEGIN;

-- ── developer_invite_codes ──────────────────────────────────
-- Registration gate — invite codes for developer portal access.
-- 0-row table (2 codes seeded manually via dashboard).
COMMENT ON TABLE developer_invite_codes IS
    'Developer portal registration gate. Invite codes control portal access. '
    'RLS: anon SELECT for registration validation. No tenant_id — global codes.';

-- ── developer_profiles ──────────────────────────────────────
-- One profile per auth user. Linked to auth.users via auth_user_id.
COMMENT ON TABLE developer_profiles IS
    'Developer portal user profiles. 1:1 with auth.users via auth_user_id. '
    'RLS: users can SELECT/UPDATE their own profile only. '
    'No tenant_id — developer portal is per-user, not per-tenant.';

-- ── developer_api_keys ──────────────────────────────────────
-- API keys for external developer access. Keys are SHA-256 hashed.
-- Only key_prefix (first 12 chars) is stored in plaintext for display.
COMMENT ON TABLE developer_api_keys IS
    'Developer API keys. key_hash stores SHA-256 hash (never plaintext). '
    'key_prefix stores first 12 chars for display. '
    'RLS: developers can manage their own keys only (via developer_id FK).';

-- ── developer_api_usage ──────────────────────────────────────
-- Per-request usage log for API analytics dashboard.
COMMENT ON TABLE developer_api_usage IS
    'Developer API usage log. One row per API request for analytics. '
    'RLS: developers can read their own usage only (via developer_id FK).';

-- ── assessment_submissions ──────────────────────────────────
-- Lead capture from free compliance tools. No auth required.
-- Triggers notify-new-lead edge function on INSERT.
COMMENT ON TABLE assessment_submissions IS
    'Lead capture from free compliance tools (no login required). '
    'RLS: anon INSERT + SELECT (duplicate check) + UPDATE (enrichment). '
    'Triggers notify-new-lead edge function on INSERT. '
    'No tenant_id — these are anonymous pre-signup submissions.';

COMMIT;
