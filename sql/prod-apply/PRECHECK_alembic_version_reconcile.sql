-- Read-only reconcile precheck for public.alembic_version.
-- Companion to docs/runbooks/ALEMBIC_VERSION_RECONCILE.md and
-- docs/decisions/2026-10-30-schema-change-channel.md.
--
-- What it does: for every Alembic revision after 267d8053ced5 (v079, the
-- revision production was observed at on 2026-10-20), test one catalog
-- signature that the revision's upgrade() leaves behind, in chain order.
-- It then reports the highest revision through which every observable
-- signature is present, and every revision whose signature is present
-- beyond that point (effects that reached the database without the chain).
--
-- What it never does: write. Only BEGIN READ ONLY, SET LOCAL, WITH/SELECT and
-- ROLLBACK appear below. It reads pg_catalog only; no customer rows.
--
-- Run:  psql -X -v ON_ERROR_STOP=1 -f sql/prod-apply/PRECHECK_alembic_version_reconcile.sql
--
-- Reading the result:
--   present = true   the signature exists (or, for absent_* kinds, is gone)
--   present = false  the revision's effect is not in this database
--   present = NULL   not observable from the catalog (merge or data revision,
--                    or a role the check needs does not exist)
-- Kinds absent_relation, absent_fk and absent_policy read true on any
-- database that never had the object, so they cannot distinguish "never
-- created" from "removed by the revision"; weigh them with their neighbours.
-- Signatures marked HAND-APPLIED in note are expected present even on a
-- database whose version row is far behind: they reached production through
-- supabase/migrations or sql/prod-apply, not through Alembic.

BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL search_path = pg_catalog;

-- 1. The version row as recorded.
SELECT 'alembic_version' AS object_type, version_num AS value
FROM public.alembic_version;

