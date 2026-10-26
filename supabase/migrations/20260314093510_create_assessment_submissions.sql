
CREATE TABLE IF NOT EXISTS public.assessment_submissions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  company TEXT NOT NULL,
  role TEXT,
  facility_count TEXT,
  phone TEXT,
  quiz_score NUMERIC,
  quiz_grade TEXT,
  quiz_answers JSONB,
  source TEXT DEFAULT 'recall-readiness',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for duplicate checking (email + recent submissions)
CREATE INDEX IF NOT EXISTS idx_assessment_submissions_email_created
  ON public.assessment_submissions (email, created_at DESC);

-- Index for listing/filtering
CREATE INDEX IF NOT EXISTS idx_assessment_submissions_created
  ON public.assessment_submissions (created_at DESC);

-- Enable RLS
ALTER TABLE public.assessment_submissions ENABLE ROW LEVEL SECURITY;

-- Allow inserts from anon key (public form submissions)
CREATE POLICY "Allow public inserts" ON public.assessment_submissions
  FOR INSERT TO anon
  WITH CHECK (true);

-- Allow select for duplicate checking from anon key
CREATE POLICY "Allow public select for duplicate check" ON public.assessment_submissions
  FOR SELECT TO anon
  USING (true);
;
