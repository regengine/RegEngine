-- Manufacturing Compliance Service - Initial Schema
-- Version: V001
-- Description: Create NCR, CAPA, supplier quality, and audit finding tables

-- Non-Conformance Reports
CREATE TABLE non_conformance_reports (
    id SERIAL PRIMARY KEY,
    ncr_number VARCHAR(100) NOT NULL UNIQUE,
    detected_date TIMESTAMP NOT NULL,
    detected_by VARCHAR(255) NOT NULL,
    detection_source VARCHAR(100) NOT NULL CHECK (detection_source IN ('INTERNAL_AUDIT', 'CUSTOMER_COMPLAINT', 'PROCESS_MONITORING', 'SUPPLIER_ISSUE')),
    part_number VARCHAR(100),
    lot_number VARCHAR(100),
    quantity_affected INTEGER,
    description TEXT NOT NULL,
    severity VARCHAR(50) NOT NULL CHECK (severity IN ('CRITICAL', 'MAJOR', 'MINOR')),
    containment_action TEXT,
    containment_date TIMESTAMP,
    root_cause TEXT,
    rca_method VARCHAR(100),
    rca_completed_date TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CAPA_IN_PROGRESS', 'VERIFICATION', 'CLOSED')),
    iso_9001_relevant BOOLEAN DEFAULT TRUE,
    iso_14001_relevant BOOLEAN DEFAULT FALSE,
    iso_45001_relevant BOOLEAN DEFAULT FALSE,
    closed_date TIMESTAMP,
    closed_by VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ncr_number ON non_conformance_reports(ncr_number);
CREATE INDEX idx_ncr_detected_date ON non_conformance_reports(detected_date);

-- Corrective Actions
CREATE TABLE corrective_actions (
    id SERIAL PRIMARY KEY,
    ncr_id INTEGER NOT NULL REFERENCES non_conformance_reports(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL CHECK (action_type IN ('CORRECTIVE', 'PREVENTIVE')),
    description TEXT NOT NULL,
    assigned_to VARCHAR(255) NOT NULL,
    assigned_date TIMESTAMP NOT NULL DEFAULT NOW(),
    due_date TIMESTAMP NOT NULL,
    implementation_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    implementation_date TIMESTAMP,
    implementation_notes TEXT,
    verification_required BOOLEAN DEFAULT TRUE,
    verification_date TIMESTAMP,
    verification_result VARCHAR(50),
    verified_by VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_capa_ncr_id ON corrective_actions(ncr_id);

-- Supplier Quality Issues
CREATE TABLE supplier_quality_issues (
    id SERIAL PRIMARY KEY,
    supplier_name VARCHAR(255) NOT NULL,
    supplier_code VARCHAR(100),
    issue_date TIMESTAMP NOT NULL,
    part_number VARCHAR(100) NOT NULL,
    defect_description TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Audit Findings  
CREATE TABLE audit_findings (
    id SERIAL PRIMARY KEY,
    audit_type VARCHAR(100) NOT NULL,
    audit_date TIMESTAMP NOT NULL,
    finding_number VARCHAR(100) NOT NULL UNIQUE,
    finding_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
