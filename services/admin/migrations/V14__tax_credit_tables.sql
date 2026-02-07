-- V14: Tax Credit Pre-Screening Tables
-- CA Film Tax Credit 4.0 compliance tracking

-- ============================================================================
-- Table: pcos_tax_credit_applications
-- Purpose: Track tax credit applications and eligibility status per project
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_tax_credit_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    budget_id UUID REFERENCES pcos_budgets(id) ON DELETE SET NULL,
    
    -- Program identification
    program_code VARCHAR(50) NOT NULL,  -- e.g., 'CA_FTC_4.0', 'GA_ENT', 'NY_FILM'
    program_name VARCHAR(255) NOT NULL,
    program_year INTEGER NOT NULL,
    
    -- Eligibility status
    eligibility_status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, eligible, ineligible, partial
    eligibility_score DECIMAL(5,2),  -- 0-100
    
    -- Thresholds and requirements
    min_spend_threshold DECIMAL(15,2),
    actual_qualified_spend DECIMAL(15,2),
    qualified_spend_pct DECIMAL(5,2),
    
    -- Credit calculation
    base_credit_rate DECIMAL(5,2),  -- e.g., 20.00 for 20%
    uplift_rate DECIMAL(5,2),       -- additional % for certain conditions
    total_credit_rate DECIMAL(5,2),
    estimated_credit_amount DECIMAL(15,2),
    
    -- Requirements checklist
    requirements_met JSONB DEFAULT '{}',  -- {"ca_resident_hiring": true, "independent_film": false}
    requirements_notes TEXT,
    
    -- Rule evaluation metadata
    rule_pack_version VARCHAR(50),
    evaluated_at TIMESTAMPTZ,
    evaluation_details JSONB,
    
    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    CONSTRAINT chk_eligibility_status CHECK (eligibility_status IN ('pending', 'eligible', 'ineligible', 'partial'))
);

-- ============================================================================
-- Table: pcos_qualified_spend_categories
-- Purpose: Break down budget spend into qualified vs non-qualified categories
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_qualified_spend_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id UUID NOT NULL REFERENCES pcos_tax_credit_applications(id) ON DELETE CASCADE,
    
    -- Category identification
    category_code VARCHAR(100) NOT NULL,  -- e.g., 'labor_btl', 'equipment_rental', 'post_production'
    category_name VARCHAR(255) NOT NULL,
    budget_department VARCHAR(100),       -- Maps to budget department (e.g., '50', '60', '70')
    
    -- Spend amounts
    total_spend DECIMAL(15,2) NOT NULL DEFAULT 0,
    qualified_spend DECIMAL(15,2) NOT NULL DEFAULT 0,
    non_qualified_spend DECIMAL(15,2) NOT NULL DEFAULT 0,
    
    -- Qualification status
    qualification_status VARCHAR(50) NOT NULL DEFAULT 'mixed',  -- qualified, non_qualified, mixed, excluded
    qualification_reason TEXT,
    
    -- Rule details
    applicable_rules JSONB,  -- List of rule IDs that apply
    exclusion_reason VARCHAR(255),  -- If excluded, why
    
    -- Line item rollup
    line_item_count INTEGER DEFAULT 0,
    line_item_ids UUID[],  -- References to pcos_budget_line_items
    
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT chk_qualification_status CHECK (qualification_status IN ('qualified', 'non_qualified', 'mixed', 'excluded'))
);

-- ============================================================================
-- Table: pcos_tax_credit_rules
-- Purpose: Store program-specific qualification rules
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_tax_credit_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Program scope
    program_code VARCHAR(50) NOT NULL,
    program_year INTEGER NOT NULL,
    rule_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    
    -- Rule definition
    rule_code VARCHAR(100) NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    rule_category VARCHAR(100) NOT NULL,  -- 'eligibility', 'spend_qualification', 'uplift', 'exclusion'
    
    -- Rule logic (stored as structured JSONB)
    rule_definition JSONB NOT NULL,
    /*
    Example rule_definition:
    {
        "type": "threshold",
        "field": "budget_total",
        "operator": ">=",
        "value": 1000000,
        "message": "Budget must be at least $1M for CA FTC 4.0"
    }
    */
    
    -- Documentation
    description TEXT,
    authority_reference VARCHAR(255),  -- e.g., "CA Rev & Tax Code §17053.98"
    effective_date DATE,
    sunset_date DATE,
    
    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(program_code, program_year, rule_code)
);

