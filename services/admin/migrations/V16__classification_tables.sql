-- V16: Worker Classification & ABC Test Tables
-- CA AB5 classification analysis for contractor vs employee determination

-- ============================================================================
-- Table: pcos_classification_analyses
-- Purpose: Store detailed ABC Test analysis for each engagement
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_classification_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    engagement_id UUID NOT NULL REFERENCES pcos_engagements(id) ON DELETE CASCADE,
    
    -- Analysis metadata
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analyzed_by UUID REFERENCES users(id),
    rule_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    
    -- ABC Test Results
    -- Prong A: Free from control and direction
    prong_a_passed BOOLEAN,
    prong_a_score INTEGER,  -- 0-100
    prong_a_factors JSONB DEFAULT '{}',
    prong_a_reasoning TEXT,
    
    -- Prong B: Work outside usual course of business
    prong_b_passed BOOLEAN,
    prong_b_score INTEGER,
    prong_b_factors JSONB DEFAULT '{}',
    prong_b_reasoning TEXT,
    prong_b_questionnaire_completed BOOLEAN DEFAULT FALSE,
    
    -- Prong C: Customarily engaged in independent trade
    prong_c_passed BOOLEAN,
    prong_c_score INTEGER,
    prong_c_factors JSONB DEFAULT '{}',
    prong_c_reasoning TEXT,
    
    -- Overall determination
    overall_result VARCHAR(30) NOT NULL,  -- 'employee', 'contractor', 'uncertain'
    overall_score INTEGER NOT NULL,  -- 0-100 (higher = more likely contractor)
    confidence_level VARCHAR(20) NOT NULL DEFAULT 'medium',  -- low, medium, high
    
    -- Risk assessment
    risk_level VARCHAR(20) NOT NULL DEFAULT 'medium',  -- low, medium, high, critical
    risk_factors JSONB DEFAULT '[]',
    recommended_action VARCHAR(100),
    
    -- Industry exemption check (CA AB5 has exemptions for certain roles)
    exemption_applicable BOOLEAN DEFAULT FALSE,
    exemption_type VARCHAR(100),
    exemption_reasoning TEXT,
    
    -- Evidence and documentation
    supporting_evidence JSONB DEFAULT '[]',
    notes TEXT,
    
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT chk_overall_result CHECK (overall_result IN ('employee', 'contractor', 'uncertain')),
    CONSTRAINT chk_confidence_level CHECK (confidence_level IN ('low', 'medium', 'high')),
    CONSTRAINT chk_risk_level CHECK (risk_level IN ('low', 'medium', 'high', 'critical'))
);

-- ============================================================================
-- Table: pcos_abc_questionnaire_responses
-- Purpose: Store detailed questionnaire responses for Prong B analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_abc_questionnaire_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    analysis_id UUID NOT NULL REFERENCES pcos_classification_analyses(id) ON DELETE CASCADE,
    
    -- Question tracking
    question_code VARCHAR(50) NOT NULL,
    question_text TEXT NOT NULL,
    question_category VARCHAR(50) NOT NULL,  -- 'control', 'integration', 'skill', 'investment'
    
    -- Response
    response_value VARCHAR(50),  -- 'yes', 'no', 'partial', 'unknown'
    response_details TEXT,
    response_weight INTEGER DEFAULT 1,  -- Weight for scoring
    
    -- Impact
    supports_contractor BOOLEAN,
    impact_score INTEGER,  -- -100 to +100 (negative = employee, positive = contractor)
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Table: pcos_classification_exemptions
-- Purpose: Store CA AB5 exemption rules
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_classification_exemptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Exemption identification
    exemption_code VARCHAR(50) NOT NULL UNIQUE,
    exemption_name VARCHAR(255) NOT NULL,
    exemption_category VARCHAR(100) NOT NULL,  -- 'professional', 'business', 'creative', 'other'
    
    -- Qualifying criteria
    qualifying_criteria JSONB NOT NULL,
    /*
    Example:
    {
        "role_keywords": ["photographer", "videographer", "editor"],
        "license_required": false,
        "business_entity_required": true,
        "written_contract_required": true,
        "rate_negotiation_required": true
    }
    */
    
    -- Documentation
    description TEXT,
    legal_reference VARCHAR(255),  -- e.g., "CA Labor Code §2750.3"
    effective_date DATE,
    
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_classification_tenant ON pcos_classification_analyses(tenant_id);
CREATE INDEX IF NOT EXISTS idx_classification_engagement ON pcos_classification_analyses(engagement_id);
CREATE INDEX IF NOT EXISTS idx_classification_result ON pcos_classification_analyses(overall_result);
CREATE INDEX IF NOT EXISTS idx_classification_risk ON pcos_classification_analyses(risk_level);

