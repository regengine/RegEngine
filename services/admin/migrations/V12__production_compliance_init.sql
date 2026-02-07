-- Migration V12: Production Compliance OS (CA/LA) Add-On Module
--
-- This migration creates domain tables for the Production Compliance OS module,
-- designed for small film/TV production companies operating in California/LA.
--
-- All tables are multi-tenant with Row-Level Security (RLS) enabled.
-- Prefix: pcos_ (Production Compliance OS)
--
-- Phase: Add-On Module - Production Compliance OS v1
-- Date: 2026-01-21

-- ============================================================================
-- STEP 1: Enum Types
-- ============================================================================

DO $$
BEGIN
    -- Location types
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_location_type') THEN
        CREATE TYPE pcos_location_type AS ENUM (
            'certified_studio',
            'private_property',
            'residential',
            'public_row'
        );
    END IF;

    -- Worker classification
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_classification_type') THEN
        CREATE TYPE pcos_classification_type AS ENUM (
            'employee',
            'contractor'
        );
    END IF;

    -- Task status
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_task_status') THEN
        CREATE TYPE pcos_task_status AS ENUM (
            'pending',
            'in_progress',
            'completed',
            'blocked',
            'cancelled'
        );
    END IF;

    -- Project gate states
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_gate_state') THEN
        CREATE TYPE pcos_gate_state AS ENUM (
            'draft',
            'ready_for_review',
            'greenlit',
            'in_production',
            'wrap',
            'archived'
        );
    END IF;

    -- Entity types
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_entity_type') THEN
        CREATE TYPE pcos_entity_type AS ENUM (
            'sole_proprietor',
            'llc_single_member',
            'llc_multi_member',
            's_corp',
            'c_corp',
            'partnership'
        );
    END IF;

    -- Owner pay mode
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_owner_pay_mode') THEN
        CREATE TYPE pcos_owner_pay_mode AS ENUM (
            'draw',
            'payroll'
        );
    END IF;

    -- Registration type
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_registration_type') THEN
        CREATE TYPE pcos_registration_type AS ENUM (
            'sos',          -- Secretary of State
            'ftb',          -- Franchise Tax Board
            'btrc',         -- LA Business Tax Registration Certificate
            'dba_fbn',      -- DBA / Fictitious Business Name
            'edd',          -- Employment Development Department
            'dir'           -- Department of Industrial Relations
        );
    END IF;

    -- Insurance policy type
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_insurance_type') THEN
        CREATE TYPE pcos_insurance_type AS ENUM (
            'general_liability',
            'workers_comp',
            'errors_omissions',
            'equipment',
            'auto',
            'umbrella'
        );
    END IF;

    -- Evidence type
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_evidence_type') THEN
        CREATE TYPE pcos_evidence_type AS ENUM (
            'coi',
            'permit_approved',
            'classification_memo_signed',
            'workers_comp_policy',
            'iipp_policy',
            'wvpp_policy',
            'w9',
            'i9',
            'w4',
            'vendor_coi',
            'minor_work_permit',
            'signed_contract',
            'location_release',
            'talent_release',
            'paystub',
            'training_record',
            'other'
        );
    END IF;

    -- Project type
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_project_type') THEN
        CREATE TYPE pcos_project_type AS ENUM (
            'commercial',
            'narrative_feature',
            'narrative_short',
            'documentary',
            'music_video',
            'branded_content',
            'still_photo',
            'other'
        );
    END IF;

    -- Jurisdiction
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pcos_jurisdiction') THEN
        CREATE TYPE pcos_jurisdiction AS ENUM (
            'la_city',
            'la_county',
            'ca_other',
            'out_of_state'
        );
    END IF;

END $$;

-- ============================================================================
-- STEP 2: Company Profile Tables
-- ============================================================================