-- 2. One signature per revision, in chain order.
WITH sig(ord, revision, label, kind, arg1, arg2, note) AS (
  VALUES
    (1, '8a9b0c1d2e3f', 'v080', 'relation', 'fsma.rule_rejections', '', ''),
    (2, 'c1d2e3f4a5b6', 'v079', 'relation', 'fsma.ingestion_run_receipts', '', 'second v079 label; use revision ids'),
    (3, 'd2e3f4a5b6c7', 'v080', 'relation', 'fsma.agent_artifacts', '', ''),
    (4, '3e7a1c5b9f24', 'v081', 'column', 'fsma.key_data_elements', 'tenant_id', ''),
    (5, 'a7b8c9d0e1f2', 'v081', 'index', 'fsma.idx_cte_events_tenant_sha', '', ''),
    (6, '70d5e59e3257', 'v082', 'merge', '', '', 'merge revision; nothing to observe'),
    (7, 'e3f4a5b6c7d8', 'v083', 'column', 'fsma.cte_kdes_backfill_log_v059', 'tenant_id', ''),
    (8, 'da5d93004161', 'v084', 'relation', 'public.user_emails', '', 'passwordless auth schema'),
    (9, 'f8a9b0c1d2e3', 'v085', 'column', 'public.organizations', 'domain_name', ''),
    (10, 'a9b0c1d2e3f4', 'v086', 'column', 'public.organizations', 'domain_verified', ''),
    (11, 'b0c1d2e3f4a5', 'v087', 'relation', 'public.webauthn_credentials', '', ''),
    (12, 'bdb2bec8bcc6', 'v088', 'absent_relation', 'public.password_reset_tokens', '', 'destructive: table dropped'),
    (13, '38e02636e340', 'v089', 'column', 'public.sessions', 'authenticated_at', ''),
    (14, '44225a26ed58', 'v090', 'column', 'public.audit_logs', 'sequence_num', ''),
    (15, '4c5d6e7f8a9b', 'v090', 'absent_fk', 'fsma.hash_chain', 'fsma.cte_events', 'also hand-applied by supabase 20260403235145'),
    (16, 'd1bdfe74d1fd', 'v090', 'merge', '', '', ''),
    (17, 'a128f7f95db8', 'v090', 'policy', 'tenant_isolation_tasks', 'fsma.task_queue', 'AMBIGUOUS: supabase 20261025100200 recreates a policy of the same name'),
    (18, '127a24ffb54c', 'v091', 'constraint', 'uq_request_signoffs_tenant_case_type', 'fsma.request_signoffs', ''),
    (19, 'b3c8e1f4a627', 'v092', 'privilege_absent', 'anon', 'fsma.cte_events', 'client-role lockdown; NULL when role anon is absent'),
    (20, '16cb29a3938c', 'v093', 'relation', 'public.scheduler_seen_items', '', ''),
    (21, 'feb267263e0a', 'v094', 'data_user_emails_fingerprint', '', '', 'data backfill; NULL when public.user_emails is absent'),
    (22, 'c7a1e5f2b9d4', 'v095', 'relation', 'fsma.remediation_cases', '', ''),
    (23, 'c3a51e2f7b90', 'v096', 'policy', 'tenant_isolation_audit', 'fsma.fsma_audit_trail', ''),
    (24, 'e4d7b2a9c561', 'v097', 'func_config_search_path', 'public.get_tenant_context', '', ''),
    (25, '8b2f4e6a9c31', 'v098', 'relation', 'fsma.exchange_packages', '', ''),
    (26, '2aa607050c84', 'v099', 'function', 'public.set_admin_context', '', ''),
    (27, '3ba0291a69f2', 'v100', 'policy', 'memberships_sysadmin_read', 'public.memberships', ''),
    (28, '7c4d9a1f2e8b', 'v101', 'column', 'fsma.notification_outbox', 'attempts', ''),
    (29, '1b10a708e36a', 'v102', 'relation', 'fsma.mock_audit_drills', '', ''),
    (30, 'fcf558aeb1e2', 'v103', 'relation', 'fsma.compliance_evidence_snapshots', '', ''),
    (31, '7c1f2c8ffe05', 'v104', 'policy', 'obligation_cte_rules_tenant_isolation', 'public.obligation_cte_rules', ''),
    (32, '323c945cf68d', 'v105', 'relation', 'fsma.rule_evaluation_deadletter', '', ''),
    (33, '8633e0a7a84e', 'v106', 'relation', 'fsma.tenant_seed_state', '', ''),
    (34, 'c35358cae7d4', 'v107', 'func_src', 'fsma.prevent_cte_mutation', 'RETURN NEW', ''),
    (35, 'a43b0fb1edd0', 'v108', 'column', 'fsma.traceability_events', 'evaluation_error', ''),
    (36, '51701aedee57', 'v109', 'function', 'fsma.get_team_roster', '', ''),
    (37, '6f8c2d1a4b90', 'v110', 'policy', 'developers_insert_own_profile', 'public.developer_profiles', ''),
    (38, 'df664d92adba', 'v111', 'force_rls', 'public.controls', '', ''),
    (39, 'd8b2056471a7', 'v112', 'func_secdef', 'seed_obligations_for_tenant', '', 'any schema'),
    (40, '4e9c1f7a02b6', 'v113', 'function', 'public.get_invite_tenant_by_token_hash', '', ''),
    (41, 'c4f1a7e93b28', 'v114', 'column', 'fsma.fda_export_log', 'include_pii', ''),
    (42, 'c1d4e8f20a37', 'v115', 'index', 'fsma.idx_task_queue_idempotency', '', ''),
    (43, 'e4a7c2d91b06', 'v116', 'data', '', '', 'rule seed integrity; not catalog-observable'),
    (44, '6f4c2a9d8b17', 'v110', 'data_roles_review_decide', '', '', 'NULL when public.roles is absent'),
    (45, 'b71d9e4c2a60', 'v111', 'force_rls', 'fsma.organizations', '', 'runtime role grants; FORCE RLS is the observable part'),
    (46, '8b866e4b4798', 'v119', 'data', '', '', 'seed reconcile; not catalog-observable'),
    (47, 'c6a120b4e901', 'v120', 'data', '', '', 'rule citations; not catalog-observable'),
    (48, '7551be5c64ac', 'v121', 'index', 'fsma.idx_label_charges_tenant_created', '', ''),
    (49, '8301f3cad96a', 'v121', 'relation', 'fsma.tenant_inbound_email_addresses', '', ''),
    (50, 'ceb552c6d36d', 'v121', 'relation', 'billing.tenant_usage_counters', '', ''),
    (51, '5541fb62ee2d', 'v121', 'merge', '', '', ''),
    (52, 'bd0c6549153a', 'v121', 'relation', 'agent_org.agent_pods', '', ''),
    (53, 'ccaa01e4fd7c', 'v121', 'relation', 'fsma.inbound_email_audit', '', ''),
    (54, 'd14f8a2b9c31', 'v122', 'function', 'fsma.claim_inbound_email_audit', '', ''),
    (55, 'e9f2a4c71b05', 'v123', 'merge', '', '', ''),
    (56, '26d215418784', 'v124', 'data', '', '', 'rule field paths; not catalog-observable'),
    (57, '22a278f6dc78', 'v125', 'column', 'fsma.traceability_events', 'evaluation_verdict', ''),
    (58, 'c51d4898e0a2', 'v126', 'data', '', '', 'grants only; not checked here'),
    (59, 'd2e7a7319b33', 'v127', 'data', '', '', 'function owner RLS setting; not checked here'),
    (60, '2db4f1d7b4ca', 'v126', 'data', '', '', 'composite FK rewrite; not checked here'),
    (61, '486eb6809921', 'v126', 'data', '', '', 'drops a function; not checked here'),
    (62, 'ed902d03df45', 'v127', 'merge', '', '', ''),
    (63, 'a5e7c9b2d341', 'v128', 'policy', 'v128_cte_events_select_regengine', 'fsma.cte_events', 'HAND-APPLIED: supabase 20261016234347 / sql/prod-apply/apply_v128_fsma_rls.sql'),
    (64, '93eb33f262a1', 'v128', 'data', '', '', 'HAND-APPLIED: supabase 20261016234352 / apply_v128_policy_merges.sql; merged policy names vary per table'),
    (65, '0a329588b824', 'v131', 'column', 'public.tool_leads', 'utm_source', 'HAND-APPLIED: sql/prod-apply/apply_v131_tool_leads_utm.sql'),
    (66, 'a9ea09050a30', 'v132', 'absent_policy', 'v128_client_guard_ingestion_runs', 'fsma.ingestion_runs', 'AMBIGUOUS: absent both before v128 and after v132'),
    (67, 'c4d8f1a2b6e7', 'v133', 'privilege_column_update', 'regengine_sysadmin', 'public.tenants', 'NULL when the role is absent'),
    (68, '1faec7148e78', 'v134', 'policy', 'portal_links_select', 'fsma.tenant_portal_links', 'HAND-APPLIED: sql/prod-apply/apply_sel314_rls_dedupe.sql'),
    (69, '41f96588d87c', 'v135', 'relation', 'public.data_gap_events', '', 'HAND-APPLIED: supabase 20261025033803'),
    (70, 'b005ddbf1dba', 'v136', 'column', 'public.supplier_facilities', 'agreed_sending_hours', 'HAND-APPLIED: supabase 20261025090000'),
    (71, 'a3f7ce361b0e', 'v137', 'relation', 'fsma.epcis_document_receipts', '', 'HAND-APPLIED: supabase 20261025090100; current head')
),
checked AS (
  SELECT ord, revision, label, kind, arg1, arg2, note,
    CASE kind
      WHEN 'relation' THEN pg_catalog.to_regclass(arg1) IS NOT NULL
      WHEN 'index'    THEN pg_catalog.to_regclass(arg1) IS NOT NULL
      WHEN 'absent_relation' THEN pg_catalog.to_regclass(arg1) IS NULL
      WHEN 'column' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_attribute a
          WHERE a.attrelid = pg_catalog.to_regclass(arg1)
            AND a.attname = arg2 AND NOT a.attisdropped AND a.attnum > 0)
      WHEN 'function' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname || '.' || p.proname = arg1)
      WHEN 'func_src' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname || '.' || p.proname = arg1
            AND p.prosrc ILIKE '%' || arg2 || '%')
      WHEN 'func_secdef' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_proc p
          WHERE p.proname = arg1 AND p.prosecdef)
      WHEN 'func_config_search_path' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname || '.' || p.proname = arg1
            AND p.proconfig IS NOT NULL
            AND array_to_string(p.proconfig, ',') ILIKE '%search_path%')
      WHEN 'policy' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_policy pol
          WHERE pol.polrelid = pg_catalog.to_regclass(arg2) AND pol.polname = arg1)
      WHEN 'absent_policy' THEN NOT EXISTS (
          SELECT 1 FROM pg_catalog.pg_policy pol
          WHERE pol.polrelid = pg_catalog.to_regclass(arg2) AND pol.polname = arg1)
      WHEN 'constraint' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_constraint c
          WHERE c.conname = arg1 AND c.conrelid = pg_catalog.to_regclass(arg2))
      WHEN 'absent_fk' THEN NOT EXISTS (
          SELECT 1 FROM pg_catalog.pg_constraint c
          WHERE c.contype = 'f'
            AND c.conrelid = pg_catalog.to_regclass(arg1)
            AND c.confrelid = pg_catalog.to_regclass(arg2))
      WHEN 'force_rls' THEN (
          SELECT c.relforcerowsecurity FROM pg_catalog.pg_class c
          WHERE c.oid = pg_catalog.to_regclass(arg1))
      WHEN 'privilege_absent' THEN (
          CASE WHEN EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname = arg1)
                AND pg_catalog.to_regclass(arg2) IS NOT NULL
               THEN NOT pg_catalog.has_table_privilege(arg1, arg2, 'SELECT')
               ELSE NULL END)
      WHEN 'privilege_column_update' THEN (
          CASE WHEN EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname = arg1)
                AND pg_catalog.to_regclass(arg2) IS NOT NULL
               THEN pg_catalog.has_column_privilege(arg1, arg2, 'name', 'UPDATE')
               ELSE NULL END)
      WHEN 'data_user_emails_fingerprint' THEN (
          CASE WHEN pg_catalog.to_regclass('public.user_emails') IS NULL THEN NULL
               WHEN NOT EXISTS (
                   SELECT 1 FROM pg_catalog.pg_attribute a
                   WHERE a.attrelid = pg_catalog.to_regclass('public.user_emails')
                     AND a.attname = 'email_fingerprint' AND NOT a.attisdropped) THEN FALSE
               ELSE NULL END)
      WHEN 'data_roles_review_decide' THEN (
          CASE WHEN pg_catalog.to_regclass('public.roles') IS NULL THEN NULL
               WHEN NOT EXISTS (
                   SELECT 1 FROM pg_catalog.pg_attribute a
                   WHERE a.attrelid = pg_catalog.to_regclass('public.roles')
                     AND a.attname = 'permissions' AND NOT a.attisdropped) THEN FALSE
               ELSE NULL END)
      ELSE NULL
    END AS present
  FROM sig
)
SELECT ord, revision, label, kind, arg1, arg2, present, note
FROM checked
ORDER BY ord;

