
-- Developer invite codes for gated registration
CREATE TABLE public.developer_invite_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(32) NOT NULL UNIQUE,
    label varchar(100),
    max_uses integer NOT NULL DEFAULT 1,
    used_count integer NOT NULL DEFAULT 0,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by varchar(255)
);

-- Developer profiles linked to Supabase auth.users
CREATE TABLE public.developer_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id uuid NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    email varchar(255) NOT NULL,
    company_name varchar(255),
    display_name varchar(255),
    invite_code_id uuid REFERENCES public.developer_invite_codes(id),
    status varchar(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'revoked')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);

-- Developer API keys (separate from tenant api_keys)
CREATE TABLE public.developer_api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    developer_id uuid NOT NULL REFERENCES public.developer_profiles(id) ON DELETE CASCADE,
    name varchar(100) NOT NULL,
    key_prefix varchar(12) NOT NULL,
    key_hash varchar(128) NOT NULL,
    scopes text[] DEFAULT ARRAY['read'],
    last_used_at timestamptz,
    total_requests integer NOT NULL DEFAULT 0,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

-- API usage log for the usage dashboard
CREATE TABLE public.developer_api_usage (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    developer_id uuid NOT NULL REFERENCES public.developer_profiles(id) ON DELETE CASCADE,
    api_key_id uuid REFERENCES public.developer_api_keys(id) ON DELETE SET NULL,
    endpoint varchar(255) NOT NULL,
    method varchar(10) NOT NULL,
    status_code integer NOT NULL,
    response_time_ms integer,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Index for fast usage queries
CREATE INDEX idx_dev_usage_developer_created ON public.developer_api_usage(developer_id, created_at DESC);
CREATE INDEX idx_dev_api_keys_developer ON public.developer_api_keys(developer_id);

-- Enable RLS on all tables
ALTER TABLE public.developer_invite_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.developer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.developer_api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.developer_api_usage ENABLE ROW LEVEL SECURITY;

-- RLS: developers can read their own profile
CREATE POLICY "developers_read_own_profile" ON public.developer_profiles
    FOR SELECT USING (auth.uid() = auth_user_id);

-- RLS: developers can update their own profile
CREATE POLICY "developers_update_own_profile" ON public.developer_profiles
    FOR UPDATE USING (auth.uid() = auth_user_id);

-- RLS: developers can read their own API keys
CREATE POLICY "developers_read_own_keys" ON public.developer_api_keys
    FOR SELECT USING (
        developer_id IN (SELECT id FROM public.developer_profiles WHERE auth_user_id = auth.uid())
    );

-- RLS: developers can insert their own API keys
CREATE POLICY "developers_insert_own_keys" ON public.developer_api_keys
    FOR INSERT WITH CHECK (
        developer_id IN (SELECT id FROM public.developer_profiles WHERE auth_user_id = auth.uid())
    );

-- RLS: developers can update (revoke) their own API keys
CREATE POLICY "developers_update_own_keys" ON public.developer_api_keys
    FOR UPDATE USING (
        developer_id IN (SELECT id FROM public.developer_profiles WHERE auth_user_id = auth.uid())
    );

-- RLS: developers can read their own usage
CREATE POLICY "developers_read_own_usage" ON public.developer_api_usage
    FOR SELECT USING (
        developer_id IN (SELECT id FROM public.developer_profiles WHERE auth_user_id = auth.uid())
    );

-- RLS: invite codes are readable during registration (anon can check validity)
CREATE POLICY "anon_read_invite_codes" ON public.developer_invite_codes
    FOR SELECT USING (true);
;
