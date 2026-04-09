-- RLS Policy Example
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation
  ON projects
  USING (tenant_id = get_tenant_context());
