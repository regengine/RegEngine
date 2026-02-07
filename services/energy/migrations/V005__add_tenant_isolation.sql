-- Migration V005: Add tenant isolation to Energy service
-- Priority: P1 - High
-- Date: 2026-01-31
--
-- Adds tenant_id columns to all Energy service tables for multi-tenant isolation

-- ============================================================================
-- Add tenant_id to compliance_snapshots
-- ============================================================================

-- PRE-MIGRATION FIX: Ensure V001 columns exist (Remediation for Schema Drift)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'compliance_snapshots' AND column_name = 'substation_id') THEN
        ALTER TABLE compliance_snapshots 
        ADD COLUMN substation_id VARCHAR(255) NOT NULL DEFAULT 'UNKNOWN-SUBSTATION';
        
        RAISE NOTICE 'Fixed Schema Drift: Added missing substation_id column to compliance_snapshots';
    END IF;
END $$;

ALTER TABLE compliance_snapshots 
ADD COLUMN IF NOT EXISTS tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'::UUID;

CREATE INDEX IF NOT EXISTS idx_snapshots_tenant 
  ON compliance_snapshots(tenant_id);

-- Composite index for common query pattern
CREATE INDEX IF NOT EXISTS idx_snapshots_tenant_substation_time 
  ON compliance_snapshots(tenant_id, substation_id, snapshot_time DESC);

COMMENT ON COLUMN compliance_snapshots.tenant_id IS 
  'Tenant isolation - all snapshots belong to a specific tenant';

-- ============================================================================
-- Add tenant_id to mismatches
-- ============================================================================

ALTER TABLE mismatches 
ADD COLUMN IF NOT EXISTS tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'::UUID;

CREATE INDEX IF NOT EXISTS idx_mismatches_tenant 
  ON mismatches(tenant_id);

-- Composite index for active mismatches by tenant
CREATE INDEX IF NOT EXISTS idx_mismatches_tenant_status 
  ON mismatches(tenant_id, status) 
  WHERE status IN ('OPEN', 'UNDER_REVIEW');

COMMENT ON COLUMN mismatches.tenant_id IS 
  'Tenant isolation - all mismatches belong to a specific tenant';

-- ============================================================================
-- Add tenant_id to attestations
-- ============================================================================

ALTER TABLE attestations 
ADD COLUMN IF NOT EXISTS tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'::UUID;

CREATE INDEX IF NOT EXISTS idx_attestations_tenant 
  ON attestations(tenant_id);

COMMENT ON COLUMN attestations.tenant_id IS 
  'Tenant isolation - all attestations belong to a specific tenant';

-- ============================================================================
-- Add tenant_id to idempotency_keys (if exists)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' AND table_name = 'idempotency_keys') THEN
        
        ALTER TABLE idempotency_keys 
        ADD COLUMN IF NOT EXISTS tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'::UUID;
        
        CREATE INDEX IF NOT EXISTS idx_idempotency_tenant 
          ON idempotency_keys(tenant_id);
          
        COMMENT ON COLUMN idempotency_keys.tenant_id IS 
          'Tenant isolation - idempotency keys are tenant-scoped';
    END IF;
END $$;

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
DECLARE
    snapshot_count INTEGER;
    mismatch_count INTEGER;
    attestation_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO snapshot_count FROM information_schema.columns 
    WHERE table_name = 'compliance_snapshots' AND column_name = 'tenant_id';
    
    SELECT COUNT(*) INTO mismatch_count FROM information_schema.columns 
    WHERE table_name = 'mismatches' AND column_name = 'tenant_id';
    
    SELECT COUNT(*) INTO attestation_count FROM information_schema.columns 
    WHERE table_name = 'attestations' AND column_name = 'tenant_id';
    
    IF snapshot_count = 1 AND mismatch_count = 1 AND attestation_count = 1 THEN
        RAISE NOTICE 'V005 Migration Complete: tenant_id added to all Energy tables';
        RAISE NOTICE 'Tables updated: compliance_snapshots, mismatches, attestations, idempotency_keys';
        RAISE NOTICE 'Indexes created for efficient tenant-scoped queries';
    ELSE
        RAISE WARNING 'V005 Migration incomplete - some columns missing';
    END IF;
END $$;
