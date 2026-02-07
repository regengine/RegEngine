-- V17: Paperwork Tracking & Visa Flags
-- Document requirements, status tracking, and immigration timeline management

-- ============================================================================
-- Table: pcos_document_requirements
-- Purpose: Define required documents per engagement type/classification
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_document_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Requirement scope
    requirement_code VARCHAR(50) NOT NULL UNIQUE,
    requirement_name VARCHAR(255) NOT NULL,
    document_type VARCHAR(100) NOT NULL,  -- 'tax', 'employment', 'permit', 'insurance', 'visa'
    
    -- Applicability rules
    applies_to_classification VARCHAR(20),  -- 'employee', 'contractor', 'both'
    applies_to_union_status VARCHAR(50),    -- 'union', 'non_union', 'both'
    applies_to_minor BOOLEAN DEFAULT FALSE,
    applies_to_visa_holder BOOLEAN DEFAULT FALSE,
    
    -- Requirement details
    description TEXT,
    legal_reference VARCHAR(255),
    deadline_days_before_start INTEGER,  -- Days before engagement start
    deadline_type VARCHAR(50) DEFAULT 'before_start',  -- 'before_start', 'within_days', 'before_pay'
    
    -- Document metadata
    form_number VARCHAR(50),
    issuing_authority VARCHAR(100),
    template_id UUID REFERENCES pcos_form_templates(id),
    
    -- Status
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Table: pcos_engagement_documents
-- Purpose: Track document status per engagement
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_engagement_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    engagement_id UUID NOT NULL REFERENCES pcos_engagements(id) ON DELETE CASCADE,
    requirement_id UUID NOT NULL REFERENCES pcos_document_requirements(id),
    
    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, requested, received, verified, expired, waived
    
    -- Dates
    requested_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    verified_by UUID REFERENCES users(id),
    expires_at DATE,
    
    -- Document reference
    evidence_id UUID REFERENCES pcos_evidence(id),  -- Link to uploaded document
    file_name VARCHAR(255),
    
    -- Notes
    notes TEXT,
    waiver_reason TEXT,
    
    -- Reminder tracking
    reminder_sent_at TIMESTAMPTZ,
    reminder_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT chk_doc_status CHECK (status IN ('pending', 'requested', 'received', 'verified', 'expired', 'waived')),
    UNIQUE(engagement_id, requirement_id)
);

-- ============================================================================
-- Table: pcos_visa_categories
-- Purpose: Visa types with processing times and work authorization rules
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_visa_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    visa_code VARCHAR(20) NOT NULL UNIQUE,  -- 'O-1A', 'O-1B', 'P-1', 'H-1B', etc.
    visa_name VARCHAR(255) NOT NULL,
    visa_category VARCHAR(50) NOT NULL,  -- 'artist', 'athlete', 'specialized', 'student'
    
    -- Work authorization details
    work_authorized BOOLEAN NOT NULL DEFAULT TRUE,
    employer_specific BOOLEAN NOT NULL DEFAULT FALSE,  -- Tied to specific employer
    duration_months INTEGER,
    renewable BOOLEAN DEFAULT TRUE,
    
    -- Processing timeline (in days)
    standard_processing_days INTEGER,
    premium_processing_days INTEGER,
    premium_processing_available BOOLEAN DEFAULT FALSE,
    
    -- Requirements
    requires_petition BOOLEAN DEFAULT TRUE,
    requires_labor_certification BOOLEAN DEFAULT FALSE,
    
    -- Entertainment specific
    common_in_entertainment BOOLEAN DEFAULT FALSE,
    notes TEXT,
    
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Table: pcos_person_visa_status
-- Purpose: Track visa status per person
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_person_visa_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    person_id UUID NOT NULL REFERENCES pcos_people(id) ON DELETE CASCADE,
    
    -- Visa details
    visa_category_id UUID REFERENCES pcos_visa_categories(id),
    visa_code VARCHAR(20),
    
    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'active',  -- active, expired, pending, revoked
    
    -- Dates
    issue_date DATE,
    expiration_date DATE,
    last_entry_date DATE,
    
    -- I-94 details
    i94_number VARCHAR(20),
    i94_expiration DATE,
    
    -- Work authorization
    ead_expiration DATE,  -- Employment Authorization Document
    is_work_authorized BOOLEAN DEFAULT TRUE,
    employer_restricted BOOLEAN DEFAULT FALSE,
    restricted_to_employer VARCHAR(255),
    
    -- Document storage
    evidence_id UUID REFERENCES pcos_evidence(id),
    
    notes TEXT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT chk_visa_status CHECK (status IN ('active', 'expired', 'pending', 'revoked'))
);

