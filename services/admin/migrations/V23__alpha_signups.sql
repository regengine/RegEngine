-- Alpha Waitlist Signups Table
-- Run this in Supabase SQL Editor or via migration

CREATE TABLE IF NOT EXISTS alpha_signups (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    company TEXT,
    role TEXT,
    source TEXT DEFAULT 'alpha-page',
    ip TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'contacted', 'accepted', 'declined')),
    notes TEXT
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_alpha_signups_email ON alpha_signups (email);
CREATE INDEX IF NOT EXISTS idx_alpha_signups_status ON alpha_signups (status);
CREATE INDEX IF NOT EXISTS idx_alpha_signups_created ON alpha_signups (created_at DESC);

-- Enable RLS
ALTER TABLE alpha_signups ENABLE ROW LEVEL SECURITY;

-- Service role can do everything (for API route)
CREATE POLICY "Service role full access" ON alpha_signups
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Prevent anonymous reads (signups are private)
-- Only service_role key can access this table
REVOKE ALL ON alpha_signups FROM anon;
REVOKE ALL ON alpha_signups FROM authenticated;
GRANT ALL ON alpha_signups TO service_role;
