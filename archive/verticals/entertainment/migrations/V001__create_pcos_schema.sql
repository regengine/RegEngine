-- Migration V001: Create Entertainment (PCOS) Schema
-- 
-- CONTEXT:
-- Move Production Compliance OS (PCOS) tables from Admin DB to dedicated
-- Entertainment vertical database, following RegEngine's vertical isolation pattern.
--
-- RATIONALE:
-- - Entertainment is industry-specific (like Energy, Healthcare, Manufacturing)
-- - PCOS has high write volume (production tracking, timecards, tasks)
-- - Isolating to dedicated DB improves performance and follows architecture
--
-- MIGRATION SOURCE:
-- Admin DB V12__production_compliance_init.sql (PCOS tables)
-- This migration recreates PCOS tables in Entertainment DB
--
-- Author: Platform Team
-- Date: 2026-01-30
-- Phase: Architecture Optimization - P1

-- ============================================================================
-- STEP 1: Enable Extensions
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- STEP 2: Enum Types
-- ============================================================================

-- Location types
CREATE TYPE pcos_location_type AS ENUM (
    'certified_studio',
    'private_property',
    'residential',
    'public_row'
);

-- Worker classification
CREATE TYPE pcos_classification_type AS ENUM (
    'employee',
    'contractor'
);

-- Task status
CREATE TYPE pcos_task_status AS ENUM (
    'pending',
    'in_progress',
    'completed',
    'blocked',
    'cancelled'
);

-- Project gate states
CREATE TYPE pcos_gate_state AS ENUM (
    'draft',
    'ready_for_review',
    'greenlit',
    'in_production',
    'wrap',
    'archived'
);

-- Entity types
CREATE TYPE pcos_entity_type AS ENUM (
    'sole_proprietor',
    'llc_single_member',
    'llc_multi_member',
    's_corp',
    'c_corp',
    'partnership'
);

-- Owner pay mode
CREATE TYPE pcos_owner_pay_mode AS ENUM (
    'draw',
    'payroll'
);

-- Registration type
CREATE TYPE pcos_registration_type AS ENUM (
    'sos',          -- Secretary of State
    'ftb',          -- Franchise Tax Board
    'btrc',         -- LA Business Tax Registration Certificate
    'dba_fbn',      -- DBA / Fictitious Business Name
    'edd',          -- Employment Development Department
    'dir'           -- Department of Industrial Relations
);

-- Insurance policy type
CREATE TYPE pcos_insurance_type AS ENUM (
    'general_liability',
    'workers_comp',
    'errors_omissions',
    'equipment',
    'auto',
    'umbrella'
);

-- Evidence type
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

-- Project type
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

-- Jurisdiction
CREATE TYPE pcos_jurisdiction AS ENUM (
    'la_city',
    'la_county',
    'ca_other',
    'out_of_state'
);

-- ============================================================================
-- STEP 3: Core Tables
-- ============================================================================

-- NOTE: tenant_id links to Admin DB tenants table (logical foreign key, not enforced)
-- This allows cross-database tenant isolation without hard DB constraints

-- Companies
CREATE TABLE pcos_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,  -- Links to admin.tenants
    
    -- Legal entity info
    legal_name VARCHAR(255) NOT NULL,
    entity_type pcos_entity_type NOT NULL,
    ein VARCHAR(20),
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
    
    -- Payroll provider config
    payroll_provider_config JSONB DEFAULT '{}'::jsonb,
    
    -- Metadata
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'archived')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_by UUID,  -- Links to admin.users
    updated_by UUID   -- Links to admin.users
);

CREATE INDEX idx_pcos_companies_tenant ON pcos_companies(tenant_id);
CREATE INDEX idx_pcos_companies_status ON pcos_companies(status);

-- Company registrations
CREATE TABLE pcos_company_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    company_id UUID NOT NULL REFERENCES pcos_companies(id) ON DELETE CASCADE,
    
    registration_type pcos_registration_type NOT NULL,
    registration_number VARCHAR(100),
    registration_name VARCHAR(255),
    jurisdiction VARCHAR(100),
    
    issue_date DATE,
    expiration_date DATE,
    renewal_date DATE,
    
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'expired', 'cancelled')),
    evidence_id UUID,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pcos_registrations_tenant ON pcos_company_registrations(tenant_id);
CREATE INDEX idx_pcos_registrations_company ON pcos_company_registrations(company_id);
CREATE INDEX idx_pcos_registrations_expiry ON pcos_company_registrations(expiration_date);

-- Insurance policies
CREATE TABLE pcos_insurance_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
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
    evidence_id UUID,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pcos_insurance_tenant ON pcos_insurance_policies(tenant_id);
CREATE INDEX idx_pcos_insurance_company ON pcos_insurance_policies(company_id);
CREATE INDEX idx_pcos_insurance_expiry ON pcos_insurance_policies(expiration_date);

-- Projects
CREATE TABLE pcos_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    company_id UUID NOT NULL REFERENCES pcos_companies(id) ON DELETE CASCADE,
    
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50),
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
    gate_state_changed_at TIMESTAMPTZ,
    gate_state_changed_by UUID,
    
    -- Risk assessment
    risk_score INTEGER DEFAULT 0 CHECK (risk_score >= 0 AND risk_score <= 100),
    blocking_tasks_count INTEGER DEFAULT 0,
    
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_by UUID,
    updated_by UUID
);

