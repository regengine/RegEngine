-- Migration V27.5: Add tenant_id to PCOS tables in Admin DB
-- Priority: P0 - Required before V28
-- Date: 2026-01-31
--
-- This migration adds tenant_id columns to all PCOS tables in the Admin database.
-- These tables are in the 'public' schema on Supabase, not in vertical databases.

-- Add tenant_id to all PCOS tables
DO $$
DECLARE
  pcos_tables text[] := ARRAY[
    'pcos_companies',
    'pcos_people', 
    'pcos_projects',
    'pcos_engagements',
    'pcos_tasks',
    'pcos_timecards',
    'pcos_evidence',
    'pcos_authority_documents',
    'pcos_document_requirements',
    'pcos_engagement_documents',
    'pcos_company_registrations',
    'pcos_insurance_policies',
    'pcos_safety_policies',
    'pcos_locations',
    'pcos_permit_packets',
    'pcos_form_templates',
    'pcos_generated_forms',
    'pcos_budgets',
    'pcos_budget_line_items',
    'pcos_tax_credit_applications',
    'pcos_tax_credit_rules',
    'pcos_qualified_spend_categories',
    'pcos_classification_analyses',
    'pcos_abc_questionnaire_responses',
    'pcos_classification_exemptions',
    'pcos_visa_categories',
    'pcos_person_visa_status',
    'pcos_extracted_facts',
    'pcos_fact_citations',
    'pcos_analysis_runs',
    'pcos_compliance_snapshots',
    'pcos_audit_events',
    'pcos_task_events',
    'pcos_rule_evaluations',
    'pcos_gate_evaluations',
    'pcos_union_rate_checks',
    'vertical_projects',
    'vertical_rule_instances'
  ];
  tbl_name text;
BEGIN
  FOREACH tbl_name IN ARRAY pcos_tables
  LOOP
    -- Check if table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = tbl_name) THEN
      -- Check if tenant_id column already exists
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = tbl_name 
          AND column_name = 'tenant_id'
      ) THEN
        -- Add tenant_id column with default
        EXECUTE format('ALTER TABLE %I ADD COLUMN tenant_id UUID DEFAULT ''00000000-0000-0000-0000-000000000001''::UUID NOT NULL', tbl_name);
        
        -- Create index
        EXECUTE format('CREATE INDEX idx_%s_tenant_id ON %I(tenant_id)', tbl_name, tbl_name);
        
        RAISE NOTICE 'Added tenant_id to %', tbl_name;
      ELSE
        RAISE NOTICE 'Table % already has tenant_id column', tbl_name;
      END IF;
    ELSE
      RAISE NOTICE 'Table % does not exist, skipping', tbl_name;
    END IF;
  END LOOP;
  
  RAISE NOTICE 'V27.5 Complete: tenant_id added to all PCOS tables';
END $$;

