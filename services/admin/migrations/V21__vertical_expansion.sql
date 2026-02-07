-- Migration V21: Vertical Expansion
-- Supports generic compliance projects for Healthcare, Finance, Gaming, Energy, and Tech.

-- 1. Create Vertical Projects table
CREATE TABLE vertical_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- e.g. 'healthcare', 'finance', 'gaming'
    vertical VARCHAR(50) NOT NULL,
    
    -- Flexible metadata storage (e.g. { "facility_type": "hospital" })
    vertical_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id)
);

-- Indices for Vertical Projects
CREATE INDEX idx_vertical_projects_tenant ON vertical_projects(tenant_id);
CREATE INDEX idx_vertical_projects_vertical ON vertical_projects(vertical);
CREATE INDEX idx_vertical_projects_status ON vertical_projects(status);


-- 2. Create Vertical Rule Instances table
-- Links a project to a specific rule from the JSON RulePacks
CREATE TABLE vertical_rule_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES vertical_projects(id) ON DELETE CASCADE,
    
    -- Link to static definition
    rule_pack_id VARCHAR(100) NOT NULL, -- e.g. 'healthcare_hipaa_v1'
    rule_id VARCHAR(100) NOT NULL,      -- e.g. 'HIPAA-ADM-01'
    
    -- Compliance state
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, compliant, non_compliant, not_applicable
    
    -- Evidence
    evidence_links JSONB DEFAULT '[]'::jsonb,
    auditor_notes TEXT,
    
    assigned_to UUID REFERENCES users(id),
    due_date TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

-- Indices for Rule Instances
CREATE INDEX idx_vertical_rules_tenant ON vertical_rule_instances(tenant_id);
CREATE INDEX idx_vertical_rules_project ON vertical_rule_instances(project_id);
CREATE INDEX idx_vertical_rules_status ON vertical_rule_instances(status);
CREATE INDEX idx_vertical_rules_lookup ON vertical_rule_instances(rule_pack_id, rule_id);
