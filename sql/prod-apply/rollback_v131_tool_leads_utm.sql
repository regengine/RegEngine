-- alembic-revision: 0a329588b824
-- rendered-from: alembic/versions/20261016_0a329588b824_v131_tool_leads_utm.py (downgrade)
-- Manual rollback of revision 0a329588b824. Attribution values will be lost.
BEGIN;

ALTER TABLE public.tool_leads
    DROP COLUMN IF EXISTS utm_campaign,
    DROP COLUMN IF EXISTS utm_medium,
    DROP COLUMN IF EXISTS utm_source;

COMMIT;
