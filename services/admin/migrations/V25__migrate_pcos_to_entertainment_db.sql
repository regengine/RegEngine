-- Migration V25: Migrate PCOS Tables to Entertainment DB
--
-- CONTEXT:
-- PCOS tables currently live in Admin DB (Supabase). This creates:
-- 1. Performance issues (high-write production tracking in cloud DB)
-- 2. Architectural inconsistency (Entertainment should have own DB like Energy)
-- 3. Schema pollution (mixing platform auth with vertical-specific logic)
--
-- SOLUTION:
-- 1. Create entertainment DB with PCOS schema
-- 2. Migrate data from Admin DB → Entertainment DB
-- 3. Drop PCOS tables from Admin DB
--
-- EXECUTION PLAN:
-- - Run V001 on entertainment DB first (creates tables)
-- - Run this migration on Admin DB (copies data, drops tables)
-- - Update Admin service to proxy PCOS routes to Entertainment service
--
-- Author: Platform Team
-- Date: 2026-01-30
-- Phase: Architecture Optimization - P1

-- ============================================================================
-- PREREQUISITE CHECK
-- ============================================================================

DO $$
BEGIN
    -- Verify entertainment DB exists before proceeding
    IF NOT EXISTS (
        SELECT 1 FROM pg_database WHERE datname = 'entertainment'
    ) THEN
        RAISE EXCEPTION 'Entertainment database does not exist. Run V001 on entertainment DB first.';
    END IF;
    
    RAISE NOTICE 'Entertainment DB exists. Proceeding with migration.';
END $$;

-- ============================================================================
-- STEP 1: Export Data to Temporary Tables
-- ============================================================================

-- NOTE: In production, use pg_dump/pg_restore or manual data copy
-- This migration provides the structure

COMMENT ON SCHEMA public IS 
    'V25 Migration: PCOS tables moved to entertainment DB. ' ||
    'Run entertainment/V001 first, then copy data manually: ' ||
    'pg_dump -t pcos_* regengine_admin | psql entertainment';

-- ============================================================================
-- STEP 2: Drop PCOS Tables from Admin DB
-- ============================================================================

-- NOTE: Uncomment after data migration verified

/*
-- Drop dependent views/functions first
DROP VIEW IF EXISTS pcos_project_compliance_summary CASCADE;
DROP VIEW IF EXISTS pcos_task_summary CASCADE;

-- Drop tables in dependency order
DROP TABLE IF EXISTS pcos_contract_templates CASCADE;
DROP TABLE IF EXISTS pcos_gate_evaluations CASCADE;
DROP TABLE IF EXISTS pcos_compliance_snapshots CASCADE;
DROP TABLE IF EXISTS pcos_evidence CASCADE;
DROP TABLE IF EXISTS pcos_task_events CASCADE;
DROP TABLE IF EXISTS pcos_tasks CASCADE;
DROP TABLE IF EXISTS pcos_payroll_exports CASCADE;
DROP TABLE IF EXISTS pcos_timecards CASCADE;
DROP TABLE IF EXISTS pcos_engagements CASCADE;
DROP TABLE IF EXISTS pcos_people CASCADE;
DROP TABLE IF EXISTS pcos_permit_packets CASCADE;
DROP TABLE IF EXISTS pcos_locations CASCADE;
DROP TABLE IF EXISTS pcos_projects CASCADE;
DROP TABLE IF EXISTS pcos_safety_policies CASCADE;
DROP TABLE IF EXISTS pcos_insurance_policies CASCADE;
DROP TABLE IF EXISTS pcos_company_registrations CASCADE;
DROP TABLE IF EXISTS pcos_companies CASCADE;

-- Drop enums
DROP TYPE IF EXISTS pcos_jurisdiction CASCADE;
DROP TYPE IF EXISTS pcos_project_type CASCADE;
DROP TYPE IF EXISTS pcos_evidence_type CASCADE;
DROP TYPE IF EXISTS pcos_insurance_type CASCADE;
DROP TYPE IF EXISTS pcos_registration_type CASCADE;
DROP TYPE IF EXISTS pcos_owner_pay_mode CASCADE;
DROP TYPE IF EXISTS pcos_entity_type CASCADE;
DROP TYPE IF EXISTS pcos_gate_state CASCADE;
DROP TYPE IF EXISTS pcos_task_status CASCADE;
DROP TYPE IF EXISTS pcos_classification_type CASCADE;
DROP TYPE IF EXISTS pcos_location_type CASCADE;

RAISE NOTICE 'PCOS tables and enums dropped from Admin DB';
*/

-- ============================================================================
-- MANUAL MIGRATION COMMANDS
-- ============================================================================

-- Run these commands outside of migration:

-- 1. Create entertainment DB and schema:
--    docker exec -i regengine-postgres-1 psql -U regengine -d entertainment < services/entertainment/migrations/V001__create_pcos_schema.sql

-- 2. Copy data from Admin DB to Entertainment DB:
--    docker exec regengine-postgres-1 pg_dump -U regengine -d regengine_admin \
--      -t 'pcos_*' --data-only --column-inserts | \
--    docker exec -i regengine-postgres-1 psql -U regengine -d entertainment

-- 3. Verify data copied:
--    docker exec regengine-postgres-1 psql -U regengine -d entertainment -c "SELECT COUNT(*) FROM pcos_companies;"

-- 4. Uncomment DROP statements above and re-run this migration

-- ============================================================================
-- DOCUMENTATION
-- ============================================================================

COMMENT ON DATABASE regengine_admin IS 
    'RegEngine Admin database (Supabase equivalent). ' ||
    'PCOS tables migrated to entertainment DB as of V25.';
