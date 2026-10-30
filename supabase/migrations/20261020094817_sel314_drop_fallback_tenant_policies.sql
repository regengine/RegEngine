-- alembic-revision: 1faec7148e78
-- rendered-from: alembic/versions/20261020_1faec7148e78_v134_sel314_rls_policy_dedupe.py (upgrade)
DROP POLICY IF EXISTS compliance_alerts_tenant_isolation ON public.compliance_alerts;
DROP POLICY IF EXISTS compliance_status_log_tenant_isolation ON public.compliance_status_log;
DROP POLICY IF EXISTS invites_tenant_isolation ON public.invites;
DROP POLICY IF EXISTS memberships_tenant_isolation ON public.memberships;
DROP POLICY IF EXISTS tenant_isolation_policy ON public.review_items;
DROP POLICY IF EXISTS roles_tenant_isolation ON public.roles;
DROP POLICY IF EXISTS tenant_compliance_status_isolation ON public.tenant_compliance_status;
DROP POLICY IF EXISTS tenant_product_profile_isolation ON public.tenant_product_profile;
DROP POLICY IF EXISTS vertical_projects_tenant_isolation ON public.vertical_projects;;
