-- SEL-399 rollback: recreate the policies exactly as captured 2026-10-24 10:30 PM PT
begin;
drop policy if exists api_keys_backend       on public.api_keys;
drop policy if exists api_keys_authenticated on public.api_keys;
drop policy if exists sessions_backend       on public.sessions;
drop policy if exists sessions_authenticated on public.sessions;
drop policy if exists users_backend          on public.users;
drop policy if exists users_authenticated    on public.users;

create policy tenant_isolation_api_keys on public.api_keys as permissive for all to public
  using ((tenant_id IS NULL) OR ((tenant_id)::text = NULLIF(( SELECT current_setting('app.tenant_id'::text, true) AS current_setting), ''::text)) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND (( SELECT current_setting('regengine.is_sysadmin'::text, true) AS current_setting) = 'true'::text)))
  with check ((tenant_id IS NULL) OR ((tenant_id)::text = NULLIF(( SELECT current_setting('app.tenant_id'::text, true) AS current_setting), ''::text)) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND (( SELECT current_setting('regengine.is_sysadmin'::text, true) AS current_setting) = 'true'::text)));
create policy tenant_isolation_policy on public.api_keys as permissive for all to authenticated
  using (((tenant_id)::uuid = COALESCE((NULLIF(( SELECT current_setting('app.tenant_id'::text, true) AS current_setting), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

create policy sessions_user_isolation on public.sessions as permissive for all to public
  using ((user_id = (NULLIF(( SELECT current_setting('regengine.user_id'::text, true) AS current_setting), ''::text))::uuid) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND (( SELECT current_setting('regengine.is_sysadmin'::text, true) AS current_setting) = 'true'::text)))
  with check ((user_id = (NULLIF(( SELECT current_setting('regengine.user_id'::text, true) AS current_setting), ''::text))::uuid) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND (( SELECT current_setting('regengine.is_sysadmin'::text, true) AS current_setting) = 'true'::text)));
create policy sessions_user_owns on public.sessions as permissive for all to authenticated
  using ((user_id = ( SELECT auth.uid() AS uid)));

create policy user_self_isolation on public.users as permissive for all to public
  using ((id = (NULLIF(( SELECT current_setting('regengine.user_id'::text, true) AS current_setting), ''::text))::uuid) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND (( SELECT current_setting('regengine.is_sysadmin'::text, true) AS current_setting) = 'true'::text)))
  with check ((id = (NULLIF(( SELECT current_setting('regengine.user_id'::text, true) AS current_setting), ''::text))::uuid) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND (( SELECT current_setting('regengine.is_sysadmin'::text, true) AS current_setting) = 'true'::text)));
create policy users_own_data on public.users as permissive for all to authenticated
  using ((id = ( SELECT auth.uid() AS uid)));
commit;
