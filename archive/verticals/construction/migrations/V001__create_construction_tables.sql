-- Construction Service - Initial Schema
CREATE TABLE bim_change_records (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(100) NOT NULL,
    project_name VARCHAR(255) NOT NULL,
    change_number VARCHAR(100) NOT NULL UNIQUE,
    change_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    file_name VARCHAR(500) NOT NULL,
    file_version VARCHAR(50) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    submitted_by VARCHAR(255) NOT NULL,
    submission_date TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE osha_safety_inspections (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(100) NOT NULL,
    inspection_date TIMESTAMP NOT NULL,
    inspector_name VARCHAR(255) NOT NULL,
    inspection_type VARCHAR(100) NOT NULL,
    violations_found INTEGER DEFAULT 0,
    violation_description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bim_project ON bim_change_records(project_id);
CREATE INDEX idx_osha_project ON osha_safety_inspections(project_id);
