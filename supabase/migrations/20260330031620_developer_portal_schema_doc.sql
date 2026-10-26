
-- Document developer portal schema with COMMENT annotations

COMMENT ON TABLE developer_invite_codes IS
    'Developer portal registration gate. Invite codes control portal access. RLS: anon SELECT for registration validation. No tenant_id — global codes.';

COMMENT ON TABLE developer_profiles IS
    'Developer portal user profiles. 1:1 with auth.users via auth_user_id. RLS: users can SELECT/UPDATE their own profile only. No tenant_id — developer portal is per-user, not per-tenant.';

COMMENT ON TABLE developer_api_keys IS
    'Developer API keys. key_hash stores SHA-256 hash (never plaintext). key_prefix stores first 12 chars for display. RLS: developers can manage their own keys only (via developer_id FK).';

COMMENT ON TABLE developer_api_usage IS
    'Developer API usage log. One row per API request for analytics. RLS: developers can read their own usage only (via developer_id FK).';

COMMENT ON TABLE assessment_submissions IS
    'Lead capture from free compliance tools (no login required). RLS: anon INSERT + SELECT (duplicate check) + UPDATE (enrichment). Triggers notify-new-lead edge function on INSERT. No tenant_id — these are anonymous pre-signup submissions.';
;
