-- V050 — Enable RLS on food_traceability_list, obligations, obligation_cte_rules
-- ======================================================================
-- Context: These 3 tables were seeded via migrations but never had RLS enabled.
--          All contain FSMA 204 regulatory reference data.
--          food_traceability_list and obligation_cte_rules are global reference data (no tenant_id).
--          obligations has a tenant_id column (text) for tenant-scoped filtering.
-- Risk: LOW — these tables have data (15, 78, 37 rows respectively) but are reference/seed data.
--        Enabling RLS without policies will BLOCK all client access until policies are added.
--        This migration adds both RLS and read-only policies in a single transaction.

BEGIN;

-- ============================================================
-- 1. food_traceability_list (15 rows, no tenant_id)
--    Global FSMA food traceability reference data.
--    Policy: Any authenticated user can read. No client writes.
-- ============================================================

ALTER TABLE public.food_traceability_list ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owner (prevents bypassing via service role in client code)
ALTER TABLE public.food_traceability_list FORCE ROW LEVEL SECURITY;

-- Read-only for authenticated users
CREATE POLICY "food_traceability_list_select_authenticated"
  ON public.food_traceability_list
  FOR SELECT
  TO authenticated
  USING (true);

-- No INSERT/UPDATE/DELETE policies = client cannot modify this table

-- ============================================================
-- 2. obligations (78 rows, has tenant_id as text)
--    FSMA 204 regulatory obligations, tenant-scoped.
--    Policy: Authenticated users can read rows matching their tenant.
-- ============================================================

ALTER TABLE public.obligations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.obligations FORCE ROW LEVEL SECURITY;

-- Read-only, scoped to the user's tenant via memberships table
-- NOTE: obligations.tenant_id is TEXT, memberships.tenant_id is UUID.
--       This cast handles the type mismatch.
CREATE POLICY "obligations_select_tenant_scoped"
  ON public.obligations
  FOR SELECT
  TO authenticated
  USING (
    tenant_id::uuid IN (
      SELECT m.tenant_id
      FROM public.memberships m
      WHERE m.user_id = auth.uid()
    )
  );

-- No INSERT/UPDATE/DELETE policies = client cannot modify

-- ============================================================
-- 3. obligation_cte_rules (37 rows, no tenant_id)
--    CTE (Critical Tracking Event) rules linked to obligations.
--    Policy: Authenticated users can read rules for obligations
--            they have access to (via the obligations tenant scope).
-- ============================================================

ALTER TABLE public.obligation_cte_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.obligation_cte_rules FORCE ROW LEVEL SECURITY;

-- Read-only, scoped via the parent obligation's tenant access
CREATE POLICY "obligation_cte_rules_select_via_obligation"
  ON public.obligation_cte_rules
  FOR SELECT
  TO authenticated
  USING (
    obligation_id IN (
      SELECT o.id
      FROM public.obligations o
      INNER JOIN public.memberships m ON o.tenant_id::uuid = m.tenant_id
      WHERE m.user_id = auth.uid()
    )
  );

-- No INSERT/UPDATE/DELETE policies = client cannot modify

COMMIT;
