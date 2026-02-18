-- Migration V002: Complete PCOS Schema Migration
-- 
-- CONTEXT:
-- Migrate all 38 PCOS tables from Admin DB to Entertainment vertical DB
-- This completes vertical data isolation following RegEngine architecture.
--
-- MIGRATION SOURCE:
-- Exported from regengine_admin (Admin DB) V12-V20 PCOS migrations
-- This replaces the partial 9-table schema from V001
--
-- Author: Platform Team
-- Date: 2026-01-31
-- Phase: Architecture Optimization - P1 (Vertical Isolation)
--
-- ============================================================================
-- EXPORTED SCHEMA FROM ADMIN DB
-- ============================================================================

--
-- PostgreSQL database dump
--

\restrict L9HE842Uha7uZlCk7cdgUqcXARnmf9PjPX64AqcG8FsShjcJeB9OFB1aJS7VR41

-- Dumped from database version 15.15 (Debian 15.15-1.pgdg13+1)
-- Dumped by pg_dump version 15.15 (Debian 15.15-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

DROP POLICY tenant_isolation_policy ON public.pcos_timecards;
DROP POLICY tenant_isolation_policy ON public.pcos_tasks;
DROP POLICY tenant_isolation_policy ON public.pcos_task_events;
DROP POLICY tenant_isolation_policy ON public.pcos_safety_policies;
DROP POLICY tenant_isolation_policy ON public.pcos_projects;
DROP POLICY tenant_isolation_policy ON public.pcos_permit_packets;
DROP POLICY tenant_isolation_policy ON public.pcos_people;
DROP POLICY tenant_isolation_policy ON public.pcos_payroll_exports;
DROP POLICY tenant_isolation_policy ON public.pcos_locations;
DROP POLICY tenant_isolation_policy ON public.pcos_insurance_policies;
DROP POLICY tenant_isolation_policy ON public.pcos_gate_evaluations;
DROP POLICY tenant_isolation_policy ON public.pcos_evidence;
DROP POLICY tenant_isolation_policy ON public.pcos_engagements;
DROP POLICY tenant_isolation_policy ON public.pcos_contract_templates;
DROP POLICY tenant_isolation_policy ON public.pcos_company_registrations;
DROP POLICY tenant_isolation_policy ON public.pcos_companies;
DROP POLICY snapshots_tenant ON public.pcos_compliance_snapshots;
DROP POLICY snapshots_insert ON public.pcos_compliance_snapshots;
DROP POLICY rule_evals_tenant ON public.pcos_rule_evaluations;
DROP POLICY rule_evals_insert ON public.pcos_rule_evaluations;
DROP POLICY person_visa_tenant_isolation ON public.pcos_person_visa_status;
DROP POLICY person_visa_insert ON public.pcos_person_visa_status;
DROP POLICY pcos_fact_citations_tenant_isolation ON public.pcos_fact_citations;
DROP POLICY pcos_extracted_facts_tenant_isolation ON public.pcos_extracted_facts;
DROP POLICY pcos_authority_documents_tenant_isolation ON public.pcos_authority_documents;
DROP POLICY pcos_analysis_runs_tenant_isolation ON public.pcos_analysis_runs;
DROP POLICY audit_events_tenant ON public.pcos_audit_events;
DROP POLICY audit_events_insert ON public.pcos_audit_events;
ALTER TABLE ONLY public.pcos_union_rate_checks DROP CONSTRAINT pcos_union_rate_checks_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_union_rate_checks DROP CONSTRAINT pcos_union_rate_checks_line_item_id_fkey;
ALTER TABLE ONLY public.pcos_union_rate_checks DROP CONSTRAINT pcos_union_rate_checks_engagement_id_fkey;
ALTER TABLE ONLY public.pcos_timecards DROP CONSTRAINT pcos_timecards_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_timecards DROP CONSTRAINT pcos_timecards_submitted_by_fkey;
ALTER TABLE ONLY public.pcos_timecards DROP CONSTRAINT pcos_timecards_rejected_by_fkey;
ALTER TABLE ONLY public.pcos_timecards DROP CONSTRAINT pcos_timecards_engagement_id_fkey;
ALTER TABLE ONLY public.pcos_timecards DROP CONSTRAINT pcos_timecards_approved_by_fkey;
ALTER TABLE ONLY public.pcos_tax_credit_applications DROP CONSTRAINT pcos_tax_credit_applications_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_tax_credit_applications DROP CONSTRAINT pcos_tax_credit_applications_project_id_fkey;
ALTER TABLE ONLY public.pcos_tax_credit_applications DROP CONSTRAINT pcos_tax_credit_applications_created_by_fkey;
ALTER TABLE ONLY public.pcos_tax_credit_applications DROP CONSTRAINT pcos_tax_credit_applications_budget_id_fkey;
ALTER TABLE ONLY public.pcos_tasks DROP CONSTRAINT pcos_tasks_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_tasks DROP CONSTRAINT pcos_tasks_completed_by_fkey;
ALTER TABLE ONLY public.pcos_tasks DROP CONSTRAINT pcos_tasks_assigned_to_fkey;
ALTER TABLE ONLY public.pcos_task_events DROP CONSTRAINT pcos_task_events_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_task_events DROP CONSTRAINT pcos_task_events_task_id_fkey;
ALTER TABLE ONLY public.pcos_task_events DROP CONSTRAINT pcos_task_events_actor_id_fkey;
ALTER TABLE ONLY public.pcos_safety_policies DROP CONSTRAINT pcos_safety_policies_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_safety_policies DROP CONSTRAINT pcos_safety_policies_company_id_fkey;
ALTER TABLE ONLY public.pcos_rule_evaluations DROP CONSTRAINT pcos_rule_evaluations_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_rule_evaluations DROP CONSTRAINT pcos_rule_evaluations_task_id_fkey;
ALTER TABLE ONLY public.pcos_rule_evaluations DROP CONSTRAINT pcos_rule_evaluations_project_id_fkey;
ALTER TABLE ONLY public.pcos_rule_evaluations DROP CONSTRAINT pcos_rule_evaluations_evaluated_by_fkey;
ALTER TABLE ONLY public.pcos_rule_evaluations DROP CONSTRAINT pcos_rule_evaluations_analysis_run_id_fkey;
ALTER TABLE ONLY public.pcos_qualified_spend_categories DROP CONSTRAINT pcos_qualified_spend_categories_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_qualified_spend_categories DROP CONSTRAINT pcos_qualified_spend_categories_application_id_fkey;
ALTER TABLE ONLY public.pcos_projects DROP CONSTRAINT pcos_projects_updated_by_fkey;
ALTER TABLE ONLY public.pcos_projects DROP CONSTRAINT pcos_projects_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_projects DROP CONSTRAINT pcos_projects_gate_state_changed_by_fkey;
ALTER TABLE ONLY public.pcos_projects DROP CONSTRAINT pcos_projects_created_by_fkey;
ALTER TABLE ONLY public.pcos_projects DROP CONSTRAINT pcos_projects_company_id_fkey;
ALTER TABLE ONLY public.pcos_person_visa_status DROP CONSTRAINT pcos_person_visa_status_visa_category_id_fkey;
ALTER TABLE ONLY public.pcos_person_visa_status DROP CONSTRAINT pcos_person_visa_status_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_person_visa_status DROP CONSTRAINT pcos_person_visa_status_person_id_fkey;
ALTER TABLE ONLY public.pcos_person_visa_status DROP CONSTRAINT pcos_person_visa_status_evidence_id_fkey;
ALTER TABLE ONLY public.pcos_permit_packets DROP CONSTRAINT pcos_permit_packets_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_permit_packets DROP CONSTRAINT pcos_permit_packets_project_id_fkey;
ALTER TABLE ONLY public.pcos_permit_packets DROP CONSTRAINT pcos_permit_packets_location_id_fkey;
ALTER TABLE ONLY public.pcos_people DROP CONSTRAINT pcos_people_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_payroll_exports DROP CONSTRAINT pcos_payroll_exports_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_payroll_exports DROP CONSTRAINT pcos_payroll_exports_project_id_fkey;
ALTER TABLE ONLY public.pcos_payroll_exports DROP CONSTRAINT pcos_payroll_exports_exported_by_fkey;
ALTER TABLE ONLY public.pcos_locations DROP CONSTRAINT pcos_locations_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_locations DROP CONSTRAINT pcos_locations_project_id_fkey;
ALTER TABLE ONLY public.pcos_insurance_policies DROP CONSTRAINT pcos_insurance_policies_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_insurance_policies DROP CONSTRAINT pcos_insurance_policies_company_id_fkey;
ALTER TABLE ONLY public.pcos_generated_forms DROP CONSTRAINT pcos_generated_forms_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_generated_forms DROP CONSTRAINT pcos_generated_forms_template_id_fkey;
ALTER TABLE ONLY public.pcos_generated_forms DROP CONSTRAINT pcos_generated_forms_signed_by_fkey;
ALTER TABLE ONLY public.pcos_generated_forms DROP CONSTRAINT pcos_generated_forms_project_id_fkey;
ALTER TABLE ONLY public.pcos_generated_forms DROP CONSTRAINT pcos_generated_forms_location_id_fkey;
ALTER TABLE ONLY public.pcos_generated_forms DROP CONSTRAINT pcos_generated_forms_generated_by_fkey;
ALTER TABLE ONLY public.pcos_gate_evaluations DROP CONSTRAINT pcos_gate_evaluations_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_gate_evaluations DROP CONSTRAINT pcos_gate_evaluations_project_id_fkey;
ALTER TABLE ONLY public.pcos_gate_evaluations DROP CONSTRAINT pcos_gate_evaluations_evaluated_by_fkey;
ALTER TABLE ONLY public.pcos_form_templates DROP CONSTRAINT pcos_form_templates_created_by_fkey;
ALTER TABLE ONLY public.pcos_fact_citations DROP CONSTRAINT pcos_fact_citations_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_fact_citations DROP CONSTRAINT pcos_fact_citations_extracted_fact_id_fkey;
ALTER TABLE ONLY public.pcos_extracted_facts DROP CONSTRAINT pcos_extracted_facts_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_extracted_facts DROP CONSTRAINT pcos_extracted_facts_previous_fact_id_fkey;
ALTER TABLE ONLY public.pcos_extracted_facts DROP CONSTRAINT pcos_extracted_facts_authority_document_id_fkey;
ALTER TABLE ONLY public.pcos_evidence DROP CONSTRAINT pcos_evidence_uploaded_by_fkey;
ALTER TABLE ONLY public.pcos_evidence DROP CONSTRAINT pcos_evidence_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_engagements DROP CONSTRAINT pcos_engagements_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_engagements DROP CONSTRAINT pcos_engagements_project_id_fkey;
ALTER TABLE ONLY public.pcos_engagements DROP CONSTRAINT pcos_engagements_person_id_fkey;
ALTER TABLE ONLY public.pcos_engagement_documents DROP CONSTRAINT pcos_engagement_documents_verified_by_fkey;
ALTER TABLE ONLY public.pcos_engagement_documents DROP CONSTRAINT pcos_engagement_documents_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_engagement_documents DROP CONSTRAINT pcos_engagement_documents_requirement_id_fkey;
ALTER TABLE ONLY public.pcos_engagement_documents DROP CONSTRAINT pcos_engagement_documents_evidence_id_fkey;
ALTER TABLE ONLY public.pcos_engagement_documents DROP CONSTRAINT pcos_engagement_documents_engagement_id_fkey;
ALTER TABLE ONLY public.pcos_document_requirements DROP CONSTRAINT pcos_document_requirements_template_id_fkey;
ALTER TABLE ONLY public.pcos_contract_templates DROP CONSTRAINT pcos_contract_templates_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_compliance_snapshots DROP CONSTRAINT pcos_compliance_snapshots_triggered_by_fkey;
ALTER TABLE ONLY public.pcos_compliance_snapshots DROP CONSTRAINT pcos_compliance_snapshots_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_compliance_snapshots DROP CONSTRAINT pcos_compliance_snapshots_project_id_fkey;
ALTER TABLE ONLY public.pcos_compliance_snapshots DROP CONSTRAINT pcos_compliance_snapshots_previous_snapshot_id_fkey;
ALTER TABLE ONLY public.pcos_compliance_snapshots DROP CONSTRAINT pcos_compliance_snapshots_attested_by_fkey;
ALTER TABLE ONLY public.pcos_company_registrations DROP CONSTRAINT pcos_company_registrations_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_company_registrations DROP CONSTRAINT pcos_company_registrations_company_id_fkey;
ALTER TABLE ONLY public.pcos_companies DROP CONSTRAINT pcos_companies_updated_by_fkey;
ALTER TABLE ONLY public.pcos_companies DROP CONSTRAINT pcos_companies_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_companies DROP CONSTRAINT pcos_companies_created_by_fkey;
ALTER TABLE ONLY public.pcos_classification_analyses DROP CONSTRAINT pcos_classification_analyses_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_classification_analyses DROP CONSTRAINT pcos_classification_analyses_engagement_id_fkey;
ALTER TABLE ONLY public.pcos_classification_analyses DROP CONSTRAINT pcos_classification_analyses_analyzed_by_fkey;
ALTER TABLE ONLY public.pcos_budgets DROP CONSTRAINT pcos_budgets_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_budgets DROP CONSTRAINT pcos_budgets_project_id_fkey;
ALTER TABLE ONLY public.pcos_budgets DROP CONSTRAINT pcos_budgets_created_by_fkey;
ALTER TABLE ONLY public.pcos_budget_line_items DROP CONSTRAINT pcos_budget_line_items_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_budget_line_items DROP CONSTRAINT pcos_budget_line_items_budget_id_fkey;
ALTER TABLE ONLY public.pcos_authority_documents DROP CONSTRAINT pcos_authority_documents_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_authority_documents DROP CONSTRAINT pcos_authority_documents_supersedes_document_id_fkey;
ALTER TABLE ONLY public.pcos_audit_events DROP CONSTRAINT pcos_audit_events_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_audit_events DROP CONSTRAINT pcos_audit_events_project_id_fkey;
ALTER TABLE ONLY public.pcos_audit_events DROP CONSTRAINT pcos_audit_events_actor_id_fkey;
ALTER TABLE ONLY public.pcos_analysis_runs DROP CONSTRAINT pcos_analysis_runs_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_analysis_runs DROP CONSTRAINT pcos_analysis_runs_project_id_fkey;
ALTER TABLE ONLY public.pcos_abc_questionnaire_responses DROP CONSTRAINT pcos_abc_questionnaire_responses_tenant_id_fkey;
ALTER TABLE ONLY public.pcos_abc_questionnaire_responses DROP CONSTRAINT pcos_abc_questionnaire_responses_analysis_id_fkey;
DROP TRIGGER trg_snapshots_updated ON public.pcos_compliance_snapshots;
DROP TRIGGER trg_rule_evaluations_immutable ON public.pcos_rule_evaluations;
DROP TRIGGER trg_person_visa_updated ON public.pcos_person_visa_status;
DROP TRIGGER trg_fact_citations_immutable ON public.pcos_fact_citations;
DROP TRIGGER trg_extracted_facts_updated ON public.pcos_extracted_facts;
DROP TRIGGER trg_extracted_facts_immutable ON public.pcos_extracted_facts;
DROP TRIGGER trg_compliance_snapshots_immutable ON public.pcos_compliance_snapshots;
DROP TRIGGER trg_authority_documents_updated ON public.pcos_authority_documents;
DROP TRIGGER trg_audit_events_immutable ON public.pcos_audit_events;
DROP TRIGGER trg_analysis_runs_immutable ON public.pcos_analysis_runs;
DROP INDEX public.idx_visa_categories_code;
DROP INDEX public.idx_tax_rules_program;
DROP INDEX public.idx_tax_credit_apps_tenant;
DROP INDEX public.idx_tax_credit_apps_project;
DROP INDEX public.idx_tax_credit_apps_program;
DROP INDEX public.idx_snapshots_type;
DROP INDEX public.idx_snapshots_tenant;
DROP INDEX public.idx_snapshots_project;
DROP INDEX public.idx_snapshots_created;
DROP INDEX public.idx_rule_evaluations_run;
DROP INDEX public.idx_rule_evals_time;
DROP INDEX public.idx_rule_evals_tenant;
DROP INDEX public.idx_rule_evals_snapshot;
DROP INDEX public.idx_rule_evals_rule;
DROP INDEX public.idx_rule_evals_result;
DROP INDEX public.idx_rule_evals_project;
DROP INDEX public.idx_rule_evals_entity;
DROP INDEX public.idx_questionnaire_tenant;
DROP INDEX public.idx_questionnaire_analysis;
DROP INDEX public.idx_qualified_spend_tenant;
DROP INDEX public.idx_qualified_spend_app;
DROP INDEX public.idx_person_visa_tenant;
DROP INDEX public.idx_person_visa_person;
DROP INDEX public.idx_person_visa_expiration;
DROP INDEX public.idx_pcos_timecards_tenant;
DROP INDEX public.idx_pcos_timecards_status;
DROP INDEX public.idx_pcos_timecards_engagement;
DROP INDEX public.idx_pcos_timecards_date;
DROP INDEX public.idx_pcos_templates_unique;
DROP INDEX public.idx_pcos_templates_tenant;
DROP INDEX public.idx_pcos_templates_code;
DROP INDEX public.idx_pcos_tasks_tenant;
DROP INDEX public.idx_pcos_tasks_status;
DROP INDEX public.idx_pcos_tasks_source;
DROP INDEX public.idx_pcos_tasks_due;
DROP INDEX public.idx_pcos_tasks_blocking;
DROP INDEX public.idx_pcos_task_events_tenant;
DROP INDEX public.idx_pcos_task_events_task;
DROP INDEX public.idx_pcos_task_events_created;
DROP INDEX public.idx_pcos_safety_tenant;
DROP INDEX public.idx_pcos_safety_company;
DROP INDEX public.idx_pcos_registrations_tenant;
DROP INDEX public.idx_pcos_registrations_expiry;
DROP INDEX public.idx_pcos_registrations_company;
DROP INDEX public.idx_pcos_rate_checks_tenant;
DROP INDEX public.idx_pcos_rate_checks_line_item;
DROP INDEX public.idx_pcos_rate_checks_engagement;
DROP INDEX public.idx_pcos_projects_tenant;
DROP INDEX public.idx_pcos_projects_gate;
DROP INDEX public.idx_pcos_projects_dates;
DROP INDEX public.idx_pcos_projects_company;
DROP INDEX public.idx_pcos_permits_tenant;
DROP INDEX public.idx_pcos_permits_status;
DROP INDEX public.idx_pcos_permits_project;
DROP INDEX public.idx_pcos_people_tenant;
DROP INDEX public.idx_pcos_people_name;
DROP INDEX public.idx_pcos_people_email;
DROP INDEX public.idx_pcos_locations_type;
DROP INDEX public.idx_pcos_locations_tenant;
DROP INDEX public.idx_pcos_locations_project;
DROP INDEX public.idx_pcos_insurance_tenant;
DROP INDEX public.idx_pcos_insurance_expiry;
DROP INDEX public.idx_pcos_insurance_company;
DROP INDEX public.idx_pcos_gate_evals_tenant;
DROP INDEX public.idx_pcos_gate_evals_project;
DROP INDEX public.idx_pcos_gate_evals_date;
DROP INDEX public.idx_pcos_exports_tenant;
DROP INDEX public.idx_pcos_exports_project;
DROP INDEX public.idx_pcos_evidence_validity;
DROP INDEX public.idx_pcos_evidence_type;
DROP INDEX public.idx_pcos_evidence_tenant;
DROP INDEX public.idx_pcos_evidence_entity;
DROP INDEX public.idx_pcos_engagements_tenant;
DROP INDEX public.idx_pcos_engagements_project;
DROP INDEX public.idx_pcos_engagements_person;
DROP INDEX public.idx_pcos_engagements_classification;
DROP INDEX public.idx_pcos_companies_tenant;
DROP INDEX public.idx_pcos_companies_status;
DROP INDEX public.idx_pcos_budgets_tenant;
DROP INDEX public.idx_pcos_budgets_project;
DROP INDEX public.idx_pcos_budget_items_tenant;
DROP INDEX public.idx_pcos_budget_items_dept;
DROP INDEX public.idx_pcos_budget_items_budget;
DROP INDEX public.idx_generated_forms_tenant;
DROP INDEX public.idx_generated_forms_status;
DROP INDEX public.idx_generated_forms_project;
DROP INDEX public.idx_form_templates_type;
DROP INDEX public.idx_form_templates_code;
DROP INDEX public.idx_fact_citations_tenant;
DROP INDEX public.idx_fact_citations_fact;
DROP INDEX public.idx_fact_citations_entity;
DROP INDEX public.idx_extracted_facts_tenant;
DROP INDEX public.idx_extracted_facts_key;
DROP INDEX public.idx_extracted_facts_current;
DROP INDEX public.idx_extracted_facts_category;
DROP INDEX public.idx_extracted_facts_authority;
DROP INDEX public.idx_exemptions_code;
DROP INDEX public.idx_exemptions_category;
DROP INDEX public.idx_engagement_docs_tenant;
DROP INDEX public.idx_engagement_docs_status;
DROP INDEX public.idx_engagement_docs_engagement;
DROP INDEX public.idx_doc_requirements_type;
DROP INDEX public.idx_classification_tenant;
DROP INDEX public.idx_classification_result;
DROP INDEX public.idx_classification_engagement;
DROP INDEX public.idx_authority_docs_type;
DROP INDEX public.idx_authority_docs_tenant;
DROP INDEX public.idx_authority_docs_status;
DROP INDEX public.idx_authority_docs_issuer;
DROP INDEX public.idx_authority_docs_effective;
DROP INDEX public.idx_audit_events_type;
DROP INDEX public.idx_audit_events_time;
DROP INDEX public.idx_audit_events_tenant;
DROP INDEX public.idx_audit_events_project;
DROP INDEX public.idx_audit_events_actor;
DROP INDEX public.idx_analysis_runs_tenant;
DROP INDEX public.idx_analysis_runs_status;
DROP INDEX public.idx_analysis_runs_project;
DROP INDEX public.idx_analysis_runs_created;
ALTER TABLE ONLY public.pcos_tax_credit_rules DROP CONSTRAINT uq_tax_rule_program_code;
ALTER TABLE ONLY public.pcos_extracted_facts DROP CONSTRAINT uq_fact_key_version;
ALTER TABLE ONLY public.pcos_engagement_documents DROP CONSTRAINT uq_engagement_doc;
ALTER TABLE ONLY public.pcos_authority_documents DROP CONSTRAINT uq_authority_doc_code_tenant;
ALTER TABLE ONLY public.pcos_visa_categories DROP CONSTRAINT pcos_visa_categories_visa_code_key;
ALTER TABLE ONLY public.pcos_visa_categories DROP CONSTRAINT pcos_visa_categories_pkey;
ALTER TABLE ONLY public.pcos_union_rate_checks DROP CONSTRAINT pcos_union_rate_checks_pkey;
ALTER TABLE ONLY public.pcos_timecards DROP CONSTRAINT pcos_timecards_pkey;
ALTER TABLE ONLY public.pcos_tax_credit_rules DROP CONSTRAINT pcos_tax_credit_rules_pkey;
ALTER TABLE ONLY public.pcos_tax_credit_applications DROP CONSTRAINT pcos_tax_credit_applications_pkey;
ALTER TABLE ONLY public.pcos_tasks DROP CONSTRAINT pcos_tasks_pkey;
ALTER TABLE ONLY public.pcos_task_events DROP CONSTRAINT pcos_task_events_pkey;
ALTER TABLE ONLY public.pcos_safety_policies DROP CONSTRAINT pcos_safety_policies_pkey;
ALTER TABLE ONLY public.pcos_rule_evaluations DROP CONSTRAINT pcos_rule_evaluations_pkey;
ALTER TABLE ONLY public.pcos_qualified_spend_categories DROP CONSTRAINT pcos_qualified_spend_categories_pkey;
ALTER TABLE ONLY public.pcos_projects DROP CONSTRAINT pcos_projects_pkey;
ALTER TABLE ONLY public.pcos_person_visa_status DROP CONSTRAINT pcos_person_visa_status_pkey;
ALTER TABLE ONLY public.pcos_permit_packets DROP CONSTRAINT pcos_permit_packets_pkey;
ALTER TABLE ONLY public.pcos_people DROP CONSTRAINT pcos_people_pkey;
ALTER TABLE ONLY public.pcos_payroll_exports DROP CONSTRAINT pcos_payroll_exports_pkey;
ALTER TABLE ONLY public.pcos_locations DROP CONSTRAINT pcos_locations_pkey;
ALTER TABLE ONLY public.pcos_insurance_policies DROP CONSTRAINT pcos_insurance_policies_pkey;
ALTER TABLE ONLY public.pcos_generated_forms DROP CONSTRAINT pcos_generated_forms_pkey;
ALTER TABLE ONLY public.pcos_gate_evaluations DROP CONSTRAINT pcos_gate_evaluations_pkey;
ALTER TABLE ONLY public.pcos_form_templates DROP CONSTRAINT pcos_form_templates_template_code_key;
ALTER TABLE ONLY public.pcos_form_templates DROP CONSTRAINT pcos_form_templates_pkey;
ALTER TABLE ONLY public.pcos_fact_citations DROP CONSTRAINT pcos_fact_citations_pkey;
ALTER TABLE ONLY public.pcos_extracted_facts DROP CONSTRAINT pcos_extracted_facts_pkey;
ALTER TABLE ONLY public.pcos_evidence DROP CONSTRAINT pcos_evidence_pkey;
ALTER TABLE ONLY public.pcos_engagements DROP CONSTRAINT pcos_engagements_pkey;
ALTER TABLE ONLY public.pcos_engagement_documents DROP CONSTRAINT pcos_engagement_documents_pkey;
ALTER TABLE ONLY public.pcos_document_requirements DROP CONSTRAINT pcos_document_requirements_requirement_code_key;
ALTER TABLE ONLY public.pcos_document_requirements DROP CONSTRAINT pcos_document_requirements_pkey;
ALTER TABLE ONLY public.pcos_contract_templates DROP CONSTRAINT pcos_contract_templates_pkey;
ALTER TABLE ONLY public.pcos_compliance_snapshots DROP CONSTRAINT pcos_compliance_snapshots_pkey;
ALTER TABLE ONLY public.pcos_company_registrations DROP CONSTRAINT pcos_company_registrations_pkey;
ALTER TABLE ONLY public.pcos_companies DROP CONSTRAINT pcos_companies_pkey;
ALTER TABLE ONLY public.pcos_classification_exemptions DROP CONSTRAINT pcos_classification_exemptions_pkey;
ALTER TABLE ONLY public.pcos_classification_exemptions DROP CONSTRAINT pcos_classification_exemptions_exemption_code_key;
ALTER TABLE ONLY public.pcos_classification_analyses DROP CONSTRAINT pcos_classification_analyses_pkey;
ALTER TABLE ONLY public.pcos_budgets DROP CONSTRAINT pcos_budgets_pkey;
ALTER TABLE ONLY public.pcos_budget_line_items DROP CONSTRAINT pcos_budget_line_items_pkey;
ALTER TABLE ONLY public.pcos_authority_documents DROP CONSTRAINT pcos_authority_documents_pkey;
ALTER TABLE ONLY public.pcos_audit_events DROP CONSTRAINT pcos_audit_events_pkey;
ALTER TABLE ONLY public.pcos_analysis_runs DROP CONSTRAINT pcos_analysis_runs_pkey;
ALTER TABLE ONLY public.pcos_abc_questionnaire_responses DROP CONSTRAINT pcos_abc_questionnaire_responses_pkey;
DROP TABLE public.pcos_visa_categories;
DROP TABLE public.pcos_union_rate_checks;
DROP TABLE public.pcos_timecards;
DROP TABLE public.pcos_tax_credit_rules;
DROP TABLE public.pcos_tax_credit_applications;
DROP TABLE public.pcos_tasks;
DROP TABLE public.pcos_task_events;
DROP TABLE public.pcos_safety_policies;
DROP TABLE public.pcos_rule_evaluations;
DROP TABLE public.pcos_qualified_spend_categories;
DROP TABLE public.pcos_projects;
DROP TABLE public.pcos_person_visa_status;
DROP TABLE public.pcos_permit_packets;
DROP TABLE public.pcos_people;
DROP TABLE public.pcos_payroll_exports;
DROP TABLE public.pcos_locations;
DROP TABLE public.pcos_insurance_policies;
DROP TABLE public.pcos_generated_forms;
DROP TABLE public.pcos_gate_evaluations;
DROP TABLE public.pcos_form_templates;
DROP TABLE public.pcos_fact_citations;
DROP TABLE public.pcos_extracted_facts;
DROP TABLE public.pcos_evidence;
DROP TABLE public.pcos_engagements;
DROP TABLE public.pcos_engagement_documents;
DROP TABLE public.pcos_document_requirements;
DROP TABLE public.pcos_contract_templates;
DROP TABLE public.pcos_compliance_snapshots;
DROP TABLE public.pcos_company_registrations;
DROP TABLE public.pcos_companies;
DROP TABLE public.pcos_classification_exemptions;
DROP TABLE public.pcos_classification_analyses;
DROP TABLE public.pcos_budgets;
DROP TABLE public.pcos_budget_line_items;
DROP TABLE public.pcos_authority_documents;
DROP TABLE public.pcos_audit_events;
DROP TABLE public.pcos_analysis_runs;
DROP TABLE public.pcos_abc_questionnaire_responses;
SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: pcos_abc_questionnaire_responses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_abc_questionnaire_responses (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    analysis_id uuid NOT NULL,
    question_code character varying(50) NOT NULL,
    question_text text NOT NULL,
    question_category character varying(50) NOT NULL,
    response_value character varying(50),
    response_details text,
    response_weight integer,
    supports_contractor boolean,
    impact_score integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_analysis_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_analysis_runs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    run_type character varying(50) NOT NULL,
    run_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    project_id uuid,
    entity_type character varying(50),
    entity_id uuid,
    run_parameters jsonb DEFAULT '{}'::jsonb NOT NULL,
    rule_pack_version character varying(50),
    fact_snapshot_time timestamp with time zone DEFAULT now() NOT NULL,
    total_evaluations integer DEFAULT 0,
    pass_count integer DEFAULT 0,
    fail_count integer DEFAULT 0,
    warning_count integer DEFAULT 0,
    indeterminate_count integer DEFAULT 0,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    execution_time_ms integer,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_audit_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid,
    event_type character varying(100) NOT NULL,
    event_action character varying(100) NOT NULL,
    actor_id uuid,
    actor_email character varying(255),
    actor_role character varying(100),
    entity_type character varying(50),
    entity_id uuid,
    event_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    previous_state jsonb,
    new_state jsonb,
    ip_address character varying(45),
    user_agent text,
    request_id character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_authority_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_authority_documents (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    document_code character varying(100) NOT NULL,
    document_name character varying(255) NOT NULL,
    document_type character varying(50) NOT NULL,
    issuer_name character varying(255) NOT NULL,
    issuer_type character varying(50),
    effective_date date NOT NULL,
    expiration_date date,
    supersedes_document_id uuid,
    document_hash character varying(64),
    hash_algorithm character varying(20) DEFAULT 'SHA-256'::character varying,
    original_file_path text,
    content_type character varying(100),
    file_size_bytes bigint,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    ingested_by uuid,
    extraction_method character varying(50),
    extraction_notes text,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    verified_at timestamp with time zone,
    verified_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_budget_line_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_budget_line_items (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    budget_id uuid NOT NULL,
    row_number integer NOT NULL,
    cost_code character varying(20),
    department character varying(100),
    description text NOT NULL,
    rate numeric(12,2),
    quantity numeric(10,2),
    extension numeric(15,2) NOT NULL,
    classification character varying(20),
    role_category character varying(50),
    is_union_covered boolean,
    detected_union character varying(20),
    deal_memo_status character varying(20),
    compliance_flags character varying[],
    raw_row_data jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_budgets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_budgets (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    source_file_name character varying(255) NOT NULL,
    source_file_hash character varying(64),
    source_file_s3_key text,
    parsed_at timestamp with time zone DEFAULT now() NOT NULL,
    parser_version character varying(20),
    sheet_name character varying(100),
    grand_total numeric(15,2) NOT NULL,
    subtotal numeric(15,2) NOT NULL,
    contingency_amount numeric(15,2),
    contingency_percent numeric(5,2),
    detected_location character varying(10),
    status character varying(20) NOT NULL,
    is_active boolean NOT NULL,
    compliance_issue_count integer,
    critical_issue_count integer,
    risk_score integer,
    metadata jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    created_by uuid
);


--
-- Name: pcos_classification_analyses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_classification_analyses (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    engagement_id uuid NOT NULL,
    analyzed_at timestamp with time zone DEFAULT now() NOT NULL,
    analyzed_by uuid,
    rule_version character varying(20) NOT NULL,
    prong_a_passed boolean,
    prong_a_score integer,
    prong_a_factors jsonb,
    prong_a_reasoning text,
    prong_b_passed boolean,
    prong_b_score integer,
    prong_b_factors jsonb,
    prong_b_reasoning text,
    prong_b_questionnaire_completed boolean,
    prong_c_passed boolean,
    prong_c_score integer,
    prong_c_factors jsonb,
    prong_c_reasoning text,
    overall_result character varying(30) NOT NULL,
    overall_score integer NOT NULL,
    confidence_level character varying(20) NOT NULL,
    risk_level character varying(20) NOT NULL,
    risk_factors jsonb,
    recommended_action character varying(100),
    exemption_applicable boolean,
    exemption_type character varying(100),
    exemption_reasoning text,
    supporting_evidence jsonb,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_classification_exemptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_classification_exemptions (
    id uuid NOT NULL,
    exemption_code character varying(50) NOT NULL,
    exemption_name character varying(255) NOT NULL,
    exemption_category character varying(100) NOT NULL,
    qualifying_criteria jsonb NOT NULL,
    description text,
    legal_reference character varying(255),
    effective_date date,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_companies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    legal_name character varying(255) NOT NULL,
    entity_type public.pcos_entity_type NOT NULL,
    ein character varying(20),
    sos_entity_number character varying(50),
    legal_address_line1 character varying(255),
    legal_address_line2 character varying(255),
    legal_address_city character varying(100),
    legal_address_state character varying(2) DEFAULT 'CA'::character varying,
    legal_address_zip character varying(10),
    mailing_address_line1 character varying(255),
    mailing_address_line2 character varying(255),
    mailing_address_city character varying(100),
    mailing_address_state character varying(2),
    mailing_address_zip character varying(10),
    has_la_city_presence boolean DEFAULT false NOT NULL,
    la_business_address_line1 character varying(255),
    la_business_address_city character varying(100),
    la_business_address_zip character varying(10),
    owner_pay_mode public.pcos_owner_pay_mode,
    owner_pay_cpa_approved boolean DEFAULT false NOT NULL,
    owner_pay_cpa_approved_date date,
    payroll_provider_config jsonb DEFAULT '{}'::jsonb,
    status character varying(50) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_by uuid,
    updated_by uuid,
    CONSTRAINT pcos_companies_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'suspended'::character varying, 'archived'::character varying])::text[])))
);


