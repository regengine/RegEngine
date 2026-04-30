-- V067 — Inflow Workbench persistence companion SQL
-- =================================================
-- Raw SQL companion for the Alembic v073 Inflow Workbench migration.
-- Production deployments should use alembic/versions/
-- 20260430_b8c9d0e1f2a3_v073_inflow_workbench_postgres.py.

BEGIN;

CREATE SCHEMA IF NOT EXISTS fsma;

CREATE TABLE IF NOT EXISTS fsma.inflow_workbench_scenarios (
    scenario_id        TEXT NOT NULL,
    tenant_id          UUID NOT NULL,
    name               TEXT NOT NULL,
    outcome            TEXT NOT NULL DEFAULT 'Custom scenario',
    record_count_label TEXT NOT NULL DEFAULT '0 CTE records',
    csv_text           TEXT NOT NULL,
    built_in           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, scenario_id)
);

CREATE TABLE IF NOT EXISTS fsma.inflow_workbench_runs (
    run_id              TEXT PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    source              TEXT NOT NULL DEFAULT 'inflow-lab',
    csv_text            TEXT NOT NULL DEFAULT '',
    result_payload      JSONB NOT NULL,
    readiness_payload   JSONB NOT NULL,
    commit_gate_payload JSONB NOT NULL,
    input_hash          TEXT,
    result_hash         TEXT,
    saved_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_inflow_run_input_hash
        CHECK (input_hash IS NULL OR input_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_inflow_run_result_hash
        CHECK (result_hash IS NULL OR result_hash ~ '^[0-9a-f]{64}$')
);

ALTER TABLE fsma.inflow_workbench_runs ADD COLUMN IF NOT EXISTS input_hash TEXT;
ALTER TABLE fsma.inflow_workbench_runs ADD COLUMN IF NOT EXISTS result_hash TEXT;

CREATE TABLE IF NOT EXISTS fsma.inflow_workbench_fix_items (
    item_id    TEXT PRIMARY KEY,
    run_id     TEXT NOT NULL REFERENCES fsma.inflow_workbench_runs(run_id),
    tenant_id  UUID NOT NULL,
    title      TEXT NOT NULL,
    owner      TEXT NOT NULL DEFAULT 'Source data owner',
    status     TEXT NOT NULL DEFAULT 'open',
    severity   TEXT NOT NULL DEFAULT 'warning',
    impact     TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'Inflow Lab',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_inflow_fix_status
        CHECK (status IN ('open', 'waiting', 'corrected', 'accepted')),
    CONSTRAINT chk_inflow_fix_severity
        CHECK (severity IN ('blocked', 'warning', 'info'))
);

CREATE TABLE IF NOT EXISTS fsma.inflow_workbench_commit_decisions (
    decision_id     TEXT PRIMARY KEY,
    run_id          TEXT REFERENCES fsma.inflow_workbench_runs(run_id),
    tenant_id       UUID NOT NULL,
    mode            TEXT NOT NULL,
    allowed         BOOLEAN NOT NULL DEFAULT FALSE,
    export_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    reasons         JSONB NOT NULL DEFAULT '[]'::jsonb,
    next_state      TEXT NOT NULL,
    input_hash      TEXT,
    result_hash     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_inflow_commit_mode
        CHECK (mode IN ('simulation', 'preflight', 'staging', 'production_evidence')),
    CONSTRAINT chk_inflow_commit_input_hash
        CHECK (input_hash IS NULL OR input_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_inflow_commit_result_hash
        CHECK (result_hash IS NULL OR result_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_inflow_scenarios_tenant_created
    ON fsma.inflow_workbench_scenarios (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inflow_runs_tenant_saved
    ON fsma.inflow_workbench_runs (tenant_id, saved_at DESC);
CREATE INDEX IF NOT EXISTS idx_inflow_fix_items_tenant_status
    ON fsma.inflow_workbench_fix_items (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inflow_fix_items_run
    ON fsma.inflow_workbench_fix_items (run_id);
CREATE INDEX IF NOT EXISTS idx_inflow_commit_decisions_tenant_created
    ON fsma.inflow_workbench_commit_decisions (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inflow_runs_tenant_run
    ON fsma.inflow_workbench_runs (tenant_id, run_id);

CREATE OR REPLACE FUNCTION fsma.prevent_inflow_workbench_evidence_update()
RETURNS TRIGGER AS $fn$
BEGIN
    RAISE EXCEPTION 'Inflow workbench run and commit-decision records are append-only';
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inflow_runs_append_only ON fsma.inflow_workbench_runs;
CREATE TRIGGER trg_inflow_runs_append_only
    BEFORE UPDATE OR DELETE ON fsma.inflow_workbench_runs
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_inflow_workbench_evidence_update();

DROP TRIGGER IF EXISTS trg_inflow_commit_decisions_append_only ON fsma.inflow_workbench_commit_decisions;
CREATE TRIGGER trg_inflow_commit_decisions_append_only
    BEFORE UPDATE OR DELETE ON fsma.inflow_workbench_commit_decisions
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_inflow_workbench_evidence_update();

ALTER TABLE fsma.inflow_workbench_scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.inflow_workbench_scenarios FORCE ROW LEVEL SECURITY;
ALTER TABLE fsma.inflow_workbench_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.inflow_workbench_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE fsma.inflow_workbench_fix_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.inflow_workbench_fix_items FORCE ROW LEVEL SECURITY;
ALTER TABLE fsma.inflow_workbench_commit_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.inflow_workbench_commit_decisions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_inflow_scenarios ON fsma.inflow_workbench_scenarios;
CREATE POLICY tenant_isolation_inflow_scenarios ON fsma.inflow_workbench_scenarios
    FOR ALL TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    )
    WITH CHECK (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP POLICY IF EXISTS tenant_isolation_inflow_runs ON fsma.inflow_workbench_runs;
CREATE POLICY tenant_isolation_inflow_runs ON fsma.inflow_workbench_runs
    FOR ALL TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    )
    WITH CHECK (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP POLICY IF EXISTS tenant_isolation_inflow_fix_items ON fsma.inflow_workbench_fix_items;
CREATE POLICY tenant_isolation_inflow_fix_items ON fsma.inflow_workbench_fix_items
    FOR ALL TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    )
    WITH CHECK (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

DROP POLICY IF EXISTS tenant_isolation_inflow_commit_decisions ON fsma.inflow_workbench_commit_decisions;
CREATE POLICY tenant_isolation_inflow_commit_decisions ON fsma.inflow_workbench_commit_decisions
    FOR ALL TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    )
    WITH CHECK (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

COMMENT ON TABLE fsma.inflow_workbench_scenarios IS
    'Tenant-scoped Inflow Lab replay scenarios saved from uploaded or mapped traceability feeds.';
COMMENT ON TABLE fsma.inflow_workbench_runs IS
    'Tenant-scoped Inflow Workbench preflight runs with input/result hashes and readiness snapshots.';
COMMENT ON TABLE fsma.inflow_workbench_fix_items IS
    'Tenant-scoped remediation queue created from Inflow Workbench validation failures.';
COMMENT ON TABLE fsma.inflow_workbench_commit_decisions IS
    'Tenant-scoped append-only commit-gate decisions for Inflow Workbench runs.';

COMMIT;
