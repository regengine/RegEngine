-- A-2190 / 21 CFR 1.1310: optional business phone on supplier_facilities.
-- Mirrors alembic 20261031_e5cd73f8d1bb_v141_supplier_facility_phone.py.
-- Additive and nullable. Synthetic fixtures only until SEL-590 clears.

ALTER TABLE public.supplier_facilities
  ADD COLUMN IF NOT EXISTS phone text;

COMMENT ON COLUMN public.supplier_facilities.phone IS
  'Facility business phone for 21 CFR 1.1310 location description (A-2190)';
