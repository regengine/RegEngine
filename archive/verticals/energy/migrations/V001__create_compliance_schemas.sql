-- Energy Vertical: Compliance Infrastructure Schema
-- Version: V001
-- Purpose: Create immutable compliance snapshot system for NERC CIP-013
-- Author: Platform Team
-- Date: 2026-01-25

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ========================================
-- Custom Types
-- ========================================

CREATE TYPE snapshot_trigger_event AS ENUM (
    'ASSET_VERIFICATION_CHANGE',
    'MISMATCH_CREATED',
    'MISMATCH_RESOLVED',
    'ESP_TOPOLOGY_CHANGE',
    'PATCH_VELOCITY_BREACH',
    'SCHEDULED_DAILY',
    'USER_MANUAL_REQUEST',
    'INITIAL_BASELINE'
);

CREATE TYPE system_status_enum AS ENUM (
    'NOMINAL',
    'DEGRADED',
    'NON_COMPLIANT'
);

CREATE TYPE mismatch_type_enum AS ENUM (
    'FIRMWARE_HASH_MISMATCH',
    'VERSION_DRIFT',
    'UNAUTHORIZED_CHANGE',
    'MISSING_VERIFICATION'
);

CREATE TYPE severity_enum AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

CREATE TYPE mismatch_status_enum AS ENUM (
    'OPEN',
    'UNDER_REVIEW',
    'RESOLVED',
    'RISK_ACCEPTED'
);

CREATE TYPE resolution_type_enum AS ENUM (
    'VENDOR_APPROVED_PATCH',
    'EMERGENCY_OVERRIDE',
    'RISK_ACCEPTED',
    'FALSE_POSITIVE'
);

CREATE TYPE snapshot_generator_enum AS ENUM (
    'SYSTEM_AUTO',
    'USER_MANUAL',
    'SCHEDULED'
);

-- ========================================
-- Core Tables
-- ========================================

-- 1. ComplianceSnapshot (Immutable Audit Trail)
CREATE TABLE compliance_snapshots (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Temporal
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    snapshot_time TIMESTAMPTZ NOT NULL,
    
    -- Scope
    substation_id VARCHAR(255) NOT NULL,
    facility_name VARCHAR(500) NOT NULL,
    
    -- System State
    system_status system_status_enum NOT NULL,
    
    -- Denormalized State (JSONB for immutability)
    asset_states JSONB NOT NULL,
    esp_config JSONB NOT NULL,
    patch_metrics JSONB NOT NULL,
    active_mismatches JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Generation Metadata
    generated_by snapshot_generator_enum NOT NULL,
    trigger_event snapshot_trigger_event,
    generator_user_id UUID,
    
    -- Integrity
    content_hash VARCHAR(64) NOT NULL,
    previous_snapshot_id UUID REFERENCES compliance_snapshots(id),
    
    -- Compliance References
    regulatory_version VARCHAR(50) DEFAULT 'CIP-013-1',
    
    -- Constraints
    CONSTRAINT valid_hash_length CHECK (length(content_hash) = 64),
    CONSTRAINT manual_requires_user CHECK (
        (generated_by = 'USER_MANUAL' AND generator_user_id IS NOT NULL) OR
        (generated_by != 'USER_MANUAL')
    )
);

-- 2. Mismatch (First-Class Risk Object)
CREATE TABLE mismatches (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Discovery
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detection_snapshot_id UUID NOT NULL REFERENCES compliance_snapshots(id),
    
    -- Asset Context
    asset_id VARCHAR(255) NOT NULL,
    asset_name VARCHAR(500) NOT NULL,
    vendor VARCHAR(255),
    
    -- Integrity Violation
    mismatch_type mismatch_type_enum NOT NULL,
    
    -- State Deltas
    hash_expected VARCHAR(64),
    hash_actual VARCHAR(64),
    version_expected VARCHAR(100),
    version_actual VARCHAR(100),
    last_known_good_snapshot_id UUID REFERENCES compliance_snapshots(id),
    
    -- Risk Assessment
    severity severity_enum NOT NULL,
    
    -- Regulatory Mapping
    regulatory_refs JSONB DEFAULT '[]'::jsonb,
    
    -- Resolution State
    status mismatch_status_enum NOT NULL DEFAULT 'OPEN',
    resolved_at TIMESTAMPTZ,
    resolution_snapshot_id UUID REFERENCES compliance_snapshots(id),
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT resolved_requires_timestamp CHECK (
        (status IN ('RESOLVED', 'RISK_ACCEPTED') AND resolved_at IS NOT NULL) OR
        (status IN ('OPEN', 'UNDER_REVIEW') AND resolved_at IS NULL)
    ),
    CONSTRAINT resolved_requires_snapshot CHECK (
        (status IN ('RESOLVED', 'RISK_ACCEPTED') AND resolution_snapshot_id IS NOT NULL) OR
        (status IN ('OPEN', 'UNDER_REVIEW'))
    )
);

