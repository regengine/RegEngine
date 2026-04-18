-- ==========================================
-- RegEngine: Versioned Rules Engine
-- Migration V044: Compliance Rule Definitions + Evaluation Results
-- ==========================================
-- Separates regulatory logic from application logic.
-- Rules are versioned policy artifacts, not code paths.
-- Every evaluation is explainable: pass/fail/warn + why_failed + evidence.
--
-- A user should see:
--   "Failed because receiving event is missing traceability lot code source reference"
-- NOT:
--   "validation_error_17"

BEGIN;

-- --------------------------------------------------------
-- 1. Rule Definitions — versioned compliance rule catalog
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.rule_definitions (
    rule_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_version        INTEGER NOT NULL DEFAULT 1,

    -- Human-readable identification
    title               TEXT NOT NULL,
    description         TEXT,

    -- Classification
    severity            TEXT NOT NULL DEFAULT 'warning'
                        CHECK (severity IN ('critical', 'warning', 'info')),
    category            TEXT NOT NULL DEFAULT 'kde_presence'
                        CHECK (category IN (
                            'kde_presence',          -- required KDE missing
                            'temporal_ordering',     -- time arrow violations
                            'lot_linkage',           -- TLC source/lineage breaks
                            'source_reference',      -- reference document missing
                            'identifier_format',     -- GLN/GTIN/TLC format errors
                            'quantity_consistency',   -- mass balance / quantity checks
                            'entity_resolution',     -- facility/firm alias issues
                            'record_completeness',   -- overall record completeness
                            'chain_integrity'        -- hash chain / tamper detection
                        )),

    -- Applicability conditions (which events does this rule apply to?)
    applicability_conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Expected structure:
    -- {
    --   "cte_types": ["shipping", "receiving"],
    --   "commodities": ["produce", "seafood"],
    --   "event_fields": {"from_facility_reference": "required"}
    -- }

    -- Regulatory citation
    citation_reference  TEXT,                    -- e.g., "21 CFR 1.1345(b)(3)"
    effective_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    retired_date        DATE,

    -- Evaluation specification
    evaluation_logic    JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Expected structure:
    -- {
    --   "type": "field_presence",           -- field_presence | field_format | temporal_order | custom
    --   "field": "kdes.tlc_source_reference",
    --   "condition": "not_empty",
    --   "params": {}
    -- }

    -- Human-readable output templates
    failure_reason_template TEXT NOT NULL
        DEFAULT 'Rule evaluation failed',
    -- Template with {field} placeholders:
    -- "Receiving event missing {field_name} required by {citation}"

    remediation_suggestion TEXT,
    -- "Request the traceability lot code source reference from your immediate supplier"

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          TEXT,

    -- Versioning: (title, rule_version) should be unique
    UNIQUE (title, rule_version)
);

-- --------------------------------------------------------
-- 2. Rule Evaluations — per-event evaluation results
-- --------------------------------------------------------
-- Every time a record is evaluated against a rule, the result is stored.
-- This is the evidentiary basis for compliance assertions.

CREATE TABLE IF NOT EXISTS fsma.rule_evaluations (
    evaluation_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    -- What was evaluated
    event_id            UUID NOT NULL,           -- canonical traceability_events.event_id
    rule_id             UUID NOT NULL REFERENCES fsma.rule_definitions(rule_id),
    rule_version        INTEGER NOT NULL,

    -- Result
    result              TEXT NOT NULL CHECK (result IN ('pass', 'fail', 'warn', 'skip')),
    why_failed          TEXT,                    -- human-readable explanation (rendered from template)

    -- Evidence
    evidence_fields_inspected JSONB DEFAULT '[]'::jsonb,
    -- Which fields were checked and what their values were:
    -- [{"field": "kdes.tlc_source_reference", "value": null, "expected": "not_empty"}]

    confidence          DOUBLE PRECISION DEFAULT 1.0
                        CHECK (confidence >= 0.0 AND confidence <= 1.0),

    -- Audit
    evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------
-- 3. Rule Change Audit Log — track rule modifications
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.rule_audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id             UUID NOT NULL REFERENCES fsma.rule_definitions(rule_id),
    action              TEXT NOT NULL CHECK (action IN ('created', 'updated', 'retired', 'activated')),
    old_values          JSONB,
    new_values          JSONB,
    changed_by          TEXT,
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- --------------------------------------------------------
-- Indexes
-- --------------------------------------------------------

-- Rule definitions
CREATE INDEX IF NOT EXISTS idx_rule_defs_category
    ON fsma.rule_definitions (category);
CREATE INDEX IF NOT EXISTS idx_rule_defs_severity
    ON fsma.rule_definitions (severity);
CREATE INDEX IF NOT EXISTS idx_rule_defs_active
    ON fsma.rule_definitions (effective_date, retired_date)
    WHERE retired_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_rule_defs_applicability
    ON fsma.rule_definitions USING GIN (applicability_conditions);

-- Rule evaluations
CREATE INDEX IF NOT EXISTS idx_rule_evals_tenant
    ON fsma.rule_evaluations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_event
    ON fsma.rule_evaluations (event_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_rule
    ON fsma.rule_evaluations (rule_id);
CREATE INDEX IF NOT EXISTS idx_rule_evals_result
    ON fsma.rule_evaluations (tenant_id, result)
    WHERE result IN ('fail', 'warn');
CREATE INDEX IF NOT EXISTS idx_rule_evals_timestamp
    ON fsma.rule_evaluations (evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rule_evals_event_rule
    ON fsma.rule_evaluations (event_id, rule_id);

-- Rule audit log
CREATE INDEX IF NOT EXISTS idx_rule_audit_rule
    ON fsma.rule_audit_log (rule_id);
CREATE INDEX IF NOT EXISTS idx_rule_audit_timestamp
    ON fsma.rule_audit_log (changed_at DESC);


-- --------------------------------------------------------
-- Row-Level Security
-- --------------------------------------------------------
-- Rule definitions are global (not tenant-scoped) — they are regulatory rules.
-- Rule evaluations ARE tenant-scoped — they contain tenant data.

ALTER TABLE fsma.rule_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.rule_evaluations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_rule_evals ON fsma.rule_evaluations;
CREATE POLICY tenant_isolation_rule_evals ON fsma.rule_evaluations
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid);


-- --------------------------------------------------------
-- Comments
-- --------------------------------------------------------

COMMENT ON TABLE fsma.rule_definitions IS
    'Versioned compliance rule catalog — regulatory logic as declarative policy artifacts, '
    'not application code. Every rule is citable, explainable, and independently deployable.';
COMMENT ON TABLE fsma.rule_evaluations IS
    'Per-event rule evaluation results — the evidentiary record that a specific check was run '
    'against a specific record with a specific outcome. Stores why_failed in human-readable form.';
COMMENT ON TABLE fsma.rule_audit_log IS
    'Append-only audit trail for rule definition changes — proves to auditors that rules '
    'were not silently modified.';

COMMENT ON COLUMN fsma.rule_definitions.failure_reason_template IS
    'Human-readable template with {field} placeholders. '
    'Example: "Receiving event missing {field_name} required by {citation}"';
COMMENT ON COLUMN fsma.rule_definitions.evaluation_logic IS
    'Declarative evaluation specification: type (field_presence, field_format, temporal_order, custom), '
    'target field, condition, and parameters';
COMMENT ON COLUMN fsma.rule_evaluations.why_failed IS
    'Rendered human-readable explanation of the failure. Must be understandable by '
    'a compliance manager, not just a developer.';

COMMIT;
