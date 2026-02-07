-- Migration V002: Add Tenant Isolation to Manufacturing Service
-- Date: 2026-01-31
-- Purpose: Add multi-tenant support to all Manufacturing tables

-- ============================================================================
-- STEP 1: Add tenant_id columns
-- ============================================================================

-- Add tenant_id to non_conformance_reports
ALTER TABLE non_conformance_reports 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to corrective_actions
ALTER TABLE corrective_actions 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to supplier_quality_issues
ALTER TABLE supplier_quality_issues 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- Add tenant_id to audit_findings
ALTER TABLE audit_findings 
  ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

-- ============================================================================
-- STEP 2: Create indexes for tenant filtering
-- ============================================================================

-- Index for NCR tenant filtering
CREATE INDEX idx_ncr_tenant ON non_conformance_reports(tenant_id);
CREATE INDEX idx_ncr_tenant_date ON non_conformance_reports(tenant_id, detected_date DESC);
CREATE INDEX idx_ncr_tenant_status ON non_conformance_reports(tenant_id, status);
CREATE INDEX idx_ncr_tenant_severity ON non_conformance_reports(tenant_id, severity);

-- Index for CAPA tenant filtering
CREATE INDEX idx_capa_tenant ON corrective_actions(tenant_id);
CREATE INDEX idx_capa_tenant_ncr ON corrective_actions(tenant_id, ncr_id);
CREATE INDEX idx_capa_tenant_assigned ON corrective_actions(tenant_id, assigned_to);

-- Index for supplier quality issues tenant filtering
CREATE INDEX idx_supplier_tenant ON supplier_quality_issues(tenant_id);
CREATE INDEX idx_supplier_tenant_name ON supplier_quality_issues(tenant_id, supplier_name);
CREATE INDEX idx_supplier_tenant_status ON supplier_quality_issues(tenant_id, status);

-- Index for audit findings tenant filtering
CREATE INDEX idx_audit_tenant ON audit_findings(tenant_id);
CREATE INDEX idx_audit_tenant_type ON audit_findings(tenant_id, audit_type);
CREATE INDEX idx_audit_tenant_status ON audit_findings(tenant_id, status);

-- ============================================================================
-- STEP 3: Add documentation comments
-- ============================================================================

COMMENT ON COLUMN non_conformance_reports.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for NCRs.';

COMMENT ON COLUMN corrective_actions.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for CAPAs.';

COMMENT ON COLUMN supplier_quality_issues.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for supplier quality tracking.';

COMMENT ON COLUMN audit_findings.tenant_id IS 
  'Links to admin.tenants (logical FK, not enforced due to cross-database reference). Enables multi-tenant isolation for audit findings.';

-- ============================================================================
-- STEP 4: Add database-level comment
-- ============================================================================

COMMENT ON DATABASE manufacturing_db IS 
  'Manufacturing vertical database for NCRs, CAPAs, supplier quality, and audit findings. Tenant isolation added in V002.';

-- ============================================================================
-- VERIFICATION QUERIES (for manual testing)
-- ============================================================================

-- Verify tenant_id columns exist:
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name IN ('non_conformance_reports', 'corrective_actions', 'supplier_quality_issues', 'audit_findings')
-- AND column_name = 'tenant_id';

-- Verify indexes created:
-- SELECT indexname, tablename FROM pg_indexes 
-- WHERE tablename IN ('non_conformance_reports', 'corrective_actions', 'supplier_quality_issues', 'audit_findings')
-- AND indexname LIKE '%tenant%';
