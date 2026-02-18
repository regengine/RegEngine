-- Automotive Compliance Service - Initial Schema
-- Version: V001
-- Description: Create PPAP submissions, elements, and LPA audit tables

-- PPAP submissions table
CREATE TABLE ppap_submissions (
    id SERIAL PRIMARY KEY,
    part_number VARCHAR(100) NOT NULL,
    part_name VARCHAR(255) NOT NULL,
    submission_level INTEGER NOT NULL CHECK (submission_level >= 1 AND submission_level <= 5),
    oem_customer VARCHAR(255) NOT NULL,
    customer_part_number VARCHAR(100),
    submission_date TIMESTAMP NOT NULL,
    approval_status VARCHAR(50) NOT NULL DEFAULT 'PENDING' CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED', 'INTERIM')),
    approval_date TIMESTAMP,
    approval_notes TEXT,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for ppap_submissions
CREATE INDEX idx_ppap_part_number ON ppap_submissions(part_number);
CREATE INDEX idx_ppap_oem_customer ON ppap_submissions(oem_customer);
CREATE INDEX idx_ppap_submission_date ON ppap_submissions(submission_date);
CREATE INDEX idx_ppap_part_customer ON ppap_submissions(part_number, oem_customer);
CREATE INDEX idx_ppap_status_date ON ppap_submissions(approval_status, submission_date);

-- PPAP elements table (18 PPAP elements)
CREATE TABLE ppap_elements (
    id SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES ppap_submissions(id) ON DELETE CASCADE,
    element_type VARCHAR(100) NOT NULL,
    filename VARCHAR(500) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    mime_type VARCHAR(100),
    version INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    uploaded_by VARCHAR(255)
);

-- Indexes for ppap_elements
CREATE INDEX idx_element_submission_id ON ppap_elements(submission_id);
CREATE INDEX idx_element_submission_type ON ppap_elements(submission_id, element_type);
CREATE INDEX idx_element_content_hash ON ppap_elements(content_hash);

-- LPA (Layered Process Audit) table
CREATE TABLE lpa_audits (
    id SERIAL PRIMARY KEY,
    audit_date TIMESTAMP NOT NULL,
    layer VARCHAR(50) NOT NULL CHECK (layer IN ('EXECUTIVE', 'MANAGEMENT', 'FRONTLINE')),
    part_number VARCHAR(100),
    process_step VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    result VARCHAR(50) NOT NULL CHECK (result IN ('PASS', 'FAIL', 'NA')),
    auditor_name VARCHAR(255) NOT NULL,
    corrective_action TEXT,
    corrective_action_due TIMESTAMP,
    corrective_action_status VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for lpa_audits
CREATE INDEX idx_lpa_audit_date ON lpa_audits(audit_date);
CREATE INDEX idx_lpa_part_number ON lpa_audits(part_number);
CREATE INDEX idx_lpa_result_date ON lpa_audits(result, audit_date);
CREATE INDEX idx_lpa_part_date ON lpa_audits(part_number, audit_date);

-- Update trigger for ppap_submissions.updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ppap_submissions_updated_at BEFORE UPDATE ON ppap_submissions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE ppap_submissions IS 'PPAP (Production Part Approval Process) submissions per AIAG PPAP Manual 4th Edition';
COMMENT ON TABLE ppap_elements IS '18 PPAP elements with cryptographic integrity verification';
COMMENT ON TABLE lpa_audits IS 'Layered Process Audit records for continuous compliance monitoring';

COMMENT ON COLUMN ppap_submissions.submission_level IS 'PPAP level (1-5): determines required documentation depth';
COMMENT ON COLUMN ppap_elements.content_hash IS 'SHA-256 hash for file integrity verification';
COMMENT ON COLUMN ppap_elements.version IS 'Element version number (increments on re-upload)';
COMMENT ON COLUMN lpa_audits.layer IS 'Audit layer: EXECUTIVE, MANAGEMENT, or FRONTLINE';
