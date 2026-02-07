-- RLS Policy Example
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation
  ON projects
  USING (tenant_id = current_setting('regengine.tenant_id'));
