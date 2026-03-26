-- ==========================================
-- RegEngine: Exception & Remediation Queue
-- Migration V045: Turn record defects into managed operational work
-- ==========================================
-- Transforms compliance failures from passive alerts into an active
-- remediation workflow with ownership, deadlines, waivers, and signoffs.

BEGIN;

-- --------------------------------------------------------
-- 1. Exception Cases — remediation work items
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.exception_cases (
    case_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    -- Classification
    severity            TEXT NOT NULL DEFAULT 'warning'
                        CHECK (severity IN ('critical', 'warning', 'info')),
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN (
                            'open', 'in_review', 'awaiting_supplier',
                            'resolved', 'waived'
                        )),

    -- Linked records
    linked_event_ids    UUID[] NOT NULL DEFAULT '{}',
    linked_rule_evaluation_ids UUID[] NOT NULL DEFAULT '{}',

    -- Ownership
    owner_user_id       TEXT,
    due_date            TIMESTAMPTZ,

    -- Source context
    source_supplier     TEXT,
    source_facility_reference TEXT,
    rule_category       TEXT,

    -- Remediation
    recommended_remediation TEXT,
    resolution_summary  TEXT,

    -- Waiver handling
    waiver_reason       TEXT,
    waiver_approved_by  TEXT,
    waiver_approved_at  TIMESTAMPTZ,

    -- Link to active request case (inherits SLA deadline)
    request_case_id     UUID,

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ
);

-- --------------------------------------------------------
-- 2. Exception Comments — threaded discussion
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.exception_comments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    case_id             UUID NOT NULL REFERENCES fsma.exception_cases(case_id) ON DELETE CASCADE,

    author_user_id      TEXT NOT NULL,
    comment_text        TEXT NOT NULL,
    comment_type        TEXT NOT NULL DEFAULT 'note'
                        CHECK (comment_type IN ('note', 'status_change', 'assignment', 'supplier_response', 'system')),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------
-- 3. Exception Attachments — supporting documents
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.exception_attachments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    case_id             UUID NOT NULL REFERENCES fsma.exception_cases(case_id) ON DELETE CASCADE,

    file_name           TEXT NOT NULL,
    file_hash           TEXT,
    file_size           BIGINT,
    mime_type           TEXT,
    storage_uri         TEXT,

    uploaded_by         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------
-- 4. Exception Signoffs — approval chain
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.exception_signoffs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    case_id             UUID NOT NULL REFERENCES fsma.exception_cases(case_id) ON DELETE CASCADE,

    signoff_type        TEXT NOT NULL CHECK (signoff_type IN ('review', 'approve', 'waive', 'reject')),
    signed_by           TEXT NOT NULL,
    signed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason              TEXT
);


-- --------------------------------------------------------
-- Indexes
-- --------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_exception_cases_tenant
    ON fsma.exception_cases (tenant_id);
CREATE INDEX IF NOT EXISTS idx_exception_cases_status
    ON fsma.exception_cases (tenant_id, status)
    WHERE status NOT IN ('resolved', 'waived');
CREATE INDEX IF NOT EXISTS idx_exception_cases_severity
    ON fsma.exception_cases (tenant_id, severity);
CREATE INDEX IF NOT EXISTS idx_exception_cases_owner
    ON fsma.exception_cases (owner_user_id)
    WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_exception_cases_due
    ON fsma.exception_cases (due_date)
    WHERE status NOT IN ('resolved', 'waived');
CREATE INDEX IF NOT EXISTS idx_exception_cases_supplier
    ON fsma.exception_cases (tenant_id, source_supplier)
    WHERE source_supplier IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_exception_cases_request
    ON fsma.exception_cases (request_case_id)
    WHERE request_case_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_exception_cases_events
    ON fsma.exception_cases USING GIN (linked_event_ids);

CREATE INDEX IF NOT EXISTS idx_exception_comments_case
    ON fsma.exception_comments (case_id);
CREATE INDEX IF NOT EXISTS idx_exception_attachments_case
    ON fsma.exception_attachments (case_id);
CREATE INDEX IF NOT EXISTS idx_exception_signoffs_case
    ON fsma.exception_signoffs (case_id);


-- --------------------------------------------------------
-- Row-Level Security
-- --------------------------------------------------------

ALTER TABLE fsma.exception_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.exception_cases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_exception_cases ON fsma.exception_cases;
CREATE POLICY tenant_isolation_exception_cases ON fsma.exception_cases
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid);

ALTER TABLE fsma.exception_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.exception_comments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_exception_comments ON fsma.exception_comments;
CREATE POLICY tenant_isolation_exception_comments ON fsma.exception_comments
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid);

ALTER TABLE fsma.exception_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.exception_attachments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_exception_attachments ON fsma.exception_attachments;
CREATE POLICY tenant_isolation_exception_attachments ON fsma.exception_attachments
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid);

ALTER TABLE fsma.exception_signoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.exception_signoffs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_exception_signoffs ON fsma.exception_signoffs;
CREATE POLICY tenant_isolation_exception_signoffs ON fsma.exception_signoffs
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid);


-- --------------------------------------------------------
-- Comments
-- --------------------------------------------------------

COMMENT ON TABLE fsma.exception_cases IS
    'Remediation work items — every failed rule evaluation can generate or attach to an exception case. '
    'Supports ownership, SLA deadlines, waiver workflow, and signoff chain.';
COMMENT ON TABLE fsma.exception_comments IS
    'Threaded discussion on exception cases — notes, status changes, supplier responses';
COMMENT ON TABLE fsma.exception_signoffs IS
    'Approval chain — every waiver, override, or resolution requires identity and reason';

COMMIT;
