-- V35: Fix audit_logs schema mismatches between migration V30 and application code
--
-- Issues:
-- 1. actor_ip was INET type but SQLAlchemy model sends VARCHAR strings
-- 2. audit_action_check constraint was too restrictive (app uses 'session.create', 'tenant.create', etc.)
-- 3. audit_event_category_check constraint was too restrictive (app uses 'authentication', 'tenant_management', etc.)
--
-- These were hotfixed directly in production on 2026-03-08. This migration captures those fixes.

-- 1. Change actor_ip from INET to TEXT to match SQLAlchemy String column
ALTER TABLE audit_logs ALTER COLUMN actor_ip TYPE TEXT;

-- 2. Drop overly restrictive CHECK constraints that don't match application audit events
ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_action_check;
ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_event_category_check;

-- Note: audit_severity_check is retained as it matches the app's usage (info, warning, error, critical)
