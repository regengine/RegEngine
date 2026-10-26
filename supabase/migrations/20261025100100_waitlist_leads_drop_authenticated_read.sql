-- DeepSeek FAIL on #3600: "Service role can read all" was TO authenticated
-- USING (true), so any signed-in user could read every waitlist email.
-- service_role bypasses RLS and needs no policy. Anonymous inserts stay.
DROP POLICY IF EXISTS "Service role can read all" ON public.waitlist_leads;