CREATE INDEX IF NOT EXISTS idx_questionnaire_analysis ON pcos_abc_questionnaire_responses(analysis_id);
CREATE INDEX IF NOT EXISTS idx_questionnaire_tenant ON pcos_abc_questionnaire_responses(tenant_id);

CREATE INDEX IF NOT EXISTS idx_exemptions_code ON pcos_classification_exemptions(exemption_code);
CREATE INDEX IF NOT EXISTS idx_exemptions_category ON pcos_classification_exemptions(exemption_category);

-- ============================================================================
-- Row Level Security
-- ============================================================================
ALTER TABLE pcos_classification_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_abc_questionnaire_responses ENABLE ROW LEVEL SECURITY;

CREATE POLICY classification_tenant_isolation ON pcos_classification_analyses
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY classification_insert ON pcos_classification_analyses
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY classification_update ON pcos_classification_analyses
    FOR UPDATE USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY classification_delete ON pcos_classification_analyses
    FOR DELETE USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY questionnaire_tenant_isolation ON pcos_abc_questionnaire_responses
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY questionnaire_insert ON pcos_abc_questionnaire_responses
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

-- ============================================================================
-- Seed AB5 Exemptions for Film/Entertainment Industry
-- ============================================================================
INSERT INTO pcos_classification_exemptions (
    exemption_code, exemption_name, exemption_category, qualifying_criteria, description, legal_reference
) VALUES
-- Professional Services Exemption (Borello Test applies instead of ABC)
('PRO_SERVICES', 'Professional Services', 'professional',
 '{"role_keywords": ["writer", "editor", "marketing", "consultant"], "license_required": false, "business_entity_required": true, "written_contract_required": true, "rate_negotiation_required": true, "deadlines_not_dictated": true}'::jsonb,
 'Business-to-business professional services exemption under AB5',
 'CA Labor Code §2750.3(c)(1)'),

-- Fine Artist Exemption
('FINE_ARTIST', 'Fine Artist', 'creative',
 '{"role_keywords": ["fine artist", "sculptor", "painter"], "creates_original_works": true, "sells_or_licenses_work": true}'::jsonb,
 'Fine artists who create, exhibit, or sell original works of art',
 'CA Labor Code §2750.3(c)(2)'),

-- Photographer/Videographer Exemption
('PHOTO_VIDEO', 'Photographer/Videographer', 'creative',
 '{"role_keywords": ["photographer", "photojournalist", "videographer", "photo editor"], "business_entity_required": true, "written_contract_required": true, "owns_equipment": true}'::jsonb,
 'Still photographers, photojournalists, videographers, and photo editors',
 'CA Labor Code §2750.3(c)(2)'),

-- Music Industry Exemption
('MUSIC_INDUSTRY', 'Music Professional', 'creative',
 '{"role_keywords": ["musician", "composer", "singer", "songwriter", "recording artist", "music producer", "music director", "remix artist"], "written_contract_required": true}'::jsonb,
 'Musicians, composers, and music industry professionals',
 'CA Labor Code §2750.3(c)(2)'),

-- Licensed Professional Exemption
('LICENSED_PRO', 'Licensed Professional', 'professional',
 '{"role_keywords": ["accountant", "attorney", "architect", "engineer", "registered nurse"], "license_required": true, "independent_judgment": true}'::jsonb,
 'State-licensed professionals maintaining independent practice',
 'CA Labor Code §2750.3(b)'),

-- Direct Sales Exemption  
('DIRECT_SALES', 'Direct Sales', 'business',
 '{"role_keywords": ["sales representative", "sales agent"], "commission_based": true, "written_contract_required": true}'::jsonb,
 'Direct sales representatives with commission-based compensation',
 'CA Labor Code §2750.3(d)'),

-- Freelance Writer/Editor Exemption (with limits)
('FREELANCE_WRITER', 'Freelance Writer (Limited)', 'creative',
 '{"role_keywords": ["writer", "editor", "newspaper", "magazine", "content"], "submission_limit": 35, "written_contract_required": true}'::jsonb,
 'Freelance writers/editors with 35 or fewer submissions per year to a single outlet',
 'CA Labor Code §2750.3(c)(2)')

ON CONFLICT (exemption_code) DO NOTHING;

-- ============================================================================
-- Update trigger
-- ============================================================================
CREATE OR REPLACE FUNCTION update_classification_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_classification_updated
    BEFORE UPDATE ON pcos_classification_analyses
    FOR EACH ROW EXECUTE FUNCTION update_classification_updated_at();
