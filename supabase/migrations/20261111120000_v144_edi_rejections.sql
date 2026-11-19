-- alembic-revision: 056ffd2f8045
-- rendered-from: alembic/versions/20261111_056ffd2f8045_v144_edi_rejections.py (upgrade)
-- v144: durable EDI rejections.
--
-- Mirrors alembic/versions/20261111_056ffd2f8045_v144_edi_rejections.py.
-- Rejection ids were backed only by one worker's memory. Append-only for the
-- runtime role; RLS is forced. v111's inventory keeps these grants across
-- deploys.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS fsma.edi_rejections (
    rejection_id          text primary key,
    tenant_id             uuid not null,
    transaction_set       text not null,
    traceability_lot_code text,
    partner_id            text,
    source                text,
    reason                text not null,
    needs_review          boolean not null default false,
    errors                jsonb not null default '[]'::jsonb,
    extracted             jsonb not null default '{}'::jsonb,
    recorded_at           timestamptz not null default now()
);

create index if not exists idx_edi_rejections_tenant_recorded
    on fsma.edi_rejections (tenant_id, recorded_at desc);

ALTER TABLE fsma.edi_rejections ENABLE ROW LEVEL SECURITY;

ALTER TABLE fsma.edi_rejections FORCE ROW LEVEL SECURITY;

drop policy if exists tenant_isolation_edi_rejections on fsma.edi_rejections;

create policy tenant_isolation_edi_rejections on fsma.edi_rejections
    for all
    using (
        case
            when (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 and current_user = 'regengine_sysadmin' then true
            else tenant_id = (select public.get_tenant_context())
        end
    )
    with check (
        case
            when (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 and current_user = 'regengine_sysadmin' then true
            else tenant_id = (select public.get_tenant_context())
        end
    );

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on fsma.edi_rejections from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on fsma.edi_rejections from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname = 'regengine') then
        grant select, insert on fsma.edi_rejections to regengine;
    end if;
    if exists (select 1 from pg_roles where rolname = 'regengine_sysadmin') then
        grant select on fsma.edi_rejections to regengine_sysadmin;
    end if;
end $$;
