-- Energy Service Performance Indexes
-- Version: 004
-- Description: Add indexes for common query patterns

-- Snapshots by substation and time range (most common query)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshots_substation_time
ON snapshots(substation_id, created_at DESC)
WHERE deleted_at IS NULL;

-- Snapshot lookups by chain_hash (integrity verification)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshots_chain_hash
ON snapshots(chain_hash)
WHERE deleted_at IS NULL;

-- Snapshot lookup by previous_hash (chain traversal)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshots_previous_hash
ON snapshots(previous_hash)
WHERE deleted_at IS NULL;

-- Mismatches by snapshot (detail queries)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mismatches_snapshot
ON mismatches(snapshot_id, created_at DESC)
WHERE resolved_at IS NULL;

-- Mismatches by type (analytics)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mismatches_type
ON mismatches(mismatch_type, severity)
WHERE resolved_at IS NULL;

-- Export queries by time range and substation
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshots_export
ON snapshots(created_at DESC, substation_id, facility_name)
WHERE deleted_at IS NULL;

-- Tenant-scoped queries (if multi-tenant added later)
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_snapshots_tenant
-- ON snapshots(tenant_id, created_at DESC)
-- WHERE deleted_at IS NULL;

-- Update statistics for query planner
ANALYZE snapshots;
ANALYZE mismatches;

-- Add comments for documentation
COMMENT ON INDEX idx_snapshots_substation_time IS 'Optimizes time-range queries by substation';
COMMENT ON INDEX idx_snapshots_chain_hash IS 'Supports chain integrity verification';
COMMENT ON INDEX idx_mismatches_snapshot IS 'Improves mismatch detail lookups';
