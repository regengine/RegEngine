-- V5: Add Production Indexes for Sprint 5 Hardening

-- API Keys Tenant Index (High cardinality filter)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_api_keys_tenant_id ON api_keys (tenant_id);

-- Review Items Confidence Score (For prioritization/filtering)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_review_items_confidence_score ON review_items (confidence_score);

-- Review Items Created At (For time-based queries/retention)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_review_items_created_at ON review_items (created_at);

-- Review Items Composite Status/Confidence (For "Get next pending item" optimization)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_review_items_pending_priority ON review_items (status, confidence_score DESC) WHERE status = 'PENDING';
