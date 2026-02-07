-- Migration V003: Create Subcontractor Certifications Table
-- Date: 2026-02-01
-- Purpose: Add tracking for subcontractor certifications with tenant isolation

CREATE TABLE subcontractor_certifications (
    id SERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,  -- Multi-tenant isolation
    subcontractor_name VARCHAR(255) NOT NULL,
    subcontractor_code VARCHAR(100),
    certification_type VARCHAR(100) NOT NULL, -- INSURANCE | LICENSE | OSHA_10 | OSHA_30 | TRADE_CERT
    certification_number VARCHAR(100),
    issue_date TIMESTAMP NOT NULL,
    expiration_date TIMESTAMP NOT NULL,
    document_hash VARCHAR(64), -- SHA-256
    is_active BOOLEAN DEFAULT TRUE,
    verification_status VARCHAR(50) NOT NULL DEFAULT 'PENDING', -- PENDING | VERIFIED | EXPIRED
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for performance and filtering
CREATE INDEX idx_subcontractor_tenant ON subcontractor_certifications(tenant_id);
CREATE INDEX idx_subcontractor_name ON subcontractor_certifications(subcontractor_name);
CREATE INDEX idx_subcontractor_tenant_name ON subcontractor_certifications(tenant_id, subcontractor_name);
CREATE INDEX idx_subcontractor_tenant_exp ON subcontractor_certifications(tenant_id, expiration_date);

-- Comments
COMMENT ON TABLE subcontractor_certifications IS 'Tracks subcontractor qualifications and certifications per tenant.';
COMMENT ON COLUMN subcontractor_certifications.tenant_id IS 'Links to admin.tenants (logical FK). Enables multi-tenant isolation.';
