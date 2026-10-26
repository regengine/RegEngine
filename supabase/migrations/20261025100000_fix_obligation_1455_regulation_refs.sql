-- Correct three 21 CFR §1.1455 paragraph citations in public.obligations.
-- Source: https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455
--   24 hour outbreak response is §1.1455(c)(3)
--   electronic sortable spreadsheet is §1.1455(c)(3)(ii)
--   2 year record retention is §1.1455(d)
-- Rows are targeted by id and by the old value, so rerunning is a no-op.

UPDATE public.obligations
   SET regulation_ref = '21 CFR §1.1455(c)(3)'
 WHERE id = 'b381b42a-b006-4ae3-b763-24a07db06310'
   AND regulation_ref = '21 CFR §1.1455(e)';

UPDATE public.obligations
   SET regulation_ref = '21 CFR §1.1455(c)(3)(ii)'
 WHERE id = '28e26fad-7571-4a97-bb29-0aab029ba153'
   AND regulation_ref = '21 CFR §1.1455(f)';

UPDATE public.obligations
   SET regulation_ref = '21 CFR §1.1455(d)'
 WHERE id = '479ef721-da25-45ca-8455-52df7db65115'
   AND regulation_ref = '21 CFR §1.1455(h)';
