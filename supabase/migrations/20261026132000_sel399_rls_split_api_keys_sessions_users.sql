-- SEL-399: consolidate overlapping RLS policies (RegEngine prod magbeerafyxmyuqmbfgv)
-- PREP ONLY. Do not apply without C.Lee's yes. Take a backup first.
begin;

-- public.api_keys (tenant_id is varchar; compared as text, no cast error risk)
drop policy if exists tenant_isolation_api_keys on public.api_keys;
drop policy if exists tenant_isolation_policy   on public.api_keys;
create policy api_keys_backend on public.api_keys
  as permissive for all to regengine, regengine_sysadmin
  using      ( tenant_id is null
               or tenant_id::text = (select nullif(current_setting('app.tenant_id', true), ''))
               or (current_user = 'regengine_sysadmin'::name AND (select current_setting('regengine.is_sysadmin', true)) = 'true') )
  with check ( tenant_id::text = (select nullif(current_setting('app.tenant_id', true), ''))
               or (current_user = 'regengine_sysadmin'::name AND (select current_setting('regengine.is_sysadmin', true)) = 'true') );
create policy api_keys_authenticated on public.api_keys
  as permissive for all to authenticated
  using      ( tenant_id::text = (select nullif(current_setting('app.tenant_id', true), '')) )
  with check ( tenant_id::text = (select nullif(current_setting('app.tenant_id', true), '')) );

-- public.sessions (no tenant_id column; scoped by user)
drop policy if exists sessions_user_isolation on public.sessions;
drop policy if exists sessions_user_owns      on public.sessions;
create policy sessions_backend on public.sessions
  as permissive for all to regengine, regengine_sysadmin
  using      ( user_id = (select nullif(current_setting('regengine.user_id', true), '')::uuid) or (current_user = 'regengine_sysadmin'::name AND (select current_setting('regengine.is_sysadmin', true)) = 'true') )
  with check ( user_id = (select nullif(current_setting('regengine.user_id', true), '')::uuid) or (current_user = 'regengine_sysadmin'::name AND (select current_setting('regengine.is_sysadmin', true)) = 'true') );
create policy sessions_authenticated on public.sessions
  as permissive for all to authenticated
  using      ( user_id = (select auth.uid()) )
  with check ( user_id = (select auth.uid()) );

-- public.users (no tenant_id column; scoped by id)
drop policy if exists user_self_isolation on public.users;
drop policy if exists users_own_data      on public.users;
create policy users_backend on public.users
  as permissive for all to regengine, regengine_sysadmin
  using      ( id = (select nullif(current_setting('regengine.user_id', true), '')::uuid) or (current_user = 'regengine_sysadmin'::name AND (select current_setting('regengine.is_sysadmin', true)) = 'true') )
  with check ( id = (select nullif(current_setting('regengine.user_id', true), '')::uuid) or (current_user = 'regengine_sysadmin'::name AND (select current_setting('regengine.is_sysadmin', true)) = 'true') );
create policy users_authenticated on public.users
  as permissive for all to authenticated
  using      ( id = (select auth.uid()) )
  with check ( id = (select auth.uid()) );

-- fsma.tenant_portal_links: already one policy per purpose, already role scoped. No change.
-- service_role and postgres have BYPASSRLS: unaffected.
commit;
