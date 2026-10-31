-- alembic-revision: a5e7c9b2d341
-- rendered-from: alembic/versions/20261016_a5e7c9b2d341_v128_fsma_rls_policy_repair.py (downgrade)
-- v128 FSMA RLS policy repair, rendered from downgrade() in
-- alembic/versions/20261016_a5e7c9b2d341_v128_fsma_rls_policy_repair.py.

BEGIN;

DO $rollback$
BEGIN
    IF to_regclass('fsma.key_data_elements') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_key_data_elements ON fsma.key_data_elements';

    END IF;
END
$rollback$;

DO $rollback$
BEGIN
    IF to_regclass('fsma.exception_attachments') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_exception_attachments ON fsma.exception_attachments';

    END IF;
END
$rollback$;

DO $rollback$
BEGIN
    IF to_regclass('fsma.entity_merge_history') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_entity_merge_history ON fsma.entity_merge_history';

    END IF;
END
$rollback$;

DO $rollback$
BEGIN
    IF to_regclass('fsma.cte_kdes_backfill_log_v059') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_cte_kdes_backfill_log_v059 ON fsma.cte_kdes_backfill_log_v059';

    END IF;
END
$rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.traceability_events') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_traceability_events ON fsma.traceability_events';
                    EXECUTE 'DROP POLICY IF EXISTS v128_traceability_events_select_regengine ON fsma.traceability_events';
EXECUTE 'DROP POLICY IF EXISTS v128_traceability_events_insert_regengine ON fsma.traceability_events';
EXECUTE 'DROP POLICY IF EXISTS v128_traceability_events_update_regengine ON fsma.traceability_events';
                END IF;
            END
            $rollback$;

DO $rollback$
BEGIN
    IF to_regclass('fsma.tenant_suppliers') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_tenant_suppliers ON fsma.tenant_suppliers';
        EXECUTE 'DROP POLICY IF EXISTS v128_tenant_suppliers_select_regengine ON fsma.tenant_suppliers';
    END IF;
END
$rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.submission_log') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_submission_log ON fsma.submission_log';
                    EXECUTE 'DROP POLICY IF EXISTS v128_submission_log_select_regengine ON fsma.submission_log';
EXECUTE 'DROP POLICY IF EXISTS v128_submission_log_insert_regengine ON fsma.submission_log';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.rule_evaluations') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_rule_evaluations ON fsma.rule_evaluations';
                    EXECUTE 'DROP POLICY IF EXISTS v128_rule_evaluations_select_regengine ON fsma.rule_evaluations';
EXECUTE 'DROP POLICY IF EXISTS v128_rule_evaluations_insert_regengine ON fsma.rule_evaluations';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.response_packages') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_response_packages ON fsma.response_packages';
                    EXECUTE 'DROP POLICY IF EXISTS v128_response_packages_select_regengine ON fsma.response_packages';
EXECUTE 'DROP POLICY IF EXISTS v128_response_packages_insert_regengine ON fsma.response_packages';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.request_signoffs') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_request_signoffs ON fsma.request_signoffs';
                    EXECUTE 'DROP POLICY IF EXISTS v128_request_signoffs_select_regengine ON fsma.request_signoffs';
EXECUTE 'DROP POLICY IF EXISTS v128_request_signoffs_insert_regengine ON fsma.request_signoffs';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.request_cases') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_request_cases ON fsma.request_cases';
                    EXECUTE 'DROP POLICY IF EXISTS v128_request_cases_select_regengine ON fsma.request_cases';
EXECUTE 'DROP POLICY IF EXISTS v128_request_cases_insert_regengine ON fsma.request_cases';
EXECUTE 'DROP POLICY IF EXISTS v128_request_cases_update_regengine ON fsma.request_cases';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.ingestion_runs') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_ingestion_runs ON fsma.ingestion_runs';
                    EXECUTE 'DROP POLICY IF EXISTS v128_ingestion_runs_select_regengine ON fsma.ingestion_runs';
