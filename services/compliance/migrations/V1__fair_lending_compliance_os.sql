-- RegEngine Fair Lending Compliance OS
-- Phase-oriented schema for regulatory intelligence, model governance,
-- analysis evidence, and knowledge graph backbone.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS regulations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_name TEXT NOT NULL,
    citation TEXT NOT NULL,
    section TEXT NOT NULL,
    text TEXT NOT NULL,
    effective_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS obligations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    regulation_id UUID NOT NULL REFERENCES regulations(id) ON DELETE CASCADE,
    obligation_text TEXT NOT NULL,
    risk_category TEXT NOT NULL CHECK (risk_category IN ('disparate_impact', 'disparate_treatment', 'documentation')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS controls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    obligation_id UUID NOT NULL REFERENCES obligations(id) ON DELETE CASCADE,
    control_name TEXT NOT NULL,
    control_type TEXT NOT NULL CHECK (control_type IN ('statistical_test', 'documentation', 'monitoring')),
    frequency TEXT NOT NULL CHECK (frequency IN ('real_time', 'monthly', 'quarterly')),
    threshold_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    control_id UUID NOT NULL REFERENCES controls(id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    methodology TEXT NOT NULL CHECK (methodology IN ('DIR', 'regression', 'KS_test', 'feature_importance')),
    metric_definition TEXT NOT NULL,
    failure_threshold TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    external_model_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    owner TEXT NOT NULL,
    deployment_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'deprecated')),
    deployment_locked BOOLEAN NOT NULL DEFAULT FALSE,
    lock_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, external_model_id)
);

CREATE TABLE IF NOT EXISTS validations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    model_id UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    validation_type TEXT NOT NULL CHECK (validation_type IN ('fairness', 'performance', 'conceptual_soundness')),
    validator TEXT NOT NULL,
    date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    model_id UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL CHECK (change_type IN ('feature_added', 'threshold_change', 'retrain')),
    description TEXT NOT NULL,
    date DATE NOT NULL,
    requires_revalidation BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_compliance_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    model_id UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    protected_attribute TEXT NOT NULL,
    min_dir NUMERIC(6,4) NOT NULL,
    dir_results JSONB NOT NULL,
    regression_result JSONB,
    drift_results JSONB,
    regression_bias_flag BOOLEAN NOT NULL,
    drift_flag BOOLEAN NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    recommended_action TEXT NOT NULL,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    exposure_score NUMERIC(5,2)
);

CREATE TABLE IF NOT EXISTS audit_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    model_id UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    output_type TEXT NOT NULL CHECK (
        output_type IN (
            'regulator_examination_package',
            'fair_lending_summary_report',
            'model_validation_dossier',
            'bias_incident_timeline'
        )
    ),
    version INTEGER NOT NULL,
    immutable BOOLEAN NOT NULL DEFAULT TRUE,
    hash_sha256 TEXT NOT NULL,
    reviewer_sign_off TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, model_id, output_type, version)
);

CREATE TABLE IF NOT EXISTS ckg_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    node_type TEXT NOT NULL,
    node_key TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, node_type, node_key)
);

CREATE TABLE IF NOT EXISTS ckg_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_node_type TEXT NOT NULL,
    source_node_key TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    target_node_type TEXT NOT NULL,
    target_node_key TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_regulations_tenant_citation ON regulations (tenant_id, citation);
CREATE INDEX IF NOT EXISTS idx_obligations_tenant_regulation ON obligations (tenant_id, regulation_id);
CREATE INDEX IF NOT EXISTS idx_controls_tenant_obligation ON controls (tenant_id, obligation_id);
CREATE INDEX IF NOT EXISTS idx_tests_tenant_control ON tests (tenant_id, control_id);
CREATE INDEX IF NOT EXISTS idx_models_tenant_external ON models (tenant_id, external_model_id);
CREATE INDEX IF NOT EXISTS idx_model_changes_tenant_model ON model_changes (tenant_id, model_id);
CREATE INDEX IF NOT EXISTS idx_results_tenant_model_analyzed ON model_compliance_results (tenant_id, model_id, analyzed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_exports_tenant_model_generated ON audit_exports (tenant_id, model_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ckg_edges_tenant_source_target ON ckg_edges (tenant_id, source_node_type, source_node_key, target_node_type, target_node_key);

-- Row-level security to enforce tenant isolation.
ALTER TABLE regulations ENABLE ROW LEVEL SECURITY;
ALTER TABLE obligations ENABLE ROW LEVEL SECURITY;
ALTER TABLE controls ENABLE ROW LEVEL SECURITY;
ALTER TABLE tests ENABLE ROW LEVEL SECURITY;
ALTER TABLE models ENABLE ROW LEVEL SECURITY;
ALTER TABLE validations ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_compliance_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE ckg_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE ckg_edges ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_regulations ON regulations
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_obligations ON obligations
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_controls ON controls
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_tests ON tests
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_models ON models
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_validations ON validations
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_model_changes ON model_changes
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_model_results ON model_compliance_results
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_audit_exports ON audit_exports
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_ckg_nodes ON ckg_nodes
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_isolation_ckg_edges ON ckg_edges
    USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