--
-- Name: pcos_company_registrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_company_registrations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    registration_type public.pcos_registration_type NOT NULL,
    registration_number character varying(100),
    registration_name character varying(255),
    jurisdiction character varying(100),
    issue_date date,
    expiration_date date,
    renewal_date date,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    evidence_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_company_registrations_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'active'::character varying, 'expired'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: pcos_compliance_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_compliance_snapshots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    snapshot_type character varying(50) NOT NULL,
    snapshot_name character varying(255),
    triggered_by uuid,
    trigger_reason text,
    total_rules_evaluated integer DEFAULT 0 NOT NULL,
    rules_passed integer DEFAULT 0 NOT NULL,
    rules_failed integer DEFAULT 0 NOT NULL,
    rules_warning integer DEFAULT 0 NOT NULL,
    overall_score integer,
    compliance_status character varying(50) DEFAULT 'unknown'::character varying NOT NULL,
    category_scores jsonb DEFAULT '{}'::jsonb,
    previous_snapshot_id uuid,
    delta_summary jsonb,
    project_state jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_attested boolean DEFAULT false,
    attested_at timestamp with time zone,
    attested_by uuid,
    attestation_signature_id character varying(255),
    attestation_notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_contract_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_contract_templates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid,
    template_code character varying(100) NOT NULL,
    template_name character varying(255) NOT NULL,
    description text,
    template_version character varying(20) DEFAULT '1.0'::character varying NOT NULL,
    template_body text,
    template_s3_key text,
    required_fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    is_system boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: pcos_document_requirements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_document_requirements (
    id uuid NOT NULL,
    requirement_code character varying(50) NOT NULL,
    requirement_name character varying(255) NOT NULL,
    document_type character varying(100) NOT NULL,
    applies_to_classification character varying(20),
    applies_to_union_status character varying(50),
    applies_to_minor boolean,
    applies_to_visa_holder boolean,
    description text,
    legal_reference character varying(255),
    deadline_days_before_start integer,
    deadline_type character varying(50),
    form_number character varying(50),
    issuing_authority character varying(100),
    template_id uuid,
    is_required boolean NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_engagement_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_engagement_documents (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    engagement_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    status character varying(50) NOT NULL,
    requested_at timestamp with time zone,
    received_at timestamp with time zone,
    verified_at timestamp with time zone,
    verified_by uuid,
    expires_at date,
    evidence_id uuid,
    file_name character varying(255),
    notes text,
    waiver_reason text,
    reminder_sent_at timestamp with time zone,
    reminder_count integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_engagements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_engagements (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    person_id uuid NOT NULL,
    role_title character varying(255) NOT NULL,
    department character varying(100),
    classification public.pcos_classification_type NOT NULL,
    pay_rate numeric(10,2) NOT NULL,
    pay_type character varying(50) NOT NULL,
    overtime_eligible boolean DEFAULT true NOT NULL,
    start_date date,
    end_date date,
    guaranteed_days integer,
    classification_memo_signed boolean DEFAULT false NOT NULL,
    classification_memo_date date,
    w9_received boolean DEFAULT false,
    i9_received boolean DEFAULT false,
    w4_received boolean DEFAULT false,
    deal_memo_signed boolean DEFAULT false,
    status character varying(50) DEFAULT 'active'::character varying NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_engagements_pay_type_check CHECK (((pay_type)::text = ANY ((ARRAY['hourly'::character varying, 'daily'::character varying, 'weekly'::character varying, 'flat'::character varying, 'kit_rental'::character varying])::text[]))),
    CONSTRAINT pcos_engagements_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'active'::character varying, 'completed'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: pcos_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_evidence (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id uuid NOT NULL,
    evidence_type public.pcos_evidence_type NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    file_name character varying(255),
    file_size_bytes bigint,
    mime_type character varying(100),
    s3_key text NOT NULL,
    sha256_hash character varying(64),
    valid_from date,
    valid_until date,
    is_signed boolean DEFAULT false,
    signed_at timestamp with time zone,
    signer_name character varying(255),
    esign_envelope_id character varying(255),
    uploaded_by uuid,
    tags text[],
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: pcos_extracted_facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_extracted_facts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    authority_document_id uuid NOT NULL,
    fact_key character varying(100) NOT NULL,
    fact_category character varying(50) NOT NULL,
    fact_name character varying(255) NOT NULL,
    fact_description text,
    fact_value_type character varying(20) NOT NULL,
    fact_value_decimal numeric(15,4),
    fact_value_integer integer,
    fact_value_string text,
    fact_value_boolean boolean,
    fact_value_date date,
    fact_value_json jsonb,
    fact_unit character varying(50),
    validity_conditions jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    previous_fact_id uuid,
    is_current boolean DEFAULT true NOT NULL,
    source_page integer,
    source_section character varying(255),
    source_quote text,
    extraction_confidence numeric(3,2),
    extraction_method character varying(50),
    extraction_notes text,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL,
    extracted_by uuid,
    verified_at timestamp with time zone,
    verified_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_fact_citations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_fact_citations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    citing_entity_type character varying(50) NOT NULL,
    citing_entity_id uuid NOT NULL,
    extracted_fact_id uuid NOT NULL,
    fact_value_used text NOT NULL,
    context_applied jsonb,
    citation_type character varying(50) NOT NULL,
    citation_notes text,
    evaluation_result character varying(20),
    comparison_operator character varying(20),
    input_value text,
    cited_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_form_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_form_templates (
    id uuid NOT NULL,
    template_code character varying(100) NOT NULL,
    template_name character varying(255) NOT NULL,
    template_version character varying(20) NOT NULL,
    form_authority character varying(100),
    form_url character varying(500),
    form_type character varying(50) NOT NULL,
    jurisdiction character varying(20),
    field_mappings jsonb NOT NULL,
    pdf_template_path character varying(500),
    pdf_template_hash character varying(64),
    description text,
    instructions text,
    estimated_fill_time_minutes integer,
    is_active boolean NOT NULL,
    requires_signature boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by uuid
);


--
-- Name: pcos_gate_evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_gate_evaluations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    evaluated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    evaluated_by uuid,
    trigger_type character varying(50),
    current_state public.pcos_gate_state NOT NULL,
    target_state public.pcos_gate_state,
    transition_allowed boolean NOT NULL,
    blocking_tasks_count integer DEFAULT 0 NOT NULL,
    blocking_task_ids uuid[],
    missing_evidence text[],
    risk_score integer DEFAULT 0 NOT NULL,
    reasons text[],
    snapshot jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_gate_evaluations_risk_score_check CHECK (((risk_score >= 0) AND (risk_score <= 100)))
);


--
-- Name: pcos_generated_forms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_generated_forms (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    template_id uuid NOT NULL,
    location_id uuid,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    generated_by uuid,
    source_data_snapshot jsonb NOT NULL,
    pdf_storage_path character varying(500),
    pdf_file_hash character varying(64),
    pdf_file_size_bytes integer,
    status character varying(50) NOT NULL,
    submitted_at timestamp with time zone,
    approved_at timestamp with time zone,
    rejection_reason text,
    external_reference character varying(100),
    requires_signature boolean NOT NULL,
    signature_status character varying(50),
    signed_at timestamp with time zone,
    signed_by uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_insurance_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_insurance_policies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    policy_type public.pcos_insurance_type NOT NULL,
    carrier_name character varying(255),
    policy_number character varying(100),
    coverage_amount numeric(15,2),
    deductible_amount numeric(15,2),
    effective_date date,
    expiration_date date NOT NULL,
    is_required boolean DEFAULT false NOT NULL,
    status character varying(50) DEFAULT 'active'::character varying NOT NULL,
    evidence_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_insurance_policies_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'expired'::character varying, 'cancelled'::character varying, 'pending'::character varying])::text[])))
);


