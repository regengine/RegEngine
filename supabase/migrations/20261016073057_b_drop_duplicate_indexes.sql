-- Migration B: drop duplicate indexes (advisor lint duplicate_index, 6 pairs).
-- Drops exactly one index per identical pair; the kept index is named in each comment.
-- No dropped index backs a constraint. public.invites_token_hash_key backs the UNIQUE
-- constraint invites_token_hash_key and is kept.
-- Generated 2026-10-16 from regengine-fix-plan-2026-10-15.md (P1). Not applied.

DROP INDEX IF EXISTS fsma.ux_cte_events_tenant_idempotency_key;  -- keep fsma.cte_events_tenant_idempotency_key
DROP INDEX IF EXISTS public.idx_assessment_created;  -- keep public.idx_assessment_submissions_created
DROP INDEX IF EXISTS public.idx_alerts_severity;  -- keep public.idx_compliance_alerts_severity
DROP INDEX IF EXISTS public.idx_alerts_tenant_status;  -- keep public.idx_compliance_alerts_tenant_status
DROP INDEX IF EXISTS public.idx_status_log_tenant;  -- keep public.idx_compliance_status_log_tenant
DROP INDEX IF EXISTS public.ix_invites_token_hash;  -- keep public.invites_token_hash_key
;