-- Main company table
CREATE TABLE IF NOT EXISTS pcos_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Legal entity info
    legal_name VARCHAR(255) NOT NULL,
    entity_type pcos_entity_type NOT NULL,
    ein VARCHAR(20),  -- Encrypted at app layer
    sos_entity_number VARCHAR(50),
    
    -- Addresses
    legal_address_line1 VARCHAR(255),
    legal_address_line2 VARCHAR(255),
    legal_address_city VARCHAR(100),
    legal_address_state VARCHAR(2) DEFAULT 'CA',
    legal_address_zip VARCHAR(10),
    
    mailing_address_line1 VARCHAR(255),
    mailing_address_line2 VARCHAR(255),
    mailing_address_city VARCHAR(100),
    mailing_address_state VARCHAR(2),
    mailing_address_zip VARCHAR(10),
    
    -- LA presence
    has_la_city_presence BOOLEAN NOT NULL DEFAULT false,
    la_business_address_line1 VARCHAR(255),
    la_business_address_city VARCHAR(100),
    la_business_address_zip VARCHAR(10),
    
    -- Owner compensation
    owner_pay_mode pcos_owner_pay_mode,
    owner_pay_cpa_approved BOOLEAN NOT NULL DEFAULT false,
    owner_pay_cpa_approved_date DATE,
    
    -- Payroll provider config (JSON for flexibility)
    payroll_provider_config JSONB DEFAULT '{}'::jsonb,
    
    -- Metadata
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'archived')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_pcos_companies_tenant ON pcos_companies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_companies_status ON pcos_companies(status);

-- Company registrations (SOS, FTB, BTRC, DBA)
CREATE TABLE IF NOT EXISTS pcos_company_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES pcos_companies(id) ON DELETE CASCADE,
    
    registration_type pcos_registration_type NOT NULL,
    registration_number VARCHAR(100),
    registration_name VARCHAR(255),  -- For DBA/FBN
    jurisdiction VARCHAR(100),
    
    issue_date DATE,
    expiration_date DATE,
    renewal_date DATE,
    
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'expired', 'cancelled')),
    evidence_id UUID,  -- Link to uploaded document
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_registrations_tenant ON pcos_company_registrations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_registrations_company ON pcos_company_registrations(company_id);
CREATE INDEX IF NOT EXISTS idx_pcos_registrations_expiry ON pcos_company_registrations(expiration_date);

-- Insurance policies
CREATE TABLE IF NOT EXISTS pcos_insurance_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES pcos_companies(id) ON DELETE CASCADE,
    
    policy_type pcos_insurance_type NOT NULL,
    carrier_name VARCHAR(255),
    policy_number VARCHAR(100),
    
    coverage_amount NUMERIC(15, 2),
    deductible_amount NUMERIC(15, 2),
    
    effective_date DATE,
    expiration_date DATE NOT NULL,
    
    is_required BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'cancelled', 'pending')),
    evidence_id UUID,  -- Link to uploaded COI
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_insurance_tenant ON pcos_insurance_policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_insurance_company ON pcos_insurance_policies(company_id);
CREATE INDEX IF NOT EXISTS idx_pcos_insurance_expiry ON pcos_insurance_policies(expiration_date);

-- Safety policies (IIPP, WVPP)
CREATE TABLE IF NOT EXISTS pcos_safety_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES pcos_companies(id) ON DELETE CASCADE,
    
    policy_type VARCHAR(50) NOT NULL CHECK (policy_type IN ('iipp', 'wvpp', 'heat_illness', 'covid', 'other')),
    policy_name VARCHAR(255),
    
    effective_date DATE,
    last_review_date DATE,
    next_review_date DATE,
    
    is_uploaded BOOLEAN NOT NULL DEFAULT false,
    evidence_id UUID,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_safety_tenant ON pcos_safety_policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_safety_company ON pcos_safety_policies(company_id);

-- ============================================================================
-- STEP 3: Project & Location Tables
-- ============================================================================

-- Projects
CREATE TABLE IF NOT EXISTS pcos_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES pcos_companies(id) ON DELETE CASCADE,
    
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50),  -- Internal project code
    project_type pcos_project_type NOT NULL,
    
    is_commercial BOOLEAN NOT NULL DEFAULT false,
    client_name VARCHAR(255),
    
    start_date DATE,
    end_date DATE,
    first_shoot_date DATE,
    
    union_status VARCHAR(50) DEFAULT 'non_union' CHECK (union_status IN ('non_union', 'sag_aftra', 'iatse', 'teamsters', 'multi_union')),
    minor_involved BOOLEAN NOT NULL DEFAULT false,
    
    -- Gate state machine
    gate_state pcos_gate_state NOT NULL DEFAULT 'draft',
    gate_state_changed_at TIMESTAMP WITH TIME ZONE,
    gate_state_changed_by UUID REFERENCES users(id),
    
    -- Risk assessment
    risk_score INTEGER DEFAULT 0 CHECK (risk_score >= 0 AND risk_score <= 100),
    blocking_tasks_count INTEGER DEFAULT 0,
    
    -- Metadata
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_pcos_projects_tenant ON pcos_projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_projects_company ON pcos_projects(company_id);
CREATE INDEX IF NOT EXISTS idx_pcos_projects_gate ON pcos_projects(gate_state);
CREATE INDEX IF NOT EXISTS idx_pcos_projects_dates ON pcos_projects(first_shoot_date, start_date);

