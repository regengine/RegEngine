-- Migration V24: Remove Duplicate Compliance Snapshots Table
-- 
-- CONTEXT:
-- The Admin DB has a generic `compliance_snapshots` table (V6) that conflicts
-- with the Energy vertical's NERC CIP-specific `compliance_snapshots` table.
-- This causes schema confusion and bugs (e.g., snapshot_time column mismatch).
--
-- DECISION:
-- - Energy vertical owns high-frequency compliance snapshots (NERC CIP-specific)
-- - Admin DB should NOT have a compliance_snapshots table
-- - Remove to eliminate confusion and prevent future schema drift
--
-- IMPACT:
-- - Low risk: Investigation shows this table is unused in application code
-- - Fixes QA bug: Energy service expects `snapshot_time`, Admin DB had `snapshot_name`
-- - Improves: Schema clarity, vertical data ownership
--
-- Author: Platform Team
-- Date: 2026-01-30
-- Phase: Architecture Optimization - P0

-- ============================================================================
-- VERIFICATION: Check if table exists and has data
-- ============================================================================

DO $$
DECLARE
    row_count INTEGER;
BEGIN
    -- Check if table exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'compliance_snapshots' 
        AND table_schema = 'public'
    ) THEN
        -- Count rows
        SELECT COUNT(*) INTO row_count FROM compliance_snapshots;
        
        RAISE NOTICE 'compliance_snapshots table exists with % rows', row_count;
        
        -- Safety check: If table has data, log warning
        IF row_count > 0 THEN
            RAISE WARNING 'compliance_snapshots table has % rows. Proceeding with drop as per architecture decision.', row_count;
            
            -- Optional: Create backup table for safety
            CREATE TABLE IF NOT EXISTS compliance_snapshots_backup_v24 AS 
            SELECT * FROM compliance_snapshots;
            
            RAISE NOTICE 'Created backup: compliance_snapshots_backup_v24';
        END IF;
    ELSE
        RAISE NOTICE 'compliance_snapshots table does not exist. No action needed.';
    END IF;
END $$;

-- ============================================================================
-- DROP TABLE: compliance_snapshots
-- ============================================================================

-- Drop dependent indexes first (created in V6)
DROP INDEX IF EXISTS idx_snapshots_tenant_time;
DROP INDEX IF EXISTS idx_snapshots_hash;
DROP INDEX IF EXISTS idx_snapshots_status;

-- Drop the table
DROP TABLE IF EXISTS compliance_snapshots CASCADE;

-- ============================================================================
-- DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE compliance_snapshots_backup_v24 IS 
    'Backup of compliance_snapshots table before removal in V24. This table was determined to be unused and conflicted with Energy vertical schema. Retained for 90 days as safety measure. Review and drop after 2026-04-30.';

-- ============================================================================
-- VERIFICATION QUERY (for manual testing)
-- ============================================================================

-- After migration, verify table is gone:
-- SELECT table_name FROM information_schema.tables 
-- WHERE table_name = 'compliance_snapshots';
-- Expected: 0 rows

-- Verify Energy DB still has its table:
-- \c energy_db
-- \d compliance_snapshots
-- Expected: Table exists with substation_id, snapshot_time, etc.
