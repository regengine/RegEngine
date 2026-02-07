-- Migration V002: Add Tenant Isolation to Construction Service
-- Date: 2026-01-31
-- Purpose: Add multi-tenant support to all Construction tables

-- ============================================================================
-- STEP 1: Add tenant_id columns
-- ============================================================================

-- Add tenant_id to bim_change_records
ALTER TABLE bim_change_records 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to osha_safety_inspections
ALTER TABLE osha_safety_inspections 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- ============================================================================
-- STEP 2: Create indexes for tenant filtering
-- ============================================================================

-- Index for BIM change records tenant filtering
CREATE INDEX idx_bim_tenant ON bim_change_records(tenant_id);
CREATE INDEX idx_bim_tenant_project ON bim_change_records(tenant_id, project_id);
CREATE INDEX idx_bim_tenant_date ON bim_change_records(tenant_id, submission_date DESC);

-- Index for OSHA inspections tenant filtering
CREATE INDEX idx_osha_tenant ON osha_safety_inspections(tenant_id);
CREATE INDEX idx_osha_tenant_project ON osha_safety_inspections(tenant_id, project_id);
CREATE INDEX idx_osha_tenant_date ON osha_safety_inspections(tenant_id, inspection_date DESC);

-- ============================================================================
-- STEP 3: Add documentation comments
-- ============================================================================

COMMENT ON COLUMN bim_change_records.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for BIM change records.';

COMMENT ON COLUMN osha_safety_inspections.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for OSHA safety inspections.';

-- ============================================================================
-- STEP 4: Add database-level comment
-- ============================================================================

COMMENT ON DATABASE construction_db IS 
  'Construction vertical database for BIM change records and OSHA safety inspections. Tenant isolation added in V002.';

-- ============================================================================
-- VERIFICATION QUERIES (for manual testing)
-- ============================================================================

-- Verify tenant_id columns exist:
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name IN ('bim_change_records', 'osha_safety_inspections')
-- AND column_name = 'tenant_id';

-- Verify indexes created:
-- SELECT indexname, tablename FROM pg_indexes 
-- WHERE tablename IN ('bim_change_records', 'osha_safety_inspections')
-- AND indexname LIKE '%tenant%';
