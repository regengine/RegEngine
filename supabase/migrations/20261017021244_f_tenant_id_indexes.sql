-- Migration: 20261017020100_f_tenant_id_indexes.sql
-- Purpose: Add a tenant_id index to each table that has a tenant_id column
--          but no index with tenant_id as its leading column. This speeds up
--          tenant-scoped queries and row-level security (RLS) predicates.
-- Count: 10 indexes.
-- Note: Plain CREATE INDEX, not CONCURRENTLY, because this migration runs
--       inside a transaction. Each build takes a SHARE lock on its table and
--       blocks writes (INSERT/UPDATE/DELETE) until it finishes. Reads are not
--       blocked. Run off-peak.

CREATE INDEX IF NOT EXISTS idx_evidence_logs_tenant_id ON public.evidence_logs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_compliance_snapshots_tenant_id ON public.compliance_snapshots (tenant_id);
CREATE INDEX IF NOT EXISTS idx_cte_kdes_tenant_id ON fsma.cte_kdes (tenant_id);
CREATE INDEX IF NOT EXISTS idx_exception_comments_tenant_id ON fsma.exception_comments (tenant_id);
CREATE INDEX IF NOT EXISTS idx_exception_attachments_tenant_id ON fsma.exception_attachments (tenant_id);
CREATE INDEX IF NOT EXISTS idx_exception_signoffs_tenant_id ON fsma.exception_signoffs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_obligations_tenant_id ON public.obligations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_webhook_failures_tenant_id ON dlq.webhook_failures (tenant_id);
CREATE INDEX IF NOT EXISTS idx_compliance_notifications_tenant_id ON public.compliance_notifications (tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_suppliers_tenant_id ON fsma.tenant_suppliers (tenant_id);

-- Rollback:
-- DROP INDEX IF EXISTS public.idx_evidence_logs_tenant_id;
-- DROP INDEX IF EXISTS public.idx_compliance_snapshots_tenant_id;
-- DROP INDEX IF EXISTS fsma.idx_cte_kdes_tenant_id;
-- DROP INDEX IF EXISTS fsma.idx_exception_comments_tenant_id;
-- DROP INDEX IF EXISTS fsma.idx_exception_attachments_tenant_id;
-- DROP INDEX IF EXISTS fsma.idx_exception_signoffs_tenant_id;
-- DROP INDEX IF EXISTS public.idx_obligations_tenant_id;
-- DROP INDEX IF EXISTS dlq.idx_webhook_failures_tenant_id;
-- DROP INDEX IF EXISTS public.idx_compliance_notifications_tenant_id;
-- DROP INDEX IF EXISTS fsma.idx_tenant_suppliers_tenant_id;
;
