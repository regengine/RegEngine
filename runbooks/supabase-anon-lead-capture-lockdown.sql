-- Supabase (auxiliary project magbeerafyxmyuqmbfgv) — anon access lockdown.
-- APPLIED 2026-07-30 via Supabase MCP apply_migration. Recorded here because
-- this project is NOT managed by the repo's alembic chain (that targets the
-- Railway production Postgres). Re-run is idempotent-safe.
--
-- WHY -------------------------------------------------------------------
-- Policies named "Service role full access" were created with no TO clause,
-- so they defaulted to PUBLIC — granting EVERY role (including anon, whose
-- key ships publicly) ALL commands with USING(true)/WITH CHECK(true). With
-- Supabase's default table grants to anon, any holder of the publishable key
-- could SELECT, UPDATE and DELETE every row of the lead tables. A separate
-- anon SELECT policy ("Allow public select for duplicate check") also exposed
-- every lead's name/email/phone/revenue; the Supabase linter does not flag
-- SELECT USING(true), so it was invisible in the advisor report.
--
-- Verified after apply (as the anon role, via supabase-js):
--   RPC insert            -> ok
--   RPC enrich (dedupe)   -> ok, single row, fields merged
--   direct table SELECT   -> blocked, 42501
--   direct table DELETE   -> blocked, 42501

-- ── assessment_submissions: public roles may only insert a new lead ─────
DROP POLICY IF EXISTS "Service role full access" ON public.assessment_submissions;
DROP POLICY IF EXISTS "Allow public select for duplicate check" ON public.assessment_submissions;
DROP POLICY IF EXISTS "Anon update enrichment" ON public.assessment_submissions;
DROP POLICY IF EXISTS "Allow public inserts" ON public.assessment_submissions;
DROP POLICY IF EXISTS "Anon insert only" ON public.assessment_submissions;

CREATE POLICY "service_role_full_access" ON public.assessment_submissions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Kept so lead capture survived the window between this apply and the
-- frontend deploy that switched to the RPC. Safe to drop once deployed:
--   DROP POLICY "public_lead_capture_insert" ON public.assessment_submissions;
--   REVOKE INSERT ON public.assessment_submissions FROM anon, authenticated;
CREATE POLICY "public_lead_capture_insert" ON public.assessment_submissions
    FOR INSERT TO anon, authenticated WITH CHECK (true);

REVOKE SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.assessment_submissions FROM anon, authenticated;

-- ── Write-only door for the submit flow ────────────────────────────────
-- SECURITY DEFINER so callers need no table privileges; RETURNS void so it
-- cannot read leads back; search_path pinned (linter 0011).
CREATE OR REPLACE FUNCTION public.submit_assessment_lead(payload jsonb)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_email       text := lower(trim(payload->>'email'));
    v_name        text := nullif(trim(payload->>'name'), '');
    v_company     text := nullif(trim(payload->>'company'), '');
    v_existing_id uuid;
