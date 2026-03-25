-- ==========================================
-- RegEngine: Shared Identity Resolution Layer
-- Migration V047: Cross-Record Identity for Entities, Facilities, Products, Lots
-- ==========================================
-- Creates a durable identity layer that resolves aliases, tracks merges,
-- and provides canonical IDs across all traceability records.

BEGIN;

-- --------------------------------------------------------
-- 1. Canonical Entities — master records for firms, facilities, products, lots
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.canonical_entities (
    entity_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    entity_type         TEXT NOT NULL CHECK (entity_type IN (
                            'firm', 'facility', 'product', 'lot',
                            'trading_relationship'
                        )),

    -- Canonical identifiers
    canonical_name      TEXT NOT NULL,
    gln                 TEXT,                    -- GS1 Global Location Number (facilities)
    gtin                TEXT,                    -- GS1 GTIN (products)
    fda_registration    TEXT,                    -- FDA facility registration
    internal_id         TEXT,                    -- customer's internal code

    -- Contact / address
    address             TEXT,
    city                TEXT,
    state               TEXT,
    country             TEXT DEFAULT 'US',
    contact_name        TEXT,
    contact_phone       TEXT,
    contact_email       TEXT,

    -- Metadata
    verification_status TEXT NOT NULL DEFAULT 'unverified'
                        CHECK (verification_status IN (
                            'verified', 'unverified', 'pending_review'
                        )),
    confidence_score    DOUBLE PRECISION DEFAULT 1.0
                        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          TEXT,
    verified_by         TEXT,
    verified_at         TIMESTAMPTZ
);

-- --------------------------------------------------------
-- 2. Entity Aliases — alternate identifiers for the same entity
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.entity_aliases (
    alias_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    entity_id           UUID NOT NULL REFERENCES fsma.canonical_entities(entity_id),

    alias_type          TEXT NOT NULL CHECK (alias_type IN (
                            'name', 'gln', 'gtin', 'fda_registration',
                            'internal_code', 'duns', 'tlc_prefix',
                            'address_variant', 'abbreviation', 'trade_name'
                        )),
    alias_value         TEXT NOT NULL,
    source_system       TEXT,                    -- where this alias was first seen
    source_file         TEXT,

    -- Quality
    confidence          DOUBLE PRECISION DEFAULT 1.0
                        CHECK (confidence >= 0.0 AND confidence <= 1.0),

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          TEXT,

    -- Prevent duplicate aliases for the same entity
    UNIQUE (entity_id, alias_type, alias_value)
);

-- --------------------------------------------------------
-- 3. Entity Merge History — reversible merge/split log
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.entity_merge_history (
    merge_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    action              TEXT NOT NULL CHECK (action IN ('merge', 'split', 'undo_merge')),

    -- For merge: source entities merged into target
    -- For split: source entity split into targets
    source_entity_ids   UUID[] NOT NULL,
    target_entity_id    UUID NOT NULL REFERENCES fsma.canonical_entities(entity_id),

    reason              TEXT,
    performed_by        TEXT NOT NULL,
    performed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Undo support
    is_reversed         BOOLEAN NOT NULL DEFAULT FALSE,
    reversed_by         TEXT,
    reversed_at         TIMESTAMPTZ
);

-- --------------------------------------------------------
-- 4. Identity Review Queue — ambiguous matches for human review
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS fsma.identity_review_queue (
    review_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,

    -- Candidate entities
    entity_a_id         UUID NOT NULL REFERENCES fsma.canonical_entities(entity_id),
    entity_b_id         UUID NOT NULL REFERENCES fsma.canonical_entities(entity_id),

    -- Match assessment
    match_type          TEXT NOT NULL CHECK (match_type IN (
                            'exact', 'likely', 'ambiguous', 'unresolved'
                        )),
    match_confidence    DOUBLE PRECISION NOT NULL
                        CHECK (match_confidence >= 0.0 AND match_confidence <= 1.0),

    -- Matching evidence
    matching_fields     JSONB DEFAULT '[]'::jsonb,
    -- [{"field": "name", "a_value": "ABC Foods", "b_value": "ABC Foods Inc", "similarity": 0.92}]

    -- Resolution
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'confirmed_match', 'confirmed_distinct', 'deferred')),
    resolved_by         TEXT,
    resolved_at         TIMESTAMPTZ,
    resolution_notes    TEXT,

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate review pairs
    UNIQUE (entity_a_id, entity_b_id)
);


