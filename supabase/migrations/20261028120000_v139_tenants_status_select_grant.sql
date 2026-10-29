-- v139 / SEL-616: column-level SELECT on public.tenants(status) for regengine.
--
-- Mirrors alembic/versions/20261028_e7a1c9d2f4b0_v139_tenants_status_select_grant.py.
-- Auth (api_key_store.get_tenant_status) needs status to fail closed on
-- suspended tenants. v111 only granted SELECT (id). Do NOT grant table-level
-- SELECT — names, settings, and webhook config stay control-plane.
--
-- Idempotent. Do not apply to prod without C.Lee's approval via DevOps.
-- Pairs with the Compliance Dashboard degrade in #3740.

DO $grant$
BEGIN
    IF to_regclass('public.tenants') IS NOT NULL
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
        -- Column-level only. Never GRANT SELECT ON public.tenants (table-level).
        GRANT SELECT (status) ON TABLE public.tenants TO regengine;
    END IF;
END
$grant$;

-- Downgrade (run by hand only):
--
-- DO $revoke$
-- BEGIN
--     IF to_regclass('public.tenants') IS NOT NULL
--        AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
--         REVOKE SELECT (status) ON TABLE public.tenants FROM regengine;
--     END IF;
-- END
-- $revoke$;
