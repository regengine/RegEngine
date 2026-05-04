-- ==========================================
-- RegEngine: Canonical TraceabilityEvent Model
-- Migration V043: Compliance Control Plane Foundation
-- ==========================================
-- Creates the canonical event store that ALL ingestion paths normalize into.
-- This is the single internal truth model for FSMA 204 compliance operations.
--
-- Design principles:
--   1. Every record preserves raw source alongside normalized form
--   2. Every record carries provenance metadata (who, when, how, what version)
--   3. Amendment chains are explicit (supersedes_event_id)
--   4. Schema is versioned for forward compatibility
--   5. KDEs are structured JSONB, not key-value, for queryability
--
-- Relationship to existing tables:
--   fsma.cte_events    — remains as legacy write target during migration period
--   fsma.cte_kdes      — replaced by traceability_events.kdes JSONB column
--   fsma.hash_chain    — unchanged, entries reference traceability_events.event_id
--   fsma.compliance_alerts — will be superseded by rule_evaluations (V044)

BEGIN;

-- --------------------------------------------------------
-- 1. Ingestion Runs — batch provenance per import
-- --------------------------------------------------------
-- Every file upload, API call, or EPCIS document creates one ingestion run.
-- This is the "receipt" for a batch of records entering the system.

CREATE TABLE IF NOT EXISTS fsma.ingestion_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    -- Source identification
    source_system       TEXT NOT NULL,           -- 'webhook_api', 'csv_upload', 'xlsx_upload', 'epcis_api', 'edi', 'manual'
    source_file_name    TEXT,                    -- original filename if file upload
    source_file_hash    TEXT,                    -- SHA-256 of uploaded file
    source_file_size    BIGINT,                  -- bytes

    -- Batch metadata
    record_count        INTEGER NOT NULL DEFAULT 0,
    accepted_count      INTEGER NOT NULL DEFAULT 0,
    rejected_count      INTEGER NOT NULL DEFAULT 0,

    -- Mapper versioning
    mapper_version      TEXT NOT NULL DEFAULT '1.0.0',
    schema_version      TEXT NOT NULL DEFAULT '1.0.0',

    -- Processing state
    status              TEXT NOT NULL DEFAULT 'processing'
                        CHECK (status IN ('processing', 'completed', 'partial', 'failed')),

    -- Audit
    initiated_by        TEXT,                    -- user or system identity
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,

    -- Error tracking
    errors              JSONB DEFAULT '[]'::jsonb
);

-- --------------------------------------------------------
-- 2. Traceability Events — the canonical truth layer
-- --------------------------------------------------------
-- This is the ONE object that every ingestion path normalizes into.
-- Downstream services (rules engine, export, graph sync) consume
-- ONLY this model — never format-specific payloads.

