-- Migration V002: Add Tenant Isolation to Gaming Service
-- Date: 2026-01-31
-- Purpose: Add multi-tenant support to all Gaming tables

-- ============================================================================
-- STEP 1: Add tenant_id columns
-- ============================================================================

-- Add tenant_id to transaction_logs
ALTER TABLE transaction_logs 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to self_exclusion_records
ALTER TABLE self_exclusion_records 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to responsible_gaming_alerts
ALTER TABLE responsible_gaming_alerts 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- ============================================================================
-- STEP 2: Create indexes for tenant filtering
-- ============================================================================

-- Index for transaction logs tenant filtering
CREATE INDEX idx_transaction_tenant ON transaction_logs(tenant_id);
CREATE INDEX idx_transaction_tenant_player ON transaction_logs(tenant_id, player_id);
CREATE INDEX idx_transaction_tenant_time ON transaction_logs(tenant_id, timestamp DESC);
CREATE INDEX idx_transaction_tenant_jurisdiction ON transaction_logs(tenant_id, jurisdiction);

-- Index for self-exclusion records tenant filtering
CREATE INDEX idx_exclusion_tenant ON self_exclusion_records(tenant_id);
CREATE INDEX idx_exclusion_tenant_player ON self_exclusion_records(tenant_id, player_id);
CREATE INDEX idx_exclusion_tenant_status ON self_exclusion_records(tenant_id, status);

-- Index for responsible gaming alerts tenant filtering
CREATE INDEX idx_alert_tenant ON responsible_gaming_alerts(tenant_id);
CREATE INDEX idx_alert_tenant_player ON responsible_gaming_alerts(tenant_id, player_id);
CREATE INDEX idx_alert_tenant_status ON responsible_gaming_alerts(tenant_id, status);

-- ============================================================================
-- STEP 3: Add documentation comments
-- ============================================================================

COMMENT ON COLUMN transaction_logs.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for gaming transaction logs.';

COMMENT ON COLUMN self_exclusion_records.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for self-exclusion records.';

COMMENT ON COLUMN responsible_gaming_alerts.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for responsible gaming alerts.';

-- ============================================================================
-- STEP 4: Add database-level comment
-- ============================================================================

COMMENT ON DATABASE gaming_db IS 
  'Gaming vertical database for transaction logs, self-exclusion, and responsible gaming. Tenant isolation added in V002.';

-- ============================================================================
-- VERIFICATION QUERIES (for manual testing)
-- ============================================================================

-- Verify tenant_id columns exist:
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name IN ('transaction_logs', 'self_exclusion_records', 'responsible_gaming_alerts')
-- AND column_name = 'tenant_id';

-- Verify indexes created:
-- SELECT indexname, tablename FROM pg_indexes 
-- WHERE tablename IN ('transaction_logs', 'self_exclusion_records', 'responsible_gaming_alerts')
-- AND indexname LIKE '%tenant%';