-- ============================================================================
-- Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_tax_credit_apps_tenant ON pcos_tax_credit_applications(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tax_credit_apps_project ON pcos_tax_credit_applications(project_id);
CREATE INDEX IF NOT EXISTS idx_tax_credit_apps_program ON pcos_tax_credit_applications(program_code, program_year);
CREATE INDEX IF NOT EXISTS idx_tax_credit_apps_status ON pcos_tax_credit_applications(eligibility_status);

CREATE INDEX IF NOT EXISTS idx_qualified_spend_tenant ON pcos_qualified_spend_categories(tenant_id);
CREATE INDEX IF NOT EXISTS idx_qualified_spend_app ON pcos_qualified_spend_categories(application_id);
CREATE INDEX IF NOT EXISTS idx_qualified_spend_category ON pcos_qualified_spend_categories(category_code);

CREATE INDEX IF NOT EXISTS idx_tax_rules_program ON pcos_tax_credit_rules(program_code, program_year);
CREATE INDEX IF NOT EXISTS idx_tax_rules_active ON pcos_tax_credit_rules(is_active) WHERE is_active = TRUE;

-- ============================================================================
-- Row Level Security
-- ============================================================================
ALTER TABLE pcos_tax_credit_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_qualified_spend_categories ENABLE ROW LEVEL SECURITY;

-- Tax credit applications: tenant isolation
CREATE POLICY tax_credit_apps_tenant_isolation ON pcos_tax_credit_applications
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY tax_credit_apps_insert ON pcos_tax_credit_applications
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY tax_credit_apps_update ON pcos_tax_credit_applications
    FOR UPDATE USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY tax_credit_apps_delete ON pcos_tax_credit_applications
    FOR DELETE USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

-- Qualified spend categories: tenant isolation
CREATE POLICY qualified_spend_tenant_isolation ON pcos_qualified_spend_categories
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY qualified_spend_insert ON pcos_qualified_spend_categories
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY qualified_spend_update ON pcos_qualified_spend_categories
    FOR UPDATE USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY qualified_spend_delete ON pcos_qualified_spend_categories
    FOR DELETE USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

-- ============================================================================
-- Initial CA Film Tax Credit 4.0 Rules (Seed Data)
-- ============================================================================
INSERT INTO pcos_tax_credit_rules (program_code, program_year, rule_code, rule_name, rule_category, rule_definition, description, authority_reference, effective_date)
VALUES 
-- Eligibility Rules
('CA_FTC_4.0', 2024, 'MIN_BUDGET', 'Minimum Budget Requirement', 'eligibility',
 '{"type": "threshold", "field": "budget_total", "operator": ">=", "value": 1000000}',
 'Feature films must have a minimum budget of $1 million',
 'CA Rev & Tax Code §17053.98', '2025-07-01'),

('CA_FTC_4.0', 2024, 'CA_FILMING_PCT', 'California Filming Percentage', 'eligibility',
 '{"type": "threshold", "field": "ca_filming_days_pct", "operator": ">=", "value": 75}',
 'At least 75% of principal photography must occur in California',
 'CA Rev & Tax Code §17053.98', '2025-07-01'),

('CA_FTC_4.0', 2024, 'PROD_COMPANY_CA', 'California Production Company', 'eligibility',
 '{"type": "boolean", "field": "is_ca_registered", "value": true}',
 'Production company must be registered to do business in California',
 'CA Rev & Tax Code §17053.98', '2025-07-01'),

-- Spend Qualification Rules
('CA_FTC_4.0', 2024, 'BTL_LABOR_QUALIFIED', 'Below-the-Line Labor Qualified', 'spend_qualification',
 '{"type": "category_inclusion", "category": "labor_btl", "qualified": true, "conditions": ["ca_resident", "wages_paid_ca"]}',
 'Below-the-line labor is qualified spend when paid to CA residents',
 'CA Film Commission Guidelines', '2025-07-01'),

('CA_FTC_4.0', 2024, 'ATL_LABOR_EXCLUDED', 'Above-the-Line Labor Excluded', 'exclusion',
 '{"type": "category_exclusion", "categories": ["labor_atl_star", "labor_atl_director", "labor_atl_producer"], "reason": "ATL personnel excluded from qualified spend"}',
 'Above-the-line talent, directors, and producers are excluded from qualified spend',
 'CA Film Commission Guidelines', '2025-07-01'),

('CA_FTC_4.0', 2024, 'VENDOR_CA_QUALIFIED', 'California Vendor Spend', 'spend_qualification',
 '{"type": "vendor_location", "state": "CA", "qualified": true}',
 'Payments to California vendors qualify for the credit',
 'CA Film Commission Guidelines', '2025-07-01'),

-- Credit Rate Rules  
('CA_FTC_4.0', 2024, 'BASE_CREDIT_RATE', 'Base Credit Rate', 'credit_rate',
 '{"type": "rate", "base_rate": 20.0}',
 'Base credit rate is 20% of qualified expenditures',
 'CA Rev & Tax Code §17053.98', '2025-07-01'),

('CA_FTC_4.0', 2024, 'INDIE_UPLIFT', 'Independent Film Uplift', 'uplift',
 '{"type": "conditional_rate", "condition": {"field": "is_independent", "operator": "==", "value": true}, "uplift": 5.0}',
 'Independent films receive an additional 5% credit (25% total)',
 'CA Film Commission Guidelines', '2025-07-01'),

('CA_FTC_4.0', 2024, 'RELOCATION_UPLIFT', 'Relocation Uplift', 'uplift',
 '{"type": "conditional_rate", "condition": {"field": "is_relocating", "operator": "==", "value": true}, "uplift": 5.0}',
 'Productions relocating from outside CA receive 5% uplift',
 'CA Film Commission Guidelines', '2025-07-01'),

('CA_FTC_4.0', 2024, 'JOBS_RATIO_UPLIFT', 'Jobs Ratio Uplift', 'uplift',
 '{"type": "conditional_rate", "condition": {"field": "ca_jobs_ratio", "operator": ">=", "value": 0.85}, "uplift": 5.0}',
 'Productions with 85%+ CA-based jobs receive 5% uplift',
 'CA Film Commission Guidelines', '2025-07-01')

ON CONFLICT (program_code, program_year, rule_code) DO NOTHING;

-- ============================================================================
-- Update trigger for updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_tax_credit_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tax_credit_apps_updated
    BEFORE UPDATE ON pcos_tax_credit_applications
    FOR EACH ROW EXECUTE FUNCTION update_tax_credit_updated_at();

CREATE TRIGGER trg_qualified_spend_updated
    BEFORE UPDATE ON pcos_qualified_spend_categories
    FOR EACH ROW EXECUTE FUNCTION update_tax_credit_updated_at();