-- --------------------------------------------------------
-- Indexes
-- --------------------------------------------------------

-- Canonical entities
CREATE INDEX IF NOT EXISTS idx_canonical_entities_tenant
    ON fsma.canonical_entities (tenant_id);
CREATE INDEX IF NOT EXISTS idx_canonical_entities_type
    ON fsma.canonical_entities (tenant_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_canonical_entities_gln
    ON fsma.canonical_entities (gln)
    WHERE gln IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_entities_gtin
    ON fsma.canonical_entities (gtin)
    WHERE gtin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_entities_name
    ON fsma.canonical_entities (tenant_id, canonical_name);
CREATE INDEX IF NOT EXISTS idx_canonical_entities_fda_reg
    ON fsma.canonical_entities (fda_registration)
    WHERE fda_registration IS NOT NULL;

-- Entity aliases
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity
    ON fsma.entity_aliases (entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_tenant
    ON fsma.entity_aliases (tenant_id);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_value
    ON fsma.entity_aliases (alias_type, alias_value);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_lookup
    ON fsma.entity_aliases (tenant_id, alias_type, alias_value);

-- Merge history
CREATE INDEX IF NOT EXISTS idx_merge_history_tenant
    ON fsma.entity_merge_history (tenant_id);
CREATE INDEX IF NOT EXISTS idx_merge_history_target
    ON fsma.entity_merge_history (target_entity_id);

-- Review queue
CREATE INDEX IF NOT EXISTS idx_identity_review_tenant
    ON fsma.identity_review_queue (tenant_id);
CREATE INDEX IF NOT EXISTS idx_identity_review_pending
    ON fsma.identity_review_queue (tenant_id, status)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_identity_review_confidence
    ON fsma.identity_review_queue (match_confidence DESC)
    WHERE status = 'pending';


-- --------------------------------------------------------
-- Row-Level Security
-- --------------------------------------------------------

ALTER TABLE fsma.canonical_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.canonical_entities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_canonical_entities ON fsma.canonical_entities;
CREATE POLICY tenant_isolation_canonical_entities ON fsma.canonical_entities
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.entity_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.entity_aliases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_entity_aliases ON fsma.entity_aliases;
CREATE POLICY tenant_isolation_entity_aliases ON fsma.entity_aliases
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.entity_merge_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.entity_merge_history FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_merge_history ON fsma.entity_merge_history;
CREATE POLICY tenant_isolation_merge_history ON fsma.entity_merge_history
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());

ALTER TABLE fsma.identity_review_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.identity_review_queue FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_identity_review ON fsma.identity_review_queue;
CREATE POLICY tenant_isolation_identity_review ON fsma.identity_review_queue
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context());


-- --------------------------------------------------------
-- Comments
-- --------------------------------------------------------

COMMENT ON TABLE fsma.canonical_entities IS
    'Master entity records — canonical IDs for firms, facilities, products, and lots. '
    'All traceability views resolve through this table.';
COMMENT ON TABLE fsma.entity_aliases IS
    'Alternate identifiers for the same entity — names, GLNs, internal codes, abbreviations. '
    'Enables cross-supplier and cross-format linkage.';
COMMENT ON TABLE fsma.entity_merge_history IS
    'Reversible merge/split log — every identity resolution action is auditable and undoable.';
COMMENT ON TABLE fsma.identity_review_queue IS
    'Ambiguous match queue for human review — confidence-scored candidates awaiting resolution.';

COMMIT;
