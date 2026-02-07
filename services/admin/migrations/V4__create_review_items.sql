-- Migration V4: Create review_items table with tenant isolation
--
-- This migration creates the review_items table for storing extracted document
-- content alongside review metadata. It enables row-level security to isolate
-- data per tenant using the `app.current_tenant` session setting.

-- Enable UUID generation support
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create review_items table
CREATE TABLE IF NOT EXISTS review_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID,
  doc_hash TEXT NOT NULL,
  text_raw TEXT NOT NULL,

  extraction JSONB NOT NULL,
  provenance JSONB,
  embedding JSONB,

  confidence_score REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING',
  reviewer_id TEXT,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT review_items_status_check
    CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),

  CONSTRAINT review_items_unique_content
    UNIQUE (tenant_id, doc_hash, text_raw)
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_review_items_status ON review_items (status);
CREATE INDEX IF NOT EXISTS idx_review_items_tenant ON review_items (tenant_id);

-- Enable Row Level Security
ALTER TABLE review_items ENABLE ROW LEVEL SECURITY;

-- Ensure tenant isolation policy uses the current tenant context
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'review_items' AND policyname = 'tenant_isolation_policy'
    ) THEN
        DROP POLICY tenant_isolation_policy ON review_items;
    END IF;

    CREATE POLICY tenant_isolation_policy ON review_items
        FOR ALL
        USING (
            tenant_id = current_setting('app.tenant_id', true)::uuid
        );
END $$;
