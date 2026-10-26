-- Follow-up to lockdown_anon_lead_capture_and_definer_rpcs.
-- PR #2682 merged and prod deployment dpl_GadM61PCwi7NTVFFSRxCK44sxSHH
-- (commit 06b6fe1a) is live, so the deployed server action now writes via
-- submit_assessment_lead() only. Remove the transitional direct-INSERT path.
-- After this, anon/authenticated hold NO privileges on the table; the
-- SECURITY DEFINER RPC is the sole write door.
DROP POLICY IF EXISTS "public_lead_capture_insert" ON public.assessment_submissions;
REVOKE INSERT ON public.assessment_submissions FROM anon, authenticated;;
