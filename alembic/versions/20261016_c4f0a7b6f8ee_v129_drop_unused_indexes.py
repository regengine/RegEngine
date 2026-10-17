# DO NOT APPLY until idx_scan=0 is re-verified over >=14 days; pg_stat_database.stats_reset is NULL so the observation window is unknown.
"""Drop catalog-reported unused indexes after the observation gate is met.

Revision ID: c4f0a7b6f8ee
Revises: 93eb33f262a1
Create Date: 2026-10-16

The catalog excludes primary, unique, and constraint-backed indexes.
This revision additionally excludes FK-leading indexes, code references,
and indexes created in migrations within the last 30 days.
"""

from alembic import op

revision = "c4f0a7b6f8ee"  # pragma: allowlist secret
down_revision = "93eb33f262a1"  # pragma: allowlist secret
branch_labels = None
depends_on = None

# schema, index name, exact pg_indexes.indexdef from the read-only export.
_INDEXES = (
    (
        "audit",
        "idx_sysadmin_access_log_accessed_at",
        "CREATE INDEX idx_sysadmin_access_log_accessed_at ON audit.sysadmin_access_log USING btree (accessed_at DESC)",
    ),
    (
        "dlq",
        "idx_dlq_webhook_failures_replayed_at",
        "CREATE INDEX idx_dlq_webhook_failures_replayed_at ON dlq.webhook_failures USING btree (replayed_at) WHERE (replayed_at IS NOT NULL)",
    ),
    (
        "fsma",
        "idx_fsma_audit_entity",
        "CREATE INDEX idx_fsma_audit_entity ON fsma.audit_log USING btree (entity_type, entity_id)",
    ),
    (
        "fsma",
        "idx_fsma_audit_log_tenant",
        "CREATE INDEX idx_fsma_audit_log_tenant ON fsma.audit_log USING btree (tenant_id)",
    ),
    ("fsma", "idx_fsma_audit_org", "CREATE INDEX idx_fsma_audit_org ON fsma.audit_log USING btree (org_id)"),
    ("fsma", "idx_fsma_audit_time", "CREATE INDEX idx_fsma_audit_time ON fsma.audit_log USING btree (created_at)"),
    (
        "fsma",
        "idx_canonical_entities_fda_reg",
        "CREATE INDEX idx_canonical_entities_fda_reg ON fsma.canonical_entities USING btree (fda_registration) WHERE (fda_registration IS NOT NULL)",
    ),
    (
        "fsma",
        "idx_canonical_entities_gln",
        "CREATE INDEX idx_canonical_entities_gln ON fsma.canonical_entities USING btree (gln) WHERE (gln IS NOT NULL)",
    ),
    (
        "fsma",
        "idx_canonical_entities_gtin",
        "CREATE INDEX idx_canonical_entities_gtin ON fsma.canonical_entities USING btree (gtin) WHERE (gtin IS NOT NULL)",
    ),
    (
        "fsma",
        "idx_canonical_entities_tenant",
        "CREATE INDEX idx_canonical_entities_tenant ON fsma.canonical_entities USING btree (tenant_id)",
    ),
    (
        "fsma",
        "idx_canonical_entities_type",
        "CREATE INDEX idx_canonical_entities_type ON fsma.canonical_entities USING btree (tenant_id, entity_type)",
    ),
    (
        "fsma",
        "idx_alerts_unresolved",
        "CREATE INDEX idx_alerts_unresolved ON fsma.compliance_alerts USING btree (tenant_id, resolved) WHERE (resolved = false)",
    ),
    (
        "fsma",
        "idx_compliance_alerts_cte_event_id",
        "CREATE INDEX idx_compliance_alerts_cte_event_id ON fsma.compliance_alerts USING btree (cte_event_id)",
    ),
    (
        "fsma",
        "idx_fsma_alerts_tenant_unresolved",
        "CREATE INDEX idx_fsma_alerts_tenant_unresolved ON fsma.compliance_alerts USING btree (tenant_id) WHERE (resolved = false)",
    ),
    (
        "fsma",
        "idx_fsma_snapshots_tenant_date",
        "CREATE INDEX idx_fsma_snapshots_tenant_date ON fsma.compliance_snapshots USING btree (tenant_id, snapshot_date DESC)",
    ),
    (
        "fsma",
        "idx_fsma_cte_event_time",
        "CREATE INDEX idx_fsma_cte_event_time ON fsma.critical_tracking_events USING btree (event_time)",
    ),
    (
        "fsma",
        "idx_fsma_cte_event_type",
        "CREATE INDEX idx_fsma_cte_event_type ON fsma.critical_tracking_events USING btree (event_type)",
    ),
    (
        "fsma",
        "idx_fsma_cte_lot",
        "CREATE INDEX idx_fsma_cte_lot ON fsma.critical_tracking_events USING btree (lot_code)",
    ),
    ("fsma", "idx_fsma_cte_org", "CREATE INDEX idx_fsma_cte_org ON fsma.critical_tracking_events USING btree (org_id)"),
    (
        "fsma",
        "idx_fsma_cte_product",
        "CREATE INDEX idx_fsma_cte_product ON fsma.critical_tracking_events USING btree (product_id)",
    ),
    ("fsma", "idx_fsma_cte_tlc", "CREATE INDEX idx_fsma_cte_tlc ON fsma.critical_tracking_events USING btree (tlc)"),
    (
        "fsma",
        "idx_entity_aliases_entity",
        "CREATE INDEX idx_entity_aliases_entity ON fsma.entity_aliases USING btree (entity_id)",
    ),
    (
        "fsma",
        "idx_entity_aliases_lookup",
        "CREATE INDEX idx_entity_aliases_lookup ON fsma.entity_aliases USING btree (tenant_id, alias_type, alias_value)",
    ),
    (
        "fsma",
        "idx_entity_aliases_tenant",
        "CREATE INDEX idx_entity_aliases_tenant ON fsma.entity_aliases USING btree (tenant_id)",
    ),
    (
        "fsma",
        "idx_entity_aliases_tlc_prefix",
        "CREATE INDEX idx_entity_aliases_tlc_prefix ON fsma.entity_aliases USING btree (tenant_id, alias_value) WHERE (alias_type = 'tlc_prefix'::text)",
    ),
    (
        "fsma",
        "idx_entity_aliases_value",
        "CREATE INDEX idx_entity_aliases_value ON fsma.entity_aliases USING btree (alias_type, alias_value)",
    ),
    (
        "fsma",
        "ix_entity_aliases_alias_value_trgm",
        "CREATE INDEX ix_entity_aliases_alias_value_trgm ON fsma.entity_aliases USING gin (lower(alias_value) gin_trgm_ops)",
    ),
    (
        "fsma",
        "idx_merge_history_target",
        "CREATE INDEX idx_merge_history_target ON fsma.entity_merge_history USING btree (target_entity_id)",
    ),
    (
        "fsma",
        "idx_merge_history_tenant",
        "CREATE INDEX idx_merge_history_tenant ON fsma.entity_merge_history USING btree (tenant_id)",
    ),
    (
        "fsma",
        "idx_exception_attachments_case",
        "CREATE INDEX idx_exception_attachments_case ON fsma.exception_attachments USING btree (case_id)",
    ),
    (
        "fsma",
        "idx_exception_cases_due",
        "CREATE INDEX idx_exception_cases_due ON fsma.exception_cases USING btree (due_date) WHERE (status <> ALL (ARRAY['resolved'::text, 'waived'::text]))",
    ),
    (
        "fsma",
        "idx_exception_cases_events",
        "CREATE INDEX idx_exception_cases_events ON fsma.exception_cases USING gin (linked_event_ids)",
    ),
    (
        "fsma",
        "idx_exception_cases_owner",
        "CREATE INDEX idx_exception_cases_owner ON fsma.exception_cases USING btree (owner_user_id) WHERE (owner_user_id IS NOT NULL)",
    ),
    (
        "fsma",
        "idx_exception_cases_request",
        "CREATE INDEX idx_exception_cases_request ON fsma.exception_cases USING btree (request_case_id) WHERE (request_case_id IS NOT NULL)",
    ),
    (
        "fsma",
        "idx_exception_cases_supplier",
        "CREATE INDEX idx_exception_cases_supplier ON fsma.exception_cases USING btree (tenant_id, source_supplier) WHERE (source_supplier IS NOT NULL)",
    ),
    (
        "fsma",
        "idx_exception_cases_tenant",
        "CREATE INDEX idx_exception_cases_tenant ON fsma.exception_cases USING btree (tenant_id)",
    ),
    (
        "fsma",
        "idx_exception_comments_case",
        "CREATE INDEX idx_exception_comments_case ON fsma.exception_comments USING btree (case_id)",
    ),
    (
        "fsma",
        "idx_exception_signoffs_case",
        "CREATE INDEX idx_exception_signoffs_case ON fsma.exception_signoffs USING btree (case_id)",
    ),
    (
        "fsma",
        "idx_identity_review_pending",
        "CREATE INDEX idx_identity_review_pending ON fsma.identity_review_queue USING btree (tenant_id, status) WHERE (status = 'pending'::text)",
    ),
    (
        "fsma",
        "idx_identity_review_queue_entity_b_id",
        "CREATE INDEX idx_identity_review_queue_entity_b_id ON fsma.identity_review_queue USING btree (entity_b_id)",
    ),
    (
        "fsma",
        "idx_identity_review_queue_previous_review_id",
        "CREATE INDEX idx_identity_review_queue_previous_review_id ON fsma.identity_review_queue USING btree (previous_review_id)",
    ),
    (
        "fsma",
        "idx_identity_review_tenant",
        "CREATE INDEX idx_identity_review_tenant ON fsma.identity_review_queue USING btree (tenant_id)",
    ),
    (
        "fsma",
        "idx_inflow_commit_decisions_tenant_created",
        "CREATE INDEX idx_inflow_commit_decisions_tenant_created ON fsma.inflow_workbench_commit_decisions USING btree (tenant_id, created_at DESC)",
    ),
    (
        "fsma",
        "idx_inflow_workbench_commit_decisions_run_id",
        "CREATE INDEX idx_inflow_workbench_commit_decisions_run_id ON fsma.inflow_workbench_commit_decisions USING btree (run_id)",
    ),
    (
        "fsma",
        "idx_inflow_fix_items_run",
        "CREATE INDEX idx_inflow_fix_items_run ON fsma.inflow_workbench_fix_items USING btree (run_id)",
    ),
    (
        "fsma",
        "idx_inflow_scenarios_tenant_created",
        "CREATE INDEX idx_inflow_scenarios_tenant_created ON fsma.inflow_workbench_scenarios USING btree (tenant_id, created_at DESC)",
    ),
    ("fsma", "idx_fsma_kde_cte", "CREATE INDEX idx_fsma_kde_cte ON fsma.key_data_elements USING btree (cte_id)"),
    ("fsma", "idx_fsma_locations_org", "CREATE INDEX idx_fsma_locations_org ON fsma.locations USING btree (org_id)"),
    (
        "fsma",
        "idx_organizations_fei",
        "CREATE INDEX idx_organizations_fei ON fsma.organizations USING btree (fei_number) WHERE (fei_number IS NOT NULL)",
    ),
    ("fsma", "idx_organizations_type", "CREATE INDEX idx_organizations_type ON fsma.organizations USING btree (type)"),
    (
        "fsma",
        "idx_fsma_products_ftl",
        "CREATE INDEX idx_fsma_products_ftl ON fsma.products USING btree (ftl_covered) WHERE (ftl_covered = true)",
    ),
    ("fsma", "idx_fsma_products_org", "CREATE INDEX idx_fsma_products_org ON fsma.products USING btree (org_id)"),
    ("fsma", "idx_fsma_recall_org", "CREATE INDEX idx_fsma_recall_org ON fsma.recall_assessments USING btree (org_id)"),
    (
        "fsma",
        "idx_fsma_recall_tenant",
        "CREATE INDEX idx_fsma_recall_tenant ON fsma.recall_assessments USING btree (tenant_id)",
    ),
    (
        "fsma",
        "idx_request_cases_due",
        "CREATE INDEX idx_request_cases_due ON fsma.request_cases USING btree (response_due_at) WHERE (package_status <> ALL (ARRAY['submitted'::text, 'amended'::text]))",
    ),
    (
        "fsma",
        "idx_request_cases_facilities",
        "CREATE INDEX idx_request_cases_facilities ON fsma.request_cases USING gin (affected_facilities)",
    ),
    (
        "fsma",
        "idx_request_cases_lots",
        "CREATE INDEX idx_request_cases_lots ON fsma.request_cases USING gin (affected_lots)",
    ),
    (
        "fsma",
        "idx_response_packages_request",
        "CREATE INDEX idx_response_packages_request ON fsma.response_packages USING btree (request_case_id)",
    ),
    ("fsma", "idx_rule_audit_rule", "CREATE INDEX idx_rule_audit_rule ON fsma.rule_audit_log USING btree (rule_id)"),
    (
        "fsma",
        "idx_rule_defs_category",
        "CREATE INDEX idx_rule_defs_category ON fsma.rule_definitions USING btree (category)",
    ),
    ("fsma", "idx_rule_evals_rule", "CREATE INDEX idx_rule_evals_rule ON fsma.rule_evaluations USING btree (rule_id)"),
    (
        "fsma",
        "idx_submission_log_package_id",
        "CREATE INDEX idx_submission_log_package_id ON fsma.submission_log USING btree (package_id)",
    ),
    (
        "fsma",
        "idx_submission_log_request",
        "CREATE INDEX idx_submission_log_request ON fsma.submission_log USING btree (request_case_id)",
    ),
    (
        "fsma",
        "idx_supplier_profiles_tenant_status",
        "CREATE INDEX idx_supplier_profiles_tenant_status ON fsma.supplier_integration_profiles USING btree (tenant_id, status, updated_at DESC)",
    ),
    ("fsma", "idx_fsma_suppliers_org", "CREATE INDEX idx_fsma_suppliers_org ON fsma.suppliers USING btree (org_id)"),
    (
        "fsma",
        "idx_tenant_portal_links_tid",
        "CREATE INDEX idx_tenant_portal_links_tid ON fsma.tenant_portal_links USING btree (tenant_id)",
    ),
    (
        "fsma",
        "idx_tenant_portal_links_token_active",
        "CREATE INDEX idx_tenant_portal_links_token_active ON fsma.tenant_portal_links USING btree (link_token) WHERE (status = 'active'::text)",
    ),
    (
        "fsma",
        "idx_te_tenant_tlc",
        "CREATE INDEX idx_te_tenant_tlc ON fsma.traceability_events USING btree (tenant_id, traceability_lot_code)",
    ),
    ("fsma", "idx_te_tlc", "CREATE INDEX idx_te_tlc ON fsma.traceability_events USING btree (traceability_lot_code)"),
    (
        "fsma",
        "idx_tl_event",
        "CREATE INDEX idx_tl_event ON fsma.transformation_links USING btree (transformation_event_id)",
    ),
    (
        "fsma",
        "idx_tl_input_tlc",
        "CREATE INDEX idx_tl_input_tlc ON fsma.transformation_links USING btree (tenant_id, input_tlc)",
    ),
    (
        "fsma",
        "idx_tl_output_tlc",
        "CREATE INDEX idx_tl_output_tlc ON fsma.transformation_links USING btree (tenant_id, output_tlc)",
    ),
    ("fsma", "idx_tl_tenant", "CREATE INDEX idx_tl_tenant ON fsma.transformation_links USING btree (tenant_id)"),
    (
        "ingestion",
        "idx_audit_log_action",
        "CREATE INDEX idx_audit_log_action ON ingestion.audit_log USING btree (action)",
    ),
    (
        "ingestion",
        "idx_audit_log_job_id",
        "CREATE INDEX idx_audit_log_job_id ON ingestion.audit_log USING btree (job_id)",
    ),
    (
        "ingestion",
        "idx_audit_log_timestamp",
        'CREATE INDEX idx_audit_log_timestamp ON ingestion.audit_log USING btree ("timestamp" DESC)',
    ),
    (
        "ingestion",
        "idx_documents_content_sha256",
        "CREATE INDEX idx_documents_content_sha256 ON ingestion.documents USING btree (content_sha256)",
    ),
    (
        "ingestion",
        "idx_documents_created_at",
        "CREATE INDEX idx_documents_created_at ON ingestion.documents USING btree (created_at DESC)",
    ),
    (
        "ingestion",
        "idx_documents_source_type",
        "CREATE INDEX idx_documents_source_type ON ingestion.documents USING btree (source_type)",
    ),
    (
        "ingestion",
        "idx_documents_tenant",
        "CREATE INDEX idx_documents_tenant ON ingestion.documents USING btree (tenant_id)",
    ),
    (
        "ingestion",
        "idx_documents_title_search",
        "CREATE INDEX idx_documents_title_search ON ingestion.documents USING gin (to_tsvector('english'::regconfig, title))",
    ),
    (
        "ingestion",
        "idx_documents_vertical",
        "CREATE INDEX idx_documents_vertical ON ingestion.documents USING btree (vertical)",
    ),
    (
        "ingestion",
        "idx_jobs_created_at",
        "CREATE INDEX idx_jobs_created_at ON ingestion.jobs USING btree (created_at DESC)",
    ),
    ("ingestion", "idx_jobs_status", "CREATE INDEX idx_jobs_status ON ingestion.jobs USING btree (status)"),
    ("ingestion", "idx_jobs_vertical", "CREATE INDEX idx_jobs_vertical ON ingestion.jobs USING btree (vertical)"),
    (
        "net",
        "_http_response_created_idx",
        "CREATE INDEX _http_response_created_idx ON net._http_response USING btree (created)",
    ),
    (
        "public",
        "ix_api_keys_partner_id",
        "CREATE INDEX ix_api_keys_partner_id ON public.api_keys USING btree (partner_id) WHERE (partner_id IS NOT NULL)",
    ),
    (
        "public",
        "ix_api_keys_tenant_id",
        "CREATE INDEX ix_api_keys_tenant_id ON public.api_keys USING btree (tenant_id)",
    ),
    (
        "public",
        "idx_assessment_source",
        "CREATE INDEX idx_assessment_source ON public.assessment_submissions USING btree (source)",
    ),
    (
        "public",
        "idx_assessment_submissions_created",
        "CREATE INDEX idx_assessment_submissions_created ON public.assessment_submissions USING btree (created_at DESC)",
    ),
    (
        "public",
        "idx_compliance_alerts_countdown",
        "CREATE INDEX idx_compliance_alerts_countdown ON public.compliance_alerts USING btree (countdown_end) WHERE ((status)::text = 'ACTIVE'::text)",
    ),
    (
        "public",
        "idx_compliance_alerts_severity",
        "CREATE INDEX idx_compliance_alerts_severity ON public.compliance_alerts USING btree (severity, status)",
    ),
    (
        "public",
        "idx_compliance_alerts_tenant_status",
        "CREATE INDEX idx_compliance_alerts_tenant_status ON public.compliance_alerts USING btree (tenant_id, status)",
    ),
    (
        "public",
        "idx_compliance_status_log_tenant",
        "CREATE INDEX idx_compliance_status_log_tenant ON public.compliance_status_log USING btree (tenant_id, created_at)",
    ),
    ("public", "ix_evidence_hash", "CREATE INDEX ix_evidence_hash ON public.evidence_logs USING btree (content_hash)"),
    (
        "public",
        "ix_evidence_project_rule",
        "CREATE INDEX ix_evidence_project_rule ON public.evidence_logs USING btree (project_id, rule_id)",
    ),
    (
        "public",
        "idx_funnel_events_event_name",
        "CREATE INDEX idx_funnel_events_event_name ON public.funnel_events USING btree (event_name)",
    ),
    (
        "public",
        "idx_graph_outbox_pending",
        "CREATE INDEX idx_graph_outbox_pending ON public.graph_outbox USING btree (next_attempt_at, id) WHERE (status = 'pending'::text)",
    ),
    (
        "public",
        "idx_graph_outbox_tenant_status",
        "CREATE INDEX idx_graph_outbox_tenant_status ON public.graph_outbox USING btree (tenant_id, status)",
    ),
    (
        "public",
        "idx_audit_events_type",
        "CREATE INDEX idx_audit_events_type ON public.pcos_audit_events USING btree (event_type)",
    ),
    (
        "public",
        "idx_authority_docs_effective",
        "CREATE INDEX idx_authority_docs_effective ON public.pcos_authority_documents USING btree (effective_date)",
    ),
    (
        "public",
        "idx_authority_docs_issuer",
        "CREATE INDEX idx_authority_docs_issuer ON public.pcos_authority_documents USING btree (issuer_name)",
    ),
    (
        "public",
        "idx_authority_docs_status",
        "CREATE INDEX idx_authority_docs_status ON public.pcos_authority_documents USING btree (status)",
    ),
    (
        "public",
        "idx_authority_docs_type",
        "CREATE INDEX idx_authority_docs_type ON public.pcos_authority_documents USING btree (document_type)",
    ),
    (
        "public",
        "idx_pcos_budget_items_dept",
        "CREATE INDEX idx_pcos_budget_items_dept ON public.pcos_budget_line_items USING btree (department)",
    ),
    (
        "public",
        "idx_classification_result",
        "CREATE INDEX idx_classification_result ON public.pcos_classification_analyses USING btree (overall_result)",
    ),
    (
        "public",
        "idx_exemptions_category",
        "CREATE INDEX idx_exemptions_category ON public.pcos_classification_exemptions USING btree (exemption_category)",
    ),
    (
        "public",
        "idx_exemptions_code",
        "CREATE INDEX idx_exemptions_code ON public.pcos_classification_exemptions USING btree (exemption_code)",
    ),
    (
        "public",
        "idx_pcos_classification_exemptions_tenant_id",
        "CREATE INDEX idx_pcos_classification_exemptions_tenant_id ON public.pcos_classification_exemptions USING btree (tenant_id)",
    ),
    (
        "public",
        "idx_pcos_companies_status",
        "CREATE INDEX idx_pcos_companies_status ON public.pcos_companies USING btree (status)",
    ),
    (
        "public",
        "idx_pcos_registrations_expiry",
        "CREATE INDEX idx_pcos_registrations_expiry ON public.pcos_company_registrations USING btree (expiration_date)",
    ),
    (
        "public",
        "idx_snapshots_type",
        "CREATE INDEX idx_snapshots_type ON public.pcos_compliance_snapshots USING btree (snapshot_type)",
    ),
    (
        "public",
        "idx_doc_requirements_type",
        "CREATE INDEX idx_doc_requirements_type ON public.pcos_document_requirements USING btree (document_type)",
    ),
    (
        "public",
        "idx_pcos_document_requirements_tenant_id",
        "CREATE INDEX idx_pcos_document_requirements_tenant_id ON public.pcos_document_requirements USING btree (tenant_id)",
    ),
    (
        "public",
        "idx_engagement_docs_status",
        "CREATE INDEX idx_engagement_docs_status ON public.pcos_engagement_documents USING btree (status)",
    ),
    (
        "public",
        "idx_pcos_engagements_classification",
        "CREATE INDEX idx_pcos_engagements_classification ON public.pcos_engagements USING btree (classification)",
    ),
    (
        "public",
        "idx_pcos_evidence_entity",
        "CREATE INDEX idx_pcos_evidence_entity ON public.pcos_evidence USING btree (entity_type, entity_id)",
    ),
    (
        "public",
        "idx_pcos_evidence_type",
        "CREATE INDEX idx_pcos_evidence_type ON public.pcos_evidence USING btree (evidence_type)",
    ),
    (
        "public",
        "idx_pcos_evidence_validity",
        "CREATE INDEX idx_pcos_evidence_validity ON public.pcos_evidence USING btree (valid_until)",
    ),
    (
        "public",
        "idx_extracted_facts_category",
        "CREATE INDEX idx_extracted_facts_category ON public.pcos_extracted_facts USING btree (fact_category)",
    ),
    (
        "public",
        "idx_extracted_facts_key",
        "CREATE INDEX idx_extracted_facts_key ON public.pcos_extracted_facts USING btree (fact_key)",
    ),
    (
        "public",
        "idx_fact_citations_entity",
        "CREATE INDEX idx_fact_citations_entity ON public.pcos_fact_citations USING btree (citing_entity_type, citing_entity_id)",
    ),
    (
        "public",
        "idx_form_templates_code",
        "CREATE INDEX idx_form_templates_code ON public.pcos_form_templates USING btree (template_code)",
    ),
    (
        "public",
        "idx_form_templates_type",
        "CREATE INDEX idx_form_templates_type ON public.pcos_form_templates USING btree (form_type)",
    ),
    (
        "public",
        "idx_pcos_form_templates_tenant_id",
        "CREATE INDEX idx_pcos_form_templates_tenant_id ON public.pcos_form_templates USING btree (tenant_id)",
    ),
    (
        "public",
        "idx_pcos_gate_evals_date",
        "CREATE INDEX idx_pcos_gate_evals_date ON public.pcos_gate_evaluations USING btree (evaluated_at)",
    ),
    (
        "public",
        "idx_generated_forms_status",
        "CREATE INDEX idx_generated_forms_status ON public.pcos_generated_forms USING btree (status)",
    ),
    (
        "public",
        "idx_pcos_insurance_expiry",
        "CREATE INDEX idx_pcos_insurance_expiry ON public.pcos_insurance_policies USING btree (expiration_date)",
    ),
    (
        "public",
        "idx_pcos_locations_type",
        "CREATE INDEX idx_pcos_locations_type ON public.pcos_locations USING btree (location_type)",
    ),
    ("public", "idx_pcos_people_email", "CREATE INDEX idx_pcos_people_email ON public.pcos_people USING btree (email)"),
    (
        "public",
        "idx_pcos_people_name",
        "CREATE INDEX idx_pcos_people_name ON public.pcos_people USING btree (last_name, first_name)",
    ),
    (
        "public",
        "idx_pcos_permits_status",
        "CREATE INDEX idx_pcos_permits_status ON public.pcos_permit_packets USING btree (status)",
    ),
    (
        "public",
        "idx_person_visa_expiration",
        "CREATE INDEX idx_person_visa_expiration ON public.pcos_person_visa_status USING btree (expiration_date)",
    ),
    (
        "public",
        "idx_pcos_projects_dates",
        "CREATE INDEX idx_pcos_projects_dates ON public.pcos_projects USING btree (first_shoot_date, start_date)",
    ),
    (
        "public",
        "idx_pcos_projects_gate",
        "CREATE INDEX idx_pcos_projects_gate ON public.pcos_projects USING btree (gate_state)",
    ),
    (
        "public",
        "idx_rule_evals_result",
        "CREATE INDEX idx_rule_evals_result ON public.pcos_rule_evaluations USING btree (result)",
    ),
    (
        "public",
        "idx_rule_evals_rule",
        "CREATE INDEX idx_rule_evals_rule ON public.pcos_rule_evaluations USING btree (rule_code)",
    ),
    (
        "public",
        "idx_pcos_task_events_created",
        "CREATE INDEX idx_pcos_task_events_created ON public.pcos_task_events USING btree (created_at)",
    ),
    ("public", "idx_pcos_tasks_due", "CREATE INDEX idx_pcos_tasks_due ON public.pcos_tasks USING btree (due_date)"),
    (
        "public",
        "idx_pcos_tasks_source",
        "CREATE INDEX idx_pcos_tasks_source ON public.pcos_tasks USING btree (source_type, source_id)",
    ),
    ("public", "idx_pcos_tasks_status", "CREATE INDEX idx_pcos_tasks_status ON public.pcos_tasks USING btree (status)"),
    (
        "public",
        "idx_tax_credit_apps_program",
        "CREATE INDEX idx_tax_credit_apps_program ON public.pcos_tax_credit_applications USING btree (program_code, program_year)",
    ),
    (
        "public",
        "idx_pcos_tax_credit_rules_tenant_id",
        "CREATE INDEX idx_pcos_tax_credit_rules_tenant_id ON public.pcos_tax_credit_rules USING btree (tenant_id)",
    ),
    (
        "public",
        "idx_tax_rules_program",
        "CREATE INDEX idx_tax_rules_program ON public.pcos_tax_credit_rules USING btree (program_code, program_year)",
    ),
    (
        "public",
        "idx_pcos_timecards_date",
        "CREATE INDEX idx_pcos_timecards_date ON public.pcos_timecards USING btree (work_date)",
    ),
    (
        "public",
        "idx_pcos_timecards_status",
        "CREATE INDEX idx_pcos_timecards_status ON public.pcos_timecards USING btree (status)",
    ),
    (
        "public",
        "idx_pcos_visa_categories_tenant_id",
        "CREATE INDEX idx_pcos_visa_categories_tenant_id ON public.pcos_visa_categories USING btree (tenant_id)",
    ),
    (
        "public",
        "idx_visa_categories_code",
        "CREATE INDEX idx_visa_categories_code ON public.pcos_visa_categories USING btree (visa_code)",
    ),
    (
        "public",
        "idx_sandbox_shares_expires",
        "CREATE INDEX idx_sandbox_shares_expires ON public.sandbox_shares USING btree (expires_at)",
    ),
    (
        "public",
        "idx_search_queries_query",
        "CREATE INDEX idx_search_queries_query ON public.search_queries USING btree (query)",
    ),
    ("public", "idx_tool_leads_domain", "CREATE INDEX idx_tool_leads_domain ON public.tool_leads USING btree (domain)"),
    (
        "public",
        "idx_tool_leads_verified_at",
        "CREATE INDEX idx_tool_leads_verified_at ON public.tool_leads USING btree (verified_at)",
    ),
    (
        "public",
        "ix_vertical_projects_tenant",
        "CREATE INDEX ix_vertical_projects_tenant ON public.vertical_projects USING btree (tenant_id)",
    ),
    (
        "public",
        "idx_vertical_rule_instances_tenant_id",
        "CREATE INDEX idx_vertical_rule_instances_tenant_id ON public.vertical_rule_instances USING btree (tenant_id)",
    ),
    (
        "public",
        "idx_webhook_outbox_tenant_status",
        "CREATE INDEX idx_webhook_outbox_tenant_status ON public.webhook_outbox USING btree (tenant_id, status)",
    ),
)


def upgrade() -> None:
    for schema, index, _definition in _INDEXES:
        op.execute(f'DROP INDEX "{schema}"."{index}"')


def downgrade() -> None:
    for _schema, _index, definition in reversed(_INDEXES):
        op.execute(definition)
