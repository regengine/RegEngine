-- Phase 0: Immutability Enforcement
-- Migration: V003__immutability_enforcement.sql
-- 
-- Purpose: Enforce snapshot immutability at database layer
--          Add missing signature_hash column
--          Prevent chain forks
--          Detect clock regression
--
-- CIP-013 Mapping: R1.1 (Integrity), R1.2 (Traceability & Ordering)

-- =============================================================================
-- Part 0: Add Missing Column (if not exists from Phase 1A)
-- =============================================================================

-- Add signature_hash column (needed for immutability seal verification)
ALTER TABLE compliance_snapshots 
ADD COLUMN IF NOT EXISTS signature_hash VARCHAR(64);

COMMENT ON COLUMN compliance_snapshots.signature_hash IS 
'SHA-256 hash of (snapshot_id + content_hash). Cryptographically binds identity to content. Set transaction-locally during snapshot creation seal.';

-- =============================================================================
-- Part 1: Immutability Enforcement
-- =============================================================================

-- Prevent all UPDATEs except signature_hash on fresh snapshots (transaction-local)
CREATE OR REPLACE FUNCTION prevent_snapshot_mutation()
RETURNS TRIGGER AS $$
BEGIN
    -- Allow signature_hash update ONLY if currently NULL (transaction-local seal)
    IF OLD.signature_hash IS NULL AND NEW.signature_hash IS NOT NULL THEN
        -- Verify ONLY signature_hash changed
        IF OLD.id = NEW.id AND 
           OLD.created_at = NEW.created_at AND
           OLD.snapshot_time = NEW.snapshot_time AND
           OLD.substation_id = NEW.substation_id AND
           OLD.facility_name = NEW.facility_name AND
           OLD.system_status = NEW.system_status AND
           OLD.content_hash = NEW.content_hash AND
           COALESCE(OLD.previous_snapshot_id::text, '') = COALESCE(NEW.previous_snapshot_id::text, '') AND
           OLD.generated_by = NEW.generated_by THEN
            RETURN NEW;
        END IF;
    END IF;
    
    -- Reject all other updates
    RAISE EXCEPTION 'IMMUTABILITY_VIOLATION: Snapshots are immutable after creation (CIP-013 requirement). Snapshot ID: %', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER enforce_snapshot_immutability
BEFORE UPDATE ON compliance_snapshots
FOR EACH ROW
EXECUTE FUNCTION prevent_snapshot_mutation();

COMMENT ON TRIGGER enforce_snapshot_immutability ON compliance_snapshots IS 
'Enforces immutability: allows only signature_hash update during transaction-local sealing. All other modifications raise IMMUTABILITY_VIOLATION.';

-- =============================================================================
-- Part 2: Deletion Prevention
-- =============================================================================

CREATE OR REPLACE FUNCTION prevent_snapshot_deletion()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'DELETION_VIOLATION: Snapshots cannot be deleted (CIP-013 retention requirement). Snapshot ID: %, Substation: %', 
        OLD.id, OLD.substation_id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER enforce_snapshot_retention
BEFORE DELETE ON compliance_snapshots
FOR EACH ROW
EXECUTE FUNCTION prevent_snapshot_deletion();

COMMENT ON TRIGGER enforce_snapshot_retention ON compliance_snapshots IS 
'Prevents deletion: snapshots are compliance evidence and must be retained per regulatory requirements.';

-- =============================================================================
-- Part 3: Chain Linearity Enforcement
-- =============================================================================

-- Prevent chain forks: one successor per snapshot per substation
CREATE UNIQUE INDEX idx_chain_linearity
ON compliance_snapshots(substation_id, previous_snapshot_id)
WHERE previous_snapshot_id IS NOT NULL;

COMMENT ON INDEX idx_chain_linearity IS 
'Enforces chain linearity: prevents multiple snapshots claiming the same previous_snapshot_id for a given substation. Ensures single, linear compliance history.';

-- =============================================================================
-- Part 4: Clock Regression Detection (Non-Blocking)
-- =============================================================================

CREATE OR REPLACE FUNCTION validate_time_progression()
RETURNS TRIGGER AS $$
DECLARE
    prev_time TIMESTAMPTZ;
BEGIN
    IF NEW.previous_snapshot_id IS NOT NULL THEN
        SELECT snapshot_time INTO prev_time
        FROM compliance_snapshots
        WHERE id = NEW.previous_snapshot_id;
        
        IF NEW.snapshot_time < prev_time THEN
            -- Log warning but allow (chain authority takes precedence over timestamps)
            RAISE WARNING 'CLOCK_REGRESSION: Snapshot time moved backwards: % < % (Snapshot: %, Previous: %). Chain linkage remains authoritative.',
                NEW.snapshot_time, prev_time, NEW.id, NEW.previous_snapshot_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_temporal_progression
BEFORE INSERT ON compliance_snapshots
FOR EACH ROW
EXECUTE FUNCTION validate_time_progression();

COMMENT ON TRIGGER validate_temporal_progression ON compliance_snapshots IS 
'Detects clock regression (time moving backwards) and logs warning. Does not block insert - chain linkage is authoritative for ordering, not timestamps.';

-- =============================================================================
-- Verification Queries (For Testing)
-- =============================================================================

-- Test immutability enforcement:
-- UPDATE compliance_snapshots SET system_status = 'NOMINAL' WHERE id = (SELECT id FROM compliance_snapshots LIMIT 1);
-- Expected: ERROR - IMMUTABILITY_VIOLATION

-- Test deletion prevention:
-- DELETE FROM compliance_snapshots WHERE id = (SELECT id FROM compliance_snapshots LIMIT 1);
-- Expected: ERROR - DELETION_VIOLATION

-- Test chain fork prevention:
-- Attempt to create two snapshots with same previous_snapshot_id for same substation
-- Expected: Second insert fails with unique constraint violation on idx_chain_linearity