--
-- Name: pcos_locations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_locations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(2) DEFAULT 'CA'::character varying,
    zip character varying(10),
    jurisdiction public.pcos_jurisdiction NOT NULL,
    location_type public.pcos_location_type NOT NULL,
    estimated_crew_size integer,
    parking_spaces_needed integer,
    filming_hours_start time without time zone,
    filming_hours_end time without time zone,
    has_generator boolean DEFAULT false,
    has_special_effects boolean DEFAULT false,
    noise_level character varying(50),
    permit_required boolean,
    permit_packet_id uuid,
    shoot_dates date[],
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_locations_noise_level_check CHECK (((noise_level)::text = ANY ((ARRAY['low'::character varying, 'moderate'::character varying, 'high'::character varying])::text[])))
);


--
-- Name: pcos_payroll_exports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_payroll_exports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid,
    export_date timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    exported_by uuid,
    timecard_ids uuid[] NOT NULL,
    total_regular_hours numeric(10,2),
    total_overtime_hours numeric(10,2),
    total_gross_pay numeric(15,2),
    export_format character varying(50) DEFAULT 'csv'::character varying,
    file_path text,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    confirmation_evidence_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_payroll_exports_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'exported'::character varying, 'imported_confirmation'::character varying])::text[])))
);


--
-- Name: pcos_people; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_people (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    first_name character varying(100) NOT NULL,
    last_name character varying(100) NOT NULL,
    email character varying(255),
    phone character varying(50),
    ssn_last_four character varying(4),
    date_of_birth date,
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(2),
    zip character varying(10),
    preferred_classification public.pcos_classification_type,
    is_loan_out boolean DEFAULT false,
    loan_out_company_name character varying(255),
    loan_out_ein character varying(20),
    emergency_contact_name character varying(255),
    emergency_contact_phone character varying(50),
    emergency_contact_relation character varying(100),
    notes text,
    status character varying(50) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_people_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'inactive'::character varying])::text[])))
);


