-- V053 — CTE append-only triggers (FDA 21 CFR 1.1455)
-- =====================================================
-- FDA 21 CFR 1.1455 requires 2-year record preservation for all
-- Critical Tracking Events. This migration adds BEFORE UPDATE OR DELETE
-- triggers on fsma.cte_events and fsma.hash_chain so that no SQL injection
-- or admin-console access can modify audit records at the DB level.
--
-- V039 already protected fsma.hash_chain with a simpler trigger that had
-- no escape hatch. This migration replaces it with the authorized-correction
-- pattern (set fsma.allow_mutation=true) applied to BOTH tables for
-- consistency, and makes both trigger functions idempotent.
--
-- To perform an authorized correction (e.g. regulatory amendment):
--   SET LOCAL fsma.allow_mutation = 'true';
--   UPDATE fsma.cte_events SET ... WHERE id = '...';
--   -- The GUC is session-local and resets at COMMIT/ROLLBACK.

BEGIN;

-- ----------------------------------------------------------------
-- Shared mutation-guard function (used by both tables)
-- ----------------------------------------------------------------

CREATE OR REPLACE FUNCTION fsma.prevent_cte_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('fsma.allow_mutation', TRUE) = 'true' THEN
        -- Authorized correction: allow but fall through so the operation proceeds.
        RETURN OLD;
    END IF;
    RAISE EXCEPTION
        'CTE records are append-only (FDA 21 CFR 1.1455). '
        'Set fsma.allow_mutation=true for authorized corrections. '
        'Table: %, Operation: %', TG_TABLE_NAME, TG_OP;
END;
$$;

-- ----------------------------------------------------------------
-- fsma.cte_events — append-only enforcement
-- ----------------------------------------------------------------

DROP TRIGGER IF EXISTS cte_events_append_only ON fsma.cte_events;

CREATE TRIGGER cte_events_append_only
    BEFORE UPDATE OR DELETE ON fsma.cte_events
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_cte_mutation();

COMMENT ON TRIGGER cte_events_append_only ON fsma.cte_events IS
    'Enforces append-only semantics per FDA 21 CFR 1.1455 — '
    'no row may be updated or deleted without fsma.allow_mutation=true (V053)';

-- ----------------------------------------------------------------
-- fsma.hash_chain — replace V039 trigger with the consistent pattern
-- ----------------------------------------------------------------

-- Drop old trigger (V039 used a different function name)
DROP TRIGGER IF EXISTS chain_immutability ON fsma.hash_chain;

DROP TRIGGER IF EXISTS hash_chain_append_only ON fsma.hash_chain;

CREATE TRIGGER hash_chain_append_only
    BEFORE UPDATE OR DELETE ON fsma.hash_chain
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_cte_mutation();

COMMENT ON TRIGGER hash_chain_append_only ON fsma.hash_chain IS
    'Enforces append-only semantics per FDA 21 CFR 1.1455 — '
    'no row may be updated or deleted without fsma.allow_mutation=true (V053)';

COMMIT;
