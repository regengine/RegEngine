-- V15: Form Auto-Fill System
-- PDF form templates and generated forms for permit applications

-- ============================================================================
-- Table: pcos_form_templates
-- Purpose: Store form template definitions with field mappings
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_form_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Template identification
    template_code VARCHAR(100) NOT NULL UNIQUE,  -- e.g., 'FILMLA_PERMIT', 'CA_I9', 'DEAL_MEMO'
    template_name VARCHAR(255) NOT NULL,
    template_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    
    -- Form source
    form_authority VARCHAR(100),  -- e.g., 'FilmL.A.', 'IRS', 'DGA'
    form_url VARCHAR(500),        -- URL to official form
    
    -- Template type
    form_type VARCHAR(50) NOT NULL,  -- 'permit', 'tax', 'employment', 'insurance', 'union'
    jurisdiction VARCHAR(20),        -- 'CA', 'LA_CITY', 'federal', etc.
    
    -- Field definitions (JSONB array)
    -- Each field: {field_name, field_type, pdf_field_id, data_path, transform?, required?}
    field_mappings JSONB NOT NULL DEFAULT '[]',
    
    -- PDF template storage
    pdf_template_path VARCHAR(500),  -- Path to template PDF in storage
    pdf_template_hash VARCHAR(64),   -- SHA-256 of template for version tracking
    
    -- Metadata
    description TEXT,
    instructions TEXT,
    estimated_fill_time_minutes INTEGER,
    
    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    requires_signature BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

-- ============================================================================
-- Table: pcos_generated_forms
-- Purpose: Track generated/filled PDF forms per project
-- ============================================================================
CREATE TABLE IF NOT EXISTS pcos_generated_forms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES pcos_form_templates(id),
    
    -- Location context (for permits)
    location_id UUID REFERENCES pcos_locations(id) ON DELETE SET NULL,
    
    -- Generation details
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_by UUID REFERENCES users(id),
    
    -- Source data snapshot (for audit trail)
    source_data_snapshot JSONB NOT NULL DEFAULT '{}',
    
    -- Generated PDF
    pdf_storage_path VARCHAR(500),
    pdf_file_hash VARCHAR(64),
    pdf_file_size_bytes INTEGER,
    
    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'draft',  -- draft, ready, submitted, approved, rejected
    submitted_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,
    
    -- External reference (e.g., FilmLA application number)
    external_reference VARCHAR(100),
    
    -- Signature tracking
    requires_signature BOOLEAN NOT NULL DEFAULT FALSE,
    signature_status VARCHAR(50) DEFAULT 'pending',  -- pending, signed, declined
    signed_at TIMESTAMPTZ,
    signed_by UUID REFERENCES users(id),
    
    -- Notes
    notes TEXT,
    
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_form_templates_code ON pcos_form_templates(template_code);
CREATE INDEX IF NOT EXISTS idx_form_templates_type ON pcos_form_templates(form_type);
CREATE INDEX IF NOT EXISTS idx_form_templates_active ON pcos_form_templates(is_active) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_generated_forms_tenant ON pcos_generated_forms(tenant_id);
CREATE INDEX IF NOT EXISTS idx_generated_forms_project ON pcos_generated_forms(project_id);
CREATE INDEX IF NOT EXISTS idx_generated_forms_template ON pcos_generated_forms(template_id);
CREATE INDEX IF NOT EXISTS idx_generated_forms_status ON pcos_generated_forms(status);
CREATE INDEX IF NOT EXISTS idx_generated_forms_location ON pcos_generated_forms(location_id);

-- ============================================================================
-- Row Level Security
-- ============================================================================
ALTER TABLE pcos_generated_forms ENABLE ROW LEVEL SECURITY;

CREATE POLICY generated_forms_tenant_isolation ON pcos_generated_forms
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY generated_forms_insert ON pcos_generated_forms
    FOR INSERT WITH CHECK (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY generated_forms_update ON pcos_generated_forms
    FOR UPDATE USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

CREATE POLICY generated_forms_delete ON pcos_generated_forms
    FOR DELETE USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));

