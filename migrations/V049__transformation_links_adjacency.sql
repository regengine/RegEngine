-- ==========================================
-- RegEngine: Transformation Links Adjacency Table
-- Migration V049: Lot-to-Lot Ingredient Traceability
-- ==========================================
-- FSMA 204 requires one-up/one-back traceability for all CTEs.
-- For transformation events (e.g., spinach + kale -> salad kit),
-- we need to record which input TLCs became which output TLCs.
--
-- This adjacency table enables:
-- 1. Forward trace: "What finished products contain this lot?"
-- 2. Backward trace: "What ingredients went into this product?"
-- 3. Mass balance: "Do input quantities equal output quantities?"
-- 4. Graph traversal: Multi-hop recall scope (spinach -> salad -> shipped pallets)

BEGIN;

CREATE TABLE IF NOT EXISTS fsma.transformation_links (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               TEXT NOT NULL,

    -- The transformation event that created this link
    transformation_event_id UUID NOT NULL,

    -- Input (ingredient/source) lot
    input_tlc               TEXT NOT NULL,
    input_event_id          UUID,

    -- Output (product/result) lot
    output_tlc              TEXT NOT NULL,
    output_event_id         UUID,

    -- Quantity tracking for mass balance
    input_quantity          NUMERIC,
    input_unit              TEXT,
    output_quantity         NUMERIC,
    output_unit             TEXT,

    -- Metadata
    process_type            TEXT,
    confidence_score        NUMERIC DEFAULT 1.0,
    link_source             TEXT DEFAULT 'explicit',
    notes                   TEXT,

    -- Audit
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (tenant_id, transformation_event_id, input_tlc, output_tlc)
);

-- Forward trace: "What products contain this input lot?"
CREATE INDEX IF NOT EXISTS idx_tl_input_tlc
    ON fsma.transformation_links (tenant_id, input_tlc);

-- Backward trace: "What ingredients went into this output lot?"
CREATE INDEX IF NOT EXISTS idx_tl_output_tlc
    ON fsma.transformation_links (tenant_id, output_tlc);

CREATE INDEX IF NOT EXISTS idx_tl_event
    ON fsma.transformation_links (transformation_event_id);

CREATE INDEX IF NOT EXISTS idx_tl_tenant
    ON fsma.transformation_links (tenant_id);

ALTER TABLE fsma.transformation_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.transformation_links FORCE ROW LEVEL SECURITY;

COMMENT ON TABLE fsma.transformation_links IS
    'Lot-to-lot adjacency table for FSMA 204 transformation traceability. '
    'Each row = one input TLC contributing to one output TLC via a transformation event. '
    'Enables forward/backward trace and mass balance checks.';

COMMIT;
