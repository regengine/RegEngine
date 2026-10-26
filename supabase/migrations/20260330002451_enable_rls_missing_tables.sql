
-- 1. food_traceability_list — global FSMA reference data, read-only for authenticated
ALTER TABLE public.food_traceability_list ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.food_traceability_list FORCE ROW LEVEL SECURITY;

CREATE POLICY "food_traceability_list_select_authenticated"
  ON public.food_traceability_list
  FOR SELECT
  TO authenticated
  USING (true);

-- 2. obligations — FSMA 204 obligations, tenant-scoped via tenant_id (text)
ALTER TABLE public.obligations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.obligations FORCE ROW LEVEL SECURITY;

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

-- 3. obligation_cte_rules — CTE rules, scoped via parent obligation's tenant
ALTER TABLE public.obligation_cte_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.obligation_cte_rules FORCE ROW LEVEL SECURITY;

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
;
