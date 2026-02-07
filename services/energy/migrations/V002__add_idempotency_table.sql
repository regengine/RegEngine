-- Migration V002: Add Idempotency Table for Exactly-Once Snapshot Semantics
-- 
-- Critical Fix: C-1 from external audit
-- Provides database-level deduplication for snapshot creation events

CREATE TABLE snapshot_idempotency (
    -- Event fingerprint (primary key for uniqueness)
    event_fingerprint VARCHAR(64) PRIMARY KEY,
    
    -- When this event was first seen
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Snapshot created for this event (nullable until commit completes)
    snapshot_id UUID REFERENCES compliance_snapshots(id),
    
    -- Expiration for cleanup (5-minute dedup window)
    expires_at TIMESTAMPTZ NOT NULL,
    
    -- Metadata for debugging
    substation_id VARCHAR(255) NOT NULL,
    trigger_event VARCHAR(100) NOT NULL
);

-- Index for efficient expiration queries (cleanup cron)
CREATE INDEX idx_idempotency_expires 
    ON snapshot_idempotency(expires_at) 
    WHERE expires_at > NOW();

-- Index for finding by snapshot_id (reverse lookup)
CREATE INDEX idx_idempotency_snapshot 
    ON snapshot_idempotency(snapshot_id) 
    WHERE snapshot_id IS NOT NULL;

-- Comments for documentation
COMMENT ON TABLE snapshot_idempotency IS 
    'Idempotency table for exactly-once snapshot creation semantics. '
    'Records expire after 5 minutes. Cleanup via cron: DELETE WHERE expires_at < NOW()';

COMMENT ON COLUMN snapshot_idempotency.event_fingerprint IS 
    'SHA-256 hash of (substation_id + trigger_event + 5-minute timestamp window). '
    'Prevents duplicate snapshots from identical events within dedup window.';

COMMENT ON COLUMN snapshot_idempotency.snapshot_id IS 
    'Reference to created snapshot. NULL until transaction commits. '
    'Updated atomically with snapshot creation in same transaction.';
