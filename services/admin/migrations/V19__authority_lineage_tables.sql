-- =============================================================================
-- V19: Authority & Fact Lineage Tables
-- =============================================================================
-- Creates the traceability chain from source authority documents through
-- extracted facts to audit verdicts.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Authority Documents
-- Source CBAs, regulations, statutes, municipal codes
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pcos_authority_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Document identification
    document_code VARCHAR(100) NOT NULL,  -- e.g., 'SAG_CBA_2023', 'CA_LABOR_CODE'
    document_name VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL,   -- 'cba', 'statute', 'regulation', 'municipal_code', 'internal_policy'
    
    -- Issuer information
    issuer_name VARCHAR(255) NOT NULL,    -- e.g., 'SAG-AFTRA', 'State of California'
    issuer_type VARCHAR(50),              -- 'union', 'government', 'municipality', 'internal'
    
    -- Validity period
    effective_date DATE NOT NULL,
    expiration_date DATE,
    supersedes_document_id UUID REFERENCES pcos_authority_documents(id),
    
    -- Document integrity
    document_hash VARCHAR(64),            -- SHA-256 hash of original document
    hash_algorithm VARCHAR(20) DEFAULT 'SHA-256',
    original_file_path TEXT,
    content_type VARCHAR(100),
    file_size_bytes BIGINT,
    
    -- Extraction metadata
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ingested_by UUID,
    extraction_method VARCHAR(50),        -- 'manual', 'ocr', 'api', 'scrape'
    extraction_notes TEXT,
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'superseded', 'expired', 'draft'
    verified_at TIMESTAMPTZ,
    verified_by UUID,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_authority_doc_code_tenant UNIQUE (tenant_id, document_code)
);

CREATE INDEX idx_authority_docs_tenant ON pcos_authority_documents(tenant_id);
CREATE INDEX idx_authority_docs_type ON pcos_authority_documents(document_type);
CREATE INDEX idx_authority_docs_issuer ON pcos_authority_documents(issuer_name);
CREATE INDEX idx_authority_docs_status ON pcos_authority_documents(status);
CREATE INDEX idx_authority_docs_effective ON pcos_authority_documents(effective_date);

-- -----------------------------------------------------------------------------
-- 2. Extracted Facts
-- Versioned, structured facts extracted from authority documents
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pcos_extracted_facts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    authority_document_id UUID NOT NULL REFERENCES pcos_authority_documents(id) ON DELETE CASCADE,
    
    -- Fact identification
    fact_key VARCHAR(100) NOT NULL,       -- e.g., 'SAG_MIN_DAY_RATE', 'IATSE_600_OT_MULT'
    fact_category VARCHAR(50) NOT NULL,    -- 'rate', 'threshold', 'deadline', 'requirement', 'exemption'
    fact_name VARCHAR(255) NOT NULL,
    fact_description TEXT,
    
    -- Fact value (polymorphic)
    fact_value_type VARCHAR(20) NOT NULL,  -- 'decimal', 'integer', 'string', 'boolean', 'date', 'json'
    fact_value_decimal DECIMAL(15, 4),
    fact_value_integer INTEGER,
    fact_value_string TEXT,
    fact_value_boolean BOOLEAN,
    fact_value_date DATE,
    fact_value_json JSONB,
    fact_unit VARCHAR(50),                 -- 'USD', 'percent', 'hours', 'days'
    
    -- Validity conditions (when this fact applies)
    validity_conditions JSONB NOT NULL DEFAULT '{}',
    -- Example: {"budget_min": 2000000, "budget_max": null, "date_after": "2025-07-01", "union": "SAG-AFTRA"}
    
    -- Version tracking
    version INTEGER NOT NULL DEFAULT 1,
    previous_fact_id UUID REFERENCES pcos_extracted_facts(id),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Extraction provenance
    source_page INTEGER,
    source_section VARCHAR(255),
    source_quote TEXT,                     -- Verbatim quote from source
    
    extraction_confidence DECIMAL(3, 2),   -- 0.00 to 1.00
    extraction_method VARCHAR(50),         -- 'manual', 'regex', 'nlp', 'structured'
    extraction_notes TEXT,
    
    -- Audit
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extracted_by UUID,
    verified_at TIMESTAMPTZ,
    verified_by UUID,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_fact_key_version UNIQUE (tenant_id, fact_key, version)
);