-- ============================================================================
-- Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_doc_requirements_type ON pcos_document_requirements(document_type);
CREATE INDEX IF NOT EXISTS idx_doc_requirements_active ON pcos_document_requirements(is_active) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_engagement_docs_tenant ON pcos_engagement_documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_engagement_docs_engagement ON pcos_engagement_documents(engagement_id);
CREATE INDEX IF NOT EXISTS idx_engagement_docs_status ON pcos_engagement_documents(status);

CREATE INDEX IF NOT EXISTS idx_visa_categories_code ON pcos_visa_categories(visa_code);
CREATE INDEX IF NOT EXISTS idx_person_visa_tenant ON pcos_person_visa_status(tenant_id);
CREATE INDEX IF NOT EXISTS idx_person_visa_person ON pcos_person_visa_status(person_id);
CREATE INDEX IF NOT EXISTS idx_person_visa_expiration ON pcos_person_visa_status(expiration_date);

-- ============================================================================
-- Row Level Security
-- ============================================================================
ALTER TABLE pcos_engagement_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_person_visa_status ENABLE ROW LEVEL SECURITY;

CREATE POLICY engagement_docs_tenant_isolation ON pcos_engagement_documents
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY engagement_docs_insert ON pcos_engagement_documents
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY person_visa_tenant_isolation ON pcos_person_visa_status
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY person_visa_insert ON pcos_person_visa_status
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

-- ============================================================================
-- Seed Document Requirements
-- ============================================================================
INSERT INTO pcos_document_requirements (
    requirement_code, requirement_name, document_type, 
    applies_to_classification, applies_to_minor, applies_to_visa_holder,
    description, form_number, issuing_authority, deadline_days_before_start, is_required
) VALUES
-- Tax Documents
('W9', 'W-9 Request for Taxpayer ID', 'tax',
 'contractor', FALSE, FALSE,
 'Required for all independent contractors before first payment',
 'W-9', 'IRS', 0, TRUE),

('W4', 'W-4 Employee Withholding Certificate', 'tax',
 'employee', FALSE, FALSE,
 'Required for all W-2 employees before first paycheck',
 'W-4', 'IRS', 0, TRUE),

-- Employment Verification
('I9', 'I-9 Employment Eligibility Verification', 'employment',
 'employee', FALSE, FALSE,
 'Required within 3 days of first day of work',
 'I-9', 'USCIS', -3, TRUE),  -- Negative = after start

-- Minor Work Permits
('MINOR_PERMIT_CA', 'California Minor Work Permit', 'permit',
 'both', TRUE, FALSE,
 'Required for all minors (under 18) working in California',
 'CDE B1-1', 'CA Dept of Education', 5, TRUE),

('MINOR_COOGAN', 'Coogan Account Verification', 'permit',
 'both', TRUE, FALSE,
 'Blocked trust account required for minor performers',
 NULL, 'CA Labor Commissioner', 5, TRUE),

('MINOR_STUDIO_TEACHER', 'Studio Teacher Assignment', 'permit',
 'both', TRUE, FALSE,
 'Studio teacher required on set for minors',
 NULL, 'CA Dept of Education', 3, TRUE),

