-- ==========================================
-- RegEngine: Request-Response Workflow
-- Migration V046: 24-Hour FDA Response Readiness
-- ==========================================
-- Makes 24-hour response readiness an explicit product loop.
-- Workflow: intake → scope → collect → gap analysis → triage →
--           assemble → review → export → submit → amend

BEGIN;

-- --------------------------------------------------------
-- 1. Request Cases — FDA/auditor request tracking
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.request_cases (
    request_case_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    -- Timing
    request_received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_due_at     TIMESTAMPTZ NOT NULL,

    -- Requesting party
    requesting_party    TEXT,                    -- 'FDA', 'State DOH', 'Internal Drill', etc.
    request_channel     TEXT DEFAULT 'email'
                        CHECK (request_channel IN ('email', 'phone', 'portal', 'letter', 'drill', 'other')),

    -- Scope
    scope_type          TEXT NOT NULL DEFAULT 'tlc_trace'
                        CHECK (scope_type IN (
                            'tlc_trace',         -- trace specific lot codes
                            'product_recall',    -- recall by product
                            'facility_audit',    -- all records for a facility
                            'date_range',        -- all records in date range
                            'custom'             -- custom scope
                        )),
    scope_description   TEXT,

    -- Affected items (arrays for flexible scoping)
    affected_products   TEXT[] DEFAULT '{}',
    affected_lots       TEXT[] DEFAULT '{}',
    affected_facilities TEXT[] DEFAULT '{}',

    -- Status tracking
    package_status      TEXT NOT NULL DEFAULT 'intake'
                        CHECK (package_status IN (
                            'intake',            -- request received
                            'scoping',           -- defining scope
                            'collecting',        -- gathering records
                            'gap_analysis',      -- identifying missing data
                            'exception_triage',  -- resolving exceptions
                            'assembling',        -- building package
                            'internal_review',   -- review/signoff
                            'ready',             -- ready to submit
                            'submitted',         -- submitted to requesting party
                            'amended'            -- post-submission amendment
                        )),

    -- Review chain
    reviewer            TEXT,
    final_approver      TEXT,

    -- Submission
    submission_timestamp TIMESTAMPTZ,
    submission_notes    TEXT,

    -- Metadata
    active_exception_count INTEGER DEFAULT 0,
    total_records       INTEGER DEFAULT 0,
    gap_count           INTEGER DEFAULT 0,

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------
-- 2. Response Packages — immutable package snapshots
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.response_packages (
    package_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    request_case_id     UUID NOT NULL REFERENCES fsma.request_cases(request_case_id),

    version_number      INTEGER NOT NULL DEFAULT 1,

    -- Package contents (immutable snapshot)
    package_contents    JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Structure:
    -- {
    --   "event_ids": [...],
    --   "rule_evaluations": [...],
    --   "exception_cases": [...],
    --   "trace_data": {...},
    --   "gap_analysis": {...}
    -- }

    -- Integrity
    package_hash        TEXT NOT NULL,            -- SHA-256 of package_contents

    -- Gap analysis at time of package generation
    gap_analysis        JSONB DEFAULT '{}'::jsonb,
    -- {
    --   "missing_events": [...],
    --   "failed_rules": [...],
    --   "unresolved_exceptions": [...],
    --   "gap_owners": {"supplier_x": ["gap1", "gap2"]}
    -- }

    -- Diff from previous version
    diff_from_previous  JSONB,

    -- Audit
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_by        TEXT
);

-- --------------------------------------------------------
-- 3. Submission Log — audit trail for every submission
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.submission_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    request_case_id     UUID NOT NULL REFERENCES fsma.request_cases(request_case_id),
    package_id          UUID NOT NULL REFERENCES fsma.response_packages(package_id),

    submission_type     TEXT NOT NULL DEFAULT 'initial'
                        CHECK (submission_type IN ('initial', 'amendment', 'supplement', 'correction')),
    submitted_to        TEXT,
    submitted_by        TEXT,
    submission_method   TEXT DEFAULT 'export'
                        CHECK (submission_method IN ('export', 'email', 'portal', 'mail', 'other')),
    submission_notes    TEXT,

    -- Immutable snapshot reference
    package_hash        TEXT NOT NULL,
    record_count        INTEGER NOT NULL DEFAULT 0,

    submitted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------
-- 4. Signoff Chain — review approvals
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.request_signoffs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    request_case_id     UUID NOT NULL REFERENCES fsma.request_cases(request_case_id),

    signoff_type        TEXT NOT NULL CHECK (signoff_type IN (
                            'scope_approval', 'package_review',
                            'final_approval', 'submission_authorization'
                        )),
    signed_by           TEXT NOT NULL,
    signed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes               TEXT
);


