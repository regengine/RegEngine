-- alembic-revision: a3f7ce361b0e
-- rendered-from: alembic/versions/20261024_a3f7ce361b0e_v137_epcis_document_receipts.py (upgrade)
-- EPCIS document receipts.
--
-- One row per EPCIS document the ingest routes receive (POST
-- /api/v1/epcis/events, /events/batch and /events/xml), accepted or rejected.
-- document_sha256 is the SHA-256 of the raw request body. error_summary is a
-- short sanitized summary (exception class, HTTP status, error code or failed
-- event count); it never holds payload content or secrets.
--
-- Receipts are tenant scoped. An EPCIS upload is not linked to a supplier
-- facility, so the supplier data quality metric epcis_failed is a tenant wide
-- share shown on every facility.
--
-- Idempotent: safe to re-run. Downgrade block at the end of this file.

CREATE TABLE IF NOT EXISTS fsma.epcis_document_receipts (
    id              uuid primary key default gen_random_uuid(),
    tenant_id       uuid not null,
    document_sha256 text not null,
    received_at     timestamptz not null default now(),
    status          text not null,
    error_summary   text,
    constraint epcis_document_receipts_status_check
        check (status in ('accepted', 'rejected')),
    constraint epcis_document_receipts_sha256_check
        check (document_sha256 ~ '^[0-9a-f]{64}$'),
    constraint epcis_document_receipts_error_summary_length_check
        check (error_summary is null or char_length(error_summary) <= 200)
);

-- Read path: rejected share per tenant over a rolling window.
create index if not exists idx_epcis_document_receipts_tenant_received
    on fsma.epcis_document_receipts (tenant_id, received_at);

ALTER TABLE fsma.epcis_document_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.epcis_document_receipts FORCE ROW LEVEL SECURITY;

-- CASE form, not OR: public.get_tenant_context() raises when app.tenant_id is
-- unset and Postgres does not order OR operands, so the sysadmin arm is tested
-- first (same predicate shape as alembic v096, v134 and v135).
drop policy if exists tenant_isolation_epcis_document_receipts on fsma.epcis_document_receipts;
create policy tenant_isolation_epcis_document_receipts on fsma.epcis_document_receipts
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
-- app role until a migration names them. Insert and select only: a receipt is
-- evidence and is never updated or deleted by the app.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on fsma.epcis_document_receipts from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on fsma.epcis_document_receipts from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname = 'regengine') then
        grant select, insert on fsma.epcis_document_receipts to regengine;
    end if;
    if exists (select 1 from pg_roles where rolname = 'regengine_sysadmin') then
        grant select on fsma.epcis_document_receipts to regengine_sysadmin;
    end if;
end $$;

-- Downgrade (run by hand only; drops every receipt):
--
-- DROP POLICY IF EXISTS tenant_isolation_epcis_document_receipts ON fsma.epcis_document_receipts;
-- DROP INDEX IF EXISTS fsma.idx_epcis_document_receipts_tenant_received;
-- DROP TABLE IF EXISTS fsma.epcis_document_receipts;