-- Union Documents
('DEAL_MEMO', 'Deal Memo/Start Paperwork', 'employment',
 'both', FALSE, FALSE,
 'Standard deal memo with rate and terms',
 NULL, 'Production', 1, TRUE),

-- Visa/Immigration
('VISA_WORK_AUTH', 'Work Authorization Verification', 'visa',
 'both', FALSE, TRUE,
 'Copy of visa and I-94 for non-citizen workers',
 NULL, 'USCIS', 5, TRUE),

('EAD_COPY', 'Employment Authorization Document', 'visa',
 'employee', FALSE, TRUE,
 'EAD card copy for work authorization',
 'I-766', 'USCIS', 5, FALSE)

ON CONFLICT (requirement_code) DO NOTHING;

-- ============================================================================
-- Seed Visa Categories (Entertainment-focused)
-- ============================================================================
INSERT INTO pcos_visa_categories (
    visa_code, visa_name, visa_category, work_authorized, employer_specific,
    duration_months, standard_processing_days, premium_processing_days,
    premium_processing_available, common_in_entertainment, notes
) VALUES
('O-1A', 'O-1A Extraordinary Ability (Sciences/Business)', 'specialized',
 TRUE, TRUE, 36, 120, 15, TRUE, FALSE,
 'For individuals with extraordinary ability in sciences, education, business, or athletics'),

('O-1B', 'O-1B Extraordinary Ability (Arts)', 'artist',
 TRUE, TRUE, 36, 120, 15, TRUE, TRUE,
 'Primary visa for film/TV talent. For individuals with extraordinary ability in arts or extraordinary achievement in motion picture/TV'),

('O-2', 'O-2 Support Personnel', 'artist',
 TRUE, TRUE, 36, 120, 15, TRUE, TRUE,
 'For essential support personnel accompanying O-1 artists'),

('P-1A', 'P-1A Internationally Recognized Athlete', 'athlete',
 TRUE, TRUE, 60, 120, 15, TRUE, FALSE,
 'For individual athletes competing at internationally recognized level'),

('P-1B', 'P-1B International Entertainment Group', 'artist',
 TRUE, TRUE, 12, 120, 15, TRUE, TRUE,
 'For members of internationally recognized entertainment groups'),

('H-1B', 'H-1B Specialty Occupation', 'specialized',
 TRUE, TRUE, 36, 180, 15, TRUE, FALSE,
 'For specialty occupation workers; annual cap applies'),

('L-1A', 'L-1A Intracompany Transfer (Manager)', 'specialized',
 TRUE, TRUE, 84, 90, 15, TRUE, FALSE,
 'For managers/executives transferred within same company'),

('F-1_OPT', 'F-1 Optional Practical Training', 'student',
 TRUE, TRUE, 12, 90, 0, FALSE, FALSE,
 'Work authorization for F-1 students post-graduation'),

('F-1_CPT', 'F-1 Curricular Practical Training', 'student',
 TRUE, TRUE, 12, 30, 0, FALSE, FALSE,
 'Work authorization for F-1 students during studies'),

('TN', 'TN NAFTA Professional', 'specialized',
 TRUE, TRUE, 36, 1, 0, FALSE, FALSE,
 'For Canadian/Mexican professionals in specific occupations')

ON CONFLICT (visa_code) DO NOTHING;

-- ============================================================================
-- Update trigger
-- ============================================================================
CREATE OR REPLACE FUNCTION update_paperwork_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_engagement_docs_updated
    BEFORE UPDATE ON pcos_engagement_documents
    FOR EACH ROW EXECUTE FUNCTION update_paperwork_updated_at();

CREATE TRIGGER trg_person_visa_updated
    BEFORE UPDATE ON pcos_person_visa_status
    FOR EACH ROW EXECUTE FUNCTION update_paperwork_updated_at();