--
-- Name: pcos_permit_packets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_permit_packets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    location_id uuid,
    permit_authority character varying(100) DEFAULT 'filmla'::character varying NOT NULL,
    application_number character varying(100),
    submitted_at timestamp with time zone,
    approved_at timestamp with time zone,
    denied_at timestamp with time zone,
    denial_reason text,
    permit_number character varying(100),
    permit_valid_from date,
    permit_valid_to date,
    status character varying(50) DEFAULT 'not_started'::character varying NOT NULL,
    coi_evidence_id uuid,
    permit_evidence_id uuid,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_permit_packets_status_check CHECK (((status)::text = ANY ((ARRAY['not_started'::character varying, 'in_progress'::character varying, 'submitted'::character varying, 'approved'::character varying, 'denied'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: pcos_person_visa_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_person_visa_status (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    person_id uuid NOT NULL,
    visa_category_id uuid,
    visa_code character varying(20),
    status character varying(50) DEFAULT 'active'::character varying NOT NULL,
    issue_date date,
    expiration_date date,
    last_entry_date date,
    i94_number character varying(20),
    i94_expiration date,
    ead_expiration date,
    is_work_authorized boolean DEFAULT true,
    employer_restricted boolean DEFAULT false,
    restricted_to_employer character varying(255),
    evidence_id uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_visa_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'expired'::character varying, 'pending'::character varying, 'revoked'::character varying])::text[])))
);


--
-- Name: pcos_projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(50),
    project_type public.pcos_project_type NOT NULL,
    is_commercial boolean DEFAULT false NOT NULL,
    client_name character varying(255),
    start_date date,
    end_date date,
    first_shoot_date date,
    union_status character varying(50) DEFAULT 'non_union'::character varying,
    minor_involved boolean DEFAULT false NOT NULL,
    gate_state public.pcos_gate_state DEFAULT 'draft'::public.pcos_gate_state NOT NULL,
    gate_state_changed_at timestamp with time zone,
    gate_state_changed_by uuid,
    risk_score integer DEFAULT 0,
    blocking_tasks_count integer DEFAULT 0,
    notes text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_by uuid,
    updated_by uuid,
    CONSTRAINT pcos_projects_risk_score_check CHECK (((risk_score >= 0) AND (risk_score <= 100))),
    CONSTRAINT pcos_projects_union_status_check CHECK (((union_status)::text = ANY ((ARRAY['non_union'::character varying, 'sag_aftra'::character varying, 'iatse'::character varying, 'teamsters'::character varying, 'multi_union'::character varying])::text[])))
);


--
-- Name: pcos_qualified_spend_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_qualified_spend_categories (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    application_id uuid NOT NULL,
    category_code character varying(100) NOT NULL,
    category_name character varying(255) NOT NULL,
    budget_department character varying(100),
    total_spend numeric(15,2) NOT NULL,
    qualified_spend numeric(15,2) NOT NULL,
    non_qualified_spend numeric(15,2) NOT NULL,
    qualification_status character varying(50) NOT NULL,
    qualification_reason text,
    applicable_rules jsonb,
    exclusion_reason character varying(255),
    line_item_count integer,
    line_item_ids uuid[],
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_rule_evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_rule_evaluations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id uuid NOT NULL,
    rule_code character varying(100) NOT NULL,
    rule_name character varying(255) NOT NULL,
    rule_category character varying(100) NOT NULL,
    rule_version character varying(20) DEFAULT '1.0'::character varying NOT NULL,
    result character varying(30) NOT NULL,
    score integer,
    severity character varying(20) DEFAULT 'medium'::character varying,
    evaluation_input jsonb DEFAULT '{}'::jsonb NOT NULL,
    evaluation_output jsonb DEFAULT '{}'::jsonb NOT NULL,
    message text,
    source_authorities jsonb DEFAULT '[]'::jsonb NOT NULL,
    task_id uuid,
    finding_id uuid,
    evaluated_at timestamp with time zone DEFAULT now() NOT NULL,
    evaluated_by uuid,
    snapshot_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    analysis_run_id uuid
);


--
-- Name: pcos_safety_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_safety_policies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    policy_type character varying(50) NOT NULL,
    policy_name character varying(255),
    effective_date date,
    last_review_date date,
    next_review_date date,
    is_uploaded boolean DEFAULT false NOT NULL,
    evidence_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_safety_policies_policy_type_check CHECK (((policy_type)::text = ANY ((ARRAY['iipp'::character varying, 'wvpp'::character varying, 'heat_illness'::character varying, 'covid'::character varying, 'other'::character varying])::text[])))
);


--
-- Name: pcos_task_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_task_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    task_id uuid NOT NULL,
    event_type character varying(50) NOT NULL,
    previous_value jsonb,
    new_value jsonb,
    actor_id uuid,
    actor_type character varying(50) DEFAULT 'user'::character varying,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: pcos_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    source_type character varying(50) NOT NULL,
    source_id uuid NOT NULL,
    task_template_id character varying(100),
    task_type character varying(100) NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    assigned_to uuid,
    assigned_role character varying(100),
    due_date date,
    reminder_sent_7d boolean DEFAULT false,
    reminder_sent_3d boolean DEFAULT false,
    reminder_sent_1d boolean DEFAULT false,
    status public.pcos_task_status DEFAULT 'pending'::public.pcos_task_status NOT NULL,
    is_blocking boolean DEFAULT false NOT NULL,
    completed_at timestamp with time zone,
    completed_by uuid,
    requires_evidence boolean DEFAULT false,
    required_evidence_types public.pcos_evidence_type[],
    evidence_ids uuid[],
    rule_id character varying(100),
    rule_pack character varying(100) DEFAULT 'production_ca_la'::character varying,
    notes text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: pcos_tax_credit_applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_tax_credit_applications (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    budget_id uuid,
    program_code character varying(50) NOT NULL,
    program_name character varying(255) NOT NULL,
    program_year integer NOT NULL,
    eligibility_status character varying(50) NOT NULL,
    eligibility_score numeric(5,2),
    min_spend_threshold numeric(15,2),
    actual_qualified_spend numeric(15,2),
    qualified_spend_pct numeric(5,2),
    base_credit_rate numeric(5,2),
    uplift_rate numeric(5,2),
    total_credit_rate numeric(5,2),
    estimated_credit_amount numeric(15,2),
    requirements_met jsonb,
    requirements_notes text,
    rule_pack_version character varying(50),
    evaluated_at timestamp with time zone,
    evaluation_details jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by uuid
);


