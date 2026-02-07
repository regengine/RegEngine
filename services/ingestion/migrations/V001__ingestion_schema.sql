-- RegEngine Ingestion Framework Database Schema
-- PostgreSQL 14+

-- Create schema
CREATE SCHEMA IF NOT EXISTS ingestion;

-- Documents table
CREATE TABLE IF NOT EXISTS ingestion.documents (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    title TEXT NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    vertical VARCHAR(50) NOT NULL,
    
    -- Cryptographic hashes
    content_sha256 VARCHAR(64) NOT NULL UNIQUE,
    content_sha512 VARCHAR(128) NOT NULL,
    text_sha256 VARCHAR(64),
    text_sha512 VARCHAR(128),
    
    -- Source metadata
    source_url TEXT NOT NULL,
    fetch_timestamp TIMESTAMPTZ NOT NULL,
    http_status INTEGER,
    etag TEXT,
    last_modified TIMESTAMPTZ,
    
    -- Document metadata
    effective_date DATE,
    publication_date TIMESTAMPTZ,
    agencies TEXT[],
    cfr_references TEXT[],
    keywords TEXT[],
    
    -- Content info
    text_length INTEGER DEFAULT 0,
    content_length INTEGER DEFAULT 0,
    content_type VARCHAR(100),
    
    -- Storage reference
    storage_key TEXT NOT NULL,
    
    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Jobs table
CREATE TABLE IF NOT EXISTS ingestion.jobs (
    job_id UUID PRIMARY KEY,
    tenant_id UUID,
    vertical VARCHAR(50) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Progress metrics
    documents_processed INTEGER DEFAULT 0,
    documents_succeeded INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    documents_skipped INTEGER DEFAULT 0,
    
    -- Configuration snapshot
    config JSONB,
    
    -- Error tracking
    error_message TEXT,
    error_details JSONB
);

-- Audit log table
CREATE TABLE IF NOT EXISTS ingestion.audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    job_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id TEXT,
    status VARCHAR(20) NOT NULL,
    details JSONB,
    error TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON ingestion.documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_vertical ON ingestion.documents(vertical);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON ingestion.documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON ingestion.documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_content_sha256 ON ingestion.documents(content_sha256);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON ingestion.jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON ingestion.jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_vertical ON ingestion.jobs(vertical);

CREATE INDEX IF NOT EXISTS idx_audit_log_job_id ON ingestion.audit_log(job_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON ingestion.audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON ingestion.audit_log(action);

-- Full-text search on document titles and text
CREATE INDEX IF NOT EXISTS idx_documents_title_search ON ingestion.documents USING gin(to_tsvector('english', title));

-- Comments
COMMENT ON TABLE ingestion.documents IS 'Regulatory documents with cryptographic verification';
COMMENT ON TABLE ingestion.jobs IS 'Ingestion job tracking and metrics';
COMMENT ON TABLE ingestion.audit_log IS 'Complete audit trail for all operations';

COMMENT ON COLUMN ingestion.documents.content_sha256 IS 'SHA-256 hash for deduplication and verification';
COMMENT ON COLUMN ingestion.documents.content_sha512 IS 'SHA-512 hash for maximum security verification';