-- --------------------------------------------------------
-- Indexes
-- --------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_request_cases_tenant
    ON fsma.request_cases (tenant_id);
CREATE INDEX IF NOT EXISTS idx_request_cases_status
    ON fsma.request_cases (tenant_id, package_status)
    WHERE package_status NOT IN ('submitted', 'amended');
CREATE INDEX IF NOT EXISTS idx_request_cases_due
    ON fsma.request_cases (response_due_at)
    WHERE package_status NOT IN ('submitted', 'amended');
CREATE INDEX IF NOT EXISTS idx_request_cases_lots
    ON fsma.request_cases USING GIN (affected_lots);
CREATE INDEX IF NOT EXISTS idx_request_cases_facilities
    ON fsma.request_cases USING GIN (affected_facilities);

CREATE INDEX IF NOT EXISTS idx_response_packages_request
    ON fsma.response_packages (request_case_id);
CREATE INDEX IF NOT EXISTS idx_response_packages_tenant
    ON fsma.response_packages (tenant_id);

CREATE INDEX IF NOT EXISTS idx_submission_log_request
    ON fsma.submission_log (request_case_id);
CREATE INDEX IF NOT EXISTS idx_submission_log_tenant
    ON fsma.submission_log (tenant_id);

CREATE INDEX IF NOT EXISTS idx_request_signoffs_request
    ON fsma.request_signoffs (request_case_id);


-- --------------------------------------------------------
-- Row-Level Security
-- --------------------------------------------------------

ALTER TABLE fsma.request_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.request_cases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_request_cases ON fsma.request_cases;
CREATE POLICY tenant_isolation_request_cases ON fsma.request_cases
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.response_packages ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.response_packages FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_response_packages ON fsma.response_packages;
CREATE POLICY tenant_isolation_response_packages ON fsma.response_packages
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.submission_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.submission_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_submission_log ON fsma.submission_log;
CREATE POLICY tenant_isolation_submission_log ON fsma.submission_log
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.request_signoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.request_signoffs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_request_signoffs ON fsma.request_signoffs;
CREATE POLICY tenant_isolation_request_signoffs ON fsma.request_signoffs
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());


-- --------------------------------------------------------
-- Add FK from exception_cases to request_cases
-- --------------------------------------------------------

ALTER TABLE fsma.exception_cases
    ADD CONSTRAINT fk_exception_request_case
    FOREIGN KEY (request_case_id)
    REFERENCES fsma.request_cases(request_case_id);


-- --------------------------------------------------------
-- Comments
-- --------------------------------------------------------

COMMENT ON TABLE fsma.request_cases IS
    'FDA/auditor request tracking — the 24-hour response workflow from intake to submission. '
    'Includes countdown timer, scope definition, gap analysis, and amendment trail.';
COMMENT ON TABLE fsma.response_packages IS
    'Immutable response package snapshots — each version is SHA-256 sealed. '
    'Resubmission creates a new version with diff against prior.';
COMMENT ON TABLE fsma.submission_log IS
    'Append-only audit trail for every package submission, including method and notes.';
COMMENT ON TABLE fsma.request_signoffs IS
    'Review and approval chain for request cases — scope approval, package review, final authorization.';

COMMIT;
