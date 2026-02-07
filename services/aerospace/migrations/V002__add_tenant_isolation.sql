-- Migration V002: Add Tenant Isolation to Aerospace Service
-- Date: 2026-01-31
-- Purpose: Add multi-tenant support to all Aerospace tables

-- ============================================================================
-- STEP 1: Add tenant_id columns
-- ============================================================================

-- Add tenant_id to fai_reports
ALTER TABLE fai_reports 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to configuration_baselines
ALTER TABLE configuration_baselines 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to nadcap_evidence
ALTER TABLE nadcap_evidence 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- ============================================================================
-- STEP 2: Create indexes for tenant filtering
-- ============================================================================

-- Index for FAI reports tenant filtering
CREATE INDEX idx_fai_tenant ON fai_reports(tenant_id);
CREATE INDEX idx_fai_tenant_date ON fai_reports(tenant_id, inspection_date DESC);
CREATE INDEX idx_fai_tenant_customer ON fai_reports(tenant_id, customer_name);

-- Index for configuration baselines tenant filtering
CREATE INDEX idx_baseline_tenant ON configuration_baselines(tenant_id);
CREATE INDEX idx_baseline_tenant_assembly ON configuration_baselines(tenant_id, assembly_id);

-- Index for NADCAP evidence tenant filtering
CREATE INDEX idx_nadcap_tenant ON nadcap_evidence(tenant_id);
CREATE INDEX idx_nadcap_tenant_part ON nadcap_evidence(tenant_id, part_number);

-- ============================================================================
-- STEP 3: Add documentation comments
-- ============================================================================

COMMENT ON COLUMN fai_reports.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for FAI reports.';

COMMENT ON COLUMN configuration_baselines.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for configuration baselines.';

COMMENT ON COLUMN nadcap_evidence.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for NADCAP special process evidence.';

-- ============================================================================
-- STEP 4: Add database-level comment
-- ============================================================================

COMMENT ON DATABASE aerospace_db IS 
  'Aerospace vertical database for FAI reports, configuration baselines, and NADCAP evidence. Tenant isolation added in V002.';

-- ============================================================================
-- VERIFICATION QUERIES (for manual testing)
-- ============================================================================

-- Verify tenant_id columns exist:
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name IN ('fai_reports', 'configuration_baselines', 'nadcap_evidence')
-- AND column_name = 'tenant_id';

-- Verify indexes created:
-- SELECT indexname, tablename FROM pg_indexes 
-- WHERE tablename IN ('fai_reports', 'configuration_baselines', 'nadcap_evidence')
-- AND indexname LIKE '%tenant%';
