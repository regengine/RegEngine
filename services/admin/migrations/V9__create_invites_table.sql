CREATE TABLE IF NOT EXISTS invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    email VARCHAR NOT NULL,
    role_id UUID NOT NULL REFERENCES roles(id),
    token_hash VARCHAR NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NOT NULL REFERENCES users(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_invites_tenant_email ON invites (tenant_id, email) WHERE revoked_at IS NULL AND accepted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_invites_token_hash ON invites (token_hash);
CREATE INDEX IF NOT EXISTS ix_invites_tenant_created ON invites (tenant_id, created_at);