-- ============================================================================
-- FilmLA Permit Template (Seed Data)
-- ============================================================================
INSERT INTO pcos_form_templates (
    template_code,
    template_name,
    template_version,
    form_authority,
    form_url,
    form_type,
    jurisdiction,
    field_mappings,
    description,
    instructions,
    estimated_fill_time_minutes,
    is_active,
    requires_signature
) VALUES (
    'FILMLA_PERMIT',
    'FilmL.A. Film Permit Application',
    '2024.1',
    'FilmL.A.',
    'https://www.filmla.com/permits/',
    'permit',
    'LA_CITY',
    '[
        {"field_name": "production_company", "field_type": "text", "pdf_field_id": "company_name", "data_path": "company.name", "required": true},
        {"field_name": "production_title", "field_type": "text", "pdf_field_id": "project_title", "data_path": "project.name", "required": true},
        {"field_name": "project_type", "field_type": "select", "pdf_field_id": "production_type", "data_path": "project.project_type", "required": true},
        {"field_name": "contact_name", "field_type": "text", "pdf_field_id": "contact_person", "data_path": "company.primary_contact_name", "required": true},
        {"field_name": "contact_phone", "field_type": "text", "pdf_field_id": "contact_phone", "data_path": "company.primary_contact_phone", "required": true},
        {"field_name": "contact_email", "field_type": "text", "pdf_field_id": "contact_email", "data_path": "company.primary_contact_email", "required": true},
        {"field_name": "company_address", "field_type": "text", "pdf_field_id": "company_address", "data_path": "company.address_line1", "required": true},
        {"field_name": "company_city", "field_type": "text", "pdf_field_id": "company_city", "data_path": "company.city", "required": true},
        {"field_name": "company_state", "field_type": "text", "pdf_field_id": "company_state", "data_path": "company.state", "required": true},
        {"field_name": "company_zip", "field_type": "text", "pdf_field_id": "company_zip", "data_path": "company.zip", "required": true},
        {"field_name": "location_address", "field_type": "text", "pdf_field_id": "filming_address", "data_path": "location.address_line1", "required": true},
        {"field_name": "location_city", "field_type": "text", "pdf_field_id": "filming_city", "data_path": "location.city", "required": true},
        {"field_name": "filming_date_start", "field_type": "date", "pdf_field_id": "start_date", "data_path": "location.shoot_dates[0]", "required": true},
        {"field_name": "filming_date_end", "field_type": "date", "pdf_field_id": "end_date", "data_path": "location.shoot_dates[-1]", "required": false},
        {"field_name": "crew_size", "field_type": "number", "pdf_field_id": "crew_count", "data_path": "location.estimated_crew_size", "required": true},
        {"field_name": "vehicles_count", "field_type": "number", "pdf_field_id": "vehicles", "data_path": "location.parking_spaces_needed", "required": true},
        {"field_name": "has_generator", "field_type": "checkbox", "pdf_field_id": "generator_yn", "data_path": "location.has_generator", "required": false},
        {"field_name": "has_special_effects", "field_type": "checkbox", "pdf_field_id": "sfx_yn", "data_path": "location.has_special_effects", "required": false},
        {"field_name": "insurance_carrier", "field_type": "text", "pdf_field_id": "insurance_company", "data_path": "insurance.carrier_name", "required": true},
        {"field_name": "insurance_policy_number", "field_type": "text", "pdf_field_id": "policy_number", "data_path": "insurance.policy_number", "required": true},
        {"field_name": "coi_expiration", "field_type": "date", "pdf_field_id": "coi_exp", "data_path": "insurance.expiration_date", "required": true}
    ]'::jsonb,
    'Standard FilmL.A. permit application for filming in Los Angeles city and county locations.',
    'Complete all required fields. Ensure insurance certificate is current. Submit at least 5 business days before first shoot date.',
    30,
    TRUE,
    TRUE
)
ON CONFLICT (template_code) DO UPDATE SET
    field_mappings = EXCLUDED.field_mappings,
    template_version = EXCLUDED.template_version,
    updated_at = NOW();

-- ============================================================================
-- Update trigger
-- ============================================================================
CREATE OR REPLACE FUNCTION update_form_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_form_templates_updated
    BEFORE UPDATE ON pcos_form_templates
    FOR EACH ROW EXECUTE FUNCTION update_form_updated_at();

CREATE TRIGGER trg_generated_forms_updated
    BEFORE UPDATE ON pcos_generated_forms
    FOR EACH ROW EXECUTE FUNCTION update_form_updated_at();
