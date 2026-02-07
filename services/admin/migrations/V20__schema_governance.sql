-- =============================================================================
-- V20: Schema Governance Infrastructure
-- =============================================================================
-- Implements self-enforcing schema versioning and immutability triggers
-- per SCHEMA_CHANGE_POLICY.md
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Schema Migrations Table (Self-Registering)
-- Every migration must insert its metadata here within the same transaction
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL UNIQUE,
    checksum VARCHAR(64) NOT NULL,           -- SHA-256 of migration file
    git_sha VARCHAR(40),                      -- Git commit SHA
    description TEXT,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by VARCHAR(100) DEFAULT current_user,
    execution_time_ms INTEGER,
    success BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_schema_migrations_version ON schema_migrations(version);
CREATE INDEX idx_schema_migrations_applied ON schema_migrations(applied_at);

-- Register this migration
INSERT INTO schema_migrations (version, checksum, description)
VALUES ('V20', 'self-registering', 'Schema governance infrastructure');

-- -----------------------------------------------------------------------------
-- 2. Immutability Trigger Function
-- Prevents UPDATE and DELETE on compliance-relevant tables
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'UPDATE not allowed on immutable table %. Corrections must create new versions with supersedes_id reference.', TG_TABLE_NAME;
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'DELETE not allowed on immutable table %. Data must be archived, not destroyed.', TG_TABLE_NAME;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- 3. Apply Immutability Triggers to Compliance Tables
-- -----------------------------------------------------------------------------

-- Rule Evaluations (verdicts)
DROP TRIGGER IF EXISTS trg_rule_evaluations_immutable ON pcos_rule_evaluations;
CREATE TRIGGER trg_rule_evaluations_immutable
    BEFORE UPDATE OR DELETE ON pcos_rule_evaluations
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

-- Extracted Facts
DROP TRIGGER IF EXISTS trg_extracted_facts_immutable ON pcos_extracted_facts;
CREATE TRIGGER trg_extracted_facts_immutable
    BEFORE UPDATE OR DELETE ON pcos_extracted_facts
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

-- Fact Citations
DROP TRIGGER IF EXISTS trg_fact_citations_immutable ON pcos_fact_citations;
CREATE TRIGGER trg_fact_citations_immutable
    BEFORE UPDATE OR DELETE ON pcos_fact_citations
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

-- Compliance Snapshots
DROP TRIGGER IF EXISTS trg_compliance_snapshots_immutable ON pcos_compliance_snapshots;
CREATE TRIGGER trg_compliance_snapshots_immutable
    BEFORE UPDATE OR DELETE ON pcos_compliance_snapshots
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

-- Audit Events (already immutable by design, but enforce it)
DROP TRIGGER IF EXISTS trg_audit_events_immutable ON pcos_audit_events;
CREATE TRIGGER trg_audit_events_immutable
    BEFORE UPDATE OR DELETE ON pcos_audit_events
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

-- -----------------------------------------------------------------------------
-- 4. Analysis Run Table (Every Analysis Has a Run)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pcos_analysis_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Run identification
    run_type VARCHAR(50) NOT NULL,            -- 'compliance_check', 'rate_validation', 'classification'
    run_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed'
    
    -- What was analyzed
    project_id UUID REFERENCES pcos_projects(id),
    entity_type VARCHAR(50),                  -- 'project', 'engagement', 'budget'
    entity_id UUID,
    
    -- Run context (immutable snapshot of parameters)
    run_parameters JSONB NOT NULL DEFAULT '{}',
    rule_pack_version VARCHAR(50),
    fact_snapshot_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- Facts resolved as of this time
    
    -- Results
    total_evaluations INTEGER DEFAULT 0,
    pass_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    indeterminate_count INTEGER DEFAULT 0,
    
    -- Execution metadata
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    execution_time_ms INTEGER,
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analysis_runs_tenant ON pcos_analysis_runs(tenant_id);
CREATE INDEX idx_analysis_runs_project ON pcos_analysis_runs(project_id);
CREATE INDEX idx_analysis_runs_status ON pcos_analysis_runs(run_status);
CREATE INDEX idx_analysis_runs_created ON pcos_analysis_runs(created_at);

-- Analysis runs are also immutable once completed
CREATE OR REPLACE FUNCTION prevent_analysis_run_mutation()
RETURNS TRIGGER AS $$
BEGIN
    -- Allow status updates only while pending/running
    IF OLD.run_status IN ('completed', 'failed') THEN
        RAISE EXCEPTION 'Cannot modify completed analysis run. Create a new run instead.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_analysis_runs_immutable ON pcos_analysis_runs;
CREATE TRIGGER trg_analysis_runs_immutable
    BEFORE UPDATE ON pcos_analysis_runs
    FOR EACH ROW EXECUTE FUNCTION prevent_analysis_run_mutation();

-- -----------------------------------------------------------------------------
-- 5. Add Analysis Run Reference to Rule Evaluations
-- Links every verdict to its parent analysis run
-- -----------------------------------------------------------------------------
ALTER TABLE pcos_rule_evaluations 
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES pcos_analysis_runs(id);

CREATE INDEX IF NOT EXISTS idx_rule_evaluations_run ON pcos_rule_evaluations(analysis_run_id);

-- -----------------------------------------------------------------------------
-- 6. Verdict Completeness Check Function
-- Used by application to validate verdicts before insert
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION validate_verdict_completeness(
    p_rule_version_id UUID,
    p_fact_version_ids UUID[],
    p_authority_ids UUID[]
) RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
    v_missing TEXT[];
BEGIN
    v_missing := ARRAY[]::TEXT[];
    
    IF p_rule_version_id IS NULL THEN
        v_missing := array_append(v_missing, 'rule_version_id');
    END IF;
    
    IF p_fact_version_ids IS NULL OR array_length(p_fact_version_ids, 1) IS NULL THEN
        v_missing := array_append(v_missing, 'fact_version_ids');
    END IF;
    
    IF p_authority_ids IS NULL OR array_length(p_authority_ids, 1) IS NULL THEN
        v_missing := array_append(v_missing, 'authority_ids');
    END IF;
    
    IF array_length(v_missing, 1) > 0 THEN
        RETURN jsonb_build_object(
            'valid', FALSE,
            'verdict', 'INDETERMINATE',
            'missing', to_jsonb(v_missing),
            'reason', 'Missing required provenance: ' || array_to_string(v_missing, ', ')
        );
    END IF;
    
    RETURN jsonb_build_object('valid', TRUE);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- -----------------------------------------------------------------------------
-- 7. RLS Policy for Analysis Runs
-- -----------------------------------------------------------------------------
ALTER TABLE pcos_analysis_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY pcos_analysis_runs_tenant_isolation ON pcos_analysis_runs
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- -----------------------------------------------------------------------------
-- 8. Schema Version View (Quick Status Check)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW schema_status AS
SELECT 
    version,
    description,
    applied_at,
    success,
    (SELECT COUNT(*) FROM pcos_analysis_runs WHERE run_status = 'running') AS active_runs,
    (SELECT MAX(applied_at) FROM schema_migrations) AS last_migration
FROM schema_migrations
ORDER BY applied_at DESC
LIMIT 10;
