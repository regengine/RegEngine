-- Data gap time to fix.
--
-- One row per data gap on a traceability lot: a required KDE missing from a
-- CTE record, or a CTE record that failed rule validation. A gap opens when a
-- record for (lot_code, cte_type) fails validation and closes when a later
-- record for the same lot_code and cte_type passes. The closing record's id and
-- its canonical SHA-256 (the persisted ledger hash) are kept as the receipt.
--
-- supplier_key is the supplier facility id (public.supplier_traceability_lots
-- maps each tenant TLC to one facility) or 'unassigned' when the lot is not
-- registered to a facility.
--
-- Idempotent: safe to re-run.

create table if not exists public.data_gap_events (
    id                  uuid primary key default gen_random_uuid(),
    tenant_id           uuid not null,
    supplier_key        text not null,
    lot_code            text not null,
    cte_type            text not null,
    gap_kind            text not null,
    gap_key             text not null,
    opened_at           timestamptz not null default now(),
    closed_at           timestamptz,
    closing_record_id   uuid,
    closing_record_hash text,
    constraint data_gap_events_gap_kind_check
        check (gap_kind in ('missing_kde', 'cte_validation_failed')),
    -- An open gap carries no receipt; a closed gap always carries one.
    constraint data_gap_events_close_receipt_check
        check (
            (closed_at is null and closing_record_id is null and closing_record_hash is null)
            or (
                closed_at is not null
                and closed_at >= opened_at
                and closing_record_hash ~ '^[0-9a-f]{64}$'
            )
        )
);

-- Exactly one open row per gap identity. Closed rows are history and may repeat.
create unique index if not exists uq_data_gap_events_open
    on public.data_gap_events (tenant_id, supplier_key, lot_code, cte_type, gap_kind, gap_key)
    where closed_at is null;

-- Close path: every open gap for a tenant lot and CTE, regardless of supplier.
create index if not exists idx_data_gap_events_open_lot
    on public.data_gap_events (tenant_id, lot_code, cte_type)
    where closed_at is null;

-- Read path: per supplier summary.
create index if not exists idx_data_gap_events_supplier
    on public.data_gap_events (tenant_id, supplier_key);

alter table public.data_gap_events enable row level security;
alter table public.data_gap_events force row level security;

-- CASE form, not OR: public.get_tenant_context() raises when app.tenant_id is
-- unset and Postgres does not order OR operands, so the sysadmin arm is tested
-- first (same predicate shape as alembic v096 and v134).
drop policy if exists tenant_isolation_data_gap_events on public.data_gap_events;
create policy tenant_isolation_data_gap_events on public.data_gap_events
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

-- Runtime role allowlist (alembic v111): new tables are inaccessible to the
-- app role until a migration names them. No DELETE: gap history is evidence.
-- Not exposed through the Supabase Data API; the backend reads and writes it.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on public.data_gap_events from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on public.data_gap_events from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname = 'regengine') then
        grant select, insert, update on public.data_gap_events to regengine;
    end if;
    if exists (select 1 from pg_roles where rolname = 'regengine_sysadmin') then
        grant select on public.data_gap_events to regengine_sysadmin;
    end if;
end $$;
