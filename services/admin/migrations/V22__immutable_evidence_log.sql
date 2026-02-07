-- Migration V22: Immutable Evidence Log
-- Enforces Constitution Section 2.1: Evidence must be Append-Only.

-- 1. Create the Evidence Log Table
CREATE TABLE evidence_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Linkage
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    project_id UUID NOT NULL REFERENCES vertical_projects(id),
    rule_id VARCHAR(100) NOT NULL, -- e.g. 'GOV-01'
    
    -- Content
    evidence_type VARCHAR(50) NOT NULL, -- 'document', 'log', 'attestation'
    data JSONB NOT NULL DEFAULT '{}'::jsonb, -- The actual evidence payload (metadata only, NO PHI)
    hash VARCHAR(64) NOT NULL, -- SHA-256 integrity hash
    
    -- Provenance
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for retrieval
CREATE INDEX idx_evidence_log_project_rule ON evidence_log(project_id, rule_id);
CREATE INDEX idx_evidence_log_created_at ON evidence_log(created_at);

-- 2. Create Immutability Trigger Function
CREATE OR REPLACE FUNCTION enforce_evidence_immutability()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'UPDATE') THEN
        RAISE EXCEPTION 'Constitution Violation: Evidence is Append-Only. Updates forbidden.';
    ELSIF (TG_OP = 'DELETE') THEN
        RAISE EXCEPTION 'Constitution Violation: Evidence is Append-Only. Deletions forbidden.';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 3. Bind Trigger to Table
-- This ensures that even a database admin user would need to disable the trigger to modify records.
CREATE TRIGGER trg_evidence_immutable
BEFORE UPDATE OR DELETE ON evidence_log
FOR EACH ROW
EXECUTE FUNCTION enforce_evidence_immutability();

-- 4. Comment for schema documentation
COMMENT ON TABLE evidence_log IS 'Constitution 2.1: Immutable Ledger. Updates and Deletes are strictly forbidden by trigger.';
