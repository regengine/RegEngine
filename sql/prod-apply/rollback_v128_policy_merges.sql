-- alembic-revision: 93eb33f262a1
-- rendered-from: alembic/versions/20261016_93eb33f262a1_v128_consolidate_permissive_policies.py (downgrade)
-- Rendered from revision 93eb33f262a1, downgrade().
BEGIN;

DO $v128$
DECLARE
    pair record;
BEGIN
    FOR pair IN
        SELECT * FROM (VALUES
            ('pcos_fact_citations', 'tenant_isolation_fact_citations', 'pcos_fact_citations_tenant_isolation'),
            ('pcos_extracted_facts', 'tenant_isolation_extracted_facts', 'pcos_extracted_facts_tenant_isolation'),
            ('pcos_authority_documents', 'tenant_isolation_authority_documents', 'pcos_authority_documents_tenant_isolation'),
            ('audit_logs', 'tenant_isolation_audit_logs', 'tenant_isolation_audit')
        ) AS pairs(table_name, retained_name, removed_name)
    LOOP
        IF to_regclass(format('public.%I', pair.table_name)) IS NULL THEN
            CONTINUE;
        END IF;

        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pair.retained_name, pair.table_name);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pair.removed_name, pair.table_name);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I AS PERMISSIVE FOR ALL TO PUBLIC USING ((tenant_id = get_tenant_context())) WITH CHECK ((tenant_id = get_tenant_context()))',
            pair.retained_name, pair.table_name
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I AS PERMISSIVE FOR ALL TO PUBLIC USING ((tenant_id = get_tenant_context()))',
            pair.removed_name, pair.table_name
        );
    END LOOP;
END
$v128$;

COMMIT;
