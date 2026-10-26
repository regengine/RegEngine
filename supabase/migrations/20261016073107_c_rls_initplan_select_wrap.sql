-- Migration C: wrap per-row auth/current_setting calls in RLS policies (advisor lint auth_rls_initplan, 73).
-- Each ALTER POLICY re-states the exact current USING / WITH CHECK expression from the prod catalog,
-- with the only change being auth.<fn>(), current_setting(...) and get_tenant_context() calls
-- wrapped as (select <call>) so they are evaluated once per statement instead of once per row.
-- Roles, command and permissiveness are unchanged (ALTER POLICY does not touch them when omitted).
-- Policies listed in findings but absent from the catalog are left as comments, not guessed.
-- Generated 2026-10-16 from prod-catalog.json. Not applied.

ALTER POLICY developers_read_own_profile ON public.developer_profiles
  USING (((select auth.uid()) = auth_user_id));

ALTER POLICY users_own_data ON public.users
  USING ((id = (select auth.uid())));

ALTER POLICY memberships_tenant_isolation ON public.memberships
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY roles_tenant_isolation ON public.roles
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY sessions_user_owns ON public.sessions
  USING ((user_id = (select auth.uid())));

ALTER POLICY invites_tenant_isolation ON public.invites
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY developers_update_own_profile ON public.developer_profiles
  USING (((select auth.uid()) = auth_user_id));

ALTER POLICY tenant_isolation_policy ON public.api_keys
  USING (((tenant_id)::uuid = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY evidence_logs_tenant_isolation ON public.evidence_logs
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY compliance_snapshots_tenant_isolation ON public.compliance_snapshots
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY tenant_compliance_status_isolation ON public.tenant_compliance_status
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY tenant_product_profile_isolation ON public.tenant_product_profile
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY compliance_alerts_tenant_isolation ON public.compliance_alerts
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY compliance_status_log_tenant_isolation ON public.compliance_status_log
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY tenant_isolation_policy ON public.review_items
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY tenant_isolation_tasks ON fsma.task_queue
  USING ((((tenant_id)::text = (select current_setting('app.tenant_id'::text, true))) OR ((select current_setting('app.tenant_id'::text, true)) = ''::text)));

ALTER POLICY tenant_isolation_transformation_links ON fsma.transformation_links
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))))
  WITH CHECK (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_graph_outbox ON public.graph_outbox
  USING (((tenant_id IS NULL) OR ((tenant_id)::text = NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text)) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND ((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text))));

ALTER POLICY pcos_companies_tenant_isolation ON public.pcos_companies
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_people_tenant_isolation ON public.pcos_people
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_projects_tenant_isolation ON public.pcos_projects
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY tenant_isolation_webhook_outbox ON public.webhook_outbox
  USING ((((tenant_id)::text = NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text)) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND ((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text))));

ALTER POLICY pcos_engagements_tenant_isolation ON public.pcos_engagements
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_tasks_tenant_isolation ON public.pcos_tasks
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_timecards_tenant_isolation ON public.pcos_timecards
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_evidence_tenant_isolation ON public.pcos_evidence
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY tenant_isolation_api_keys ON public.api_keys
  USING (((tenant_id IS NULL) OR ((tenant_id)::text = NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text)) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND ((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text))))
  WITH CHECK (((tenant_id IS NULL) OR ((tenant_id)::text = NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text)) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND ((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text))));

ALTER POLICY pcos_document_requirements_tenant_isolation ON public.pcos_document_requirements
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_engagement_documents_tenant_isolation ON public.pcos_engagement_documents
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_company_registrations_tenant_isolation ON public.pcos_company_registrations
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_insurance_policies_tenant_isolation ON public.pcos_insurance_policies
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_safety_policies_tenant_isolation ON public.pcos_safety_policies
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_locations_tenant_isolation ON public.pcos_locations
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_permit_packets_tenant_isolation ON public.pcos_permit_packets
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_form_templates_tenant_isolation ON public.pcos_form_templates
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_generated_forms_tenant_isolation ON public.pcos_generated_forms
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_budgets_tenant_isolation ON public.pcos_budgets
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_budget_line_items_tenant_isolation ON public.pcos_budget_line_items
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_tax_credit_applications_tenant_isolation ON public.pcos_tax_credit_applications
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_tax_credit_rules_tenant_isolation ON public.pcos_tax_credit_rules
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_qualified_spend_categories_tenant_isolation ON public.pcos_qualified_spend_categories
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_classification_analyses_tenant_isolation ON public.pcos_classification_analyses
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_abc_questionnaire_responses_tenant_isolation ON public.pcos_abc_questionnaire_responses
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_classification_exemptions_tenant_isolation ON public.pcos_classification_exemptions
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_visa_categories_tenant_isolation ON public.pcos_visa_categories
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_person_visa_status_tenant_isolation ON public.pcos_person_visa_status
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY user_self_isolation ON public.users
  USING (((id = (NULLIF((select current_setting('regengine.user_id'::text, true)), ''::text))::uuid) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND ((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text))))
  WITH CHECK (((id = (NULLIF((select current_setting('regengine.user_id'::text, true)), ''::text))::uuid) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND ((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text))));