-- 3. Summary: the chain position the catalog supports, and what lies beyond it.
WITH sig(ord, revision, label, kind, arg1, arg2, note) AS (
  VALUES
    (1, '8a9b0c1d2e3f', 'v080', 'relation', 'fsma.rule_rejections', '', ''),
    (2, 'c1d2e3f4a5b6', 'v079', 'relation', 'fsma.ingestion_run_receipts', '', 'second v079 label; use revision ids'),
    (3, 'd2e3f4a5b6c7', 'v080', 'relation', 'fsma.agent_artifacts', '', ''),
    (4, '3e7a1c5b9f24', 'v081', 'column', 'fsma.key_data_elements', 'tenant_id', ''),
    (5, 'a7b8c9d0e1f2', 'v081', 'index', 'fsma.idx_cte_events_tenant_sha', '', ''),
    (6, '70d5e59e3257', 'v082', 'merge', '', '', 'merge revision; nothing to observe'),
    (7, 'e3f4a5b6c7d8', 'v083', 'column', 'fsma.cte_kdes_backfill_log_v059', 'tenant_id', ''),
    (8, 'da5d93004161', 'v084', 'relation', 'public.user_emails', '', 'passwordless auth schema'),
    (9, 'f8a9b0c1d2e3', 'v085', 'column', 'public.organizations', 'domain_name', ''),
    (10, 'a9b0c1d2e3f4', 'v086', 'column', 'public.organizations', 'domain_verified', ''),
    (11, 'b0c1d2e3f4a5', 'v087', 'relation', 'public.webauthn_credentials', '', ''),
    (12, 'bdb2bec8bcc6', 'v088', 'absent_relation', 'public.password_reset_tokens', '', 'destructive: table dropped'),
    (13, '38e02636e340', 'v089', 'column', 'public.sessions', 'authenticated_at', ''),
    (14, '44225a26ed58', 'v090', 'column', 'public.audit_logs', 'sequence_num', ''),
    (15, '4c5d6e7f8a9b', 'v090', 'absent_fk', 'fsma.hash_chain', 'fsma.cte_events', 'also hand-applied by supabase 20260403235145'),
    (16, 'd1bdfe74d1fd', 'v090', 'merge', '', '', ''),
    (17, 'a128f7f95db8', 'v090', 'policy', 'tenant_isolation_tasks', 'fsma.task_queue', 'AMBIGUOUS: supabase 20261025100200 recreates a policy of the same name'),
    (18, '127a24ffb54c', 'v091', 'constraint', 'uq_request_signoffs_tenant_case_type', 'fsma.request_signoffs', ''),
    (19, 'b3c8e1f4a627', 'v092', 'privilege_absent', 'anon', 'fsma.cte_events', 'client-role lockdown; NULL when role anon is absent'),
    (20, '16cb29a3938c', 'v093', 'relation', 'public.scheduler_seen_items', '', ''),
    (21, 'feb267263e0a', 'v094', 'data_user_emails_fingerprint', '', '', 'data backfill; NULL when public.user_emails is absent'),
    (22, 'c7a1e5f2b9d4', 'v095', 'relation', 'fsma.remediation_cases', '', ''),
    (23, 'c3a51e2f7b90', 'v096', 'policy', 'tenant_isolation_audit', 'fsma.fsma_audit_trail', ''),
    (24, 'e4d7b2a9c561', 'v097', 'func_config_search_path', 'public.get_tenant_context', '', ''),
    (25, '8b2f4e6a9c31', 'v098', 'relation', 'fsma.exchange_packages', '', ''),
    (26, '2aa607050c84', 'v099', 'function', 'public.set_admin_context', '', ''),
    (27, '3ba0291a69f2', 'v100', 'policy', 'memberships_sysadmin_read', 'public.memberships', ''),
    (28, '7c4d9a1f2e8b', 'v101', 'column', 'fsma.notification_outbox', 'attempts', ''),
    (29, '1b10a708e36a', 'v102', 'relation', 'fsma.mock_audit_drills', '', ''),
    (30, 'fcf558aeb1e2', 'v103', 'relation', 'fsma.compliance_evidence_snapshots', '', ''),
    (31, '7c1f2c8ffe05', 'v104', 'policy', 'obligation_cte_rules_tenant_isolation', 'public.obligation_cte_rules', ''),
    (32, '323c945cf68d', 'v105', 'relation', 'fsma.rule_evaluation_deadletter', '', ''),
    (33, '8633e0a7a84e', 'v106', 'relation', 'fsma.tenant_seed_state', '', ''),
    (34, 'c35358cae7d4', 'v107', 'func_src', 'fsma.prevent_cte_mutation', 'RETURN NEW', ''),
    (35, 'a43b0fb1edd0', 'v108', 'column', 'fsma.traceability_events', 'evaluation_error', ''),
    (36, '51701aedee57', 'v109', 'function', 'fsma.get_team_roster', '', ''),
    (37, '6f8c2d1a4b90', 'v110', 'policy', 'developers_insert_own_profile', 'public.developer_profiles', ''),
    (38, 'df664d92adba', 'v111', 'force_rls', 'public.controls', '', ''),
    (39, 'd8b2056471a7', 'v112', 'func_secdef', 'seed_obligations_for_tenant', '', 'any schema'),
    (40, '4e9c1f7a02b6', 'v113', 'function', 'public.get_invite_tenant_by_token_hash', '', ''),
    (41, 'c4f1a7e93b28', 'v114', 'column', 'fsma.fda_export_log', 'include_pii', ''),
    (42, 'c1d4e8f20a37', 'v115', 'index', 'fsma.idx_task_queue_idempotency', '', ''),
    (43, 'e4a7c2d91b06', 'v116', 'data', '', '', 'rule seed integrity; not catalog-observable'),
    (44, '6f4c2a9d8b17', 'v110', 'data_roles_review_decide', '', '', 'NULL when public.roles is absent'),
    (45, 'b71d9e4c2a60', 'v111', 'force_rls', 'fsma.organizations', '', 'runtime role grants; FORCE RLS is the observable part'),
    (46, '8b866e4b4798', 'v119', 'data', '', '', 'seed reconcile; not catalog-observable'),
    (47, 'c6a120b4e901', 'v120', 'data', '', '', 'rule citations; not catalog-observable'),
    (48, '7551be5c64ac', 'v121', 'index', 'fsma.idx_label_charges_tenant_created', '', ''),
    (49, '8301f3cad96a', 'v121', 'relation', 'fsma.tenant_inbound_email_addresses', '', ''),
    (50, 'ceb552c6d36d', 'v121', 'relation', 'billing.tenant_usage_counters', '', ''),
    (51, '5541fb62ee2d', 'v121', 'merge', '', '', ''),
    (52, 'bd0c6549153a', 'v121', 'relation', 'agent_org.agent_pods', '', ''),
    (53, 'ccaa01e4fd7c', 'v121', 'relation', 'fsma.inbound_email_audit', '', ''),
    (54, 'd14f8a2b9c31', 'v122', 'function', 'fsma.claim_inbound_email_audit', '', ''),
    (55, 'e9f2a4c71b05', 'v123', 'merge', '', '', ''),
    (56, '26d215418784', 'v124', 'data', '', '', 'rule field paths; not catalog-observable'),
    (57, '22a278f6dc78', 'v125', 'column', 'fsma.traceability_events', 'evaluation_verdict', ''),
    (58, 'c51d4898e0a2', 'v126', 'data', '', '', 'grants only; not checked here'),
    (59, 'd2e7a7319b33', 'v127', 'data', '', '', 'function owner RLS setting; not checked here'),
    (60, '2db4f1d7b4ca', 'v126', 'data', '', '', 'composite FK rewrite; not checked here'),
    (61, '486eb6809921', 'v126', 'data', '', '', 'drops a function; not checked here'),
    (62, 'ed902d03df45', 'v127', 'merge', '', '', ''),
    (63, 'a5e7c9b2d341', 'v128', 'policy', 'v128_cte_events_select_regengine', 'fsma.cte_events', 'HAND-APPLIED: supabase 20261016234347 / sql/prod-apply/apply_v128_fsma_rls.sql'),
    (64, '93eb33f262a1', 'v128', 'data', '', '', 'HAND-APPLIED: supabase 20261016234352 / apply_v128_policy_merges.sql; merged policy names vary per table'),
    (65, '0a329588b824', 'v131', 'column', 'public.tool_leads', 'utm_source', 'HAND-APPLIED: sql/prod-apply/apply_v131_tool_leads_utm.sql'),
    (66, 'a9ea09050a30', 'v132', 'absent_policy', 'v128_client_guard_ingestion_runs', 'fsma.ingestion_runs', 'AMBIGUOUS: absent both before v128 and after v132'),
    (67, 'c4d8f1a2b6e7', 'v133', 'privilege_column_update', 'regengine_sysadmin', 'public.tenants', 'NULL when the role is absent'),
    (68, '1faec7148e78', 'v134', 'policy', 'portal_links_select', 'fsma.tenant_portal_links', 'HAND-APPLIED: sql/prod-apply/apply_sel314_rls_dedupe.sql'),
    (69, '41f96588d87c', 'v135', 'relation', 'public.data_gap_events', '', 'HAND-APPLIED: supabase 20261025033803'),
    (70, 'b005ddbf1dba', 'v136', 'column', 'public.supplier_facilities', 'agreed_sending_hours', 'HAND-APPLIED: supabase 20261025090000'),
    (71, 'a3f7ce361b0e', 'v137', 'relation', 'fsma.epcis_document_receipts', '', 'HAND-APPLIED: supabase 20261025090100; current head')
),
checked AS (
  SELECT ord, revision, label, note,
    CASE kind
      WHEN 'relation' THEN pg_catalog.to_regclass(arg1) IS NOT NULL
      WHEN 'index'    THEN pg_catalog.to_regclass(arg1) IS NOT NULL
      WHEN 'absent_relation' THEN pg_catalog.to_regclass(arg1) IS NULL
      WHEN 'column' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_attribute a
          WHERE a.attrelid = pg_catalog.to_regclass(arg1)
            AND a.attname = arg2 AND NOT a.attisdropped AND a.attnum > 0)
      WHEN 'function' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname || '.' || p.proname = arg1)
      WHEN 'func_src' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname || '.' || p.proname = arg1
            AND p.prosrc ILIKE '%' || arg2 || '%')
      WHEN 'func_secdef' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_proc p WHERE p.proname = arg1 AND p.prosecdef)
      WHEN 'func_config_search_path' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname || '.' || p.proname = arg1
            AND p.proconfig IS NOT NULL
            AND array_to_string(p.proconfig, ',') ILIKE '%search_path%')
      WHEN 'policy' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_policy pol
          WHERE pol.polrelid = pg_catalog.to_regclass(arg2) AND pol.polname = arg1)
      WHEN 'absent_policy' THEN NOT EXISTS (
          SELECT 1 FROM pg_catalog.pg_policy pol
          WHERE pol.polrelid = pg_catalog.to_regclass(arg2) AND pol.polname = arg1)
      WHEN 'constraint' THEN EXISTS (
          SELECT 1 FROM pg_catalog.pg_constraint c
          WHERE c.conname = arg1 AND c.conrelid = pg_catalog.to_regclass(arg2))
      WHEN 'absent_fk' THEN NOT EXISTS (
          SELECT 1 FROM pg_catalog.pg_constraint c
          WHERE c.contype = 'f'
            AND c.conrelid = pg_catalog.to_regclass(arg1)
            AND c.confrelid = pg_catalog.to_regclass(arg2))
      WHEN 'force_rls' THEN (
          SELECT c.relforcerowsecurity FROM pg_catalog.pg_class c
          WHERE c.oid = pg_catalog.to_regclass(arg1))
      ELSE NULL
    END AS present
  FROM sig
),
observable AS (
  SELECT * FROM checked WHERE present IS NOT NULL
),
first_gap AS (
  SELECT min(ord) AS ord FROM observable WHERE present = FALSE
)
SELECT
  (SELECT version_num FROM public.alembic_version LIMIT 1)        AS recorded_version,
  (SELECT revision FROM observable
     WHERE present AND ord < COALESCE((SELECT ord FROM first_gap), 2147483647)
     ORDER BY ord DESC LIMIT 1)                                     AS supported_through_revision,
  (SELECT label FROM observable
     WHERE present AND ord < COALESCE((SELECT ord FROM first_gap), 2147483647)
     ORDER BY ord DESC LIMIT 1)                                     AS supported_through_label,
  (SELECT count(*) FROM observable WHERE present)                  AS observable_present,
  (SELECT count(*) FROM observable WHERE NOT present)              AS observable_absent,
  (SELECT string_agg(label || ':' || revision, ', ' ORDER BY ord)
     FROM observable
     WHERE present AND ord > COALESCE((SELECT ord FROM first_gap), 0)) AS present_beyond_first_gap;

ROLLBACK;