--
-- Name: pcos_tax_credit_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_tax_credit_rules (
    id uuid NOT NULL,
    program_code character varying(50) NOT NULL,
    program_year integer NOT NULL,
    rule_version character varying(20) NOT NULL,
    rule_code character varying(100) NOT NULL,
    rule_name character varying(255) NOT NULL,
    rule_category character varying(100) NOT NULL,
    rule_definition jsonb NOT NULL,
    description text,
    authority_reference character varying(255),
    effective_date date,
    sunset_date date,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_timecards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_timecards (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    engagement_id uuid NOT NULL,
    work_date date NOT NULL,
    call_time time without time zone,
    wrap_time time without time zone,
    meal_1_out time without time zone,
    meal_1_in time without time zone,
    meal_2_out time without time zone,
    meal_2_in time without time zone,
    regular_hours numeric(5,2),
    overtime_hours numeric(5,2),
    double_time_hours numeric(5,2),
    meal_penalty_count integer DEFAULT 0,
    jurisdiction public.pcos_jurisdiction,
    wage_floor_met boolean,
    wage_floor_rate numeric(10,2),
    submitted_at timestamp with time zone,
    submitted_by uuid,
    approved_at timestamp with time zone,
    approved_by uuid,
    rejected_at timestamp with time zone,
    rejected_by uuid,
    rejection_reason text,
    status character varying(50) DEFAULT 'draft'::character varying NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pcos_timecards_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'submitted'::character varying, 'approved'::character varying, 'rejected'::character varying, 'exported'::character varying])::text[])))
);


--
-- Name: pcos_union_rate_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_union_rate_checks (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    line_item_id uuid,
    engagement_id uuid,
    union_code character varying(20) NOT NULL,
    role_category character varying(50) NOT NULL,
    minimum_rate numeric(10,2) NOT NULL,
    actual_rate numeric(10,2) NOT NULL,
    is_compliant boolean NOT NULL,
    shortfall_amount numeric(10,2),
    fringe_percent_required numeric(5,2),
    fringe_amount_required numeric(10,2),
    rate_table_version character varying(20) NOT NULL,
    rate_table_effective_date date,
    checked_at timestamp with time zone DEFAULT now() NOT NULL,
    notes text
);