CREATE TABLE IF NOT EXISTS fsma.traceability_events (
    -- Identity
    event_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    -- Source provenance
    source_system       TEXT NOT NULL,           -- 'webhook_api', 'csv_upload', 'epcis_api', etc.
    source_record_id    TEXT,                    -- ID in the originating system
    source_file_id      UUID,                    -- FK to ingestion_runs if from file import
    ingestion_run_id    UUID REFERENCES fsma.ingestion_runs(id),

    -- Event classification
    event_type          TEXT NOT NULL CHECK (event_type IN (
                            'harvesting', 'cooling', 'initial_packing',
                            'first_land_based_receiving',
                            'shipping', 'receiving', 'transformation'
                        )),

    -- Temporal
    event_timestamp     TIMESTAMPTZ NOT NULL,
    event_timezone      TEXT DEFAULT 'UTC',

    -- Product + Lot references
    product_reference   TEXT,                    -- product description or GTIN
    lot_reference       TEXT,                    -- lot/batch ID
    traceability_lot_code TEXT NOT NULL,
    quantity            DOUBLE PRECISION NOT NULL CHECK (quantity > 0),
    unit_of_measure     TEXT NOT NULL,

    -- Entity + Facility references (will resolve to canonical IDs in V047)
    from_entity_reference   TEXT,                -- shipper / source firm name or ID
    to_entity_reference     TEXT,                -- receiver firm name or ID
    from_facility_reference TEXT,                -- ship-from GLN, name, or ID
    to_facility_reference   TEXT,                -- ship-to GLN, name, or ID

    -- Transport
    transport_reference TEXT,                    -- BOL, carrier, SSCC

    -- Structured KDEs (replaces key-value cte_kdes table)
    kdes                JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Dual payload preservation: raw + normalized
    raw_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,    -- verbatim source record
    normalized_payload  JSONB NOT NULL DEFAULT '{}'::jsonb,    -- canonical form after normalization

    -- Provenance metadata
    provenance_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Expected structure:
    -- {
    --   "source_file_hash": "sha256...",
    --   "ingestion_timestamp": "ISO8601",
    --   "mapper_name": "webhook_v2_normalizer",
    --   "mapper_version": "1.0.0",
    --   "normalization_rules_applied": ["gln_check_digit", "timestamp_utc_normalize"],
    --   "original_format": "json",
    --   "extraction_confidence": 0.95
    -- }

    -- Quality signals
    confidence_score    DOUBLE PRECISION DEFAULT 1.0
                        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'superseded', 'rejected', 'draft')),

    -- Amendment chain
    supersedes_event_id UUID REFERENCES fsma.traceability_events(event_id),

    -- Schema versioning
    schema_version      TEXT NOT NULL DEFAULT '1.0.0',

    -- Integrity (links to fsma.hash_chain)
    sha256_hash         TEXT,
    chain_hash          TEXT,
    idempotency_key     TEXT,

    -- EPCIS interop (nullable — only for EPCIS-ingested events)
    epcis_event_type    TEXT,
    epcis_action        TEXT,
    epcis_biz_step      TEXT,

    -- Audit timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    amended_at          TIMESTAMPTZ,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------
-- 3. Evidence Attachments — source documents linked to events
-- --------------------------------------------------------
-- BOLs, invoices, lab reports, photos, temperature logs.
-- These are the artifacts that prove the event happened.

CREATE TABLE IF NOT EXISTS fsma.evidence_attachments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    -- Link to canonical event(s)
    event_id            UUID NOT NULL REFERENCES fsma.traceability_events(event_id),

    -- Document metadata
    document_type       TEXT NOT NULL,           -- 'bol', 'invoice', 'lab_report', 'photo', 'temperature_log', 'production_record'
    file_name           TEXT,
    file_hash           TEXT,                    -- SHA-256 of file content
    file_size           BIGINT,
    mime_type           TEXT,

    -- Storage reference
    storage_uri         TEXT,                    -- MinIO/S3 URI
    storage_bucket      TEXT,

    -- Extraction results (if NLP/OCR processed)
    extracted_data      JSONB DEFAULT '{}'::jsonb,
    extraction_status   TEXT DEFAULT 'pending'
                        CHECK (extraction_status IN ('pending', 'processing', 'completed', 'failed', 'not_applicable')),

    -- Audit
    uploaded_by         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- --------------------------------------------------------
-- Indexes
-- --------------------------------------------------------