CREATE INDEX idx_pcos_projects_tenant ON pcos_projects(tenant_id);
CREATE INDEX idx_pcos_projects_company ON pcos_projects(company_id);
CREATE INDEX idx_pcos_projects_gate ON pcos_projects(gate_state);
CREATE INDEX idx_pcos_projects_dates ON pcos_projects(first_shoot_date, start_date);

-- People registry
CREATE TABLE pcos_people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    
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
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pcos_people_tenant ON pcos_people(tenant_id);
CREATE INDEX idx_pcos_people_name ON pcos_people(last_name, first_name);
CREATE INDEX idx_pcos_people_email ON pcos_people(email);

-- Engagements
CREATE TABLE pcos_engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    person_id UUID NOT NULL REFERENCES pcos_people(id) ON DELETE CASCADE,
    
    role_title VARCHAR(255) NOT NULL,
    department VARCHAR(100),
    
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
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pcos_engagements_tenant ON pcos_engagements(tenant_id);
CREATE INDEX idx_pcos_engagements_project ON pcos_engagements(project_id);
CREATE INDEX idx_pcos_engagements_person ON pcos_engagements(person_id);
CREATE INDEX idx_pcos_engagements_classification ON pcos_engagements(classification);

-- Tasks
CREATE TABLE pcos_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    
    source_type VARCHAR(50) NOT NULL,
    source_id UUID NOT NULL,
    
    task_template_id VARCHAR(100),
    task_type VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    
    assigned_to UUID,
    assigned_role VARCHAR(100),
    
    due_date DATE,
    reminder_sent_7d BOOLEAN DEFAULT false,
    reminder_sent_3d BOOLEAN DEFAULT false,
    reminder_sent_1d BOOLEAN DEFAULT false,
    
    status pcos_task_status NOT NULL DEFAULT 'pending',
    is_blocking BOOLEAN NOT NULL DEFAULT false,
    
    completed_at TIMESTAMPTZ,
    completed_by UUID,
    
    requires_evidence BOOLEAN DEFAULT false,
    required_evidence_types pcos_evidence_type[],
    evidence_ids UUID[],
    
    rule_id VARCHAR(100),
    rule_pack VARCHAR(100) DEFAULT 'production_ca_la',
    
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pcos_tasks_tenant ON pcos_tasks(tenant_id);
CREATE INDEX idx_pcos_tasks_source ON pcos_tasks(source_type, source_id);
CREATE INDEX idx_pcos_tasks_status ON pcos_tasks(status);
CREATE INDEX idx_pcos_tasks_due ON pcos_tasks(due_date);
CREATE INDEX idx_pcos_tasks_blocking ON pcos_tasks(is_blocking) WHERE is_blocking = true;

-- Evidence locker
CREATE TABLE pcos_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    
    evidence_type pcos_evidence_type NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    
    file_name VARCHAR(255),
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    s3_key TEXT NOT NULL,
    
    sha256_hash VARCHAR(64),
    
    valid_from DATE,
    valid_until DATE,
    
    is_signed BOOLEAN DEFAULT false,
    signed_at TIMESTAMPTZ,
    signer_name VARCHAR(255),
    esign_envelope_id VARCHAR(255),
    
    uploaded_by UUID,
    tags TEXT[],
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pcos_evidence_tenant ON pcos_evidence(tenant_id);
CREATE INDEX idx_pcos_evidence_entity ON pcos_evidence(entity_type, entity_id);
CREATE INDEX idx_pcos_evidence_type ON pcos_evidence(evidence_type);
CREATE INDEX idx_pcos_evidence_validity ON pcos_evidence(valid_until);

-- Compliance snapshots (PCOS-specific, separate from energy compliance_snapshots)
CREATE TABLE pcos_compliance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL REFERENCES pcos_projects(id) ON DELETE CASCADE,
    
    snapshot_name VARCHAR(255) NOT NULL,
    snapshot_reason TEXT,
    created_by VARCHAR(255) NOT NULL,
    
    compliance_status VARCHAR(50) NOT NULL,
    blocking_tasks_count INTEGER NOT NULL DEFAULT 0,
    risk_score INTEGER DEFAULT 0,
    
    -- Full state capture
    project_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    tasks_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    content_hash VARCHAR(64) NOT NULL,
    hash_algorithm VARCHAR(20) NOT NULL DEFAULT 'SHA-256',
    
    previous_snapshot_id UUID REFERENCES pcos_compliance_snapshots(id),
    
    captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pcos_snapshots_tenant ON pcos_compliance_snapshots(tenant_id);
CREATE INDEX idx_pcos_snapshots_project ON pcos_compliance_snapshots(project_id);
CREATE INDEX idx_pcos_snapshots_time ON pcos_compliance_snapshots(captured_at DESC);

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON DATABASE entertainment_db IS 
    'Entertainment vertical database for Production Compliance OS (PCOS). Migrated from Admin DB for performance isolation.';

COMMENT ON TABLE pcos_companies IS 
    'Production companies (sole props, LLCs, S-corps) operating in CA/LA entertainment industry';

COMMENT ON TABLE pcos_projects IS 
    'Film/TV productions tracked through compliance gates (draft → greenlit → production → wrap)';

COMMENT ON TABLE pcos_tasks IS 
    'Compliance tasks auto-generated from rule packs (production_ca_la)';

COMMENT ON TABLE pcos_compliance_snapshots IS 
    'Point-in-time project compliance state for audit defense. Separate from energy vertical compliance_snapshots.';

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Verify schema created
-- \dt
-- Expected: 13+ pcos_* tables

-- Verify enums
-- \dT
-- Expected: 11 pcos_* enums
