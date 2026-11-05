-- v142: runtime grants for data gap tracking.
--
-- Mirrors alembic/versions/20261104_9c0bfe465816_v142_data_gap_runtime_grants.py.
-- The v135 grant was revoked by the per-deploy runtime-role cutover, and the
-- gap insert reads supplier_traceability_lots, which regengine never had, so
-- every gap write failed. v111's inventory keeps these grants across deploys.
-- data_gap_events UPDATE is column-scoped to the close fields.
--
-- Idempotent.

DO $grant$
BEGIN
    IF to_regclass('public.data_gap_events') IS NOT NULL
       AND to_regclass('public.supplier_traceability_lots') IS NOT NULL
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
        REVOKE UPDATE ON TABLE public.data_gap_events FROM regengine;
        GRANT SELECT, INSERT ON TABLE public.data_gap_events TO regengine;
        GRANT UPDATE (closed_at, closing_record_id, closing_record_hash)
            ON TABLE public.data_gap_events TO regengine;
        GRANT SELECT ON TABLE public.data_gap_events TO regengine_sysadmin;
        GRANT SELECT (tenant_id, tlc_code, facility_id) ON TABLE public.supplier_traceability_lots TO regengine;
    END IF;
END
$grant$;
