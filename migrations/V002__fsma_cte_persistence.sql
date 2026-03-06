-- ==========================================
-- RegEngine: FSMA 204 CTE Persistence Layer
-- Migration V002: Critical Tracking Events
-- ==========================================
-- Creates the core tables for persisting supply chain
-- traceability events (CTEs), key data elements (KDEs),
-- and the tamper-evident hash chain.
--
-- This is the foundation of the entire compliance promise:
-- "When the FDA calls, produce records within 24 hours."

BEGIN;

-- --------------------------------------------------------
-- Schema
-- --------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS fsma;

-- --------------------------------------------------------
-- 1. CTE Events — the core traceability record
-- --------------------------------------------------------
-- Each row is a single Critical Tracking Event as defined
-- by FSMA 204 (§1.1325–§1.1350). Every event in the supply
-- chain — harvesting, cooling, packing, shipping, receiving,
-- transformation — gets one row here.

CREATE TABLE IF NOT EXISTS fsma.cte_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    -- CTE identity
    event_type          TEXT NOT NULL CHECK (event_type IN (
                            'harvesting', 'cooling', 'initial_packing',
                            'shipping', 'receiving', 'transformation'
                        )),
    traceability_lot_code TEXT NOT NULL,
    product_description TEXT NOT NULL,

    -- Quantities
    quantity            DOUBLE PRECISION NOT NULL CHECK (quantity > 0),
    unit_of_measure     TEXT NOT NULL,

    -- Location (GS1 GLN preferred, name as fallback)
    location_gln        TEXT,
    location_name       TEXT,

    -- Temporal
    event_timestamp     TIMESTAMPTZ NOT NULL,

    -- Source tracking
    source              TEXT NOT NULL DEFAULT 'api',
    source_event_id     TEXT,          -- external system's ID for dedup
    idempotency_key     TEXT UNIQUE,   -- SHA-256 of canonical event for dedup

    -- Integrity
    sha256_hash         TEXT NOT NULL,  -- hash of this event's canonical form
    chain_hash          TEXT NOT NULL,  -- hash chained to previous event

    -- EPCIS interop (nullable — only populated for EPCIS-ingested events)
    epcis_event_type    TEXT,
    epcis_action        TEXT,
    epcis_biz_step      TEXT,

    -- Validation
    validation_status   TEXT NOT NULL DEFAULT 'valid' CHECK (validation_status IN ('valid', 'rejected', 'warning')),

    -- Audit
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------
-- 2. KDEs — Key Data Elements per CTE
-- --------------------------------------------------------
-- FSMA 204 requires specific data elements for each CTE type.
-- Rather than an ever-widening column set, we store KDEs as
-- typed key-value pairs linked to their parent CTE.

CREATE TABLE IF NOT EXISTS fsma.cte_kdes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    cte_event_id        UUID NOT NULL REFERENCES fsma.cte_events(id) ON DELETE CASCADE,

    kde_key             TEXT NOT NULL,    -- e.g. 'harvest_date', 'temperature_celsius', 'carrier_name'
    kde_value           TEXT NOT NULL,
    is_required         BOOLEAN NOT NULL DEFAULT FALSE,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- No duplicate KDE keys per event
    UNIQUE (cte_event_id, kde_key)
);

-- --------------------------------------------------------
-- 3. Hash Chain Ledger — tamper-evident audit trail
-- --------------------------------------------------------
-- Every accepted CTE gets an entry here. The chain_hash of
-- row N is SHA-256(chain_hash[N-1] | sha256_hash[N]).
-- Chain root uses 'GENESIS' as the previous hash.
-- This table is append-only. No UPDATEs. No DELETEs.

CREATE TABLE IF NOT EXISTS fsma.hash_chain (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    cte_event_id        UUID NOT NULL REFERENCES fsma.cte_events(id),
    sequence_num        BIGINT NOT NULL,

    event_hash          TEXT NOT NULL,    -- SHA-256 of the event payload
    previous_chain_hash TEXT,             -- NULL for GENESIS (first event in tenant chain)
    chain_hash          TEXT NOT NULL,    -- SHA-256(previous_chain_hash | event_hash)

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Enforce ordering per tenant
    UNIQUE (tenant_id, sequence_num)
);

-- --------------------------------------------------------
-- 4. Compliance Alerts — flagged issues per event
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.compliance_alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    cte_event_id        UUID NOT NULL REFERENCES fsma.cte_events(id) ON DELETE CASCADE,

    severity            TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
    alert_type          TEXT NOT NULL,    -- e.g. 'missing_kde', 'incomplete_route', 'time_violation'
    message             TEXT NOT NULL,

    resolved            BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at         TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------
-- 5. FDA Export Log — audit trail for every export
-- --------------------------------------------------------
-- Every time someone generates an FDA export, we log it.
-- Proves to auditors that exports were generated and when.

