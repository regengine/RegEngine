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
GRANT EXECUTE ON FUNCTION public.submit_assessment_lead(jsonb) TO anon, authenticated;;