-- Locations
CREATE TABLE IF NOT EXISTS pcos_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    
    name VARCHAR(255) NOT NULL,
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2) DEFAULT 'CA',
    zip VARCHAR(10),
    
    jurisdiction pcos_jurisdiction NOT NULL,
    location_type pcos_location_type NOT NULL,
    
    -- Filming footprint
    estimated_crew_size INTEGER,
    parking_spaces_needed INTEGER,
    filming_hours_start TIME,
    filming_hours_end TIME,
    has_generator BOOLEAN DEFAULT false,
    has_special_effects BOOLEAN DEFAULT false,
    noise_level VARCHAR(50) CHECK (noise_level IN ('low', 'moderate', 'high')),
    
    -- Permit tracking
    permit_required BOOLEAN,
    permit_packet_id UUID,  -- Link to pcos_permit_packets
    
    shoot_dates DATE[],  -- Array of shoot dates
    
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_locations_tenant ON pcos_locations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_locations_project ON pcos_locations(project_id);
CREATE INDEX IF NOT EXISTS idx_pcos_locations_type ON pcos_locations(location_type);

-- Permit packets
CREATE TABLE IF NOT EXISTS pcos_permit_packets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    location_id UUID REFERENCES pcos_locations(id) ON DELETE SET NULL,
    
    permit_authority VARCHAR(100) NOT NULL DEFAULT 'filmla',  -- 'filmla', 'la_city', 'la_county', 'other'
    application_number VARCHAR(100),
    
    submitted_at TIMESTAMP WITH TIME ZONE,
    approved_at TIMESTAMP WITH TIME ZONE,
    denied_at TIMESTAMP WITH TIME ZONE,
    denial_reason TEXT,
    
    permit_number VARCHAR(100),
    permit_valid_from DATE,
    permit_valid_to DATE,
    
    status VARCHAR(50) NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started', 'in_progress', 'submitted', 'approved', 'denied', 'cancelled')),
    
    coi_evidence_id UUID,
    permit_evidence_id UUID,
    
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_permits_tenant ON pcos_permit_packets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_permits_project ON pcos_permit_packets(project_id);
CREATE INDEX IF NOT EXISTS idx_pcos_permits_status ON pcos_permit_packets(status);

-- ============================================================================
-- STEP 4: People & Engagement Tables
-- ============================================================================

