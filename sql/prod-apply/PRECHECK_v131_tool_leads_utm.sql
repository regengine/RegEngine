-- alembic-revision: 0a329588b824
-- rendered-from: alembic/versions/20261016_0a329588b824_v131_tool_leads_utm.py (precheck)
-- Read-only check before adding campaign attribution to public.tool_leads.
-- Existing columns, if any, must be character varying(100).
SELECT to_regclass('public.tool_leads') AS tool_leads_table;

SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'tool_leads'
  AND column_name IN ('utm_source', 'utm_medium', 'utm_campaign')
ORDER BY column_name;
