-- 20261017020000_e_wrap_get_tenant_context.sql
--
-- Wraps every bare get_tenant_context() call in RLS policy expressions as
-- (select get_tenant_context()). 86 policies, 145 calls.
--
-- get_tenant_context() is a VOLATILE plpgsql function that raises if
-- app.tenant_id is unset. As a bare call inside a policy it runs once per
-- row. Inside a scalar sub-select, the planner runs it as an initplan, so
-- it runs once per statement. The policy logic does not change: the
-- expressions, roles, command, and permissiveness stay the same. Only the
-- USING / WITH CHECK clauses that already exist are restated.

ALTER POLICY v128_canonical_entities_select_regengine ON fsma.canonical_entities
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_canonical_entities ON fsma.canonical_entities
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_cte_events_select_regengine ON fsma.cte_events
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_cte_events_insert_regengine ON fsma.cte_events
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_cte_events_delete_regengine ON fsma.cte_events
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY tenant_isolation_roles ON public.roles
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_memberships ON public.memberships
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_cte_events ON fsma.cte_events
  USING ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_cte_kdes_select_regengine ON fsma.cte_kdes
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_cte_kdes_insert_regengine ON fsma.cte_kdes
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_client_guard_cte_kdes ON fsma.cte_kdes
  USING ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_entity_aliases_select_regengine ON fsma.entity_aliases
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_entity_aliases ON fsma.entity_aliases
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY tenant_isolation_invites ON public.invites
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_exception_cases_select_regengine ON fsma.exception_cases
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_exception_cases_insert_regengine ON fsma.exception_cases
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_exception_cases_update_regengine ON fsma.exception_cases
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_exception_cases ON fsma.exception_cases
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_exception_comments_select_regengine ON fsma.exception_comments
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_exception_comments_insert_regengine ON fsma.exception_comments
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_exception_comments ON fsma.exception_comments
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_exception_signoffs_select_regengine ON fsma.exception_signoffs
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_exception_signoffs_insert_regengine ON fsma.exception_signoffs
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_review_items ON public.review_items
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_exception_signoffs ON fsma.exception_signoffs
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_fda_export_log_select_regengine ON fsma.fda_export_log
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY tenant_isolation_compliance_status ON public.tenant_compliance_status
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_compliance_alerts ON public.compliance_alerts
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_compliance_status_log ON public.compliance_status_log
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_compliance_notifications ON public.compliance_notifications
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_product_profile ON public.tenant_product_profile
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_supplier_facilities ON public.supplier_facilities
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_supplier_ftl_categories ON public.supplier_facility_ftl_categories
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_supplier_lots ON public.supplier_traceability_lots
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_supplier_cte_events ON public.supplier_cte_events
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_fda_export_log_insert_regengine ON fsma.fda_export_log
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_client_guard_fda_export_log ON fsma.fda_export_log
  USING ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY tenant_isolation_supplier_funnel_events ON public.supplier_funnel_events
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_hash_chain_select_regengine ON fsma.hash_chain
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_hash_chain_insert_regengine ON fsma.hash_chain
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY tenant_isolation_products ON fsma.products
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_locations ON fsma.locations
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_suppliers ON fsma.suppliers
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_cte ON fsma.critical_tracking_events
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_audit_log ON fsma.audit_log
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_recall ON fsma.recall_assessments
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_snapshots ON fsma.compliance_snapshots
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_alerts ON fsma.compliance_alerts
  USING (tenant_id = ((select get_tenant_context()))::text)
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_client_guard_hash_chain ON fsma.hash_chain
  USING ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_identity_review_queue_select_regengine ON fsma.identity_review_queue
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_identity_review_queue ON fsma.identity_review_queue
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_ingestion_runs_select_regengine ON fsma.ingestion_runs
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_ingestion_runs_insert_regengine ON fsma.ingestion_runs
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_ingestion_runs_update_regengine ON fsma.ingestion_runs
  USING (tenant_id = ((select get_tenant_context()))::text)
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_ingestion_runs_select_regengine_sysadmin ON fsma.ingestion_runs
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_client_guard_ingestion_runs ON fsma.ingestion_runs
  USING ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_request_cases_select_regengine ON fsma.request_cases
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_request_cases_insert_regengine ON fsma.request_cases
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_request_cases_update_regengine ON fsma.request_cases
  USING (tenant_id = (select get_tenant_context()))
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_request_cases ON fsma.request_cases
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_request_signoffs_select_regengine ON fsma.request_signoffs
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_request_signoffs_insert_regengine ON fsma.request_signoffs
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_request_signoffs ON fsma.request_signoffs
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_response_packages_select_regengine ON fsma.response_packages
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_response_packages_insert_regengine ON fsma.response_packages
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_response_packages ON fsma.response_packages
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_rule_evaluations_select_regengine ON fsma.rule_evaluations
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_rule_evaluations_insert_regengine ON fsma.rule_evaluations
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_rule_evaluations ON fsma.rule_evaluations
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_submission_log_select_regengine ON fsma.submission_log
  USING (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_submission_log_insert_regengine ON fsma.submission_log
  WITH CHECK (tenant_id = (select get_tenant_context()));

ALTER POLICY v128_client_guard_submission_log ON fsma.submission_log
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_tenant_suppliers_select_regengine ON fsma.tenant_suppliers
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_client_guard_tenant_suppliers ON fsma.tenant_suppliers
  USING ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_traceability_events_select_regengine ON fsma.traceability_events
  USING (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_traceability_events_insert_regengine ON fsma.traceability_events
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_traceability_events_update_regengine ON fsma.traceability_events
  USING (tenant_id = ((select get_tenant_context()))::text)
  WITH CHECK (tenant_id = ((select get_tenant_context()))::text);

ALTER POLICY v128_client_guard_traceability_events ON fsma.traceability_events
  USING ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
  WITH CHECK ((tenant_id = ((select get_tenant_context()))::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));

ALTER POLICY v128_client_guard_entity_merge_history ON fsma.entity_merge_history
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name, 'regengine'::name, 'regengine_sysadmin'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name, 'regengine'::name, 'regengine_sysadmin'::name])));

