-- Finance Snapshots Table Schema
-- This migration adds dual-storage support for compliance snapshots

CREATE TABLE IF NOT EXISTS finance_snapshots (
    snapshot_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    vertical VARCHAR(50) NOT NULL DEFAULT 'finance',
    
    -- Compliance scores
    bias_score DECIMAL(5,2) DEFAULT 0,
    drift_score DECIMAL(5,2) DEFAULT 0,
    documentation_score DECIMAL(5,2) DEFAULT 0,
    regulatory_mapping_score DECIMAL(5,2) DEFAULT 0,
    obligation_coverage_percent DECIMAL(5,2) DEFAULT 0,
    total_compliance_score DECIMAL(5,2) DEFAULT 0,
    
    -- Risk assessment
    risk_level VARCHAR(20) CHECK (risk_level IN ('low', 'medium', 'high', 'critical', 'unknown')),
    num_open_violations INTEGER DEFAULT 0,
    
    -- Full snapshot data as JSONB for flexible querying
    data JSONB NOT NULL,
    
    -- Audit fields
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_finance_snapshots_tenant ON finance_snapshots(tenant_id);
CREATE INDEX IF NOT EXISTS idx_finance_snapshots_timestamp ON finance_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_finance_snapshots_risk ON finance_snapshots(risk_level);
CREATE INDEX IF NOT EXISTS idx_finance_snapshots_compliance ON finance_snapshots(total_compliance_score);

-- JSONB query index for data field
CREATE INDEX IF NOT EXISTS idx_finance_snapshots_data_gin ON finance_snapshots USING GIN (data);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_finance_snapshot_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
DROP TRIGGER IF EXISTS trigger_update_finance_snapshot_timestamp ON finance_snapshots;
CREATE TRIGGER trigger_update_finance_snapshot_timestamp
    BEFORE UPDATE ON finance_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION update_finance_snapshot_timestamp();

-- Comments for documentation
COMMENT ON TABLE finance_snapshots IS 'Dual-storage compliance snapshots for finance vertical with PostgreSQL + Neo4j persistence';
COMMENT ON COLUMN finance_snapshots.data IS 'Complete snapshot data stored as JSONB for flexible querying and audit trail';
COMMENT ON COLUMN finance_snapshots.total_compliance_score IS 'Aggregate compliance score (0-100)';
COMMENT ON COLUMN finance_snapshots.obligation_coverage_percent IS 'Percentage of regulatory obligations met (0-100)';
