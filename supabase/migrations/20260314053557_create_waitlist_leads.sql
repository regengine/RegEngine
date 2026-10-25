
-- Waitlist / early access leads captured from onboarding + assessment forms
CREATE TABLE public.waitlist_leads (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  email text NOT NULL,
  company text NOT NULL,
  source text NOT NULL DEFAULT 'onboarding',
  created_at timestamptz DEFAULT now() NOT NULL,
  
  -- Prevent duplicate emails
  CONSTRAINT waitlist_leads_email_unique UNIQUE (email)
);

-- Index for quick lookups
CREATE INDEX idx_waitlist_leads_created ON public.waitlist_leads (created_at DESC);

-- Enable RLS
ALTER TABLE public.waitlist_leads ENABLE ROW LEVEL SECURITY;

-- Allow anonymous inserts (the onboarding form uses the anon key)
CREATE POLICY "Allow anonymous inserts" ON public.waitlist_leads
  FOR INSERT
  TO anon
  WITH CHECK (true);

-- Only authenticated/service role can read leads
CREATE POLICY "Service role can read all" ON public.waitlist_leads
  FOR SELECT
  TO authenticated
  USING (true);
;
