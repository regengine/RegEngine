-- Close anonymous read/write/delete access on lead-gen tables.
--
-- Root cause of the worst holes: policies named "Service role full access"
-- were created without a TO clause, so they defaulted to PUBLIC — granting
-- every role (including anon) ALL commands with USING(true)/WITH CHECK(true).
-- Combined with Supabase's default table grants to anon, any holder of the
-- public anon key could SELECT, UPDATE and DELETE every row.

-- ── 1. assessment_submissions ────────────────────────────────────────────
-- Public roles get exactly one capability: insert a new lead. Dedupe and
-- enrichment move behind submit_assessment_lead() below.
DROP POLICY IF EXISTS "Service role full access" ON public.assessment_submissions;
DROP POLICY IF EXISTS "Allow public select for duplicate check" ON public.assessment_submissions;
DROP POLICY IF EXISTS "Anon update enrichment" ON public.assessment_submissions;
DROP POLICY IF EXISTS "Allow public inserts" ON public.assessment_submissions;
DROP POLICY IF EXISTS "Anon insert only" ON public.assessment_submissions;

CREATE POLICY "service_role_full_access" ON public.assessment_submissions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Retained so the currently-deployed frontend keeps capturing leads until the
-- RPC switch ships; drop once submit-assessment.ts calls the RPC.
CREATE POLICY "public_lead_capture_insert" ON public.assessment_submissions
    FOR INSERT TO anon, authenticated WITH CHECK (true);

REVOKE SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.assessment_submissions FROM anon, authenticated;

-- ── 2. Single write-only door for the submit flow ────────────────────────
-- SECURITY DEFINER so the caller needs no table privileges; RETURNS void so
-- it cannot be used to read leads back. search_path pinned (lint 0011).
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
        -- Returning lead inside the dedupe window: enrich only supplied fields.
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
        v_name,
        v_email,
        v_company,
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

-- ── 3. product_catalog — same missing-TO-clause bug: anon could write ────
DROP POLICY IF EXISTS "Service role full access" ON public.product_catalog;
CREATE POLICY "service_role_full_access" ON public.product_catalog
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "public_read_product_catalog" ON public.product_catalog
    FOR SELECT TO anon, authenticated USING (true);
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.product_catalog FROM anon, authenticated;

-- ── 4. developer_invite_codes — anon could read every invite code ───────
-- No application reader exists against this Supabase copy (the live invite
-- logic runs on the Railway DB, seeded by alembic v058), so lock it to
-- service_role.
DROP POLICY IF EXISTS "anon_read_invite_codes" ON public.developer_invite_codes;
CREATE POLICY "service_role_full_access" ON public.developer_invite_codes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.developer_invite_codes FROM anon, authenticated;

-- ── 5. SECURITY DEFINER functions callable over PostgREST RPC ───────────
-- EXECUTE reaches anon via the default PUBLIC grant, so revoke that too.
-- notify_new_lead is a trigger function (trigger on_new_lead_notify);
-- trigger firing does not consult the invoker's EXECUTE privilege.
REVOKE EXECUTE ON FUNCTION public.increment_invite_usage(uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.notify_new_lead() FROM PUBLIC, anon, authenticated;;
