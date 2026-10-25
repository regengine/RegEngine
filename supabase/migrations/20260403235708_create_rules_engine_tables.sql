
CREATE TABLE IF NOT EXISTS fsma.rule_definitions (
    rule_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_version        INTEGER NOT NULL DEFAULT 1,
    title               TEXT NOT NULL,
    description         TEXT,
    severity            TEXT NOT NULL DEFAULT 'warning'
                        CHECK (severity IN ('critical', 'warning', 'info')),
    category            TEXT NOT NULL DEFAULT 'kde_presence'
                        CHECK (category IN (
                            'kde_presence', 'temporal_ordering', 'lot_linkage',
                            'source_reference', 'identifier_format', 'quantity_consistency',
                            'entity_resolution', 'record_completeness', 'chain_integrity'
                        )),
    applicability_conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
    citation_reference  TEXT,
    effective_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    retired_date        DATE,
    evaluation_logic    JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_reason_template TEXT NOT NULL DEFAULT 'Rule evaluation failed',
    remediation_suggestion TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          TEXT,
    UNIQUE (title, rule_version)
);

CREATE TABLE IF NOT EXISTS fsma.rule_evaluations (
    evaluation_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    event_id            UUID NOT NULL,
    rule_id             UUID NOT NULL REFERENCES fsma.rule_definitions(rule_id),
    rule_version        INTEGER NOT NULL,
    result              TEXT NOT NULL CHECK (result IN ('pass', 'fail', 'warn', 'skip')),
    why_failed          TEXT,
    evidence_fields_inspected JSONB DEFAULT '[]'::jsonb,
    confidence          DOUBLE PRECISION DEFAULT 1.0
                        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fsma.rule_audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id             UUID NOT NULL REFERENCES fsma.rule_definitions(rule_id),
    action              TEXT NOT NULL CHECK (action IN ('created', 'updated', 'retired', 'activated')),
    old_values          JSONB,
    new_values          JSONB,
    changed_by          TEXT,
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rule_defs_category ON fsma.rule_definitions (category);
CREATE INDEX IF NOT EXISTS idx_rule_defs_severity ON fsma.rule_definitions (severity);
CREATE INDEX IF NOT EXISTS idx_rule_defs_active ON fsma.rule_definitions (effective_date, retired_date) WHERE retired_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_rule_evals_tenant ON fsma.rule_evaluations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_event ON fsma.rule_evaluations (event_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_rule ON fsma.rule_evaluations (rule_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_result ON fsma.rule_evaluations (tenant_id, result) WHERE result IN ('fail', 'warn');
CREATE INDEX IF NOT EXISTS idx_rule_evals_event_rule ON fsma.rule_evaluations (event_id, rule_id);
CREATE INDEX IF NOT EXISTS idx_rule_audit_rule ON fsma.rule_audit_log (rule_id);
;
