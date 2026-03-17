-- Lead capture table for free tool assessments and gated results.
-- Stores both gate fields (required) and enrichment fields (optional second step).

CREATE TABLE IF NOT EXISTS public.assessment_submissions (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now() NOT NULL,

    -- Gate fields (required)
    name            text NOT NULL,
    email           text NOT NULL,
    company         text NOT NULL,
    role            text,

    -- Enrichment fields (optional second step)
    facility_count  text,
    phone           text,
    annual_revenue  text,
    current_system  text,       -- spreadsheets / wherefour / sap / none / other
    biggest_retailer text,      -- walmart / kroger / costco / other
    compliance_deadline text,   -- aware / unaware / past-due
    recent_fda_inspection text, -- yes-12mo / yes-older / no / unsure
    product_categories text,    -- free text or comma-separated

    -- Tool context (captured passively)
    quiz_score      numeric,
    quiz_grade      text,
    quiz_answers    jsonb,
    tool_inputs     jsonb,      -- whatever the tool collected before gating
    source          text NOT NULL DEFAULT 'unknown',

    -- Attribution
    utm_source      text,
    utm_medium      text,
    utm_campaign    text,
    referrer        text
);

-- Indexes for dedup and querying
CREATE INDEX IF NOT EXISTS idx_assessment_email ON public.assessment_submissions (email);
CREATE INDEX IF NOT EXISTS idx_assessment_created ON public.assessment_submissions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assessment_source ON public.assessment_submissions (source);

-- RLS: service role can read/write, anon can insert only
ALTER TABLE public.assessment_submissions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON public.assessment_submissions
    FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Anon insert only" ON public.assessment_submissions
    FOR INSERT
    TO anon
    WITH CHECK (true);