CREATE TABLE IF NOT EXISTS fsma.fda_export_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    export_type         TEXT NOT NULL DEFAULT 'fda_spreadsheet',
    query_tlc           TEXT,
    query_start_date    DATE,
    query_end_date      DATE,
    record_count        INTEGER NOT NULL DEFAULT 0,
    export_hash         TEXT NOT NULL,     -- SHA-256 of the generated export file
    generated_by        TEXT,              -- user or system that triggered export
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- --------------------------------------------------------
-- Indexes
-- --------------------------------------------------------

-- CTE Events: the queries that matter for FDA response
CREATE INDEX idx_cte_events_tenant          ON fsma.cte_events (tenant_id);
CREATE INDEX idx_cte_events_tlc             ON fsma.cte_events (traceability_lot_code);
CREATE INDEX idx_cte_events_type            ON fsma.cte_events (event_type);
CREATE INDEX idx_cte_events_timestamp       ON fsma.cte_events (event_timestamp DESC);
CREATE INDEX idx_cte_events_tenant_tlc      ON fsma.cte_events (tenant_id, traceability_lot_code);
CREATE INDEX idx_cte_events_tenant_type     ON fsma.cte_events (tenant_id, event_type);
CREATE INDEX idx_cte_events_idempotency     ON fsma.cte_events (idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX idx_cte_events_ingested        ON fsma.cte_events (ingested_at DESC);

-- KDEs: lookup by event
CREATE INDEX idx_cte_kdes_event             ON fsma.cte_kdes (cte_event_id);
CREATE INDEX idx_cte_kdes_tenant            ON fsma.cte_kdes (tenant_id);

-- Hash chain: verification queries
CREATE INDEX idx_hash_chain_tenant          ON fsma.hash_chain (tenant_id);
CREATE INDEX idx_hash_chain_tenant_seq      ON fsma.hash_chain (tenant_id, sequence_num DESC);
CREATE INDEX idx_hash_chain_event           ON fsma.hash_chain (cte_event_id);

-- Alerts: dashboard queries
CREATE INDEX idx_alerts_tenant              ON fsma.compliance_alerts (tenant_id);
CREATE INDEX idx_alerts_event               ON fsma.compliance_alerts (cte_event_id);
CREATE INDEX idx_alerts_unresolved          ON fsma.compliance_alerts (tenant_id, resolved) WHERE resolved = FALSE;

-- Export log
CREATE INDEX idx_export_log_tenant          ON fsma.fda_export_log (tenant_id);
CREATE INDEX idx_export_log_generated       ON fsma.fda_export_log (generated_at DESC);


-- --------------------------------------------------------
-- Row-Level Security (Double-Lock Isolation)
-- --------------------------------------------------------
-- Follows the existing RegEngine RLS pattern:
-- get_tenant_context() returns the current session's tenant UUID.

ALTER TABLE fsma.cte_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.cte_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_cte ON fsma.cte_events;
CREATE POLICY tenant_isolation_cte ON fsma.cte_events
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.cte_kdes ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.cte_kdes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_kdes ON fsma.cte_kdes;
CREATE POLICY tenant_isolation_kdes ON fsma.cte_kdes
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.hash_chain ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.hash_chain FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_chain ON fsma.hash_chain;
CREATE POLICY tenant_isolation_chain ON fsma.hash_chain
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.compliance_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.compliance_alerts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_alerts ON fsma.compliance_alerts;
CREATE POLICY tenant_isolation_alerts ON fsma.compliance_alerts
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.fda_export_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.fda_export_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_exports ON fsma.fda_export_log;
CREATE POLICY tenant_isolation_exports ON fsma.fda_export_log
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());


-- --------------------------------------------------------
-- Comments
-- --------------------------------------------------------

COMMENT ON SCHEMA fsma IS 'FSMA 204 compliance data — CTEs, KDEs, hash chain, exports';
COMMENT ON TABLE fsma.cte_events IS 'Critical Tracking Events — the core traceability record for every supply chain event';
COMMENT ON TABLE fsma.cte_kdes IS 'Key Data Elements — required and optional data attached to each CTE';
COMMENT ON TABLE fsma.hash_chain IS 'Tamper-evident hash chain — append-only ledger linking every CTE to its predecessor';
COMMENT ON TABLE fsma.compliance_alerts IS 'Compliance alerts — flagged issues (missing KDEs, broken chains, time violations)';
COMMENT ON TABLE fsma.fda_export_log IS 'FDA export audit log — records every export generated for regulatory response';

COMMENT ON COLUMN fsma.cte_events.sha256_hash IS 'SHA-256 hash of the event canonical form (pipe-delimited fields)';
COMMENT ON COLUMN fsma.cte_events.chain_hash IS 'SHA-256(previous_chain_hash | sha256_hash) — links to hash_chain table';
COMMENT ON COLUMN fsma.cte_events.idempotency_key IS 'Deduplication key — prevents double-ingestion of the same event';
COMMENT ON COLUMN fsma.hash_chain.previous_chain_hash IS 'NULL for chain genesis (first event per tenant)';

COMMIT;