EXECUTE 'DROP POLICY IF EXISTS v128_ingestion_runs_insert_regengine ON fsma.ingestion_runs';
EXECUTE 'DROP POLICY IF EXISTS v128_ingestion_runs_update_regengine ON fsma.ingestion_runs';
EXECUTE 'DROP POLICY IF EXISTS v128_ingestion_runs_select_regengine_sysadmin ON fsma.ingestion_runs';
                END IF;
            END
            $rollback$;

DO $rollback$
BEGIN
    IF to_regclass('fsma.identity_review_queue') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_identity_review_queue ON fsma.identity_review_queue';
        EXECUTE 'DROP POLICY IF EXISTS v128_identity_review_queue_select_regengine ON fsma.identity_review_queue';
    END IF;
END
$rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.hash_chain') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_hash_chain ON fsma.hash_chain';
                    EXECUTE 'DROP POLICY IF EXISTS v128_hash_chain_select_regengine ON fsma.hash_chain';
EXECUTE 'DROP POLICY IF EXISTS v128_hash_chain_insert_regengine ON fsma.hash_chain';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.fda_export_log') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_fda_export_log ON fsma.fda_export_log';
                    EXECUTE 'DROP POLICY IF EXISTS v128_fda_export_log_select_regengine ON fsma.fda_export_log';
EXECUTE 'DROP POLICY IF EXISTS v128_fda_export_log_insert_regengine ON fsma.fda_export_log';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.exception_signoffs') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_exception_signoffs ON fsma.exception_signoffs';
                    EXECUTE 'DROP POLICY IF EXISTS v128_exception_signoffs_select_regengine ON fsma.exception_signoffs';
EXECUTE 'DROP POLICY IF EXISTS v128_exception_signoffs_insert_regengine ON fsma.exception_signoffs';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.exception_comments') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_exception_comments ON fsma.exception_comments';
                    EXECUTE 'DROP POLICY IF EXISTS v128_exception_comments_select_regengine ON fsma.exception_comments';
EXECUTE 'DROP POLICY IF EXISTS v128_exception_comments_insert_regengine ON fsma.exception_comments';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.exception_cases') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_exception_cases ON fsma.exception_cases';
                    EXECUTE 'DROP POLICY IF EXISTS v128_exception_cases_select_regengine ON fsma.exception_cases';
EXECUTE 'DROP POLICY IF EXISTS v128_exception_cases_insert_regengine ON fsma.exception_cases';
EXECUTE 'DROP POLICY IF EXISTS v128_exception_cases_update_regengine ON fsma.exception_cases';
                END IF;
            END
            $rollback$;

DO $rollback$
BEGIN
    IF to_regclass('fsma.entity_aliases') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_entity_aliases ON fsma.entity_aliases';
        EXECUTE 'DROP POLICY IF EXISTS v128_entity_aliases_select_regengine ON fsma.entity_aliases';
    END IF;
END
$rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.cte_kdes') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_cte_kdes ON fsma.cte_kdes';
                    EXECUTE 'DROP POLICY IF EXISTS v128_cte_kdes_select_regengine ON fsma.cte_kdes';
EXECUTE 'DROP POLICY IF EXISTS v128_cte_kdes_insert_regengine ON fsma.cte_kdes';
                END IF;
            END
            $rollback$;

DO $rollback$
            BEGIN
                IF to_regclass('fsma.cte_events') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_cte_events ON fsma.cte_events';
                    EXECUTE 'DROP POLICY IF EXISTS v128_cte_events_select_regengine ON fsma.cte_events';
EXECUTE 'DROP POLICY IF EXISTS v128_cte_events_insert_regengine ON fsma.cte_events';
EXECUTE 'DROP POLICY IF EXISTS v128_cte_events_delete_regengine ON fsma.cte_events';
                END IF;
            END
            $rollback$;

DO $rollback$
BEGIN
    IF to_regclass('fsma.canonical_entities') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_canonical_entities ON fsma.canonical_entities';
        EXECUTE 'DROP POLICY IF EXISTS v128_canonical_entities_select_regengine ON fsma.canonical_entities';
    END IF;
END
$rollback$;

COMMIT;