BEGIN
    IF v_email IS NULL OR v_email = '' THEN
        RAISE EXCEPTION 'email is required';
    END IF;
    IF v_name IS NULL OR v_company IS NULL THEN
        RAISE EXCEPTION 'name and company are required';
    END IF;

    SELECT id INTO v_existing_id
    FROM public.assessment_submissions
    WHERE email = v_email
      AND created_at >= now() - interval '24 hours'
    ORDER BY created_at DESC
    LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
        UPDATE public.assessment_submissions SET
            facility_count        = coalesce(nullif(payload->>'facility_count', ''), facility_count),
            phone                 = coalesce(nullif(trim(payload->>'phone'), ''), phone),
            annual_revenue        = coalesce(nullif(payload->>'annual_revenue', ''), annual_revenue),
            current_system        = coalesce(nullif(payload->>'current_system', ''), current_system),
            biggest_retailer      = coalesce(nullif(payload->>'biggest_retailer', ''), biggest_retailer),
            compliance_deadline   = coalesce(nullif(payload->>'compliance_deadline', ''), compliance_deadline),
            recent_fda_inspection = coalesce(nullif(payload->>'recent_fda_inspection', ''), recent_fda_inspection),
            product_categories    = coalesce(nullif(payload->>'product_categories', ''), product_categories)
        WHERE id = v_existing_id;
        RETURN;
    END IF;

    INSERT INTO public.assessment_submissions (
        name, email, company, role, facility_count, phone, annual_revenue,
        current_system, biggest_retailer, compliance_deadline,
        recent_fda_inspection, product_categories, quiz_score, quiz_grade,
        quiz_answers, tool_inputs, source, utm_source, utm_medium,
        utm_campaign, referrer
    ) VALUES (
        v_name, v_email, v_company,
        nullif(payload->>'role', ''),
        nullif(payload->>'facility_count', ''),
        nullif(trim(payload->>'phone'), ''),
        nullif(payload->>'annual_revenue', ''),
        nullif(payload->>'current_system', ''),
        nullif(payload->>'biggest_retailer', ''),
        nullif(payload->>'compliance_deadline', ''),
        nullif(payload->>'recent_fda_inspection', ''),
        nullif(payload->>'product_categories', ''),
        (nullif(payload->>'quiz_score', ''))::numeric,
        nullif(payload->>'quiz_grade', ''),
        payload->'quiz_answers',
        payload->'tool_inputs',
        coalesce(nullif(payload->>'source', ''), 'unknown'),
        nullif(payload->>'utm_source', ''),
        nullif(payload->>'utm_medium', ''),
        nullif(payload->>'utm_campaign', ''),
        nullif(payload->>'referrer', '')
    );
END;
$fn$;

REVOKE ALL ON FUNCTION public.submit_assessment_lead(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.submit_assessment_lead(jsonb) TO anon, authenticated;

-- ── product_catalog: same missing-TO-clause bug (anon could write) ─────
DROP POLICY IF EXISTS "Service role full access" ON public.product_catalog;
CREATE POLICY "service_role_full_access" ON public.product_catalog
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "public_read_product_catalog" ON public.product_catalog
    FOR SELECT TO anon, authenticated USING (true);
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.product_catalog FROM anon, authenticated;

-- ── developer_invite_codes: anon could read every invite code ─────────
-- No application reader exists against this Supabase copy; the live invite
-- logic runs on the Railway DB (seeded by alembic v058).
DROP POLICY IF EXISTS "anon_read_invite_codes" ON public.developer_invite_codes;
CREATE POLICY "service_role_full_access" ON public.developer_invite_codes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.developer_invite_codes FROM anon, authenticated;

-- ── SECURITY DEFINER functions reachable over PostgREST RPC ───────────
-- anon inherits EXECUTE from the default PUBLIC grant, so revoke that too.
-- notify_new_lead backs trigger on_new_lead_notify; trigger firing does not
-- consult the invoker's EXECUTE privilege, so revoking is safe.
REVOKE EXECUTE ON FUNCTION public.increment_invite_usage(uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.notify_new_lead() FROM PUBLIC, anon, authenticated;

-- NOT APPLIED — pgaudit_ddl_command_end() / pgaudit_sql_drop() are owned by
-- supabase_admin, so a REVOKE issued as postgres is downgraded to a warning
-- and has no effect. They return `event_trigger`, which PostgreSQL refuses to
-- invoke directly, so they are not actually callable over RPC. Clearing the
-- linter finding requires Supabase support (or moving the pgaudit extension
-- out of the public schema).
-- REVOKE EXECUTE ON FUNCTION public.pgaudit_ddl_command_end() FROM PUBLIC, anon, authenticated;
-- REVOKE EXECUTE ON FUNCTION public.pgaudit_sql_drop() FROM PUBLIC, anon, authenticated;

-- STILL OPEN (deliberately not changed here):
--   * public.tenants "tenants_read_all" — anon SELECT USING(true). Load-bearing:
--     frontend/src/proxy.ts reads tenants.status with the anon key for the
--     tenant-suspension gate. Dropping it makes that gate fail OPEN. Fix needs
--     a narrow get_tenant_status(uuid) RPC plus a proxy.ts change.
--   * waitlist_leads "Service role can read all" and search_queries
--     "Authenticated users can read search analytics" are granted to
--     `authenticated`, not service_role — any signed-in user can read all
--     waitlist emails / search analytics. Same naming-vs-role mistake class.
--   * Supabase Auth leaked-password protection is disabled (dashboard setting).
