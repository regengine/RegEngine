-- V038 — Unify fsma.compliance_alerts schema
-- =============================================
-- Three code paths INSERT into fsma.compliance_alerts with different column
-- sets (cte_persistence.py, webhook_router_v2.py, V31 admin migration).
-- The original V002 schema and V31 schema are incompatible — whichever
-- CREATE TABLE IF NOT EXISTS ran first wins, and all INSERTs from the
-- other schema's callers fail.
--
-- This migration adds every column needed by every caller, with sensible
-- defaults so existing rows and new INSERTs from any path succeed.

BEGIN;

-- Add columns that may be missing depending on which CREATE TABLE ran first.
-- Using IF NOT EXISTS pattern via DO blocks for idempotency.

DO $$
BEGIN
    -- From V31 schema: org_id (needed by cte_persistence.py)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'org_id'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN org_id UUID DEFAULT '00000000-0000-0000-0000-000000000000';
    END IF;

    -- From V31 schema: title (needed by cte_persistence.py)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'title'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN title TEXT DEFAULT '';
    END IF;

    -- From V002 schema: cte_event_id (the FK to cte_events)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'cte_event_id'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN cte_event_id UUID REFERENCES fsma.cte_events(id) ON DELETE CASCADE;
    END IF;

    -- event_id: used by webhook_router_v2.py (stores CTE event UUID as text)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'event_id'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN event_id UUID;
    END IF;

    -- From V002 schema: message (the alert body text)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'message'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN message TEXT DEFAULT '';
    END IF;

    -- From V31 schema: description (used by V31 admin alerts)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'description'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN description TEXT;
    END IF;

    -- From webhook_router_v2.py: details (JSONB for structured alert metadata)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'details'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN details JSONB;
    END IF;

    -- From V002 schema: tenant_id (critical for RLS)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN tenant_id UUID;
    END IF;

    -- From V31 schema: entity_type, entity_id
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'entity_type'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN entity_type TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'entity_id'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN entity_id UUID;
    END IF;

    -- From V002 schema: resolved, resolved_at
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'resolved'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN resolved BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'resolved_at'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN resolved_at TIMESTAMPTZ;
    END IF;

    -- From V31 schema: resolved_by
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'resolved_by'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN resolved_by UUID;
    END IF;

    -- created_at (both schemas have this, but just in case)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'compliance_alerts' AND column_name = 'created_at'
    ) THEN
        ALTER TABLE fsma.compliance_alerts
            ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- Ensure alert_type column exists with a CHECK constraint
-- (Both V002 and V31 have alert_type, just standardize the constraint)
ALTER TABLE fsma.compliance_alerts DROP CONSTRAINT IF EXISTS compliance_alerts_alert_type_check;

-- Ensure indexes exist regardless of which schema was created first
CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON fsma.compliance_alerts (tenant_id);
CREATE INDEX IF NOT EXISTS idx_alerts_event ON fsma.compliance_alerts (cte_event_id);
CREATE INDEX IF NOT EXISTS idx_alerts_event_id ON fsma.compliance_alerts (event_id);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON fsma.compliance_alerts (tenant_id, resolved) WHERE resolved = FALSE;
CREATE INDEX IF NOT EXISTS idx_fsma_alerts_org_unresolved ON fsma.compliance_alerts (org_id) WHERE resolved = FALSE;

COMMENT ON TABLE fsma.compliance_alerts IS
    'Unified compliance alerts — supports inserts from cte_persistence, webhook_router, and admin service (V038)';

COMMIT;
