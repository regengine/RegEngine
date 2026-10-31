-- alembic-revision: a5e7c9b2d341
-- rendered-from: alembic/versions/20261016_a5e7c9b2d341_v128_fsma_rls_policy_repair.py (precheck)
-- Read-only object inventory for apply_v128_fsma_rls.sql.
-- Check the public.get_tenant_context() function used by APPLY.
-- PUBLIC is a pseudo-role.

SELECT 'role' AS object_type, expected.name AS object_name,
       CASE WHEN expected.name = 'PUBLIC' THEN TRUE
            ELSE EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname = expected.name)
       END AS "exists"
FROM (VALUES
    ('PUBLIC'),
    ('anon'),
    ('authenticated'),
    ('regengine'),
    ('regengine_sysadmin')
) AS expected(name)
ORDER BY expected.name;

SELECT 'function' AS object_type, expected.signature AS object_name,
       p.oid IS NOT NULL AS "exists", n.nspname AS resolved_schema
FROM (VALUES
    ('public.get_tenant_context()'),
    ('to_regclass(text)')
) AS expected(signature)
LEFT JOIN pg_catalog.pg_proc p ON p.oid = pg_catalog.to_regprocedure(expected.signature)
LEFT JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
ORDER BY expected.signature;

SELECT 'relation' AS object_type, expected.name AS object_name,
       c.oid IS NOT NULL AS "exists", c.relrowsecurity AS rls_enabled
FROM (VALUES
    ('fsma.canonical_entities'),
    ('fsma.cte_events'),
    ('fsma.cte_kdes'),
    ('fsma.entity_aliases'),
    ('fsma.exception_cases'),
    ('fsma.exception_comments'),
    ('fsma.exception_signoffs'),
    ('fsma.fda_export_log'),
    ('fsma.hash_chain'),
    ('fsma.identity_review_queue'),
    ('fsma.ingestion_runs'),
    ('fsma.request_cases'),
    ('fsma.request_signoffs'),
    ('fsma.response_packages'),
    ('fsma.rule_evaluations'),
    ('fsma.submission_log'),
    ('fsma.tenant_suppliers'),
    ('fsma.traceability_events'),
    ('fsma.cte_kdes_backfill_log_v059'),
    ('fsma.entity_merge_history'),
    ('fsma.exception_attachments'),
    ('fsma.key_data_elements'),
    ('pg_catalog.pg_class'),
    ('pg_catalog.pg_policy'),
    ('pg_catalog.pg_roles')
) AS expected(name)
LEFT JOIN pg_catalog.pg_class c ON c.oid = pg_catalog.to_regclass(expected.name)
ORDER BY expected.name;

SELECT 'policy' AS object_type, expected.relation_name, expected.policy_name,
       EXISTS (
           SELECT 1 FROM pg_catalog.pg_policy p
           WHERE p.polrelid = pg_catalog.to_regclass(expected.relation_name)
             AND p.polname = expected.policy_name
       ) AS "exists"