-- Ingestion Runs
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_tenant
    ON fsma.ingestion_runs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status
    ON fsma.ingestion_runs (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_started
    ON fsma.ingestion_runs (started_at DESC);

-- Traceability Events: primary query patterns
CREATE INDEX IF NOT EXISTS idx_trace_events_tenant
    ON fsma.traceability_events (tenant_id);
CREATE INDEX IF NOT EXISTS idx_trace_events_tlc
    ON fsma.traceability_events (traceability_lot_code);
CREATE INDEX IF NOT EXISTS idx_trace_events_tenant_tlc
    ON fsma.traceability_events (tenant_id, traceability_lot_code);
CREATE INDEX IF NOT EXISTS idx_trace_events_type
    ON fsma.traceability_events (event_type);
CREATE INDEX IF NOT EXISTS idx_trace_events_tenant_type
    ON fsma.traceability_events (tenant_id, event_type);
CREATE INDEX IF NOT EXISTS idx_trace_events_timestamp
    ON fsma.traceability_events (event_timestamp DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_traceability_events_tenant_idempotency_key
    ON fsma.traceability_events (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_trace_events_ingested
    ON fsma.traceability_events (ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_trace_events_status
    ON fsma.traceability_events (tenant_id, status)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_trace_events_supersedes
    ON fsma.traceability_events (supersedes_event_id)
    WHERE supersedes_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trace_events_ingestion_run
    ON fsma.traceability_events (ingestion_run_id)
    WHERE ingestion_run_id IS NOT NULL;
-- GIN index for JSONB KDE queries (e.g., WHERE kdes @> '{"harvest_date": "2026-01-15"}')
CREATE INDEX IF NOT EXISTS idx_trace_events_kdes
    ON fsma.traceability_events USING GIN (kdes);
-- GIN index for provenance queries
CREATE INDEX IF NOT EXISTS idx_trace_events_provenance
    ON fsma.traceability_events USING GIN (provenance_metadata);

-- Evidence Attachments
CREATE INDEX IF NOT EXISTS idx_evidence_event
    ON fsma.evidence_attachments (event_id);
CREATE INDEX IF NOT EXISTS idx_evidence_tenant
    ON fsma.evidence_attachments (tenant_id);
CREATE INDEX IF NOT EXISTS idx_evidence_type
    ON fsma.evidence_attachments (tenant_id, document_type);


-- --------------------------------------------------------
-- Row-Level Security
-- --------------------------------------------------------

ALTER TABLE fsma.ingestion_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.ingestion_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_ingestion_runs ON fsma.ingestion_runs;
CREATE POLICY tenant_isolation_ingestion_runs ON fsma.ingestion_runs
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid);

ALTER TABLE fsma.traceability_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.traceability_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_trace_events ON fsma.traceability_events;
CREATE POLICY tenant_isolation_trace_events ON fsma.traceability_events
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid);

ALTER TABLE fsma.evidence_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.evidence_attachments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_evidence ON fsma.evidence_attachments;
CREATE POLICY tenant_isolation_evidence ON fsma.evidence_attachments
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid);


-- --------------------------------------------------------
-- Comments
-- --------------------------------------------------------

COMMENT ON TABLE fsma.ingestion_runs IS
    'Batch provenance — one row per file upload, API call, or EPCIS document import';
COMMENT ON TABLE fsma.traceability_events IS
    'Canonical traceability event — the ONE internal truth model for all FSMA 204 records. '
    'Every ingestion path normalizes into this table. Downstream services consume only this model.';
COMMENT ON TABLE fsma.evidence_attachments IS
    'Source documents (BOLs, invoices, lab reports) linked to canonical events for evidentiary chain';

COMMENT ON COLUMN fsma.traceability_events.raw_payload IS
    'Verbatim source record as received — never modified after ingestion';
COMMENT ON COLUMN fsma.traceability_events.normalized_payload IS
    'Canonical form after normalization — the version used by all downstream services';
COMMENT ON COLUMN fsma.traceability_events.supersedes_event_id IS
    'Points to the event this record amends — creates an explicit amendment chain';
COMMENT ON COLUMN fsma.traceability_events.schema_version IS
    'Version of the canonical schema used to normalize this event — enables forward-compatible migrations';
COMMENT ON COLUMN fsma.traceability_events.provenance_metadata IS
    'Structured provenance: source file hash, mapper version, normalization rules applied, extraction confidence';
COMMENT ON COLUMN fsma.traceability_events.kdes IS
    'Structured JSONB key data elements — replaces the cte_kdes key-value table for queryability';
COMMENT ON COLUMN fsma.traceability_events.confidence_score IS
    'Normalization confidence: 1.0 = exact mapping, lower values indicate inference or ambiguity';

COMMIT;