CREATE INDEX idx_extracted_facts_tenant ON pcos_extracted_facts(tenant_id);
CREATE INDEX idx_extracted_facts_authority ON pcos_extracted_facts(authority_document_id);
CREATE INDEX idx_extracted_facts_key ON pcos_extracted_facts(fact_key);
CREATE INDEX idx_extracted_facts_category ON pcos_extracted_facts(fact_category);
CREATE INDEX idx_extracted_facts_current ON pcos_extracted_facts(tenant_id, fact_key, is_current) WHERE is_current = TRUE;

-- -----------------------------------------------------------------------------
-- 3. Fact Citations
-- Links compliance verdicts/evaluations back to the facts they used
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pcos_fact_citations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- What is being cited (polymorphic reference)
    citing_entity_type VARCHAR(50) NOT NULL,   -- 'rule_evaluation', 'compliance_verdict', 'rate_check'
    citing_entity_id UUID NOT NULL,
    
    -- The fact being cited
    extracted_fact_id UUID NOT NULL REFERENCES pcos_extracted_facts(id) ON DELETE CASCADE,
    
    -- Citation context
    fact_value_used TEXT NOT NULL,             -- Copy of value at time of citation
    context_applied JSONB,                      -- Production context that matched the fact
    
    -- Citation purpose
    citation_type VARCHAR(50) NOT NULL,         -- 'rate_comparison', 'threshold_check', 'deadline_source', 'requirement_proof'
    citation_notes TEXT,
    
    -- Result of applying this fact
    evaluation_result VARCHAR(20),              -- 'pass', 'fail', 'warning', 'info'
    comparison_operator VARCHAR(20),            -- 'gte', 'lte', 'eq', 'contains'
    input_value TEXT,                           -- What was compared against the fact
    
    -- Timestamps
    cited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fact_citations_tenant ON pcos_fact_citations(tenant_id);
CREATE INDEX idx_fact_citations_entity ON pcos_fact_citations(citing_entity_type, citing_entity_id);
CREATE INDEX idx_fact_citations_fact ON pcos_fact_citations(extracted_fact_id);

-- -----------------------------------------------------------------------------
-- 4. Seed: Common Authority Document Types
-- -----------------------------------------------------------------------------
INSERT INTO pcos_authority_documents (
    id, tenant_id, document_code, document_name, document_type,
    issuer_name, issuer_type, effective_date, status
) VALUES
    -- SAG-AFTRA CBA
    (
        uuid_generate_v4(),
        (SELECT id FROM tenants LIMIT 1),
        'SAG_CBA_2023',
        'SAG-AFTRA Theatrical and Television Basic Agreement 2023-2026',
        'cba',
        'SAG-AFTRA',
        'union',
        '2023-07-01',
        'active'
    ),
    -- DGA CBA
    (
        uuid_generate_v4(),
        (SELECT id FROM tenants LIMIT 1),
        'DGA_CBA_2023',
        'DGA Basic Agreement 2023-2026',
        'cba',
        'Directors Guild of America',
        'union',
        '2023-07-01',
        'active'
    ),
    -- CA Labor Code
    (
        uuid_generate_v4(),
        (SELECT id FROM tenants LIMIT 1),
        'CA_LABOR_CODE_AB5',
        'California Labor Code - AB5 Worker Classification',
        'statute',
        'State of California',
        'government',
        '2020-01-01',
        'active'
    ),
    -- FilmLA Requirements
    (
        uuid_generate_v4(),
        (SELECT id FROM tenants LIMIT 1),
        'FILMLA_PERMIT_REQS_2024',
        'FilmL.A. Permit Requirements 2024',
        'municipal_code',
        'FilmL.A.',
        'municipality',
        '2024-01-01',
        'active'
    )
ON CONFLICT DO NOTHING;

-- -----------------------------------------------------------------------------
-- 5. RLS Policies
-- -----------------------------------------------------------------------------
ALTER TABLE pcos_authority_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_extracted_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_fact_citations ENABLE ROW LEVEL SECURITY;

-- Authority Documents RLS
CREATE POLICY pcos_authority_documents_tenant_isolation ON pcos_authority_documents
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- Extracted Facts RLS
CREATE POLICY pcos_extracted_facts_tenant_isolation ON pcos_extracted_facts
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- Fact Citations RLS
CREATE POLICY pcos_fact_citations_tenant_isolation ON pcos_fact_citations
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- -----------------------------------------------------------------------------
-- 6. Updated timestamp trigger
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_authority_lineage_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_authority_documents_updated
    BEFORE UPDATE ON pcos_authority_documents
    FOR EACH ROW EXECUTE FUNCTION update_authority_lineage_timestamp();

CREATE TRIGGER trg_extracted_facts_updated
    BEFORE UPDATE ON pcos_extracted_facts
    FOR EACH ROW EXECUTE FUNCTION update_authority_lineage_timestamp();
