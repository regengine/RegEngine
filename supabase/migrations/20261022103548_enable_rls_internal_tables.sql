alter table ingestion.jobs enable row level security;
alter table ingestion.audit_log enable row level security;
alter table audit.sysadmin_access_log enable row level security;
alter table dlq.webhook_failures enable row level security;
alter table audit.rls_policy_restoration_log enable row level security;
create policy sysadmin_access_log_sysadmin_select on audit.sysadmin_access_log as permissive for select to regengine_sysadmin using (true);
create policy sysadmin_access_log_sysadmin_insert on audit.sysadmin_access_log as permissive for insert to regengine_sysadmin with check (true);
create policy sysadmin_access_log_regengine_insert on audit.sysadmin_access_log as permissive for insert to regengine with check (true);;
