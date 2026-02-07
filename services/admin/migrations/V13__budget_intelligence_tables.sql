-- V13: Budget Intelligence Tables
-- Part of Phase 1: Budget Data Model for PRD compliance

-- Budget uploads (parsed from spreadsheets)
CREATE TABLE pcos_budgets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    
    -- Source file
    source_file_name VARCHAR(255) NOT NULL,
    source_file_hash VARCHAR(64), -- SHA256 for deduplication
    source_file_s3_key TEXT,
    
    -- Parse metadata
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parser_version VARCHAR(20) DEFAULT '1.0',
    sheet_name VARCHAR(100),
    
    -- Totals
    grand_total NUMERIC(15, 2) NOT NULL,
    subtotal NUMERIC(15, 2) NOT NULL,
    contingency_amount NUMERIC(15, 2) DEFAULT 0,
    contingency_percent NUMERIC(5, 2) DEFAULT 0,
    
    -- Location/jurisdiction detected
    detected_location VARCHAR(10), -- CA, GA, NM, LA, etc.
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'draft', -- draft, active, archived
    is_active BOOLEAN NOT NULL DEFAULT TRUE, -- Only one active per project
    
    -- Compliance summary (denormalized for fast access)
    compliance_issue_count INTEGER DEFAULT 0,
    critical_issue_count INTEGER DEFAULT 0,
    risk_score INTEGER DEFAULT 0,
    
    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id),
    
    CONSTRAINT unique_active_budget_per_project 
        EXCLUDE (project_id WITH =) WHERE (is_active = TRUE)
);

-- RLS
ALTER TABLE pcos_budgets ENABLE ROW LEVEL SECURITY;
CREATE POLICY pcos_budgets_tenant_policy ON pcos_budgets
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Indexes
CREATE INDEX idx_pcos_budgets_tenant ON pcos_budgets(tenant_id);
CREATE INDEX idx_pcos_budgets_project ON pcos_budgets(project_id);
CREATE INDEX idx_pcos_budgets_active ON pcos_budgets(project_id) WHERE is_active = TRUE;
CREATE INDEX idx_pcos_budgets_hash ON pcos_budgets(source_file_hash);

-- Budget line items (parsed rows)
CREATE TABLE pcos_budget_line_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    budget_id UUID NOT NULL REFERENCES pcos_budgets(id) ON DELETE CASCADE,
    
    -- Line item data
    row_number INTEGER NOT NULL,
    cost_code VARCHAR(20),
    department VARCHAR(100),
    description TEXT NOT NULL,
    
    -- Financial
    rate NUMERIC(12, 2) DEFAULT 0,
    quantity NUMERIC(10, 2) DEFAULT 1,
    extension NUMERIC(15, 2) NOT NULL,
    
    -- Classification
    classification VARCHAR(20), -- employee, contractor
    role_category VARCHAR(50), -- principal, dp, gaffer, pa, etc.
    
    -- Union detection
    is_union_covered BOOLEAN DEFAULT FALSE,
    detected_union VARCHAR(20), -- sag_aftra, iatse_600, etc.
    
    -- Deal memo status (parsed from budget notes)
    deal_memo_status VARCHAR(20), -- need_to_send, sent, signed
    
    -- Compliance flags
    compliance_flags VARCHAR(50)[] DEFAULT '{}',
    -- e.g.: ['below_union_min', 'misclassification_risk', 'overtime_not_budgeted']
    
    -- Parsed metadata
    raw_row_data JSONB,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RLS
ALTER TABLE pcos_budget_line_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY pcos_budget_line_items_tenant_policy ON pcos_budget_line_items
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Indexes
CREATE INDEX idx_pcos_budget_items_tenant ON pcos_budget_line_items(tenant_id);
CREATE INDEX idx_pcos_budget_items_budget ON pcos_budget_line_items(budget_id);
CREATE INDEX idx_pcos_budget_items_dept ON pcos_budget_line_items(department);
CREATE INDEX idx_pcos_budget_items_flags ON pcos_budget_line_items USING GIN(compliance_flags);

-- Union rate checks (validation results)
CREATE TABLE pcos_union_rate_checks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Can link to budget line item OR engagement
    line_item_id UUID REFERENCES pcos_budget_line_items(id) ON DELETE CASCADE,
    engagement_id UUID REFERENCES pcos_engagements(id) ON DELETE CASCADE,
    
    -- Union info
    union_code VARCHAR(20) NOT NULL, -- sag_aftra, dga, wga, iatse_600, etc.
    role_category VARCHAR(50) NOT NULL, -- principal, day_player, dp, gaffer, etc.
    
    -- Rate comparison
    minimum_rate NUMERIC(10, 2) NOT NULL,
    actual_rate NUMERIC(10, 2) NOT NULL,
    is_compliant BOOLEAN NOT NULL,
    shortfall_amount NUMERIC(10, 2) DEFAULT 0,
    
    -- Fringe
    fringe_percent_required NUMERIC(5, 2),
    fringe_amount_required NUMERIC(10, 2),
    
    -- Provenance
    rate_table_version VARCHAR(20) NOT NULL,
    rate_table_effective_date DATE,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    notes TEXT,
    
    CONSTRAINT check_source CHECK (
        (line_item_id IS NOT NULL AND engagement_id IS NULL) OR
        (line_item_id IS NULL AND engagement_id IS NOT NULL)
    )
);

-- RLS
ALTER TABLE pcos_union_rate_checks ENABLE ROW LEVEL SECURITY;
CREATE POLICY pcos_union_rate_checks_tenant_policy ON pcos_union_rate_checks
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Indexes
CREATE INDEX idx_pcos_rate_checks_tenant ON pcos_union_rate_checks(tenant_id);
CREATE INDEX idx_pcos_rate_checks_line_item ON pcos_union_rate_checks(line_item_id);
CREATE INDEX idx_pcos_rate_checks_engagement ON pcos_union_rate_checks(engagement_id);
CREATE INDEX idx_pcos_rate_checks_compliant ON pcos_union_rate_checks(is_compliant);

-- Grants
GRANT ALL ON pcos_budgets TO regengine_app;
GRANT ALL ON pcos_budget_line_items TO regengine_app;
GRANT ALL ON pcos_union_rate_checks TO regengine_app;
