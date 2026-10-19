-- Read-only inventory for apply_v128_policy_merges.sql.
-- PUBLIC is a PostgreSQL pseudo-role, so it has no pg_roles row.
-- get_tenant_context() resolves through the session search_path, as APPLY does.
WITH required(object_type, object_name, on_table) AS (
    VALUES
        ('schema', 'public', NULL),
        ('schema', 'pg_catalog', NULL),
        ('role', 'PUBLIC', NULL),
        ('function', 'get_tenant_context()', NULL),
        ('function', 'pg_catalog.to_regclass', NULL),
        ('function', 'pg_catalog.format', NULL),
        ('function', 'pg_catalog.regexp_replace', NULL),
        ('function', 'pg_catalog.lower', NULL),
        ('catalog_view', 'pg_catalog.pg_policies', NULL),
        ('table', 'public.audit_logs', NULL),
        ('table', 'public.pcos_authority_documents', NULL),
        ('table', 'public.pcos_extracted_facts', NULL),
        ('table', 'public.pcos_fact_citations', NULL),
        ('policy', 'tenant_isolation_audit_logs', 'public.audit_logs'),
        ('policy', 'tenant_isolation_audit', 'public.audit_logs'),
        ('policy', 'tenant_isolation_authority_documents', 'public.pcos_authority_documents'),
        ('policy', 'pcos_authority_documents_tenant_isolation', 'public.pcos_authority_documents'),
        ('policy', 'tenant_isolation_extracted_facts', 'public.pcos_extracted_facts'),
        ('policy', 'pcos_extracted_facts_tenant_isolation', 'public.pcos_extracted_facts'),
        ('policy', 'tenant_isolation_fact_citations', 'public.pcos_fact_citations'),
        ('policy', 'pcos_fact_citations_tenant_isolation', 'public.pcos_fact_citations')
)
SELECT object_type, object_name, on_table,
       CASE object_type
           WHEN 'schema' THEN EXISTS (
               SELECT 1 FROM pg_namespace WHERE nspname = object_name
           )
           WHEN 'role' THEN object_name = 'PUBLIC'
           WHEN 'function' THEN CASE
               WHEN object_name = 'get_tenant_context()'
                   THEN to_regprocedure(object_name) IS NOT NULL
               ELSE EXISTS (
                   SELECT 1 FROM pg_proc AS p
                   JOIN pg_namespace AS n ON n.oid = p.pronamespace
                   WHERE n.nspname = split_part(object_name, '.', 1)
                     AND p.proname = split_part(object_name, '.', 2)
               )
           END
           WHEN 'catalog_view' THEN to_regclass(object_name) IS NOT NULL
           WHEN 'table' THEN to_regclass(object_name) IS NOT NULL
           WHEN 'policy' THEN EXISTS (
               SELECT 1 FROM pg_policies
               WHERE schemaname = split_part(on_table, '.', 1)
                 AND tablename = split_part(on_table, '.', 2)
                 AND policyname = object_name
           )
       END AS exists_now
FROM required
ORDER BY object_type, on_table NULLS FIRST, object_name;