ALTER POLICY sessions_user_isolation ON public.sessions
  USING (((user_id = (NULLIF((select current_setting('regengine.user_id'::text, true)), ''::text))::uuid) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND ((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text))))
  WITH CHECK (((user_id = (NULLIF((select current_setting('regengine.user_id'::text, true)), ''::text))::uuid) OR ((CURRENT_USER = 'regengine_sysadmin'::name) AND ((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text))));

ALTER POLICY pcos_compliance_snapshots_tenant_isolation ON public.pcos_compliance_snapshots
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_audit_events_tenant_isolation ON public.pcos_audit_events
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_task_events_tenant_isolation ON public.pcos_task_events
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_rule_evaluations_tenant_isolation ON public.pcos_rule_evaluations
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_gate_evaluations_tenant_isolation ON public.pcos_gate_evaluations
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY pcos_union_rate_checks_tenant_isolation ON public.pcos_union_rate_checks
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY vertical_projects_tenant_isolation ON public.vertical_projects
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY vertical_rule_instances_tenant_isolation ON public.vertical_rule_instances
  USING ((tenant_id = COALESCE((NULLIF((select current_setting('app.tenant_id'::text, true)), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));

ALTER POLICY developers_read_own_keys ON public.developer_api_keys
  USING ((developer_id IN ( SELECT developer_profiles.id
   FROM developer_profiles
  WHERE (developer_profiles.auth_user_id = (select auth.uid())))));

ALTER POLICY developers_insert_own_keys ON public.developer_api_keys
  WITH CHECK ((developer_id IN ( SELECT developer_profiles.id
   FROM developer_profiles
  WHERE (developer_profiles.auth_user_id = (select auth.uid())))));

ALTER POLICY developers_update_own_keys ON public.developer_api_keys
  USING ((developer_id IN ( SELECT developer_profiles.id
   FROM developer_profiles
  WHERE (developer_profiles.auth_user_id = (select auth.uid())))));

ALTER POLICY developers_read_own_usage ON public.developer_api_usage
  USING ((developer_id IN ( SELECT developer_profiles.id
   FROM developer_profiles
  WHERE (developer_profiles.auth_user_id = (select auth.uid())))));

ALTER POLICY obligations_select_tenant_scoped ON public.obligations
  USING (((tenant_id)::uuid IN ( SELECT m.tenant_id
   FROM memberships m
  WHERE (m.user_id = (select auth.uid())))));

ALTER POLICY obligation_cte_rules_select_via_obligation ON public.obligation_cte_rules
  USING ((obligation_id IN ( SELECT o.id
   FROM (obligations o
     JOIN memberships m ON (((o.tenant_id)::uuid = m.tenant_id)))
  WHERE (m.user_id = (select auth.uid())))));

ALTER POLICY tenant_isolation_inflow_scenarios ON fsma.inflow_workbench_scenarios
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))))
  WITH CHECK (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_inflow_runs ON fsma.inflow_workbench_runs
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))))
  WITH CHECK (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_inflow_fix_items ON fsma.inflow_workbench_fix_items
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))))
  WITH CHECK (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_inflow_commit_decisions ON fsma.inflow_workbench_commit_decisions
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))))
  WITH CHECK (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_portal_links ON fsma.tenant_portal_links
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))))
  WITH CHECK (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_supplier_integration_profiles ON fsma.supplier_integration_profiles
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))))
  WITH CHECK (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY portal_links_token_lookup ON fsma.tenant_portal_links
  USING (((link_token = NULLIF((select current_setting('app.portal_link_token'::text, true)), ''::text)) AND (status = 'active'::text) AND (expires_at > now())));

ALTER POLICY tenant_isolation_docs ON ingestion.documents
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_projects ON public.vertical_projects
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_evidence ON public.evidence_logs
  USING (((tenant_id = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));

ALTER POLICY tenant_isolation_obligations ON public.obligations
  USING ((((tenant_id)::uuid = (select get_tenant_context())) OR (((select current_setting('regengine.is_sysadmin'::text, true)) = 'true'::text) AND (CURRENT_USER = 'regengine_sysadmin'::name))));
;
