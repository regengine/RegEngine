-- V6: Compliance Snapshots
-- Point-in-time compliance state capture for audit defense

CREATE TABLE IF NOT EXISTS compliance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    
    -- Snapshot metadata
    snapshot_name VARCHAR(255) NOT NULL,
    snapshot_reason TEXT,
    created_by VARCHAR(255) NOT NULL,
    
    -- Point-in-time state capture
    compliance_status VARCHAR(50) NOT NULL,
    active_alert_count INTEGER NOT NULL DEFAULT 0,
    critical_alert_count INTEGER NOT NULL DEFAULT 0,
    completeness_score FLOAT DEFAULT 1.0,
    
    -- Full state (JSONB for complete capture)
    alerts_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    status_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Cryptographic integrity
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256 hex
    hash_algorithm VARCHAR(20) NOT NULL DEFAULT 'SHA-256',
    
    -- Verification
    is_verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMPTZ,
    verified_by VARCHAR(255),
    
    -- Timestamps
    captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_snapshots_tenant_time 
    ON compliance_snapshots(tenant_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_snapshots_hash 
    ON compliance_snapshots(content_hash);

CREATE INDEX IF NOT EXISTS idx_snapshots_status 
    ON compliance_snapshots(tenant_id, compliance_status);

-- Comment for documentation
COMMENT ON TABLE compliance_snapshots IS 
    'Immutable point-in-time compliance state captures for audit defense. Hash ensures data integrity.';

COMMENT ON COLUMN compliance_snapshots.content_hash IS 
    'SHA-256 hash of (status_snapshot + alerts_snapshot + profile_snapshot) for tamper detection';