-- People registry
CREATE TABLE IF NOT EXISTS pcos_people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    
    -- Legal identification (encrypted at app layer)
    ssn_last_four VARCHAR(4),
    date_of_birth DATE,
    
    -- Address
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2),
    zip VARCHAR(10),
    
    -- Default classification preference
    preferred_classification pcos_classification_type,
    
    -- Vendor/contractor info
    is_loan_out BOOLEAN DEFAULT false,
    loan_out_company_name VARCHAR(255),
    loan_out_ein VARCHAR(20),
    
    -- Emergency contact
    emergency_contact_name VARCHAR(255),
    emergency_contact_phone VARCHAR(50),
    emergency_contact_relation VARCHAR(100),
    
    notes TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_people_tenant ON pcos_people(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_people_name ON pcos_people(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_pcos_people_email ON pcos_people(email);

-- Engagements (person <-> project assignments)
CREATE TABLE IF NOT EXISTS pcos_engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    person_id UUID NOT NULL REFERENCES pcos_people(id) ON DELETE CASCADE,
    
    role_title VARCHAR(255) NOT NULL,
    department VARCHAR(100),  -- 'camera', 'grip', 'electric', 'art', 'wardrobe', 'sound', 'production', 'talent'
    
    classification pcos_classification_type NOT NULL,
    
    -- Pay terms
    pay_rate NUMERIC(10, 2) NOT NULL,
    pay_type VARCHAR(50) NOT NULL CHECK (pay_type IN ('hourly', 'daily', 'weekly', 'flat', 'kit_rental')),
    overtime_eligible BOOLEAN NOT NULL DEFAULT true,
    
    -- Work dates
    start_date DATE,
    end_date DATE,
    guaranteed_days INTEGER,
    
    -- Classification documentation
    classification_memo_signed BOOLEAN NOT NULL DEFAULT false,
    classification_memo_date DATE,
    
    -- Required documents status
    w9_received BOOLEAN DEFAULT false,
    i9_received BOOLEAN DEFAULT false,
    w4_received BOOLEAN DEFAULT false,
    deal_memo_signed BOOLEAN DEFAULT false,
    
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('pending', 'active', 'completed', 'cancelled')),
    
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_engagements_tenant ON pcos_engagements(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_engagements_project ON pcos_engagements(project_id);
CREATE INDEX IF NOT EXISTS idx_pcos_engagements_person ON pcos_engagements(person_id);
CREATE INDEX IF NOT EXISTS idx_pcos_engagements_classification ON pcos_engagements(classification);

-- ============================================================================
-- STEP 5: Timekeeping Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS pcos_timecards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    engagement_id UUID NOT NULL REFERENCES pcos_engagements(id) ON DELETE CASCADE,
    
    work_date DATE NOT NULL,
    
    -- Call/wrap times
    call_time TIME,
    wrap_time TIME,
    
    -- Meal breaks
    meal_1_out TIME,
    meal_1_in TIME,
    meal_2_out TIME,
    meal_2_in TIME,
    
    -- Calculated hours (computed at app layer)
    regular_hours NUMERIC(5, 2),
    overtime_hours NUMERIC(5, 2),
    double_time_hours NUMERIC(5, 2),
    meal_penalty_count INTEGER DEFAULT 0,
    
    -- Validation
    jurisdiction pcos_jurisdiction,
    wage_floor_met BOOLEAN,
    wage_floor_rate NUMERIC(10, 2),
    
    -- Approval workflow
    submitted_at TIMESTAMP WITH TIME ZONE,
    submitted_by UUID REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    approved_by UUID REFERENCES users(id),
    rejected_at TIMESTAMP WITH TIME ZONE,
    rejected_by UUID REFERENCES users(id),
    rejection_reason TEXT,
    
    status VARCHAR(50) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'exported')),
    
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_timecards_tenant ON pcos_timecards(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_timecards_engagement ON pcos_timecards(engagement_id);
CREATE INDEX IF NOT EXISTS idx_pcos_timecards_date ON pcos_timecards(work_date);
CREATE INDEX IF NOT EXISTS idx_pcos_timecards_status ON pcos_timecards(status);

-- Payroll export batches
CREATE TABLE IF NOT EXISTS pcos_payroll_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID REFERENCES pcos_projects(id) ON DELETE SET NULL,
    
    export_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    exported_by UUID REFERENCES users(id),
    
    timecard_ids UUID[] NOT NULL,
    total_regular_hours NUMERIC(10, 2),
    total_overtime_hours NUMERIC(10, 2),
    total_gross_pay NUMERIC(15, 2),
    
    export_format VARCHAR(50) DEFAULT 'csv',
    file_path TEXT,
    
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'exported', 'imported_confirmation')),
    confirmation_evidence_id UUID,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_exports_tenant ON pcos_payroll_exports(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_exports_project ON pcos_payroll_exports(project_id);

-- ============================================================================
-- STEP 6: Tasks & Evidence Tables
-- ============================================================================

-- Compliance tasks
CREATE TABLE IF NOT EXISTS pcos_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Link to domain object that triggered task
    source_type VARCHAR(50) NOT NULL,  -- 'company', 'project', 'location', 'engagement'
    source_id UUID NOT NULL,
    
    -- Task definition
    task_template_id VARCHAR(100),  -- Reference to YAML template
    task_type VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Assignment
    assigned_to UUID REFERENCES users(id),
    assigned_role VARCHAR(100),  -- Role-based assignment
    
    -- Dates
    due_date DATE,
    reminder_sent_7d BOOLEAN DEFAULT false,
    reminder_sent_3d BOOLEAN DEFAULT false,
    reminder_sent_1d BOOLEAN DEFAULT false,
    
    -- Status
    status pcos_task_status NOT NULL DEFAULT 'pending',
    is_blocking BOOLEAN NOT NULL DEFAULT false,
    
    -- Completion
    completed_at TIMESTAMP WITH TIME ZONE,
    completed_by UUID REFERENCES users(id),
    
    -- Evidence requirement
    requires_evidence BOOLEAN DEFAULT false,
    required_evidence_types pcos_evidence_type[],
    evidence_ids UUID[],
    
    -- Rule that created this task
    rule_id VARCHAR(100),
    rule_pack VARCHAR(100) DEFAULT 'production_ca_la',
    
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_tasks_tenant ON pcos_tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_tasks_source ON pcos_tasks(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_pcos_tasks_status ON pcos_tasks(status);
CREATE INDEX IF NOT EXISTS idx_pcos_tasks_due ON pcos_tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_pcos_tasks_blocking ON pcos_tasks(is_blocking) WHERE is_blocking = true;

-- Task events (audit trail)
CREATE TABLE IF NOT EXISTS pcos_task_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES pcos_tasks(id) ON DELETE CASCADE,
    
    event_type VARCHAR(50) NOT NULL,  -- 'created', 'assigned', 'status_changed', 'completed', 'reminder_sent'
    previous_value JSONB,
    new_value JSONB,
    
    actor_id UUID REFERENCES users(id),
    actor_type VARCHAR(50) DEFAULT 'user',  -- 'user', 'system', 'rule_engine'
    
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_task_events_tenant ON pcos_task_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_task_events_task ON pcos_task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_pcos_task_events_created ON pcos_task_events(created_at);

-- Evidence locker
CREATE TABLE IF NOT EXISTS pcos_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Link to domain object
    entity_type VARCHAR(50) NOT NULL,  -- 'company', 'project', 'engagement', 'location', 'person'
    entity_id UUID NOT NULL,
    
    -- Document metadata
    evidence_type pcos_evidence_type NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- File storage
    file_name VARCHAR(255),
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    s3_key TEXT NOT NULL,  -- S3/LocalStack object key
    
    -- Integrity
    sha256_hash VARCHAR(64),
    
    -- Validity period
    valid_from DATE,
    valid_until DATE,
    
    -- E-sign tracking
    is_signed BOOLEAN DEFAULT false,
    signed_at TIMESTAMP WITH TIME ZONE,
    signer_name VARCHAR(255),
    esign_envelope_id VARCHAR(255),
    
    -- Metadata
    uploaded_by UUID REFERENCES users(id),
    tags TEXT[],
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_evidence_tenant ON pcos_evidence(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_evidence_entity ON pcos_evidence(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_pcos_evidence_type ON pcos_evidence(evidence_type);
CREATE INDEX IF NOT EXISTS idx_pcos_evidence_validity ON pcos_evidence(valid_until);

-- ============================================================================
-- STEP 7: Gate Evaluation Snapshots
-- ============================================================================

CREATE TABLE IF NOT EXISTS pcos_gate_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    evaluated_by UUID REFERENCES users(id),
    trigger_type VARCHAR(50),  -- 'manual', 'auto', 'greenlight_attempt'
    
    current_state pcos_gate_state NOT NULL,
    target_state pcos_gate_state,
    transition_allowed BOOLEAN NOT NULL,
    
    blocking_tasks_count INTEGER NOT NULL DEFAULT 0,
    blocking_task_ids UUID[],
    
    missing_evidence TEXT[],
    risk_score INTEGER NOT NULL DEFAULT 0 CHECK (risk_score >= 0 AND risk_score <= 100),
    
    reasons TEXT[],
    
    snapshot JSONB NOT NULL,  -- Full state snapshot at evaluation time
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_gate_evals_tenant ON pcos_gate_evaluations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_gate_evals_project ON pcos_gate_evaluations(project_id);
CREATE INDEX IF NOT EXISTS idx_pcos_gate_evals_date ON pcos_gate_evaluations(evaluated_at);

-- ============================================================================
-- STEP 8: Contract Templates Registry
-- ============================================================================

CREATE TABLE IF NOT EXISTS pcos_contract_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,  -- NULL = system template
    
    template_code VARCHAR(100) NOT NULL,  -- 'crew_deal_memo', 'talent_release', 'location_release', 'client_agreement'
    template_name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Template content
    template_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    template_body TEXT,  -- Markdown or HTML template
    template_s3_key TEXT,  -- Or reference to stored PDF template
    
    -- Required metadata fields
    required_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_system BOOLEAN NOT NULL DEFAULT false,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcos_templates_tenant ON pcos_contract_templates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pcos_templates_code ON pcos_contract_templates(template_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pcos_templates_unique ON pcos_contract_templates(tenant_id, template_code, template_version);

-- ============================================================================
-- STEP 9: Enable Row-Level Security
-- ============================================================================

-- Enable RLS on all pcos tables
ALTER TABLE pcos_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_company_registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_insurance_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_safety_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_permit_packets ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_people ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_engagements ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_timecards ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_payroll_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_task_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_gate_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcos_contract_templates ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for all tables
DO $$
DECLARE
    tbl_name TEXT;
    policy_sql TEXT;
BEGIN
    FOR tbl_name IN 
        SELECT unnest(ARRAY[
            'pcos_companies', 'pcos_company_registrations', 'pcos_insurance_policies',
            'pcos_safety_policies', 'pcos_projects', 'pcos_locations', 'pcos_permit_packets',
            'pcos_people', 'pcos_engagements', 'pcos_timecards', 'pcos_payroll_exports',
            'pcos_tasks', 'pcos_task_events', 'pcos_evidence', 'pcos_gate_evaluations'
        ])
    LOOP
        -- Drop existing policy if any
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_policy ON %I', tbl_name);
        
        -- Create tenant isolation policy
        policy_sql := format(
            'CREATE POLICY tenant_isolation_policy ON %I
             USING (tenant_id = COALESCE(NULLIF(current_setting(''app.tenant_id'', TRUE), '''')::UUID, ''00000000-0000-0000-0000-000000000001''::UUID))',
            tbl_name
        );
        EXECUTE policy_sql;
    END LOOP;
END $$;

-- Special policy for contract templates (allow system templates for all)
DROP POLICY IF EXISTS tenant_isolation_policy ON pcos_contract_templates;
CREATE POLICY tenant_isolation_policy ON pcos_contract_templates
    USING (
        tenant_id IS NULL  -- System templates visible to all
        OR tenant_id = COALESCE(
            NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
            '00000000-0000-0000-0000-000000000001'::UUID
        )
    );

-- ============================================================================
-- STEP 10: Seed System Data
-- ============================================================================

-- Insert default contract templates
INSERT INTO pcos_contract_templates (id, tenant_id, template_code, template_name, description, is_system, required_fields)
VALUES 
    (gen_random_uuid(), NULL, 'crew_deal_memo', 'Crew Deal Memo', 'Standard crew employment/engagement agreement', true,
     '["person_name", "role_title", "pay_rate", "pay_type", "start_date", "classification"]'::jsonb),
    (gen_random_uuid(), NULL, 'talent_release', 'Talent Release', 'On-camera talent appearance release', true,
     '["person_name", "project_name", "usage_rights", "territory", "term"]'::jsonb),
    (gen_random_uuid(), NULL, 'location_release', 'Location Release', 'Property filming location agreement', true,
     '["property_address", "owner_name", "filming_dates", "fee", "insurance_amount"]'::jsonb),
    (gen_random_uuid(), NULL, 'client_services', 'Client Services Agreement', 'Production services master agreement', true,
     '["client_name", "project_scope", "deliverables", "payment_terms", "intellectual_property"]'::jsonb),
    (gen_random_uuid(), NULL, 'nda', 'Non-Disclosure Agreement', 'Confidentiality agreement for crew/vendors', true,
     '["party_name", "project_name", "term_years"]'::jsonb)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- VERIFICATION NOTES
-- ============================================================================
--
-- To verify this migration:
-- 
-- 1. Check tables created:
--    SELECT table_name FROM information_schema.tables 
--    WHERE table_name LIKE 'pcos_%' ORDER BY table_name;
--
-- 2. Check RLS is enabled:
--    SELECT tablename, rowsecurity FROM pg_tables 
--    WHERE tablename LIKE 'pcos_%';
--
-- 3. Check policies:
--    SELECT schemaname, tablename, policyname 
--    FROM pg_policies WHERE tablename LIKE 'pcos_%';
--
-- ============================================================================
