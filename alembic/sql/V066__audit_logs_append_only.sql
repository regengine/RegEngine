-- V066 — audit_logs append-only enforcement (ISO 27001 12.4.2)
-- =============================================================
-- The tamper-evident design for `audit_logs` (SHA-256 hash chain in
-- `prev_hash`/`integrity_hash`) assumes no UPDATE or DELETE ever fires on
-- the table. The original Flyway V30 migration installed BEFORE UPDATE /
-- BEFORE DELETE triggers to enforce that at the DB layer, but Railway
-- runs Alembic only — Flyway V30 never executes in production, so today
-- the chain is protected by application code alone. Any SQL injection,
-- psql session, or ORM mishap could silently break the chain without the
-- trigger catching it.
--
-- This migration ports V30's append-only lock into Alembic using the
-- same authorized-correction pattern established by V053 for FSMA CTE
-- tables (`fsma.prevent_cte_mutation`). Legitimate break-glass access
-- requires:
--
--     SET LOCAL audit.allow_break_glass = 'true';
--     -- ... emergency correction ...
--     -- GUC is session-local and resets at COMMIT/ROLLBACK.
--
-- Unlike V053's `fsma.allow_mutation` (which exists for regulatory
-- amendments that happen in the normal course of business), the GUC here
-- is strictly for break-glass: any use of it should trigger a security
-- review. The GUC name is deliberately distinct to prevent accidental
-- cross-wiring.
--
-- Idempotent: re-running the migration replaces the function/trigger in
-- place and tolerates the table being absent (e.g. a fresh database
-- where the baseline has not yet created `audit_logs`).

BEGIN;

-- ----------------------------------------------------------------
-- Mutation-guard function for audit_logs
-- ----------------------------------------------------------------

CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('audit.allow_break_glass', TRUE) = 'true' THEN
        -- Break-glass override: allow the operation but emit a WARNING
        -- so the event lands in Postgres logs and any log-forwarder
        -- (Sentry, Datadog) can page on it. Session-local; resets at
        -- COMMIT/ROLLBACK.
        RAISE WARNING
            'audit_logs modification via break-glass. op=% user=% row_id=%',
            TG_OP, current_user, COALESCE(NEW.id::text, OLD.id::text);
        RETURN COALESCE(NEW, OLD);
    END IF;
    RAISE EXCEPTION
        'audit_logs is append-only (ISO 27001 12.4.2). '
        'Operation % rejected. For emergency corrections, '
        'SET LOCAL audit.allow_break_glass=true within a transaction.',
        TG_OP
        USING ERRCODE = 'check_violation';
END;
$$;

-- ----------------------------------------------------------------
-- Trigger install (idempotent on schemas where the table exists)
-- ----------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('public.audit_logs') IS NULL THEN
        RETURN;
    END IF;

    -- Drop any pre-existing triggers (V30 Flyway name and any earlier
    -- Alembic variants) so the canonical Alembic-installed trigger is
    -- the only one on the table.
    DROP TRIGGER IF EXISTS audit_no_update ON public.audit_logs;
    DROP TRIGGER IF EXISTS audit_no_delete ON public.audit_logs;
    DROP TRIGGER IF EXISTS audit_append_only ON public.audit_logs;

    CREATE TRIGGER audit_append_only
        BEFORE UPDATE OR DELETE ON public.audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

    COMMENT ON TRIGGER audit_append_only ON public.audit_logs IS
        'Enforces append-only semantics per ISO 27001 12.4.2 — '
        'no row may be updated or deleted without '
        'SET LOCAL audit.allow_break_glass=true (V066).';

    -- Defense-in-depth at the grant layer. TRUNCATE is especially
    -- important — triggers do not fire on TRUNCATE by default.
    REVOKE UPDATE, DELETE, TRUNCATE ON public.audit_logs FROM PUBLIC;
END$$;

COMMIT;
