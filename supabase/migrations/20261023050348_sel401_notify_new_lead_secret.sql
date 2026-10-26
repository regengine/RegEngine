-- SEL-401: shared secret for notify-new-lead (value generated in-DB, never printed)
do $$ begin
  if not exists (select 1 from vault.secrets where name = 'notify_new_lead_secret') then
    perform vault.create_secret(encode(extensions.gen_random_bytes(32), 'hex'), 'notify_new_lead_secret', 'x-webhook-secret for notify-new-lead edge function');
  end if;
end $$;

create or replace function public.get_notify_new_lead_secret()
returns text language sql security definer set search_path = '' stable as $$
  select decrypted_secret from vault.decrypted_secrets where name = 'notify_new_lead_secret' limit 1
$$;
revoke all on function public.get_notify_new_lead_secret() from public, anon, authenticated;
grant execute on function public.get_notify_new_lead_secret() to service_role;

-- previous version called extensions.http_post, but the http extension is not installed, so it always failed silently
create or replace function public.notify_new_lead()
returns trigger language plpgsql security definer set search_path to 'public', 'pg_temp' as $function$
declare
  secret text;
begin
  select decrypted_secret into secret from vault.decrypted_secrets where name = 'notify_new_lead_secret' limit 1;
  perform net.http_post(
    url := 'https://magbeerafyxmyuqmbfgv.supabase.co/functions/v1/notify-new-lead',
    body := jsonb_build_object('record', row_to_json(NEW)::jsonb),
    headers := jsonb_build_object('Content-Type', 'application/json', 'x-webhook-secret', coalesce(secret, ''))
  );
  return NEW;
exception when others then
  raise warning 'notify_new_lead failed: %', SQLERRM;
  return NEW;
end;
$function$;