ALTER POLICY v128_client_guard_exception_attachments ON fsma.exception_attachments
  USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name, 'regengine'::name, 'regengine_sysadmin'::name])))
  WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name, 'regengine'::name, 'regengine_sysadmin'::name])));

ALTER POLICY tenant_isolation_audit_logs ON public.audit_logs
  USING ((tenant_id = (select get_tenant_context())) OR (tenant_id = (select get_tenant_context())))
  WITH CHECK ((tenant_id = (select get_tenant_context())) OR (tenant_id = (select get_tenant_context())));

ALTER POLICY tenant_isolation_authority_documents ON public.pcos_authority_documents
  USING ((tenant_id = (select get_tenant_context())) OR (tenant_id = (select get_tenant_context())))
  WITH CHECK ((tenant_id = (select get_tenant_context())) OR (tenant_id = (select get_tenant_context())));

ALTER POLICY tenant_isolation_extracted_facts ON public.pcos_extracted_facts
  USING ((tenant_id = (select get_tenant_context())) OR (tenant_id = (select get_tenant_context())))
  WITH CHECK ((tenant_id = (select get_tenant_context())) OR (tenant_id = (select get_tenant_context())));

ALTER POLICY tenants_write_own ON public.tenants
  USING (id = (select get_tenant_context()))
  WITH CHECK (id = (select get_tenant_context()));

ALTER POLICY tenant_isolation_fact_citations ON public.pcos_fact_citations
  USING ((tenant_id = (select get_tenant_context())) OR (tenant_id = (select get_tenant_context())))
  WITH CHECK ((tenant_id = (select get_tenant_context())) OR (tenant_id = (select get_tenant_context())));

ALTER POLICY pcos_analysis_runs_tenant_isolation ON public.pcos_analysis_runs
  USING (tenant_id = (select get_tenant_context()));

