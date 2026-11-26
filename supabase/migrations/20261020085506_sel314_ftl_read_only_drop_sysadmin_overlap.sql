-- alembic-revision: 1faec7148e78
-- rendered-from: alembic/versions/20261020_1faec7148e78_v134_sel314_rls_policy_dedupe.py (upgrade)
alter policy ftl_read_only on public.food_traceability_list to regengine;;
