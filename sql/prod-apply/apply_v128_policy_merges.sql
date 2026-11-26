-- alembic-revision: 93eb33f262a1
-- rendered-from: alembic/versions/20261016_93eb33f262a1_v128_consolidate_permissive_policies.py (upgrade)
-- Rendered from revision 93eb33f262a1, upgrade().
BEGIN;

DO $v128$
DECLARE
    pair record;
BEGIN
    FOR pair IN
        SELECT * FROM (VALUES
            ('audit_logs', 'tenant_isolation_audit_logs', 'tenant_isolation_audit'),
            ('pcos_authority_documents', 'tenant_isolation_authority_documents', 'pcos_authority_documents_tenant_isolation'),
            ('pcos_extracted_facts', 'tenant_isolation_extracted_facts', 'pcos_extracted_facts_tenant_isolation'),
            ('pcos_fact_citations', 'tenant_isolation_fact_citations', 'pcos_fact_citations_tenant_isolation')
        ) AS pairs(table_name, retained_name, removed_name)
    LOOP
        IF to_regclass(format('public.%I', pair.table_name)) IS NULL THEN
            CONTINUE;
        END IF;

        -- The original pair must match v128's catalog snapshot. The second
        -- accepted state is this file's own result, so a rerun is safe.
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = pair.table_name
              AND policyname = pair.retained_name
              AND permissive = 'PERMISSIVE'
              AND roles = ARRAY['public']::name[]
              AND cmd = 'ALL'
              AND qual = with_check
              AND regexp_replace(lower(qual), '[[:space:]()]', '', 'g') =
                  'tenant_id=get_tenant_contextortenant_id=get_tenant_context'
        ) OR EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = pair.table_name
              AND policyname = pair.removed_name
        ) THEN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = pair.table_name
                  AND policyname = pair.retained_name
                  AND permissive = 'PERMISSIVE'
                  AND roles = ARRAY['public']::name[]
                  AND cmd = 'ALL'
                  AND qual = '(tenant_id = get_tenant_context())'
                  AND with_check = '(tenant_id = get_tenant_context())'
            ) THEN
                RAISE EXCEPTION 'RLS policy snapshot mismatch: public.%.%', pair.table_name, pair.retained_name;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = pair.table_name
                  AND policyname = pair.removed_name
                  AND permissive = 'PERMISSIVE'
                  AND roles = ARRAY['public']::name[]
                  AND cmd = 'ALL'
                  AND qual = '(tenant_id = get_tenant_context())'
                  AND with_check IS NULL
            ) THEN
                RAISE EXCEPTION 'RLS policy snapshot mismatch: public.%.%', pair.table_name, pair.removed_name;
            END IF;
        END IF;

        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pair.retained_name, pair.table_name);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pair.removed_name, pair.table_name);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I AS PERMISSIVE FOR ALL TO PUBLIC USING (((tenant_id = get_tenant_context())) OR ((tenant_id = get_tenant_context()))) WITH CHECK (((tenant_id = get_tenant_context())) OR ((tenant_id = get_tenant_context())))',
            pair.retained_name, pair.table_name
        );
    END LOOP;
END
$v128$;

COMMIT;