-- ROLLBACK (restores the original expressions exactly as given)
--
-- ALTER POLICY v128_canonical_entities_select_regengine ON fsma.canonical_entities USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_canonical_entities ON fsma.canonical_entities USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_cte_events_select_regengine ON fsma.cte_events USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_cte_events_insert_regengine ON fsma.cte_events WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_cte_events_delete_regengine ON fsma.cte_events USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY tenant_isolation_roles ON public.roles USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_memberships ON public.memberships USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_cte_events ON fsma.cte_events USING ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_cte_kdes_select_regengine ON fsma.cte_kdes USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_cte_kdes_insert_regengine ON fsma.cte_kdes WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_client_guard_cte_kdes ON fsma.cte_kdes USING ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_entity_aliases_select_regengine ON fsma.entity_aliases USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_entity_aliases ON fsma.entity_aliases USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY tenant_isolation_invites ON public.invites USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_exception_cases_select_regengine ON fsma.exception_cases USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_exception_cases_insert_regengine ON fsma.exception_cases WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_exception_cases_update_regengine ON fsma.exception_cases USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_exception_cases ON fsma.exception_cases USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_exception_comments_select_regengine ON fsma.exception_comments USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_exception_comments_insert_regengine ON fsma.exception_comments WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_exception_comments ON fsma.exception_comments USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_exception_signoffs_select_regengine ON fsma.exception_signoffs USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_exception_signoffs_insert_regengine ON fsma.exception_signoffs WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_review_items ON public.review_items USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_exception_signoffs ON fsma.exception_signoffs USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_fda_export_log_select_regengine ON fsma.fda_export_log USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY tenant_isolation_compliance_status ON public.tenant_compliance_status USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_compliance_alerts ON public.compliance_alerts USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_compliance_status_log ON public.compliance_status_log USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_compliance_notifications ON public.compliance_notifications USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_product_profile ON public.tenant_product_profile USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_supplier_facilities ON public.supplier_facilities USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_supplier_ftl_categories ON public.supplier_facility_ftl_categories USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_supplier_lots ON public.supplier_traceability_lots USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_supplier_cte_events ON public.supplier_cte_events USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_fda_export_log_insert_regengine ON fsma.fda_export_log WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_client_guard_fda_export_log ON fsma.fda_export_log USING ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY tenant_isolation_supplier_funnel_events ON public.supplier_funnel_events USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_hash_chain_select_regengine ON fsma.hash_chain USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_hash_chain_insert_regengine ON fsma.hash_chain WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY tenant_isolation_products ON fsma.products USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_locations ON fsma.locations USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_suppliers ON fsma.suppliers USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_cte ON fsma.critical_tracking_events USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_audit_log ON fsma.audit_log USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_recall ON fsma.recall_assessments USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_snapshots ON fsma.compliance_snapshots USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY tenant_isolation_alerts ON fsma.compliance_alerts USING (tenant_id = (get_tenant_context())::text) WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_client_guard_hash_chain ON fsma.hash_chain USING ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_identity_review_queue_select_regengine ON fsma.identity_review_queue USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_identity_review_queue ON fsma.identity_review_queue USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_ingestion_runs_select_regengine ON fsma.ingestion_runs USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_ingestion_runs_insert_regengine ON fsma.ingestion_runs WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_ingestion_runs_update_regengine ON fsma.ingestion_runs USING (tenant_id = (get_tenant_context())::text) WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_ingestion_runs_select_regengine_sysadmin ON fsma.ingestion_runs USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_client_guard_ingestion_runs ON fsma.ingestion_runs USING ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_request_cases_select_regengine ON fsma.request_cases USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_request_cases_insert_regengine ON fsma.request_cases WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_request_cases_update_regengine ON fsma.request_cases USING (tenant_id = get_tenant_context()) WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_request_cases ON fsma.request_cases USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_request_signoffs_select_regengine ON fsma.request_signoffs USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_request_signoffs_insert_regengine ON fsma.request_signoffs WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_request_signoffs ON fsma.request_signoffs USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_response_packages_select_regengine ON fsma.response_packages USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_response_packages_insert_regengine ON fsma.response_packages WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_response_packages ON fsma.response_packages USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_rule_evaluations_select_regengine ON fsma.rule_evaluations USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_rule_evaluations_insert_regengine ON fsma.rule_evaluations WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_rule_evaluations ON fsma.rule_evaluations USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_submission_log_select_regengine ON fsma.submission_log USING (tenant_id = get_tenant_context());
-- ALTER POLICY v128_submission_log_insert_regengine ON fsma.submission_log WITH CHECK (tenant_id = get_tenant_context());
-- ALTER POLICY v128_client_guard_submission_log ON fsma.submission_log USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_tenant_suppliers_select_regengine ON fsma.tenant_suppliers USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_client_guard_tenant_suppliers ON fsma.tenant_suppliers USING ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_traceability_events_select_regengine ON fsma.traceability_events USING (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_traceability_events_insert_regengine ON fsma.traceability_events WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_traceability_events_update_regengine ON fsma.traceability_events USING (tenant_id = (get_tenant_context())::text) WITH CHECK (tenant_id = (get_tenant_context())::text);
-- ALTER POLICY v128_client_guard_traceability_events ON fsma.traceability_events USING ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name]))) WITH CHECK ((tenant_id = (get_tenant_context())::text) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
-- ALTER POLICY v128_client_guard_entity_merge_history ON fsma.entity_merge_history USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name, 'regengine'::name, 'regengine_sysadmin'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name, 'regengine'::name, 'regengine_sysadmin'::name])));
-- ALTER POLICY v128_client_guard_exception_attachments ON fsma.exception_attachments USING ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name, 'regengine'::name, 'regengine_sysadmin'::name]))) WITH CHECK ((tenant_id = get_tenant_context()) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name, 'regengine'::name, 'regengine_sysadmin'::name])));
-- ALTER POLICY tenant_isolation_audit_logs ON public.audit_logs USING ((tenant_id = get_tenant_context()) OR (tenant_id = get_tenant_context())) WITH CHECK ((tenant_id = get_tenant_context()) OR (tenant_id = get_tenant_context()));
-- ALTER POLICY tenant_isolation_authority_documents ON public.pcos_authority_documents USING ((tenant_id = get_tenant_context()) OR (tenant_id = get_tenant_context())) WITH CHECK ((tenant_id = get_tenant_context()) OR (tenant_id = get_tenant_context()));
-- ALTER POLICY tenant_isolation_extracted_facts ON public.pcos_extracted_facts USING ((tenant_id = get_tenant_context()) OR (tenant_id = get_tenant_context())) WITH CHECK ((tenant_id = get_tenant_context()) OR (tenant_id = get_tenant_context()));
-- ALTER POLICY tenants_write_own ON public.tenants USING (id = get_tenant_context()) WITH CHECK (id = get_tenant_context());
-- ALTER POLICY tenant_isolation_fact_citations ON public.pcos_fact_citations USING ((tenant_id = get_tenant_context()) OR (tenant_id = get_tenant_context())) WITH CHECK ((tenant_id = get_tenant_context()) OR (tenant_id = get_tenant_context()));
-- ALTER POLICY pcos_analysis_runs_tenant_isolation ON public.pcos_analysis_runs USING (tenant_id = get_tenant_context());
;
