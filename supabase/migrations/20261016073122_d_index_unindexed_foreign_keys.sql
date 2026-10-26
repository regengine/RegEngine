-- Migration D: index unindexed foreign keys (advisor lint unindexed_foreign_keys, 53).
-- One btree index per FK on the FK's columns in constraint order (columns from prod-catalog.json "fks").
-- Plain CREATE INDEX (not CONCURRENTLY) because migrations run inside a transaction; each build
-- takes a SHARE lock on its table (blocks writes, not reads) until the migration commits.
-- Generated 2026-10-16 from prod-catalog.json. Not applied.

CREATE INDEX IF NOT EXISTS idx_compliance_alerts_cte_event_id ON fsma.compliance_alerts (cte_event_id);  -- compliance_alerts_cte_event_id_fkey
CREATE INDEX IF NOT EXISTS idx_identity_review_queue_entity_b_id ON fsma.identity_review_queue (entity_b_id);  -- identity_review_queue_entity_b_id_fkey
CREATE INDEX IF NOT EXISTS idx_identity_review_queue_previous_review_id ON fsma.identity_review_queue (previous_review_id);  -- identity_review_queue_previous_review_id_fkey
CREATE INDEX IF NOT EXISTS idx_inflow_workbench_commit_decisions_run_id ON fsma.inflow_workbench_commit_decisions (run_id);  -- inflow_workbench_commit_decisions_run_id_fkey
CREATE INDEX IF NOT EXISTS idx_submission_log_package_id ON fsma.submission_log (package_id);  -- submission_log_package_id_fkey
CREATE INDEX IF NOT EXISTS idx_developer_api_usage_api_key_id ON public.developer_api_usage (api_key_id);  -- developer_api_usage_api_key_id_fkey
CREATE INDEX IF NOT EXISTS idx_developer_profiles_invite_code_id ON public.developer_profiles (invite_code_id);  -- developer_profiles_invite_code_id_fkey
CREATE INDEX IF NOT EXISTS idx_invites_created_by ON public.invites (created_by);  -- invites_created_by_fkey
CREATE INDEX IF NOT EXISTS idx_invites_role_id ON public.invites (role_id);  -- invites_role_id_fkey
CREATE INDEX IF NOT EXISTS idx_memberships_role_id ON public.memberships (role_id);  -- memberships_role_id_fkey
CREATE INDEX IF NOT EXISTS idx_obligation_cte_rules_obligation_id ON public.obligation_cte_rules (obligation_id);  -- obligation_cte_rules_obligation_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_analysis_runs_project_id ON public.pcos_analysis_runs (project_id);  -- pcos_analysis_runs_project_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_analysis_runs_tenant_id ON public.pcos_analysis_runs (tenant_id);  -- pcos_analysis_runs_tenant_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_audit_events_actor_id ON public.pcos_audit_events (actor_id);  -- pcos_audit_events_actor_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_authority_documents_supersedes_document_id ON public.pcos_authority_documents (supersedes_document_id);  -- pcos_authority_documents_supersedes_document_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_budgets_created_by ON public.pcos_budgets (created_by);  -- pcos_budgets_created_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_classification_analyses_analyzed_by ON public.pcos_classification_analyses (analyzed_by);  -- pcos_classification_analyses_analyzed_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_companies_created_by ON public.pcos_companies (created_by);  -- pcos_companies_created_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_companies_updated_by ON public.pcos_companies (updated_by);  -- pcos_companies_updated_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_compliance_snapshots_attested_by ON public.pcos_compliance_snapshots (attested_by);  -- pcos_compliance_snapshots_attested_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_compliance_snapshots_previous_snapshot_id ON public.pcos_compliance_snapshots (previous_snapshot_id);  -- pcos_compliance_snapshots_previous_snapshot_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_compliance_snapshots_triggered_by ON public.pcos_compliance_snapshots (triggered_by);  -- pcos_compliance_snapshots_triggered_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_document_requirements_template_id ON public.pcos_document_requirements (template_id);  -- pcos_document_requirements_template_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_engagement_documents_evidence_id ON public.pcos_engagement_documents (evidence_id);  -- pcos_engagement_documents_evidence_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_engagement_documents_requirement_id ON public.pcos_engagement_documents (requirement_id);  -- pcos_engagement_documents_requirement_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_engagement_documents_verified_by ON public.pcos_engagement_documents (verified_by);  -- pcos_engagement_documents_verified_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_evidence_uploaded_by ON public.pcos_evidence (uploaded_by);  -- pcos_evidence_uploaded_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_extracted_facts_previous_fact_id ON public.pcos_extracted_facts (previous_fact_id);  -- pcos_extracted_facts_previous_fact_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_form_templates_created_by ON public.pcos_form_templates (created_by);  -- pcos_form_templates_created_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_gate_evaluations_evaluated_by ON public.pcos_gate_evaluations (evaluated_by);  -- pcos_gate_evaluations_evaluated_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_generated_forms_generated_by ON public.pcos_generated_forms (generated_by);  -- pcos_generated_forms_generated_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_generated_forms_location_id ON public.pcos_generated_forms (location_id);  -- pcos_generated_forms_location_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_generated_forms_signed_by ON public.pcos_generated_forms (signed_by);  -- pcos_generated_forms_signed_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_generated_forms_template_id ON public.pcos_generated_forms (template_id);  -- pcos_generated_forms_template_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_permit_packets_location_id ON public.pcos_permit_packets (location_id);  -- pcos_permit_packets_location_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_person_visa_status_evidence_id ON public.pcos_person_visa_status (evidence_id);  -- pcos_person_visa_status_evidence_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_person_visa_status_visa_category_id ON public.pcos_person_visa_status (visa_category_id);  -- pcos_person_visa_status_visa_category_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_projects_created_by ON public.pcos_projects (created_by);  -- pcos_projects_created_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_projects_gate_state_changed_by ON public.pcos_projects (gate_state_changed_by);  -- pcos_projects_gate_state_changed_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_projects_updated_by ON public.pcos_projects (updated_by);  -- pcos_projects_updated_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_rule_evaluations_evaluated_by ON public.pcos_rule_evaluations (evaluated_by);  -- pcos_rule_evaluations_evaluated_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_rule_evaluations_supersedes_id ON public.pcos_rule_evaluations (supersedes_id);  -- pcos_rule_evaluations_supersedes_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_rule_evaluations_task_id ON public.pcos_rule_evaluations (task_id);  -- pcos_rule_evaluations_task_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_task_events_actor_id ON public.pcos_task_events (actor_id);  -- pcos_task_events_actor_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_tasks_assigned_to ON public.pcos_tasks (assigned_to);  -- pcos_tasks_assigned_to_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_tasks_completed_by ON public.pcos_tasks (completed_by);  -- pcos_tasks_completed_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_tax_credit_applications_budget_id ON public.pcos_tax_credit_applications (budget_id);  -- pcos_tax_credit_applications_budget_id_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_tax_credit_applications_created_by ON public.pcos_tax_credit_applications (created_by);  -- pcos_tax_credit_applications_created_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_timecards_approved_by ON public.pcos_timecards (approved_by);  -- pcos_timecards_approved_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_timecards_rejected_by ON public.pcos_timecards (rejected_by);  -- pcos_timecards_rejected_by_fkey
CREATE INDEX IF NOT EXISTS idx_pcos_timecards_submitted_by ON public.pcos_timecards (submitted_by);  -- pcos_timecards_submitted_by_fkey
CREATE INDEX IF NOT EXISTS idx_supplier_cte_events_supplier_user_id ON public.supplier_cte_events (supplier_user_id);  -- supplier_cte_events_supplier_user_id_fkey
CREATE INDEX IF NOT EXISTS idx_supplier_funnel_events_facility_id ON public.supplier_funnel_events (facility_id);  -- supplier_funnel_events_facility_id_fkey
;