-- 3. Attestation (Human Accountability)
CREATE TABLE attestations (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Linkage (REQUIRED)
    mismatch_id UUID NOT NULL REFERENCES mismatches(id),
    
    -- Accountability
    attestor_user_id UUID NOT NULL,
    attestor_name VARCHAR(500) NOT NULL,
    attestor_role VARCHAR(100),
    
    -- Resolution Classification
    resolution_type resolution_type_enum NOT NULL,
    
    -- Justification (REQUIRED, minimum 50 chars)
    justification TEXT NOT NULL CHECK (length(justification) >= 50),
    
    -- Supporting Evidence
    evidence_urls JSONB DEFAULT '[]'::jsonb,
    
    -- Cryptographic Integrity
    signed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    signature_fingerprint VARCHAR(128),
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraint: one attestation per mismatch
    CONSTRAINT unique_mismatch_attestation UNIQUE (mismatch_id)
);

-- ========================================
-- Indexes
-- ========================================

-- ComplianceSnapshot Indexes
CREATE INDEX idx_snapshots_substation_time 
    ON compliance_snapshots(substation_id, snapshot_time DESC);

CREATE INDEX idx_snapshots_status 
    ON compliance_snapshots(system_status) 
    WHERE system_status != 'NOMINAL';

CREATE INDEX idx_snapshots_created 
    ON compliance_snapshots(created_at DESC);

CREATE INDEX idx_snapshots_asset_states 
    ON compliance_snapshots USING GIN (asset_states);

CREATE INDEX idx_snapshots_prev 
    ON compliance_snapshots(previous_snapshot_id) 
    WHERE previous_snapshot_id IS NOT NULL;

-- Mismatch Indexes
CREATE INDEX idx_mismatches_status 
    ON mismatches(status) 
    WHERE status IN ('OPEN', 'UNDER_REVIEW');

CREATE INDEX idx_mismatches_asset 
    ON mismatches(asset_id, detected_at DESC);

CREATE INDEX idx_mismatches_severity 
    ON mismatches(severity) 
    WHERE severity IN ('HIGH', 'CRITICAL');

CREATE INDEX idx_mismatches_detection_snapshot 
    ON mismatches(detection_snapshot_id);

CREATE INDEX idx_mismatches_resolution_snapshot 
    ON mismatches(resolution_snapshot_id) 
    WHERE resolution_snapshot_id IS NOT NULL;

-- Attestation Indexes
CREATE INDEX idx_attestations_mismatch 
    ON attestations(mismatch_id);

CREATE INDEX idx_attestations_user 
    ON attestations(attestor_user_id, signed_at DESC);

CREATE INDEX idx_attestations_type 
    ON attestations(resolution_type);

-- ========================================
-- Functions
-- ========================================

-- Update trigger for mismatches
CREATE OR REPLACE FUNCTION update_mismatch_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER mismatches_update_timestamp
    BEFORE UPDATE ON mismatches
    FOR EACH ROW
    EXECUTE FUNCTION update_mismatch_timestamp();

-- ========================================
-- Comments (Documentation)
-- ========================================

COMMENT ON TABLE compliance_snapshots IS 
    'Immutable point-in-time records of compliance state. NEVER UPDATE - append only.';

COMMENT ON COLUMN compliance_snapshots.content_hash IS 
    'SHA-256 hash of canonical JSON representation for cryptographic verification';

COMMENT ON TABLE mismatches IS 
    'First-class risk objects representing integrity violations requiring resolution';

COMMENT ON TABLE attestations IS 
    'Human accountability records. Required for mismatch resolution.';

COMMENT ON CONSTRAINT unique_mismatch_attestation ON attestations IS 
    'Enforces one attestation per mismatch - prevents duplicate resolutions';

-- ========================================
-- Initial Seed Data (Optional)
-- ========================================

-- Insert baseline snapshot for Substation Alpha
INSERT INTO compliance_snapshots (
    substation_id,
    facility_name,
    snapshot_time,
    system_status,
    asset_states,
    esp_config,
    patch_metrics,
    generated_by,
    trigger_event,
    content_hash
) VALUES (
    'ALPHA-001',
    'Substation Alpha',
    NOW(),
    'NOMINAL',
    '{"assets": [], "summary": {"total_assets": 0, "verified_count": 0, "mismatch_count": 0, "unknown_count": 0}}'::jsonb,
    '{"zones": [], "open_ports": []}'::jsonb,
    '{"avg_patch_time_hours": 0, "sla_classification": "GREEN", "patches_applied_30d": 0, "patches_pending": 0}'::jsonb,
    'SYSTEM_AUTO',
    'INITIAL_BASELINE',
    -- Hash will be recalculated by application
    '0000000000000000000000000000000000000000000000000000000000000000'
);