FROM (VALUES
    ('fsma.canonical_entities', 'v128_canonical_entities_select_regengine'),
    ('fsma.canonical_entities', 'v128_client_guard_canonical_entities'),
    ('fsma.cte_events', 'v128_cte_events_select_regengine'),
    ('fsma.cte_events', 'v128_cte_events_insert_regengine'),
    ('fsma.cte_events', 'v128_cte_events_delete_regengine'),
    ('fsma.cte_events', 'v128_client_guard_cte_events'),
    ('fsma.cte_kdes', 'v128_cte_kdes_select_regengine'),
    ('fsma.cte_kdes', 'v128_cte_kdes_insert_regengine'),
    ('fsma.cte_kdes', 'v128_client_guard_cte_kdes'),
    ('fsma.entity_aliases', 'v128_entity_aliases_select_regengine'),
    ('fsma.entity_aliases', 'v128_client_guard_entity_aliases'),
    ('fsma.exception_cases', 'v128_exception_cases_select_regengine'),
    ('fsma.exception_cases', 'v128_exception_cases_insert_regengine'),
    ('fsma.exception_cases', 'v128_exception_cases_update_regengine'),
    ('fsma.exception_cases', 'v128_client_guard_exception_cases'),
    ('fsma.exception_comments', 'v128_exception_comments_select_regengine'),
    ('fsma.exception_comments', 'v128_exception_comments_insert_regengine'),
    ('fsma.exception_comments', 'v128_client_guard_exception_comments'),
    ('fsma.exception_signoffs', 'v128_exception_signoffs_select_regengine'),
    ('fsma.exception_signoffs', 'v128_exception_signoffs_insert_regengine'),
    ('fsma.exception_signoffs', 'v128_client_guard_exception_signoffs'),
    ('fsma.fda_export_log', 'v128_fda_export_log_select_regengine'),
    ('fsma.fda_export_log', 'v128_fda_export_log_insert_regengine'),
    ('fsma.fda_export_log', 'v128_client_guard_fda_export_log'),
    ('fsma.hash_chain', 'v128_hash_chain_select_regengine'),
    ('fsma.hash_chain', 'v128_hash_chain_insert_regengine'),
    ('fsma.hash_chain', 'v128_client_guard_hash_chain'),
    ('fsma.identity_review_queue', 'v128_identity_review_queue_select_regengine'),
    ('fsma.identity_review_queue', 'v128_client_guard_identity_review_queue'),
    ('fsma.ingestion_runs', 'v128_ingestion_runs_select_regengine'),
    ('fsma.ingestion_runs', 'v128_ingestion_runs_insert_regengine'),
    ('fsma.ingestion_runs', 'v128_ingestion_runs_update_regengine'),
    ('fsma.ingestion_runs', 'v128_ingestion_runs_select_regengine_sysadmin'),
    ('fsma.ingestion_runs', 'v128_client_guard_ingestion_runs'),
    ('fsma.request_cases', 'v128_request_cases_select_regengine'),
    ('fsma.request_cases', 'v128_request_cases_insert_regengine'),
    ('fsma.request_cases', 'v128_request_cases_update_regengine'),
    ('fsma.request_cases', 'v128_client_guard_request_cases'),
    ('fsma.request_signoffs', 'v128_request_signoffs_select_regengine'),
    ('fsma.request_signoffs', 'v128_request_signoffs_insert_regengine'),
    ('fsma.request_signoffs', 'v128_client_guard_request_signoffs'),
    ('fsma.response_packages', 'v128_response_packages_select_regengine'),
    ('fsma.response_packages', 'v128_response_packages_insert_regengine'),
    ('fsma.response_packages', 'v128_client_guard_response_packages'),
    ('fsma.rule_evaluations', 'v128_rule_evaluations_select_regengine'),
    ('fsma.rule_evaluations', 'v128_rule_evaluations_insert_regengine'),
    ('fsma.rule_evaluations', 'v128_client_guard_rule_evaluations'),
    ('fsma.submission_log', 'v128_submission_log_select_regengine'),
    ('fsma.submission_log', 'v128_submission_log_insert_regengine'),
    ('fsma.submission_log', 'v128_client_guard_submission_log'),
    ('fsma.tenant_suppliers', 'v128_tenant_suppliers_select_regengine'),
    ('fsma.tenant_suppliers', 'v128_client_guard_tenant_suppliers'),
    ('fsma.traceability_events', 'v128_traceability_events_select_regengine'),
    ('fsma.traceability_events', 'v128_traceability_events_insert_regengine'),
    ('fsma.traceability_events', 'v128_traceability_events_update_regengine'),
    ('fsma.traceability_events', 'v128_client_guard_traceability_events'),
    ('fsma.cte_kdes_backfill_log_v059', 'v128_client_guard_cte_kdes_backfill_log_v059'),
    ('fsma.entity_merge_history', 'v128_client_guard_entity_merge_history'),
    ('fsma.exception_attachments', 'v128_client_guard_exception_attachments'),
    ('fsma.key_data_elements', 'v128_client_guard_key_data_elements')
) AS expected(relation_name, policy_name)
ORDER BY expected.relation_name, expected.policy_name;
