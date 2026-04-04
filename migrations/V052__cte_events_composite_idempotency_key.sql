-- V052: Replace single-column unique on cte_events.idempotency_key with
--        a composite UNIQUE (tenant_id, idempotency_key).
--
-- The single-column constraint was too broad: two different tenants
-- ingesting identical events (same canonical hash) would silently drop
-- the second tenant's record. The composite constraint is correct —
-- deduplication is scoped to a tenant.
--
-- cte_persistence.py already issues:
--   ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
-- which requires this composite constraint.

BEGIN;

-- 1. Drop the old single-column unique constraint (auto-named by Postgres).
ALTER TABLE fsma.cte_events
    DROP CONSTRAINT IF EXISTS cte_events_idempotency_key_key;

-- 2. Add the composite unique constraint (idempotent — skip if already present).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'cte_events_tenant_idempotency_key'
          AND conrelid = 'fsma.cte_events'::regclass
    ) THEN
        ALTER TABLE fsma.cte_events
            ADD CONSTRAINT cte_events_tenant_idempotency_key
            UNIQUE (tenant_id, idempotency_key);
    END IF;
END
$$;

-- 3. The existing partial index on idempotency_key alone is now redundant;
--    drop it to avoid double overhead on writes.
DROP INDEX IF EXISTS fsma.idx_cte_events_idempotency;

COMMIT;
