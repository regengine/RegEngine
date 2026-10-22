-- Supabase (auxiliary project magbeerafyxmyuqmbfgv) — assessment lead RPC abuse guard.
-- NOT APPLIED. This project is NOT managed by the repo's Alembic chain (which
-- targets Railway production Postgres). Re-run is idempotent-safe.
--
-- WHY -------------------------------------------------------------------
-- The public submit_assessment_lead RPC is the only write door for assessment
-- leads. Keep its 24-hour email dedupe and insert behavior from
-- supabase-anon-lead-capture-lockdown.sql, but leave existing rows unchanged
-- on anonymous duplicates. The global 60-per-10-minutes limit counts
-- assessment submissions.

DROP TABLE IF EXISTS public.assessment_lead_throttle;

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
    v_text_key    text;
BEGIN
    IF octet_length(payload::text) > 16384 THEN
        RAISE EXCEPTION 'payload_too_large';
    END IF;

    IF v_email IS NULL OR v_email = '' THEN
        RAISE EXCEPTION 'email is required';
    END IF;
    IF v_name IS NULL OR v_company IS NULL THEN
        RAISE EXCEPTION 'name and company are required';
    END IF;
    IF char_length(payload->>'email') > 254
       OR v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' THEN
        RAISE EXCEPTION 'invalid email';
    END IF;
    IF char_length(payload->>'name') > 200
       OR char_length(payload->>'company') > 200 THEN
        RAISE EXCEPTION 'name or company is too long';
    END IF;
    FOREACH v_text_key IN ARRAY ARRAY[
        'role', 'facility_count', 'phone', 'annual_revenue',
        'current_system', 'biggest_retailer', 'compliance_deadline',
        'recent_fda_inspection', 'product_categories', 'quiz_grade',
        'source', 'utm_source', 'utm_medium', 'utm_campaign', 'referrer'
    ] LOOP
        IF char_length(payload->>v_text_key) > 1000 THEN
            RAISE EXCEPTION '% is too long', v_text_key;
        END IF;
    END LOOP;

    -- Serialize the global limit with inserts; concurrent requests cannot
    -- pass the count together and exceed the cap.
    PERFORM pg_advisory_xact_lock(561924, 1);
    IF (SELECT count(*) FROM public.assessment_submissions
        WHERE created_at >= now() - interval '10 minutes') >= 60 THEN
        RAISE EXCEPTION 'rate_limited';
    END IF;

    SELECT id INTO v_existing_id
    FROM public.assessment_submissions
    WHERE email = v_email
      AND created_at >= now() - interval '24 hours'
    ORDER BY created_at DESC
    LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
        -- A supplied email does not prove ownership of the existing lead.
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
