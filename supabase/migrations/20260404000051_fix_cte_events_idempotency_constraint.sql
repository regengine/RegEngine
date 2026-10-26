
-- Make idempotency_key unique per tenant, not globally.
-- Different tenants can legitimately have events with the same content hash.
ALTER TABLE fsma.cte_events DROP CONSTRAINT IF EXISTS cte_events_idempotency_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS cte_events_tenant_idempotency_key ON fsma.cte_events (tenant_id, idempotency_key);
;
