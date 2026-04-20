-- V057 — CTE event table immutability triggers
-- ================================================
-- fsma.cte_events and fsma.traceability_events are append-only ledgers.
-- Without DB-level enforcement, any UPDATE or DELETE — via SQL injection,
-- admin console access, or a migration bug — silently destroys audit
-- integrity and FSMA 204 compliance (#1334).
--
-- This migration creates triggers on both tables that reject UPDATE and
-- DELETE at the Postgres level, regardless of caller identity.
--
-- Supersession is handled by inserting a new row with a non-null
-- supersedes_event_id — mutation of an existing row is never valid.

BEGIN;

-- ── cte_events ──────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION fsma.prevent_cte_event_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'fsma.cte_events is append-only — UPDATE and DELETE are prohibited (see #1334). '
        'To supersede an event, insert a new row with supersedes_event_id set.';
END;
$$;

DROP TRIGGER IF EXISTS cte_event_immutability ON fsma.cte_events;

CREATE TRIGGER cte_event_immutability
    BEFORE UPDATE OR DELETE ON fsma.cte_events
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_cte_event_mutation();

COMMENT ON TRIGGER cte_event_immutability ON fsma.cte_events IS
    'Append-only enforcement — no row may be updated or deleted (V057 / #1334)';

-- ── traceability_events ──────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION fsma.prevent_traceability_event_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'fsma.traceability_events is append-only — UPDATE and DELETE are prohibited (see #1334). '
        'To supersede an event, insert a new row with supersedes_event_id set.';
END;
$$;

DROP TRIGGER IF EXISTS traceability_event_immutability ON fsma.traceability_events;

CREATE TRIGGER traceability_event_immutability
    BEFORE UPDATE OR DELETE ON fsma.traceability_events
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_traceability_event_mutation();

COMMENT ON TRIGGER traceability_event_immutability ON fsma.traceability_events IS
    'Append-only enforcement — no row may be updated or deleted (V057 / #1334)';

COMMIT;
