
-- Canonical traceability events table (new ingestion path)
CREATE TABLE IF NOT EXISTS fsma.traceability_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    source_system   TEXT NOT NULL,
    source_record_id TEXT,
    source_file_id  UUID,
    ingestion_run_id UUID,
    event_type      TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    event_timezone  TEXT,
    product_reference TEXT,
    lot_reference   TEXT,
    traceability_lot_code TEXT,
    quantity        NUMERIC,
    unit_of_measure TEXT,
    from_entity_reference TEXT,
    to_entity_reference   TEXT,
    from_facility_reference TEXT,
    to_facility_reference   TEXT,
    transport_reference TEXT,
    kdes            JSONB DEFAULT '{}',
    raw_payload     JSONB DEFAULT '{}',
    normalized_payload JSONB DEFAULT '{}',
    provenance_metadata JSONB DEFAULT '{}',
    confidence_score NUMERIC DEFAULT 1.0,
    status          TEXT DEFAULT 'active',
    supersedes_event_id UUID,
    schema_version  TEXT DEFAULT '1.0',
    sha256_hash     TEXT,
    chain_hash      TEXT,
    idempotency_key TEXT,
    epcis_event_type TEXT,
    epcis_action    TEXT,
    epcis_biz_step  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    amended_at      TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_te_tenant_id ON fsma.traceability_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_te_tlc ON fsma.traceability_events(traceability_lot_code);
CREATE INDEX IF NOT EXISTS idx_te_idempotency ON fsma.traceability_events(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_te_tenant_tlc ON fsma.traceability_events(tenant_id, traceability_lot_code);
CREATE INDEX IF NOT EXISTS idx_te_tenant_status ON fsma.traceability_events(tenant_id, status);

-- Ingestion runs tracking table
CREATE TABLE IF NOT EXISTS fsma.ingestion_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    source_system   TEXT NOT NULL,
    source_file_name TEXT,
    source_file_hash TEXT,
    source_file_size BIGINT,
    record_count    INT,
    mapper_version  TEXT,
    schema_version  TEXT,
    status          TEXT DEFAULT 'pending',
    initiated_by    TEXT,
    accepted_count  INT DEFAULT 0,
    rejected_count  INT DEFAULT 0,
    errors          JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ir_tenant_id ON fsma.ingestion_runs(tenant_id);
;