--
-- Name: pcos_visa_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pcos_visa_categories (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    visa_code character varying(20) NOT NULL,
    visa_name character varying(255) NOT NULL,
    visa_category character varying(50) NOT NULL,
    work_authorized boolean DEFAULT true NOT NULL,
    employer_specific boolean DEFAULT false NOT NULL,
    duration_months integer,
    renewable boolean DEFAULT true,
    standard_processing_days integer,
    premium_processing_days integer,
    premium_processing_available boolean DEFAULT false,
    requires_petition boolean DEFAULT true,
    requires_labor_certification boolean DEFAULT false,
    common_in_entertainment boolean DEFAULT false,
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pcos_abc_questionnaire_responses pcos_abc_questionnaire_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_abc_questionnaire_responses
    ADD CONSTRAINT pcos_abc_questionnaire_responses_pkey PRIMARY KEY (id);


--
-- Name: pcos_analysis_runs pcos_analysis_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_analysis_runs
    ADD CONSTRAINT pcos_analysis_runs_pkey PRIMARY KEY (id);


--
-- Name: pcos_audit_events pcos_audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_audit_events
    ADD CONSTRAINT pcos_audit_events_pkey PRIMARY KEY (id);


--
-- Name: pcos_authority_documents pcos_authority_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_authority_documents
    ADD CONSTRAINT pcos_authority_documents_pkey PRIMARY KEY (id);


--
-- Name: pcos_budget_line_items pcos_budget_line_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_budget_line_items
    ADD CONSTRAINT pcos_budget_line_items_pkey PRIMARY KEY (id);


--
-- Name: pcos_budgets pcos_budgets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_budgets
    ADD CONSTRAINT pcos_budgets_pkey PRIMARY KEY (id);


--
-- Name: pcos_classification_analyses pcos_classification_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_classification_analyses
    ADD CONSTRAINT pcos_classification_analyses_pkey PRIMARY KEY (id);


--
-- Name: pcos_classification_exemptions pcos_classification_exemptions_exemption_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_classification_exemptions
    ADD CONSTRAINT pcos_classification_exemptions_exemption_code_key UNIQUE (exemption_code);


--
-- Name: pcos_classification_exemptions pcos_classification_exemptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_classification_exemptions
    ADD CONSTRAINT pcos_classification_exemptions_pkey PRIMARY KEY (id);


--
-- Name: pcos_companies pcos_companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_companies
    ADD CONSTRAINT pcos_companies_pkey PRIMARY KEY (id);


--
-- Name: pcos_company_registrations pcos_company_registrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_company_registrations
    ADD CONSTRAINT pcos_company_registrations_pkey PRIMARY KEY (id);


--
-- Name: pcos_compliance_snapshots pcos_compliance_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_compliance_snapshots
    ADD CONSTRAINT pcos_compliance_snapshots_pkey PRIMARY KEY (id);


--
-- Name: pcos_contract_templates pcos_contract_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_contract_templates
    ADD CONSTRAINT pcos_contract_templates_pkey PRIMARY KEY (id);


--
-- Name: pcos_document_requirements pcos_document_requirements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_document_requirements
    ADD CONSTRAINT pcos_document_requirements_pkey PRIMARY KEY (id);


--
-- Name: pcos_document_requirements pcos_document_requirements_requirement_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_document_requirements
    ADD CONSTRAINT pcos_document_requirements_requirement_code_key UNIQUE (requirement_code);


--
-- Name: pcos_engagement_documents pcos_engagement_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagement_documents
    ADD CONSTRAINT pcos_engagement_documents_pkey PRIMARY KEY (id);


--
-- Name: pcos_engagements pcos_engagements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagements
    ADD CONSTRAINT pcos_engagements_pkey PRIMARY KEY (id);


--
-- Name: pcos_evidence pcos_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_evidence
    ADD CONSTRAINT pcos_evidence_pkey PRIMARY KEY (id);


--
-- Name: pcos_extracted_facts pcos_extracted_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_extracted_facts
    ADD CONSTRAINT pcos_extracted_facts_pkey PRIMARY KEY (id);


--
-- Name: pcos_fact_citations pcos_fact_citations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_fact_citations
    ADD CONSTRAINT pcos_fact_citations_pkey PRIMARY KEY (id);


--
-- Name: pcos_form_templates pcos_form_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_form_templates
    ADD CONSTRAINT pcos_form_templates_pkey PRIMARY KEY (id);


--
-- Name: pcos_form_templates pcos_form_templates_template_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_form_templates
    ADD CONSTRAINT pcos_form_templates_template_code_key UNIQUE (template_code);


--
-- Name: pcos_gate_evaluations pcos_gate_evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_gate_evaluations
    ADD CONSTRAINT pcos_gate_evaluations_pkey PRIMARY KEY (id);


--
-- Name: pcos_generated_forms pcos_generated_forms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_generated_forms
    ADD CONSTRAINT pcos_generated_forms_pkey PRIMARY KEY (id);


--
-- Name: pcos_insurance_policies pcos_insurance_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_insurance_policies
    ADD CONSTRAINT pcos_insurance_policies_pkey PRIMARY KEY (id);


--
-- Name: pcos_locations pcos_locations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_locations
    ADD CONSTRAINT pcos_locations_pkey PRIMARY KEY (id);


--
-- Name: pcos_payroll_exports pcos_payroll_exports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_payroll_exports
    ADD CONSTRAINT pcos_payroll_exports_pkey PRIMARY KEY (id);


--
-- Name: pcos_people pcos_people_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_people
    ADD CONSTRAINT pcos_people_pkey PRIMARY KEY (id);


--
-- Name: pcos_permit_packets pcos_permit_packets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_permit_packets
    ADD CONSTRAINT pcos_permit_packets_pkey PRIMARY KEY (id);


--
-- Name: pcos_person_visa_status pcos_person_visa_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_person_visa_status
    ADD CONSTRAINT pcos_person_visa_status_pkey PRIMARY KEY (id);


--
-- Name: pcos_projects pcos_projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_projects
    ADD CONSTRAINT pcos_projects_pkey PRIMARY KEY (id);


--
-- Name: pcos_qualified_spend_categories pcos_qualified_spend_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_qualified_spend_categories
    ADD CONSTRAINT pcos_qualified_spend_categories_pkey PRIMARY KEY (id);


--
-- Name: pcos_rule_evaluations pcos_rule_evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_rule_evaluations
    ADD CONSTRAINT pcos_rule_evaluations_pkey PRIMARY KEY (id);


--
-- Name: pcos_safety_policies pcos_safety_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_safety_policies
    ADD CONSTRAINT pcos_safety_policies_pkey PRIMARY KEY (id);


--
-- Name: pcos_task_events pcos_task_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_task_events
    ADD CONSTRAINT pcos_task_events_pkey PRIMARY KEY (id);


--
-- Name: pcos_tasks pcos_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tasks
    ADD CONSTRAINT pcos_tasks_pkey PRIMARY KEY (id);


--
-- Name: pcos_tax_credit_applications pcos_tax_credit_applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tax_credit_applications
    ADD CONSTRAINT pcos_tax_credit_applications_pkey PRIMARY KEY (id);


--
-- Name: pcos_tax_credit_rules pcos_tax_credit_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tax_credit_rules
    ADD CONSTRAINT pcos_tax_credit_rules_pkey PRIMARY KEY (id);


--
-- Name: pcos_timecards pcos_timecards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_timecards
    ADD CONSTRAINT pcos_timecards_pkey PRIMARY KEY (id);


--
-- Name: pcos_union_rate_checks pcos_union_rate_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_union_rate_checks
    ADD CONSTRAINT pcos_union_rate_checks_pkey PRIMARY KEY (id);


--
-- Name: pcos_visa_categories pcos_visa_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_visa_categories
    ADD CONSTRAINT pcos_visa_categories_pkey PRIMARY KEY (id);


--
-- Name: pcos_visa_categories pcos_visa_categories_visa_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_visa_categories
    ADD CONSTRAINT pcos_visa_categories_visa_code_key UNIQUE (visa_code);


--
-- Name: pcos_authority_documents uq_authority_doc_code_tenant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_authority_documents
    ADD CONSTRAINT uq_authority_doc_code_tenant UNIQUE (tenant_id, document_code);


--
-- Name: pcos_engagement_documents uq_engagement_doc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagement_documents
    ADD CONSTRAINT uq_engagement_doc UNIQUE (engagement_id, requirement_id);


--
-- Name: pcos_extracted_facts uq_fact_key_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_extracted_facts
    ADD CONSTRAINT uq_fact_key_version UNIQUE (tenant_id, fact_key, version);


--
-- Name: pcos_tax_credit_rules uq_tax_rule_program_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tax_credit_rules
    ADD CONSTRAINT uq_tax_rule_program_code UNIQUE (program_code, program_year, rule_code);


--
-- Name: idx_analysis_runs_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_runs_created ON public.pcos_analysis_runs USING btree (created_at);


--
-- Name: idx_analysis_runs_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_runs_project ON public.pcos_analysis_runs USING btree (project_id);


--
-- Name: idx_analysis_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_runs_status ON public.pcos_analysis_runs USING btree (run_status);


--
-- Name: idx_analysis_runs_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_runs_tenant ON public.pcos_analysis_runs USING btree (tenant_id);


--
-- Name: idx_audit_events_actor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_events_actor ON public.pcos_audit_events USING btree (actor_id);


--
-- Name: idx_audit_events_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_events_project ON public.pcos_audit_events USING btree (project_id);


--
-- Name: idx_audit_events_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_events_tenant ON public.pcos_audit_events USING btree (tenant_id);


--
-- Name: idx_audit_events_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_events_time ON public.pcos_audit_events USING btree (created_at);


--
-- Name: idx_audit_events_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_events_type ON public.pcos_audit_events USING btree (event_type);


--
-- Name: idx_authority_docs_effective; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_authority_docs_effective ON public.pcos_authority_documents USING btree (effective_date);


--
-- Name: idx_authority_docs_issuer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_authority_docs_issuer ON public.pcos_authority_documents USING btree (issuer_name);


--
-- Name: idx_authority_docs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_authority_docs_status ON public.pcos_authority_documents USING btree (status);


--
-- Name: idx_authority_docs_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_authority_docs_tenant ON public.pcos_authority_documents USING btree (tenant_id);


--
-- Name: idx_authority_docs_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_authority_docs_type ON public.pcos_authority_documents USING btree (document_type);


--
-- Name: idx_classification_engagement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_classification_engagement ON public.pcos_classification_analyses USING btree (engagement_id);


--
-- Name: idx_classification_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_classification_result ON public.pcos_classification_analyses USING btree (overall_result);


--
-- Name: idx_classification_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_classification_tenant ON public.pcos_classification_analyses USING btree (tenant_id);


--
-- Name: idx_doc_requirements_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doc_requirements_type ON public.pcos_document_requirements USING btree (document_type);


--
-- Name: idx_engagement_docs_engagement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_engagement_docs_engagement ON public.pcos_engagement_documents USING btree (engagement_id);


--
-- Name: idx_engagement_docs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_engagement_docs_status ON public.pcos_engagement_documents USING btree (status);


--
-- Name: idx_engagement_docs_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_engagement_docs_tenant ON public.pcos_engagement_documents USING btree (tenant_id);


--
-- Name: idx_exemptions_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_exemptions_category ON public.pcos_classification_exemptions USING btree (exemption_category);


--
-- Name: idx_exemptions_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_exemptions_code ON public.pcos_classification_exemptions USING btree (exemption_code);


--
-- Name: idx_extracted_facts_authority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_facts_authority ON public.pcos_extracted_facts USING btree (authority_document_id);


--
-- Name: idx_extracted_facts_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_facts_category ON public.pcos_extracted_facts USING btree (fact_category);


--
-- Name: idx_extracted_facts_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_facts_current ON public.pcos_extracted_facts USING btree (tenant_id, fact_key, is_current) WHERE (is_current = true);


--
-- Name: idx_extracted_facts_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_facts_key ON public.pcos_extracted_facts USING btree (fact_key);


--
-- Name: idx_extracted_facts_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extracted_facts_tenant ON public.pcos_extracted_facts USING btree (tenant_id);


--
-- Name: idx_fact_citations_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fact_citations_entity ON public.pcos_fact_citations USING btree (citing_entity_type, citing_entity_id);


--
-- Name: idx_fact_citations_fact; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fact_citations_fact ON public.pcos_fact_citations USING btree (extracted_fact_id);


--
-- Name: idx_fact_citations_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fact_citations_tenant ON public.pcos_fact_citations USING btree (tenant_id);


--
-- Name: idx_form_templates_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form_templates_code ON public.pcos_form_templates USING btree (template_code);


--
-- Name: idx_form_templates_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form_templates_type ON public.pcos_form_templates USING btree (form_type);


--
-- Name: idx_generated_forms_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generated_forms_project ON public.pcos_generated_forms USING btree (project_id);


--
-- Name: idx_generated_forms_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generated_forms_status ON public.pcos_generated_forms USING btree (status);


--
-- Name: idx_generated_forms_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generated_forms_tenant ON public.pcos_generated_forms USING btree (tenant_id);


--
-- Name: idx_pcos_budget_items_budget; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_budget_items_budget ON public.pcos_budget_line_items USING btree (budget_id);


--
-- Name: idx_pcos_budget_items_dept; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_budget_items_dept ON public.pcos_budget_line_items USING btree (department);


--
-- Name: idx_pcos_budget_items_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_budget_items_tenant ON public.pcos_budget_line_items USING btree (tenant_id);


--
-- Name: idx_pcos_budgets_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_budgets_project ON public.pcos_budgets USING btree (project_id);


--
-- Name: idx_pcos_budgets_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_budgets_tenant ON public.pcos_budgets USING btree (tenant_id);


--
-- Name: idx_pcos_companies_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_companies_status ON public.pcos_companies USING btree (status);


--
-- Name: idx_pcos_companies_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_companies_tenant ON public.pcos_companies USING btree (tenant_id);


--
-- Name: idx_pcos_engagements_classification; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_engagements_classification ON public.pcos_engagements USING btree (classification);


--
-- Name: idx_pcos_engagements_person; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_engagements_person ON public.pcos_engagements USING btree (person_id);


--
-- Name: idx_pcos_engagements_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_engagements_project ON public.pcos_engagements USING btree (project_id);


--
-- Name: idx_pcos_engagements_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_engagements_tenant ON public.pcos_engagements USING btree (tenant_id);


--
-- Name: idx_pcos_evidence_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_evidence_entity ON public.pcos_evidence USING btree (entity_type, entity_id);


--
-- Name: idx_pcos_evidence_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_evidence_tenant ON public.pcos_evidence USING btree (tenant_id);


--
-- Name: idx_pcos_evidence_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_evidence_type ON public.pcos_evidence USING btree (evidence_type);


--
-- Name: idx_pcos_evidence_validity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_evidence_validity ON public.pcos_evidence USING btree (valid_until);


--
-- Name: idx_pcos_exports_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_exports_project ON public.pcos_payroll_exports USING btree (project_id);


--
-- Name: idx_pcos_exports_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_exports_tenant ON public.pcos_payroll_exports USING btree (tenant_id);


--
-- Name: idx_pcos_gate_evals_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_gate_evals_date ON public.pcos_gate_evaluations USING btree (evaluated_at);


--
-- Name: idx_pcos_gate_evals_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_gate_evals_project ON public.pcos_gate_evaluations USING btree (project_id);


--
-- Name: idx_pcos_gate_evals_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_gate_evals_tenant ON public.pcos_gate_evaluations USING btree (tenant_id);


--
-- Name: idx_pcos_insurance_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_insurance_company ON public.pcos_insurance_policies USING btree (company_id);


--
-- Name: idx_pcos_insurance_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_insurance_expiry ON public.pcos_insurance_policies USING btree (expiration_date);


--
-- Name: idx_pcos_insurance_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_insurance_tenant ON public.pcos_insurance_policies USING btree (tenant_id);


--
-- Name: idx_pcos_locations_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_locations_project ON public.pcos_locations USING btree (project_id);


--
-- Name: idx_pcos_locations_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_locations_tenant ON public.pcos_locations USING btree (tenant_id);


--
-- Name: idx_pcos_locations_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_locations_type ON public.pcos_locations USING btree (location_type);


--
-- Name: idx_pcos_people_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_people_email ON public.pcos_people USING btree (email);


--
-- Name: idx_pcos_people_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_people_name ON public.pcos_people USING btree (last_name, first_name);


--
-- Name: idx_pcos_people_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_people_tenant ON public.pcos_people USING btree (tenant_id);


--
-- Name: idx_pcos_permits_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_permits_project ON public.pcos_permit_packets USING btree (project_id);


--
-- Name: idx_pcos_permits_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_permits_status ON public.pcos_permit_packets USING btree (status);


--
-- Name: idx_pcos_permits_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_permits_tenant ON public.pcos_permit_packets USING btree (tenant_id);


--
-- Name: idx_pcos_projects_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_projects_company ON public.pcos_projects USING btree (company_id);


--
-- Name: idx_pcos_projects_dates; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_projects_dates ON public.pcos_projects USING btree (first_shoot_date, start_date);


--
-- Name: idx_pcos_projects_gate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_projects_gate ON public.pcos_projects USING btree (gate_state);


--
-- Name: idx_pcos_projects_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_projects_tenant ON public.pcos_projects USING btree (tenant_id);


--
-- Name: idx_pcos_rate_checks_engagement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_rate_checks_engagement ON public.pcos_union_rate_checks USING btree (engagement_id);


--
-- Name: idx_pcos_rate_checks_line_item; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_rate_checks_line_item ON public.pcos_union_rate_checks USING btree (line_item_id);


--
-- Name: idx_pcos_rate_checks_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_rate_checks_tenant ON public.pcos_union_rate_checks USING btree (tenant_id);


--
-- Name: idx_pcos_registrations_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_registrations_company ON public.pcos_company_registrations USING btree (company_id);


--
-- Name: idx_pcos_registrations_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_registrations_expiry ON public.pcos_company_registrations USING btree (expiration_date);


--
-- Name: idx_pcos_registrations_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_registrations_tenant ON public.pcos_company_registrations USING btree (tenant_id);


--
-- Name: idx_pcos_safety_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_safety_company ON public.pcos_safety_policies USING btree (company_id);


--
-- Name: idx_pcos_safety_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_safety_tenant ON public.pcos_safety_policies USING btree (tenant_id);


--
-- Name: idx_pcos_task_events_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_task_events_created ON public.pcos_task_events USING btree (created_at);


--
-- Name: idx_pcos_task_events_task; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_task_events_task ON public.pcos_task_events USING btree (task_id);


--
-- Name: idx_pcos_task_events_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_task_events_tenant ON public.pcos_task_events USING btree (tenant_id);


--
-- Name: idx_pcos_tasks_blocking; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_tasks_blocking ON public.pcos_tasks USING btree (is_blocking) WHERE (is_blocking = true);


--
-- Name: idx_pcos_tasks_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_tasks_due ON public.pcos_tasks USING btree (due_date);


--
-- Name: idx_pcos_tasks_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_tasks_source ON public.pcos_tasks USING btree (source_type, source_id);


--
-- Name: idx_pcos_tasks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_tasks_status ON public.pcos_tasks USING btree (status);


--
-- Name: idx_pcos_tasks_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_tasks_tenant ON public.pcos_tasks USING btree (tenant_id);


--
-- Name: idx_pcos_templates_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_templates_code ON public.pcos_contract_templates USING btree (template_code);


--
-- Name: idx_pcos_templates_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_templates_tenant ON public.pcos_contract_templates USING btree (tenant_id);


--
-- Name: idx_pcos_templates_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_pcos_templates_unique ON public.pcos_contract_templates USING btree (tenant_id, template_code, template_version);


--
-- Name: idx_pcos_timecards_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_timecards_date ON public.pcos_timecards USING btree (work_date);


--
-- Name: idx_pcos_timecards_engagement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_timecards_engagement ON public.pcos_timecards USING btree (engagement_id);


--
-- Name: idx_pcos_timecards_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_timecards_status ON public.pcos_timecards USING btree (status);


--
-- Name: idx_pcos_timecards_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pcos_timecards_tenant ON public.pcos_timecards USING btree (tenant_id);


--
-- Name: idx_person_visa_expiration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_person_visa_expiration ON public.pcos_person_visa_status USING btree (expiration_date);


--
-- Name: idx_person_visa_person; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_person_visa_person ON public.pcos_person_visa_status USING btree (person_id);


--
-- Name: idx_person_visa_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_person_visa_tenant ON public.pcos_person_visa_status USING btree (tenant_id);


--
-- Name: idx_qualified_spend_app; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qualified_spend_app ON public.pcos_qualified_spend_categories USING btree (application_id);


--
-- Name: idx_qualified_spend_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qualified_spend_tenant ON public.pcos_qualified_spend_categories USING btree (tenant_id);


--
-- Name: idx_questionnaire_analysis; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_questionnaire_analysis ON public.pcos_abc_questionnaire_responses USING btree (analysis_id);


--
-- Name: idx_questionnaire_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_questionnaire_tenant ON public.pcos_abc_questionnaire_responses USING btree (tenant_id);


--
-- Name: idx_rule_evals_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_evals_entity ON public.pcos_rule_evaluations USING btree (entity_type, entity_id);


--
-- Name: idx_rule_evals_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_evals_project ON public.pcos_rule_evaluations USING btree (project_id);


--
-- Name: idx_rule_evals_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_evals_result ON public.pcos_rule_evaluations USING btree (result);


--
-- Name: idx_rule_evals_rule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_evals_rule ON public.pcos_rule_evaluations USING btree (rule_code);


--
-- Name: idx_rule_evals_snapshot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_evals_snapshot ON public.pcos_rule_evaluations USING btree (snapshot_id);


--
-- Name: idx_rule_evals_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_evals_tenant ON public.pcos_rule_evaluations USING btree (tenant_id);


--
-- Name: idx_rule_evals_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_evals_time ON public.pcos_rule_evaluations USING btree (evaluated_at);


--
-- Name: idx_rule_evaluations_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_evaluations_run ON public.pcos_rule_evaluations USING btree (analysis_run_id);


--
-- Name: idx_snapshots_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_snapshots_created ON public.pcos_compliance_snapshots USING btree (created_at);


--
-- Name: idx_snapshots_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_snapshots_project ON public.pcos_compliance_snapshots USING btree (project_id);


--
-- Name: idx_snapshots_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_snapshots_tenant ON public.pcos_compliance_snapshots USING btree (tenant_id);


--
-- Name: idx_snapshots_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_snapshots_type ON public.pcos_compliance_snapshots USING btree (snapshot_type);


--
-- Name: idx_tax_credit_apps_program; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tax_credit_apps_program ON public.pcos_tax_credit_applications USING btree (program_code, program_year);


--
-- Name: idx_tax_credit_apps_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tax_credit_apps_project ON public.pcos_tax_credit_applications USING btree (project_id);


--
-- Name: idx_tax_credit_apps_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tax_credit_apps_tenant ON public.pcos_tax_credit_applications USING btree (tenant_id);


--
-- Name: idx_tax_rules_program; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tax_rules_program ON public.pcos_tax_credit_rules USING btree (program_code, program_year);


--
-- Name: idx_visa_categories_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_visa_categories_code ON public.pcos_visa_categories USING btree (visa_code);


--
-- Name: pcos_analysis_runs trg_analysis_runs_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_analysis_runs_immutable BEFORE UPDATE ON public.pcos_analysis_runs FOR EACH ROW EXECUTE FUNCTION public.prevent_analysis_run_mutation();


--
-- Name: pcos_audit_events trg_audit_events_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_audit_events_immutable BEFORE DELETE OR UPDATE ON public.pcos_audit_events FOR EACH ROW EXECUTE FUNCTION public.prevent_mutation();


--
-- Name: pcos_authority_documents trg_authority_documents_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_authority_documents_updated BEFORE UPDATE ON public.pcos_authority_documents FOR EACH ROW EXECUTE FUNCTION public.update_authority_lineage_timestamp();


--
-- Name: pcos_compliance_snapshots trg_compliance_snapshots_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_compliance_snapshots_immutable BEFORE DELETE OR UPDATE ON public.pcos_compliance_snapshots FOR EACH ROW EXECUTE FUNCTION public.prevent_mutation();


--
-- Name: pcos_extracted_facts trg_extracted_facts_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_extracted_facts_immutable BEFORE DELETE OR UPDATE ON public.pcos_extracted_facts FOR EACH ROW EXECUTE FUNCTION public.prevent_mutation();


--
-- Name: pcos_extracted_facts trg_extracted_facts_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_extracted_facts_updated BEFORE UPDATE ON public.pcos_extracted_facts FOR EACH ROW EXECUTE FUNCTION public.update_authority_lineage_timestamp();


--
-- Name: pcos_fact_citations trg_fact_citations_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_fact_citations_immutable BEFORE DELETE OR UPDATE ON public.pcos_fact_citations FOR EACH ROW EXECUTE FUNCTION public.prevent_mutation();


--
-- Name: pcos_person_visa_status trg_person_visa_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_person_visa_updated BEFORE UPDATE ON public.pcos_person_visa_status FOR EACH ROW EXECUTE FUNCTION public.update_paperwork_updated_at();


--
-- Name: pcos_rule_evaluations trg_rule_evaluations_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_rule_evaluations_immutable BEFORE DELETE OR UPDATE ON public.pcos_rule_evaluations FOR EACH ROW EXECUTE FUNCTION public.prevent_mutation();


--
-- Name: pcos_compliance_snapshots trg_snapshots_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_snapshots_updated BEFORE UPDATE ON public.pcos_compliance_snapshots FOR EACH ROW EXECUTE FUNCTION public.update_snapshot_updated_at();


--
-- Name: pcos_abc_questionnaire_responses pcos_abc_questionnaire_responses_analysis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_abc_questionnaire_responses
    ADD CONSTRAINT pcos_abc_questionnaire_responses_analysis_id_fkey FOREIGN KEY (analysis_id) REFERENCES public.pcos_classification_analyses(id) ON DELETE CASCADE;


--
-- Name: pcos_abc_questionnaire_responses pcos_abc_questionnaire_responses_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_abc_questionnaire_responses
    ADD CONSTRAINT pcos_abc_questionnaire_responses_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_analysis_runs pcos_analysis_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_analysis_runs
    ADD CONSTRAINT pcos_analysis_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id);


