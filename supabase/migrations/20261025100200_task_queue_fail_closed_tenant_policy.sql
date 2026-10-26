-- DeepSeek FAIL on #3600: tenant_isolation_tasks allowed every row when
-- app.tenant_id was ''. Recreate it fail-closed: an empty or NULL tenant
-- context matches nothing, and writes must carry the caller's tenant.
DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue;
CREATE POLICY tenant_isolation_tasks ON fsma.task_queue
  FOR ALL TO public
  USING (
    NULLIF((SELECT current_setting('app.tenant_id', true)), '') IS NOT NULL
    AND tenant_id::text = (SELECT current_setting('app.tenant_id', true))
  )
  WITH CHECK (
    NULLIF((SELECT current_setting('app.tenant_id', true)), '') IS NOT NULL
    AND tenant_id::text = (SELECT current_setting('app.tenant_id', true))
  );
