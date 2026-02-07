-- Admin Service Performance Indexes  
-- Version: 023
-- Description: Add indexes for authentication, authorization, and audit queries

-- User authentication (email lookups)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email_active
ON users(email)
WHERE is_active = true AND deleted_at IS NULL;

-- Tenant-scoped user queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_tenant_role
ON users(tenant_id, role_id, is_active)
WHERE deleted_at IS NULL;

-- User by ID (should exist as PK, but ensure)
-- Already covered by PRIMARY KEY

-- API key validation (most frequent query)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_api_keys_key_hash_tenant
ON api_keys(key_hash, tenant_id)
WHERE revoked_at IS NULL AND deleted_at IS NULL;

-- API keys by tenant (management queries)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_api_keys_tenant
ON api_keys(tenant_id, created_at DESC)
WHERE deleted_at IS NULL;

-- Audit log queries by service and time
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_service_time
ON audit_logs(service, timestamp DESC);

-- Audit logs by user activity
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_user_time
ON audit_logs(user_id, timestamp DESC);

-- Audit logs by tenant
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_tenant
ON audit_logs(tenant_id, timestamp DESC);

-- Invites by email (checking existing invites)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_invites_email_status
ON invitations(email, status)
WHERE accepted_at IS NULL AND deleted_at IS NULL;

-- Tenant lookups by ID (should exist as PK)
-- Already covered by PRIMARY KEY

-- Review queue queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_review_queue_status
ON review_queue(status, created_at DESC);

-- Update statistics
ANALYZE users;
ANALYZE tenants;
ANALYZE api_keys;
ANALYZE audit_logs;
ANALYZE invitations;
ANALYZE review_queue;

-- Add comments
COMMENT ON INDEX idx_users_email_active IS 'Optimizes login queries';
COMMENT ON INDEX idx_api_keys_key_hash_tenant IS 'Critical for API key validation performance';
COMMENT ON INDEX idx_audit_logs_service_time IS 'Supports audit trail queries and compliance reporting';