--
-- Name: pcos_analysis_runs pcos_analysis_runs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_analysis_runs
    ADD CONSTRAINT pcos_analysis_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_audit_events pcos_audit_events_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_audit_events
    ADD CONSTRAINT pcos_audit_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: pcos_audit_events pcos_audit_events_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_audit_events
    ADD CONSTRAINT pcos_audit_events_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_audit_events pcos_audit_events_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_audit_events
    ADD CONSTRAINT pcos_audit_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_authority_documents pcos_authority_documents_supersedes_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_authority_documents
    ADD CONSTRAINT pcos_authority_documents_supersedes_document_id_fkey FOREIGN KEY (supersedes_document_id) REFERENCES public.pcos_authority_documents(id);


--
-- Name: pcos_authority_documents pcos_authority_documents_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_authority_documents
    ADD CONSTRAINT pcos_authority_documents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_budget_line_items pcos_budget_line_items_budget_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_budget_line_items
    ADD CONSTRAINT pcos_budget_line_items_budget_id_fkey FOREIGN KEY (budget_id) REFERENCES public.pcos_budgets(id) ON DELETE CASCADE;


--
-- Name: pcos_budget_line_items pcos_budget_line_items_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_budget_line_items
    ADD CONSTRAINT pcos_budget_line_items_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_budgets pcos_budgets_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_budgets
    ADD CONSTRAINT pcos_budgets_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: pcos_budgets pcos_budgets_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_budgets
    ADD CONSTRAINT pcos_budgets_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_budgets pcos_budgets_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_budgets
    ADD CONSTRAINT pcos_budgets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_classification_analyses pcos_classification_analyses_analyzed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_classification_analyses
    ADD CONSTRAINT pcos_classification_analyses_analyzed_by_fkey FOREIGN KEY (analyzed_by) REFERENCES public.users(id);


--
-- Name: pcos_classification_analyses pcos_classification_analyses_engagement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_classification_analyses
    ADD CONSTRAINT pcos_classification_analyses_engagement_id_fkey FOREIGN KEY (engagement_id) REFERENCES public.pcos_engagements(id) ON DELETE CASCADE;


--
-- Name: pcos_classification_analyses pcos_classification_analyses_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_classification_analyses
    ADD CONSTRAINT pcos_classification_analyses_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_companies pcos_companies_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_companies
    ADD CONSTRAINT pcos_companies_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: pcos_companies pcos_companies_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_companies
    ADD CONSTRAINT pcos_companies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_companies pcos_companies_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_companies
    ADD CONSTRAINT pcos_companies_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: pcos_company_registrations pcos_company_registrations_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_company_registrations
    ADD CONSTRAINT pcos_company_registrations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.pcos_companies(id) ON DELETE CASCADE;


--
-- Name: pcos_company_registrations pcos_company_registrations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_company_registrations
    ADD CONSTRAINT pcos_company_registrations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_compliance_snapshots pcos_compliance_snapshots_attested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_compliance_snapshots
    ADD CONSTRAINT pcos_compliance_snapshots_attested_by_fkey FOREIGN KEY (attested_by) REFERENCES public.users(id);


--
-- Name: pcos_compliance_snapshots pcos_compliance_snapshots_previous_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_compliance_snapshots
    ADD CONSTRAINT pcos_compliance_snapshots_previous_snapshot_id_fkey FOREIGN KEY (previous_snapshot_id) REFERENCES public.pcos_compliance_snapshots(id);


--
-- Name: pcos_compliance_snapshots pcos_compliance_snapshots_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_compliance_snapshots
    ADD CONSTRAINT pcos_compliance_snapshots_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_compliance_snapshots pcos_compliance_snapshots_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_compliance_snapshots
    ADD CONSTRAINT pcos_compliance_snapshots_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_compliance_snapshots pcos_compliance_snapshots_triggered_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_compliance_snapshots
    ADD CONSTRAINT pcos_compliance_snapshots_triggered_by_fkey FOREIGN KEY (triggered_by) REFERENCES public.users(id);


--
-- Name: pcos_contract_templates pcos_contract_templates_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_contract_templates
    ADD CONSTRAINT pcos_contract_templates_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_document_requirements pcos_document_requirements_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_document_requirements
    ADD CONSTRAINT pcos_document_requirements_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.pcos_form_templates(id);


--
-- Name: pcos_engagement_documents pcos_engagement_documents_engagement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagement_documents
    ADD CONSTRAINT pcos_engagement_documents_engagement_id_fkey FOREIGN KEY (engagement_id) REFERENCES public.pcos_engagements(id) ON DELETE CASCADE;


--
-- Name: pcos_engagement_documents pcos_engagement_documents_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagement_documents
    ADD CONSTRAINT pcos_engagement_documents_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.pcos_evidence(id);


--
-- Name: pcos_engagement_documents pcos_engagement_documents_requirement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagement_documents
    ADD CONSTRAINT pcos_engagement_documents_requirement_id_fkey FOREIGN KEY (requirement_id) REFERENCES public.pcos_document_requirements(id);


--
-- Name: pcos_engagement_documents pcos_engagement_documents_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagement_documents
    ADD CONSTRAINT pcos_engagement_documents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_engagement_documents pcos_engagement_documents_verified_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagement_documents
    ADD CONSTRAINT pcos_engagement_documents_verified_by_fkey FOREIGN KEY (verified_by) REFERENCES public.users(id);


--
-- Name: pcos_engagements pcos_engagements_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagements
    ADD CONSTRAINT pcos_engagements_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.pcos_people(id) ON DELETE CASCADE;


--
-- Name: pcos_engagements pcos_engagements_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagements
    ADD CONSTRAINT pcos_engagements_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_engagements pcos_engagements_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_engagements
    ADD CONSTRAINT pcos_engagements_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_evidence pcos_evidence_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_evidence
    ADD CONSTRAINT pcos_evidence_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_evidence pcos_evidence_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_evidence
    ADD CONSTRAINT pcos_evidence_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id);


--
-- Name: pcos_extracted_facts pcos_extracted_facts_authority_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_extracted_facts
    ADD CONSTRAINT pcos_extracted_facts_authority_document_id_fkey FOREIGN KEY (authority_document_id) REFERENCES public.pcos_authority_documents(id) ON DELETE CASCADE;


--
-- Name: pcos_extracted_facts pcos_extracted_facts_previous_fact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_extracted_facts
    ADD CONSTRAINT pcos_extracted_facts_previous_fact_id_fkey FOREIGN KEY (previous_fact_id) REFERENCES public.pcos_extracted_facts(id);


--
-- Name: pcos_extracted_facts pcos_extracted_facts_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_extracted_facts
    ADD CONSTRAINT pcos_extracted_facts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_fact_citations pcos_fact_citations_extracted_fact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_fact_citations
    ADD CONSTRAINT pcos_fact_citations_extracted_fact_id_fkey FOREIGN KEY (extracted_fact_id) REFERENCES public.pcos_extracted_facts(id) ON DELETE CASCADE;


--
-- Name: pcos_fact_citations pcos_fact_citations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_fact_citations
    ADD CONSTRAINT pcos_fact_citations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_form_templates pcos_form_templates_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_form_templates
    ADD CONSTRAINT pcos_form_templates_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: pcos_gate_evaluations pcos_gate_evaluations_evaluated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_gate_evaluations
    ADD CONSTRAINT pcos_gate_evaluations_evaluated_by_fkey FOREIGN KEY (evaluated_by) REFERENCES public.users(id);


--
-- Name: pcos_gate_evaluations pcos_gate_evaluations_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_gate_evaluations
    ADD CONSTRAINT pcos_gate_evaluations_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_gate_evaluations pcos_gate_evaluations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_gate_evaluations
    ADD CONSTRAINT pcos_gate_evaluations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_generated_forms pcos_generated_forms_generated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_generated_forms
    ADD CONSTRAINT pcos_generated_forms_generated_by_fkey FOREIGN KEY (generated_by) REFERENCES public.users(id);


--
-- Name: pcos_generated_forms pcos_generated_forms_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_generated_forms
    ADD CONSTRAINT pcos_generated_forms_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.pcos_locations(id) ON DELETE SET NULL;


--
-- Name: pcos_generated_forms pcos_generated_forms_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_generated_forms
    ADD CONSTRAINT pcos_generated_forms_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_generated_forms pcos_generated_forms_signed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_generated_forms
    ADD CONSTRAINT pcos_generated_forms_signed_by_fkey FOREIGN KEY (signed_by) REFERENCES public.users(id);


--
-- Name: pcos_generated_forms pcos_generated_forms_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_generated_forms
    ADD CONSTRAINT pcos_generated_forms_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.pcos_form_templates(id);


--
-- Name: pcos_generated_forms pcos_generated_forms_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_generated_forms
    ADD CONSTRAINT pcos_generated_forms_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_insurance_policies pcos_insurance_policies_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_insurance_policies
    ADD CONSTRAINT pcos_insurance_policies_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.pcos_companies(id) ON DELETE CASCADE;


