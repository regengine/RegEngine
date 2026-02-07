-- V18: Rule Provenance & Compliance Snapshots
-- Audit trail for all rule evaluations and point-in-time compliance snapshots

-- ============================================================================
-- Table: pcos_rule_evaluations
-- Purpose: Store every rule evaluation with source authority references
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_rule_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    
    -- Entity being evaluated
    entity_type VARCHAR(50) NOT NULL,  -- 'budget', 'engagement', 'location', 'project'
    entity_id UUID NOT NULL,
    
    -- Rule identification
    rule_code VARCHAR(100) NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    rule_category VARCHAR(100) NOT NULL,  -- 'rate_compliance', 'classification', 'permit', 'tax_credit'
    rule_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    
    -- Evaluation result
    result VARCHAR(30) NOT NULL,  -- 'pass', 'fail', 'warning', 'skip', 'error'
    score INTEGER,  -- 0-100 if applicable
    severity VARCHAR(20) DEFAULT 'medium',  -- 'low', 'medium', 'high', 'critical'
    
    -- Details
    evaluation_input JSONB NOT NULL DEFAULT '{}',  -- Input data used for evaluation
    evaluation_output JSONB NOT NULL DEFAULT '{}',  -- Full output/reasoning
    message TEXT,  -- Human-readable summary
    
    -- Source authority (provenance)
    source_authorities JSONB NOT NULL DEFAULT '[]',
    /*
    Example:
    [
        {"type": "statute", "code": "CA Labor Code §510", "section": "Overtime Pay"},
        {"type": "cba", "union": "IATSE Local 600", "article": "5.2", "effective_date": "2024-01-01"},
        {"type": "internal_policy", "name": "Contractor Classification Policy", "version": "2.1"}
    ]
    */
    
    -- Linked entities
    task_id UUID REFERENCES pcos_tasks(id) ON DELETE SET NULL,  -- If created a compliance task
    finding_id UUID,  -- If created a finding record
    
    -- Timing
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evaluated_by UUID REFERENCES users(id),  -- NULL if system-triggered
    
    -- Snapshot reference
    snapshot_id UUID,  -- If part of a compliance snapshot
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Table: pcos_compliance_snapshots
-- Purpose: Point-in-time compliance state for audit and comparison
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_compliance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    
    -- Snapshot identification
    snapshot_type VARCHAR(50) NOT NULL,  -- 'manual', 'pre_greenlight', 'scheduled', 'post_wrap'
    snapshot_name VARCHAR(255),
    
    -- Trigger info
    triggered_by UUID REFERENCES users(id),
    trigger_reason TEXT,
    
    -- Summary metrics
    total_rules_evaluated INTEGER NOT NULL DEFAULT 0,
    rules_passed INTEGER NOT NULL DEFAULT 0,
    rules_failed INTEGER NOT NULL DEFAULT 0,
    rules_warning INTEGER NOT NULL DEFAULT 0,
    
    overall_score INTEGER,  -- 0-100 composite score
    compliance_status VARCHAR(50) NOT NULL DEFAULT 'unknown',  -- 'compliant', 'partial', 'non_compliant', 'unknown'
    
    -- Category breakdown
    category_scores JSONB DEFAULT '{}',
    /*
    Example:
    {
        "rate_compliance": {"evaluated": 15, "passed": 14, "failed": 1, "score": 93},
        "classification": {"evaluated": 8, "passed": 8, "failed": 0, "score": 100},
        "permits": {"evaluated": 3, "passed": 2, "failed": 1, "score": 67}
    }
    */
    
    -- Delta from previous snapshot
    previous_snapshot_id UUID REFERENCES pcos_compliance_snapshots(id),
    delta_summary JSONB,
    /*
    Example:
    {
        "new_failures": 2,
        "resolved_failures": 3,
        "score_change": +5
    }
    */
    
    -- Full state snapshot
    project_state JSONB NOT NULL DEFAULT '{}',  -- Project metadata at time of snapshot
    
    -- Attestation (filled in by attestation workflow)
    is_attested BOOLEAN DEFAULT FALSE,
    attested_at TIMESTAMPTZ,
    attested_by UUID REFERENCES users(id),
    attestation_signature_id VARCHAR(255),  -- External e-sign reference
    attestation_notes TEXT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Table: pcos_audit_events
-- Purpose: Audit log for significant compliance events
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID REFERENCES pcos_projects(id) ON DELETE CASCADE,
    
    -- Event details
    event_type VARCHAR(100) NOT NULL,  -- 'gate_transition', 'attestation', 'rule_override', 'document_upload'
    event_action VARCHAR(100) NOT NULL,  -- 'created', 'updated', 'approved', 'rejected'
    
    -- Actor
    actor_id UUID REFERENCES users(id),
    actor_email VARCHAR(255),
    actor_role VARCHAR(100),
    
    -- Target entity
    entity_type VARCHAR(50),
    entity_id UUID,
    
    -- Event data
    event_data JSONB NOT NULL DEFAULT '{}',
    previous_state JSONB,
    new_state JSONB,
    
    -- Context
    ip_address VARCHAR(45),
    user_agent TEXT,
    request_id VARCHAR(100),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_rule_evals_tenant ON pcos_rule_evaluations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_project ON pcos_rule_evaluations(project_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_entity ON pcos_rule_evaluations(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_rule ON pcos_rule_evaluations(rule_code);
CREATE INDEX IF NOT EXISTS idx_rule_evals_result ON pcos_rule_evaluations(result);
CREATE INDEX IF NOT EXISTS idx_rule_evals_snapshot ON pcos_rule_evaluations(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_time ON pcos_rule_evaluations(evaluated_at);

CREATE INDEX IF NOT EXISTS idx_snapshots_tenant ON pcos_compliance_snapshots(tenant_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_project ON pcos_compliance_snapshots(project_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_type ON pcos_compliance_snapshots(snapshot_type);
CREATE INDEX IF NOT EXISTS idx_snapshots_created ON pcos_compliance_snapshots(created_at);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON pcos_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_project ON pcos_audit_events(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_type ON pcos_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON pcos_audit_events(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_time ON pcos_audit_events(created_at);

-- ============================================================================
-- Row Level Security
-- ============================================================================
ALTER TABLE pcos_rule_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_compliance_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_audit_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY rule_evals_tenant ON pcos_rule_evaluations
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY rule_evals_insert ON pcos_rule_evaluations
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY snapshots_tenant ON pcos_compliance_snapshots
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY snapshots_insert ON pcos_compliance_snapshots
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY audit_events_tenant ON pcos_audit_events
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY audit_events_insert ON pcos_audit_events
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

-- ============================================================================
-- Update trigger
-- ============================================================================
CREATE OR REPLACE FUNCTION update_snapshot_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_snapshots_updated
    BEFORE UPDATE ON pcos_compliance_snapshots
    FOR EACH ROW EXECUTE FUNCTION update_snapshot_updated_at();
