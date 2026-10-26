
CREATE TABLE IF NOT EXISTS fsma.transformation_links (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               TEXT NOT NULL,
    transformation_event_id UUID NOT NULL,
    input_tlc               TEXT NOT NULL,
    input_event_id          UUID,
    output_tlc              TEXT NOT NULL,
    output_event_id         UUID,
    input_quantity          NUMERIC,
    input_unit              TEXT,
    output_quantity         NUMERIC,
    output_unit             TEXT,
    process_type            TEXT,
    confidence_score        NUMERIC DEFAULT 1.0,
    link_source             TEXT DEFAULT 'explicit',
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, transformation_event_id, input_tlc, output_tlc)
);

CREATE INDEX IF NOT EXISTS idx_tl_input_tlc ON fsma.transformation_links (tenant_id, input_tlc);
CREATE INDEX IF NOT EXISTS idx_tl_output_tlc ON fsma.transformation_links (tenant_id, output_tlc);
CREATE INDEX IF NOT EXISTS idx_tl_event ON fsma.transformation_links (transformation_event_id);
CREATE INDEX IF NOT EXISTS idx_tl_tenant ON fsma.transformation_links (tenant_id);

ALTER TABLE fsma.transformation_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.transformation_links FORCE ROW LEVEL SECURITY;
;