--
-- Name: pcos_insurance_policies pcos_insurance_policies_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_insurance_policies
    ADD CONSTRAINT pcos_insurance_policies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_locations pcos_locations_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_locations
    ADD CONSTRAINT pcos_locations_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_locations pcos_locations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_locations
    ADD CONSTRAINT pcos_locations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_payroll_exports pcos_payroll_exports_exported_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_payroll_exports
    ADD CONSTRAINT pcos_payroll_exports_exported_by_fkey FOREIGN KEY (exported_by) REFERENCES public.users(id);


--
-- Name: pcos_payroll_exports pcos_payroll_exports_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_payroll_exports
    ADD CONSTRAINT pcos_payroll_exports_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE SET NULL;


--
-- Name: pcos_payroll_exports pcos_payroll_exports_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_payroll_exports
    ADD CONSTRAINT pcos_payroll_exports_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_people pcos_people_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_people
    ADD CONSTRAINT pcos_people_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_permit_packets pcos_permit_packets_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_permit_packets
    ADD CONSTRAINT pcos_permit_packets_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.pcos_locations(id) ON DELETE SET NULL;


--
-- Name: pcos_permit_packets pcos_permit_packets_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_permit_packets
    ADD CONSTRAINT pcos_permit_packets_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_permit_packets pcos_permit_packets_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_permit_packets
    ADD CONSTRAINT pcos_permit_packets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_person_visa_status pcos_person_visa_status_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_person_visa_status
    ADD CONSTRAINT pcos_person_visa_status_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.pcos_evidence(id);


--
-- Name: pcos_person_visa_status pcos_person_visa_status_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_person_visa_status
    ADD CONSTRAINT pcos_person_visa_status_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.pcos_people(id) ON DELETE CASCADE;


--
-- Name: pcos_person_visa_status pcos_person_visa_status_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_person_visa_status
    ADD CONSTRAINT pcos_person_visa_status_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_person_visa_status pcos_person_visa_status_visa_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_person_visa_status
    ADD CONSTRAINT pcos_person_visa_status_visa_category_id_fkey FOREIGN KEY (visa_category_id) REFERENCES public.pcos_visa_categories(id);


--
-- Name: pcos_projects pcos_projects_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_projects
    ADD CONSTRAINT pcos_projects_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.pcos_companies(id) ON DELETE CASCADE;


--
-- Name: pcos_projects pcos_projects_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_projects
    ADD CONSTRAINT pcos_projects_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: pcos_projects pcos_projects_gate_state_changed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_projects
    ADD CONSTRAINT pcos_projects_gate_state_changed_by_fkey FOREIGN KEY (gate_state_changed_by) REFERENCES public.users(id);


--
-- Name: pcos_projects pcos_projects_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_projects
    ADD CONSTRAINT pcos_projects_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_projects pcos_projects_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_projects
    ADD CONSTRAINT pcos_projects_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: pcos_qualified_spend_categories pcos_qualified_spend_categories_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_qualified_spend_categories
    ADD CONSTRAINT pcos_qualified_spend_categories_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.pcos_tax_credit_applications(id) ON DELETE CASCADE;


--
-- Name: pcos_qualified_spend_categories pcos_qualified_spend_categories_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_qualified_spend_categories
    ADD CONSTRAINT pcos_qualified_spend_categories_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_rule_evaluations pcos_rule_evaluations_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_rule_evaluations
    ADD CONSTRAINT pcos_rule_evaluations_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.pcos_analysis_runs(id);


--
-- Name: pcos_rule_evaluations pcos_rule_evaluations_evaluated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_rule_evaluations
    ADD CONSTRAINT pcos_rule_evaluations_evaluated_by_fkey FOREIGN KEY (evaluated_by) REFERENCES public.users(id);


--
-- Name: pcos_rule_evaluations pcos_rule_evaluations_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_rule_evaluations
    ADD CONSTRAINT pcos_rule_evaluations_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_rule_evaluations pcos_rule_evaluations_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_rule_evaluations
    ADD CONSTRAINT pcos_rule_evaluations_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.pcos_tasks(id) ON DELETE SET NULL;


--
-- Name: pcos_rule_evaluations pcos_rule_evaluations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_rule_evaluations
    ADD CONSTRAINT pcos_rule_evaluations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_safety_policies pcos_safety_policies_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_safety_policies
    ADD CONSTRAINT pcos_safety_policies_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.pcos_companies(id) ON DELETE CASCADE;


--
-- Name: pcos_safety_policies pcos_safety_policies_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_safety_policies
    ADD CONSTRAINT pcos_safety_policies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_task_events pcos_task_events_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_task_events
    ADD CONSTRAINT pcos_task_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: pcos_task_events pcos_task_events_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_task_events
    ADD CONSTRAINT pcos_task_events_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.pcos_tasks(id) ON DELETE CASCADE;


--
-- Name: pcos_task_events pcos_task_events_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_task_events
    ADD CONSTRAINT pcos_task_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_tasks pcos_tasks_assigned_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tasks
    ADD CONSTRAINT pcos_tasks_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES public.users(id);


--
-- Name: pcos_tasks pcos_tasks_completed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tasks
    ADD CONSTRAINT pcos_tasks_completed_by_fkey FOREIGN KEY (completed_by) REFERENCES public.users(id);


--
-- Name: pcos_tasks pcos_tasks_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tasks
    ADD CONSTRAINT pcos_tasks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_tax_credit_applications pcos_tax_credit_applications_budget_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tax_credit_applications
    ADD CONSTRAINT pcos_tax_credit_applications_budget_id_fkey FOREIGN KEY (budget_id) REFERENCES public.pcos_budgets(id) ON DELETE SET NULL;


--
-- Name: pcos_tax_credit_applications pcos_tax_credit_applications_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tax_credit_applications
    ADD CONSTRAINT pcos_tax_credit_applications_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: pcos_tax_credit_applications pcos_tax_credit_applications_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tax_credit_applications
    ADD CONSTRAINT pcos_tax_credit_applications_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.pcos_projects(id) ON DELETE CASCADE;


--
-- Name: pcos_tax_credit_applications pcos_tax_credit_applications_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_tax_credit_applications
    ADD CONSTRAINT pcos_tax_credit_applications_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_timecards pcos_timecards_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_timecards
    ADD CONSTRAINT pcos_timecards_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: pcos_timecards pcos_timecards_engagement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_timecards
    ADD CONSTRAINT pcos_timecards_engagement_id_fkey FOREIGN KEY (engagement_id) REFERENCES public.pcos_engagements(id) ON DELETE CASCADE;


--
-- Name: pcos_timecards pcos_timecards_rejected_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_timecards
    ADD CONSTRAINT pcos_timecards_rejected_by_fkey FOREIGN KEY (rejected_by) REFERENCES public.users(id);


--
-- Name: pcos_timecards pcos_timecards_submitted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_timecards
    ADD CONSTRAINT pcos_timecards_submitted_by_fkey FOREIGN KEY (submitted_by) REFERENCES public.users(id);


--
-- Name: pcos_timecards pcos_timecards_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_timecards
    ADD CONSTRAINT pcos_timecards_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_union_rate_checks pcos_union_rate_checks_engagement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_union_rate_checks
    ADD CONSTRAINT pcos_union_rate_checks_engagement_id_fkey FOREIGN KEY (engagement_id) REFERENCES public.pcos_engagements(id) ON DELETE CASCADE;


--
-- Name: pcos_union_rate_checks pcos_union_rate_checks_line_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_union_rate_checks
    ADD CONSTRAINT pcos_union_rate_checks_line_item_id_fkey FOREIGN KEY (line_item_id) REFERENCES public.pcos_budget_line_items(id) ON DELETE CASCADE;


--
-- Name: pcos_union_rate_checks pcos_union_rate_checks_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pcos_union_rate_checks
    ADD CONSTRAINT pcos_union_rate_checks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pcos_audit_events audit_events_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY audit_events_insert ON public.pcos_audit_events FOR INSERT WITH CHECK ((tenant_id = COALESCE((current_setting('app.tenant_id'::text, true))::uuid, tenant_id)));


--
-- Name: pcos_audit_events audit_events_tenant; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY audit_events_tenant ON public.pcos_audit_events USING ((tenant_id = COALESCE((current_setting('app.tenant_id'::text, true))::uuid, tenant_id)));


--
-- Name: pcos_analysis_runs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_analysis_runs ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_analysis_runs pcos_analysis_runs_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pcos_analysis_runs_tenant_isolation ON public.pcos_analysis_runs USING ((tenant_id = (current_setting('app.current_tenant_id'::text))::uuid));


--
-- Name: pcos_audit_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_audit_events ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_authority_documents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_authority_documents ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_authority_documents pcos_authority_documents_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pcos_authority_documents_tenant_isolation ON public.pcos_authority_documents USING ((tenant_id = (current_setting('app.current_tenant_id'::text))::uuid));


--
-- Name: pcos_companies; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_companies ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_company_registrations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_company_registrations ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_compliance_snapshots; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_compliance_snapshots ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_contract_templates; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_contract_templates ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_engagements; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_engagements ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_evidence; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_evidence ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_extracted_facts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_extracted_facts ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_extracted_facts pcos_extracted_facts_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pcos_extracted_facts_tenant_isolation ON public.pcos_extracted_facts USING ((tenant_id = (current_setting('app.current_tenant_id'::text))::uuid));


--
-- Name: pcos_fact_citations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_fact_citations ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_fact_citations pcos_fact_citations_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pcos_fact_citations_tenant_isolation ON public.pcos_fact_citations USING ((tenant_id = (current_setting('app.current_tenant_id'::text))::uuid));


--
-- Name: pcos_gate_evaluations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_gate_evaluations ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_insurance_policies; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_insurance_policies ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_locations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_locations ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_payroll_exports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_payroll_exports ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_people; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_people ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_permit_packets; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_permit_packets ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_person_visa_status; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_person_visa_status ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_projects; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_projects ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_rule_evaluations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_rule_evaluations ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_safety_policies; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_safety_policies ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_task_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_task_events ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_tasks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_tasks ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_timecards; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pcos_timecards ENABLE ROW LEVEL SECURITY;

--
-- Name: pcos_person_visa_status person_visa_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY person_visa_insert ON public.pcos_person_visa_status FOR INSERT WITH CHECK ((tenant_id = COALESCE((current_setting('app.tenant_id'::text, true))::uuid, tenant_id)));


--
-- Name: pcos_person_visa_status person_visa_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY person_visa_tenant_isolation ON public.pcos_person_visa_status USING ((tenant_id = COALESCE((current_setting('app.tenant_id'::text, true))::uuid, tenant_id)));


--
-- Name: pcos_rule_evaluations rule_evals_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY rule_evals_insert ON public.pcos_rule_evaluations FOR INSERT WITH CHECK ((tenant_id = COALESCE((current_setting('app.tenant_id'::text, true))::uuid, tenant_id)));


--
-- Name: pcos_rule_evaluations rule_evals_tenant; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY rule_evals_tenant ON public.pcos_rule_evaluations USING ((tenant_id = COALESCE((current_setting('app.tenant_id'::text, true))::uuid, tenant_id)));


--
-- Name: pcos_compliance_snapshots snapshots_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY snapshots_insert ON public.pcos_compliance_snapshots FOR INSERT WITH CHECK ((tenant_id = COALESCE((current_setting('app.tenant_id'::text, true))::uuid, tenant_id)));


--
-- Name: pcos_compliance_snapshots snapshots_tenant; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY snapshots_tenant ON public.pcos_compliance_snapshots USING ((tenant_id = COALESCE((current_setting('app.tenant_id'::text, true))::uuid, tenant_id)));


--
-- Name: pcos_companies tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_companies USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_company_registrations tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_company_registrations USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_contract_templates tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_contract_templates USING (((tenant_id IS NULL) OR (tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid))));


--
-- Name: pcos_engagements tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_engagements USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_evidence tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_evidence USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_gate_evaluations tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_gate_evaluations USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_insurance_policies tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_insurance_policies USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_locations tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_locations USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_payroll_exports tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_payroll_exports USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_people tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_people USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_permit_packets tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_permit_packets USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_projects tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_projects USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_safety_policies tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_safety_policies USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_task_events tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_task_events USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_tasks tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_tasks USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- Name: pcos_timecards tenant_isolation_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_policy ON public.pcos_timecards USING ((tenant_id = COALESCE((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid, '00000000-0000-0000-0000-000000000001'::uuid)));


--
-- PostgreSQL database dump complete
--

\unrestrict L9HE842Uha7uZlCk7cdgUqcXARnmf9PjPX64AqcG8FsShjcJeB9OFB1aJS7VR41

