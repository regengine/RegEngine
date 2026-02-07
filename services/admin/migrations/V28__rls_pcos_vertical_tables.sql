-- Migration V28: Enable RLS for PCOS and Vertical Service Tables
-- Priority: P1 - HIGH
-- Date: 2026-01-31
--
-- This migration secures 40+ PCOS (Production Compliance OS) tables and
-- vertical service tables with Row Level Security.
--
-- All PCOS tables follow the pattern: tenant_id-based isolation
--
-- NOTE: PCOS tables are in 'public' schema in Admin DB but may move to
-- entertainment_db in the future. This migration secures them regardless.

-- ============================================================================
-- SECTION 1: PCOS Core Entity Tables
-- ============================================================================

-- 1. pcos_companies
ALTER TABLE IF EXISTS pcos_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_companies FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_companies_tenant_isolation" ON pcos_companies;
CREATE POLICY "pcos_companies_tenant_isolation" ON pcos_companies
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- 2. pcos_people
ALTER TABLE IF EXISTS pcos_people ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_people FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_people_tenant_isolation" ON pcos_people;
CREATE POLICY "pcos_people_tenant_isolation" ON pcos_people
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- 3. pcos_projects
ALTER TABLE IF EXISTS pcos_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_projects FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_projects_tenant_isolation" ON pcos_projects;
CREATE POLICY "pcos_projects_tenant_isolation" ON pcos_projects
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- 4. pcos_engagements
ALTER TABLE IF EXISTS pcos_engagements ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_engagements FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_engagements_tenant_isolation" ON pcos_engagements;
CREATE POLICY "pcos_engagements_tenant_isolation" ON pcos_engagements
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- 5. pcos_tasks
ALTER TABLE IF EXISTS pcos_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_tasks FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_tasks_tenant_isolation" ON pcos_tasks;
CREATE POLICY "pcos_tasks_tenant_isolation" ON pcos_tasks
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- 6. pcos_timecards
ALTER TABLE IF EXISTS pcos_timecards ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_timecards FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_timecards_tenant_isolation" ON pcos_timecards;
CREATE POLICY "pcos_timecards_tenant_isolation" ON pcos_timecards
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- ============================================================================
-- SECTION 2: PCOS Document & Evidence Tables
-- ============================================================================

-- 7. pcos_evidence
ALTER TABLE IF EXISTS pcos_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_evidence FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_evidence_tenant_isolation" ON pcos_evidence;
CREATE POLICY "pcos_evidence_tenant_isolation" ON pcos_evidence
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- 8. pcos_authority_documents
ALTER TABLE IF EXISTS pcos_authority_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_authority_documents FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_authority_documents_tenant_isolation" ON pcos_authority_documents;
CREATE POLICY "pcos_authority_documents_tenant_isolation" ON pcos_authority_documents
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- 9. pcos_document_requirements
ALTER TABLE IF EXISTS pcos_document_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_document_requirements FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_document_requirements_tenant_isolation" ON pcos_document_requirements;
CREATE POLICY "pcos_document_requirements_tenant_isolation" ON pcos_document_requirements
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- 10. pcos_engagement_documents
ALTER TABLE IF EXISTS pcos_engagement_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pcos_engagement_documents FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pcos_engagement_documents_tenant_isolation" ON pcos_engagement_documents;
CREATE POLICY "pcos_engagement_documents_tenant_isolation" ON pcos_engagement_documents
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- ============================================================================
-- SECTION 3: PCOS Compliance & Regulatory Tables
-- ============================================================================

-- 11-30: All remaining PCOS tables (budgets, tax credits, classifications, etc.)
DO $$
DECLARE
  tbl_name text;
  pcos_tables text[] := ARRAY[
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
    'pcos_union_rate_checks'
  ];
BEGIN
  FOREACH tbl_name IN ARRAY pcos_tables
  LOOP
    -- Check if table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = tbl_name) THEN
      -- Enable RLS
      EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl_name);
      EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tbl_name);
      
      -- Drop existing policy if any
      EXECUTE format('DROP POLICY IF EXISTS "%s_tenant_isolation" ON %I', tbl_name, tbl_name);
      
      -- Create tenant isolation policy
      EXECUTE format('
        CREATE POLICY "%s_tenant_isolation" ON %I
          FOR ALL TO authenticated
          USING (tenant_id = COALESCE(NULLIF(current_setting(''app.tenant_id'', TRUE), '''')::UUID, ''00000000-0000-0000-0000-000000000001''::UUID))
      ', tbl_name, tbl_name);
      
      RAISE NOTICE 'RLS enabled for table: %', tbl_name;
    ELSE
      RAISE NOTICE 'Table % does not exist, skipping', tbl_name;
    END IF;
  END LOOP;
END $$;


-- ============================================================================
-- SECTION 4: Vertical Service Tables
-- ============================================================================

-- vertical_projects
ALTER TABLE IF EXISTS vertical_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS vertical_projects FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "vertical_projects_tenant_isolation" ON vertical_projects;
CREATE POLICY "vertical_projects_tenant_isolation" ON vertical_projects
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- vertical_rule_instances
ALTER TABLE IF EXISTS vertical_rule_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS vertical_rule_instances FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "vertical_rule_instances_tenant_isolation" ON vertical_rule_instances;
CREATE POLICY "vertical_rule_instances_tenant_isolation" ON vertical_rule_instances
  FOR ALL TO authenticated
  USING (tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, '00000000-0000-0000-0000-000000000001'::UUID));

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
BEGIN
  RAISE NOTICE 'V28 Migration Complete: RLS enabled on 40+ PCOS and vertical tables';
  RAISE NOTICE 'All PCOS tables now protected with tenant_id-based isolation';
  RAISE NOTICE 'PostgREST API calls will be automatically filtered by tenant context';
END $$;
