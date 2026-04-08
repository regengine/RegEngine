-- V38: Tool leads table for email-gated free tool access.
-- NOT tenant-scoped — leads exist before any tenant relationship.
-- No RLS on this table.

CREATE TABLE IF NOT EXISTS tool_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    domain TEXT NOT NULL,
    company_name TEXT,
    first_tool_used TEXT,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_tool_access TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    access_count INTEGER NOT NULL DEFAULT 1,
    source_url TEXT,
    ip_country TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(email)
);

CREATE INDEX IF NOT EXISTS idx_tool_leads_domain ON tool_leads(domain);
CREATE INDEX IF NOT EXISTS idx_tool_leads_verified_at ON tool_leads(verified_at);
