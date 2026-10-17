-- Manual equivalent of revision 0a329588b824. Do not run after Alembic applied it.
BEGIN;

ALTER TABLE public.tool_leads
    ADD COLUMN IF NOT EXISTS utm_source VARCHAR(100),
    ADD COLUMN IF NOT EXISTS utm_medium VARCHAR(100),
    ADD COLUMN IF NOT EXISTS utm_campaign VARCHAR(100);

COMMIT;
