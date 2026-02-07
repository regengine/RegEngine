-- ============================================================
-- V30: Audit Log Table — Append-Only, Tamper-Evident
-- ISO 27001: 12.4.1, 12.4.2, 12.4.3
--
-- Replaces the basic audit_logs table with a full
-- tamper-evident implementation including hash chain,
-- event categorization, and immutability triggers.
-- ============================================================

-- Drop the existing basic audit_logs table (no production data)
DROP TABLE IF EXISTS audit_logs CASCADE;

-- ============================================================
-- New audit_logs table with tamper-evidence
-- ============================================================

CREATE TABLE audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- WHO
    actor_id        UUID,
    actor_email     TEXT,
    actor_ip        INET,
    actor_ua        TEXT,

    -- WHAT
    event_type      TEXT NOT NULL,
    event_category  TEXT NOT NULL,
    action          TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'info',

    -- WHERE
    resource_type   TEXT,
    resource_id     TEXT,
    endpoint        TEXT,

    -- DETAILS
    metadata        JSONB DEFAULT '{}',
    request_id      UUID,

    -- TAMPER EVIDENCE
    prev_hash       TEXT,
    integrity_hash  TEXT NOT NULL,

    -- CONSTRAINTS
    CONSTRAINT audit_event_category_check CHECK (
        event_category IN ('auth', 'data', 'admin', 'system', 'api')
    ),
    CONSTRAINT audit_action_check CHECK (
        action IN ('create', 'read', 'update', 'delete', 'export',
                   'login', 'logout', 'fail', 'grant', 'revoke')
    ),
    CONSTRAINT audit_severity_check CHECK (
        severity IN ('info', 'warning', 'error', 'critical')
    )
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX idx_audit_tenant_time ON audit_logs (tenant_id, timestamp DESC);
CREATE INDEX idx_audit_event_type ON audit_logs (tenant_id, event_type);
CREATE INDEX idx_audit_actor ON audit_logs (tenant_id, actor_id);
CREATE INDEX idx_audit_resource ON audit_logs (tenant_id, resource_type, resource_id);
CREATE INDEX idx_audit_severity ON audit_logs (tenant_id, severity)
    WHERE severity IN ('warning', 'error', 'critical');
CREATE INDEX idx_audit_integrity ON audit_logs (tenant_id, id, integrity_hash);

-- ============================================================
-- Row-Level Security — INSERT only, tenant-scoped reads
-- ============================================================

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Tenant can only read their own logs
CREATE POLICY audit_select_policy ON audit_logs
    FOR SELECT
    USING (tenant_id = COALESCE(
        NULLIF(current_setting('app.tenant_id', true), '')::UUID,
        '00000000-0000-0000-0000-000000000000'::UUID
    ));

-- Service role can insert (not tied to tenant context)
CREATE POLICY audit_insert_policy ON audit_logs
    FOR INSERT
    WITH CHECK (true);

-- ============================================================
-- Immutability Triggers — No UPDATE or DELETE. Ever.
-- ============================================================

CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs table is append-only. Modifications are not permitted. ISO 27001 12.4.2.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_no_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

CREATE TRIGGER audit_no_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- ============================================================
-- Table documentation
-- ============================================================

COMMENT ON TABLE audit_logs IS
    'Append-only tamper-evident audit trail. No UPDATE or DELETE permitted. '
    'Each entry includes SHA-256 hash chain for integrity verification. '
    'ISO 27001 controls 12.4.1 (event logging), 12.4.2 (protection), 12.4.3 (admin logs).';
