
-- Create the organizations table in fsma schema
CREATE TABLE IF NOT EXISTS fsma.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'starter', 'professional', 'enterprise')),
    gln TEXT,
    fda_fei TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE fsma.organizations ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read organizations (public listing for tenant switcher)
CREATE POLICY "organizations_public_read" ON fsma.organizations
    FOR SELECT USING (true);
;
