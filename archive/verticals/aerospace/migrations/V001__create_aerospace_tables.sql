-- Aerospace Compliance Service - Initial Schema
-- Version: V001
-- Description: Create FAI reports, configuration baselines, and NADCAP evidence tables

-- FAI (First Article Inspection) reports table
CREATE TABLE fai_reports (
    id SERIAL PRIMARY KEY,
    part_number VARCHAR(100) NOT NULL,
    part_name VARCHAR(255) NOT NULL,
    drawing_number VARCHAR(100) NOT NULL,
    drawing_revision VARCHAR(50) NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_part_number VARCHAR(100),
    
    -- AS9102 Forms (JSON)
    form1_data JSONB NOT NULL,
    form2_data JSONB NOT NULL,
    form3_data JSONB NOT NULL,
    
    inspection_method VARCHAR(100) NOT NULL CHECK (inspection_method IN ('ACTUAL', 'DELTA', 'BASELINE')),
    inspection_date TIMESTAMP NOT NULL,
    inspector_name VARCHAR(255) NOT NULL,
    
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    
    approval_status VARCHAR(50) NOT NULL DEFAULT 'PENDING' CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED')),
    approval_date TIMESTAMP,
    approval_notes TEXT,
    
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for fai_reports
CREATE INDEX idx_fai_part_number ON fai_reports(part_number);
CREATE INDEX idx_fai_drawing_number ON fai_reports(drawing_number);
CREATE INDEX idx_fai_customer_name ON fai_reports(customer_name);
CREATE INDEX idx_fai_inspection_date ON fai_reports(inspection_date);
CREATE INDEX idx_fai_part_drawing ON fai_reports(part_number, drawing_revision);
CREATE INDEX idx_fai_customer_date ON fai_reports(customer_name, inspection_date);

-- Configuration baselines table (30-year lifecycle)
CREATE TABLE configuration_baselines (
    id SERIAL PRIMARY KEY,
    assembly_id VARCHAR(100) NOT NULL,
    assembly_name VARCHAR(255) NOT NULL,
    serial_number VARCHAR(100),
    
    baseline_data JSONB NOT NULL,
    baseline_hash VARCHAR(64) NOT NULL UNIQUE,
    
    fai_report_id INTEGER REFERENCES fai_reports(id) ON DELETE SET NULL,
    
    manufacturing_date TIMESTAMP NOT NULL,
    end_of_life_date TIMESTAMP,
    lifecycle_status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE' CHECK (lifecycle_status IN ('ACTIVE', 'MAINTENANCE', 'RETIRED')),
    
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for configuration_baselines
CREATE INDEX idx_baseline_assembly_id ON configuration_baselines(assembly_id);
CREATE INDEX idx_baseline_serial_number ON configuration_baselines(serial_number);
CREATE INDEX idx_baseline_assembly_serial ON configuration_baselines(assembly_id, serial_number);
CREATE INDEX idx_baseline_mfg_date ON configuration_baselines(manufacturing_date);

-- NADCAP special process evidence table
CREATE TABLE nadcap_evidence (
    id SERIAL PRIMARY KEY,
    process_type VARCHAR(100) NOT NULL,
    part_number VARCHAR(100) NOT NULL,
    lot_number VARCHAR(100),
    
    process_parameters JSONB NOT NULL,
    process_results JSONB NOT NULL,
    
    operator_name VARCHAR(255) NOT NULL,
    equipment_id VARCHAR(100) NOT NULL,
    calibration_due_date TIMESTAMP,
    
    process_date TIMESTAMP NOT NULL,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    
    nadcap_certification_number VARCHAR(100),
    certification_expiry TIMESTAMP,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for nadcap_evidence
CREATE INDEX idx_nadcap_process_type ON nadcap_evidence(process_type);
CREATE INDEX idx_nadcap_part_number ON nadcap_evidence(part_number);
CREATE INDEX idx_nadcap_process_date ON nadcap_evidence(process_date);
CREATE INDEX idx_nadcap_part_process ON nadcap_evidence(part_number, process_type);

-- Update triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_fai_reports_updated_at BEFORE UPDATE ON fai_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_configuration_baselines_updated_at BEFORE UPDATE ON configuration_baselines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE fai_reports IS 'AS9102 First Article Inspection reports with 30-year retention';
COMMENT ON TABLE configuration_baselines IS 'Configuration baselines for 30-year aerospace lifecycle tracking';
COMMENT ON TABLE nadcap_evidence IS 'NADCAP special process evidence (heat treat, welding, NDT, chemical)';

COMMENT ON COLUMN fai_reports.content_hash IS 'SHA-256 hash of AS9102 forms for cryptographic integrity';
COMMENT ON COLUMN fai_reports.form1_data IS 'AS9102 Form 1: Part Number Accountability';
COMMENT ON COLUMN fai_reports.form2_data IS 'AS9102 Form 2: Product Accountability (array)';
COMMENT ON COLUMN fai_reports.form3_data IS 'AS9102 Form 3: Characteristic Accountability (array)';
COMMENT ON COLUMN configuration_baselines.baseline_hash IS 'SHA-256 hash of component configuration';
COMMENT ON COLUMN nadcap_evidence.content_hash IS 'SHA-256 hash of process data';
