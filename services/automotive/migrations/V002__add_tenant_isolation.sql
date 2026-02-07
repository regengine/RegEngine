-- Migration V002: Add Tenant Isolation to Automotive Service
-- Date: 2026-01-31
-- Purpose: Add multi-tenant support to all Automotive tables

-- ============================================================================
-- STEP 1: Add tenant_id columns
-- ============================================================================

-- Add tenant_id to ppap_submissions
ALTER TABLE ppap_submissions 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to ppap_elements
ALTER TABLE ppap_elements 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to lpa_audits
ALTER TABLE lpa_audits 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- ============================================================================
-- STEP 2: Create indexes for tenant filtering
-- ============================================================================

-- Index for PPAP submissions tenant filtering
CREATE INDEX idx_ppap_submission_tenant ON ppap_submissions(tenant_id);
CREATE INDEX idx_ppap_submission_tenant_date ON ppap_submissions(tenant_id, submission_date DESC);
CREATE INDEX idx_ppap_submission_tenant_customer ON ppap_submissions(tenant_id, oem_customer);

-- Index for PPAP elements tenant filtering
CREATE INDEX idx_ppap_element_tenant ON ppap_elements(tenant_id);
CREATE INDEX idx_ppap_element_tenant_submission ON ppap_elements(tenant_id, submission_id);

-- Index for LPA audits tenant filtering
CREATE INDEX idx_lpa_tenant ON lpa_audits(tenant_id);
CREATE INDEX idx_lpa_tenant_date ON lpa_audits(tenant_id, audit_date DESC);
CREATE INDEX idx_lpa_tenant_part ON lpa_audits(tenant_id, part_number);

-- ============================================================================
-- STEP 3: Add documentation comments
-- ============================================================================

COMMENT ON COLUMN ppap_submissions.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for PPAP submissions.';

COMMENT ON COLUMN ppap_elements.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for PPAP elements.';

COMMENT ON COLUMN lpa_audits.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for LPA audits.';

-- ============================================================================
-- STEP 4: Add database-level comment
-- ============================================================================

COMMENT ON DATABASE automotive_db IS 
  'Automotive vertical database for PPAP submissions and LPA audits. Tenant isolation added in V002.';

-- ============================================================================
-- VERIFICATION QUERIES (for manual testing)
-- ============================================================================

-- Verify tenant_id columns exist:
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name IN ('ppap_submissions', 'ppap_elements', 'lpa_audits')
-- AND column_name = 'tenant_id';

-- Verify indexes created:
-- SELECT indexname, tablename FROM pg_indexes 
-- WHERE tablename IN ('ppap_submissions', 'ppap_elements', 'lpa_audits')
-- AND indexname LIKE '%tenant%';
