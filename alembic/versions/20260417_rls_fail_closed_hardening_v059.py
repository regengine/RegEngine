"""RLS fail-closed hardening — remove fallback-UUID COALESCE, FORCE RLS on PCOS tables

Closes #1091. Rewrites every RLS policy that fell back to the hardcoded
sandbox UUID ``'00000000-0000-0000-0000-000000000001'`` (or to the row's own
``tenant_id``) when ``app.tenant_id`` was unset. Both variants were fail-open —
the first exposed a shared bucket to every context-less connection, the second
exposed every row.

Strategy: Option A — use ``get_tenant_context()`` (defined in v056) which
RAISES ``'app.tenant_id not set'`` when the GUC is unset/empty. Policies rewrite to
``USING (tenant_id = get_tenant_context())``. This fails loudly, not silently —
any code path that forgets ``SET LOCAL app.tenant_id`` surfaces as an error
instead of a cross-tenant read.

All affected tables are re-asserted with ``ALTER TABLE ... FORCE ROW LEVEL
SECURITY`` — without FORCE, the table owner bypasses policies, so the
defense-in-depth story is incomplete without it.

Also performs a pre-check: counts rows whose ``tenant_id`` equals the literal
sandbox UUID. Those are, by definition, rows that were written under a
context-less connection — either they were seeded intentionally (column
DEFAULT in V3 / V27_5) and need reassignment, or they leaked in. The
migration logs the count and caller can set
``REGENGINE_RLS_PURGE_FALLBACK_ROWS=1`` to delete them as part of the upgrade;
default behaviour is to log and continue so production runs don't silently
destroy seed data.

Affected migrations (all now superseded for their policy expressions):
  - V12__production_compliance_init.sql     — 16 pcos_* tables
  - V13__budget_intelligence_tables.sql     — uses `::uuid` cast, already
                                               fail-closed for text '' cast,
                                               rewritten for consistency
  - V14__tax_credit_tables.sql              — 2 tables, 8 policies
  - V15__form_autofill_tables.sql           — 1 table, 4 policies
  - V16__classification_tables.sql          — 2 tables, 5 policies
  - V17__paperwork_visa_tables.sql          — 2 tables, 4 policies
  - V18__audit_provenance_tables.sql        — 3 tables, 6 policies
  - V28__rls_pcos_vertical_tables.sql       — 40+ PCOS tables + 2 vertical_*

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-17
"""
import os

from alembic import op

# revision identifiers, used by Alembic.
revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


# Every (table, policy_name, policy_kind, using_or_check) tuple rewritten
# by this migration. policy_kind ∈ {"FOR ALL", "FOR SELECT", "FOR INSERT",
# "FOR UPDATE", "FOR DELETE"}. For INSERT we emit WITH CHECK; for all
# other kinds we emit USING.
#
# Grouped by source migration so the mapping back to V-files is explicit.
_POLICIES = [
    # ------------------------------------------------------------------
    # V12 — production compliance PCOS core (tenant_isolation_policy)
    # ------------------------------------------------------------------
    *[
        (tbl, "tenant_isolation_policy", "FOR ALL", "authenticated")
        for tbl in (
            "pcos_companies", "pcos_company_registrations", "pcos_insurance_policies",
            "pcos_safety_policies", "pcos_projects", "pcos_locations",
            "pcos_permit_packets", "pcos_people", "pcos_engagements",
            "pcos_timecards", "pcos_payroll_exports", "pcos_tasks",
            "pcos_task_events", "pcos_evidence", "pcos_gate_evaluations",
        )
    ],

    # ------------------------------------------------------------------
    # V13 — budget intelligence (used text-cast, already fail-closed,
    # rewriting for consistency so CI greps don't trip)
    # ------------------------------------------------------------------
    ("pcos_budgets", "pcos_budgets_tenant_policy", "FOR ALL", "authenticated"),
    ("pcos_budget_line_items", "pcos_budget_line_items_tenant_policy", "FOR ALL", "authenticated"),
    ("pcos_union_rate_checks", "pcos_union_rate_checks_tenant_policy", "FOR ALL", "authenticated"),

    # ------------------------------------------------------------------
    # V14 — tax credit tables
    # ------------------------------------------------------------------
    ("pcos_tax_credit_applications", "tax_credit_apps_tenant_isolation", "FOR ALL", "authenticated"),
    ("pcos_tax_credit_applications", "tax_credit_apps_insert", "FOR INSERT", "authenticated"),
    ("pcos_tax_credit_applications", "tax_credit_apps_update", "FOR UPDATE", "authenticated"),
    ("pcos_tax_credit_applications", "tax_credit_apps_delete", "FOR DELETE", "authenticated"),
    ("pcos_qualified_spend_categories", "qualified_spend_tenant_isolation", "FOR ALL", "authenticated"),
    ("pcos_qualified_spend_categories", "qualified_spend_insert", "FOR INSERT", "authenticated"),
    ("pcos_qualified_spend_categories", "qualified_spend_update", "FOR UPDATE", "authenticated"),
    ("pcos_qualified_spend_categories", "qualified_spend_delete", "FOR DELETE", "authenticated"),

    # ------------------------------------------------------------------
    # V15 — form autofill
    # ------------------------------------------------------------------
    ("pcos_generated_forms", "generated_forms_tenant_isolation", "FOR ALL", "authenticated"),
    ("pcos_generated_forms", "generated_forms_insert", "FOR INSERT", "authenticated"),
    ("pcos_generated_forms", "generated_forms_update", "FOR UPDATE", "authenticated"),
    ("pcos_generated_forms", "generated_forms_delete", "FOR DELETE", "authenticated"),

    # ------------------------------------------------------------------
    # V16 — classification
    # ------------------------------------------------------------------
    ("pcos_classification_analyses", "classification_tenant_isolation", "FOR ALL", "authenticated"),
    ("pcos_classification_analyses", "classification_insert", "FOR INSERT", "authenticated"),
    ("pcos_classification_analyses", "classification_update", "FOR UPDATE", "authenticated"),
    ("pcos_classification_analyses", "classification_delete", "FOR DELETE", "authenticated"),
    ("pcos_abc_questionnaire_responses", "questionnaire_tenant_isolation", "FOR ALL", "authenticated"),
    ("pcos_abc_questionnaire_responses", "questionnaire_insert", "FOR INSERT", "authenticated"),

    # ------------------------------------------------------------------
    # V17 — paperwork / visa
    # ------------------------------------------------------------------
    ("pcos_engagement_documents", "engagement_docs_tenant_isolation", "FOR ALL", "authenticated"),
    ("pcos_engagement_documents", "engagement_docs_insert", "FOR INSERT", "authenticated"),
    ("pcos_person_visa_status", "person_visa_tenant_isolation", "FOR ALL", "authenticated"),
    ("pcos_person_visa_status", "person_visa_insert", "FOR INSERT", "authenticated"),

    # ------------------------------------------------------------------
    # V18 — audit / provenance
    # ------------------------------------------------------------------
    ("pcos_rule_evaluations", "rule_evals_tenant", "FOR ALL", "authenticated"),
    ("pcos_rule_evaluations", "rule_evals_insert", "FOR INSERT", "authenticated"),
    ("pcos_compliance_snapshots", "snapshots_tenant", "FOR ALL", "authenticated"),
    ("pcos_compliance_snapshots", "snapshots_insert", "FOR INSERT", "authenticated"),
    ("pcos_audit_events", "audit_events_tenant", "FOR ALL", "authenticated"),
    ("pcos_audit_events", "audit_events_insert", "FOR INSERT", "authenticated"),

    # ------------------------------------------------------------------
    # V28 — PCOS + vertical (40 tables, named "<tbl>_tenant_isolation")
    # ------------------------------------------------------------------
    *[
        (tbl, f"{tbl}_tenant_isolation", "FOR ALL", "authenticated")
        for tbl in (
            "pcos_companies", "pcos_people", "pcos_projects", "pcos_engagements",
            "pcos_tasks", "pcos_timecards", "pcos_evidence",
            "pcos_authority_documents", "pcos_document_requirements",
            "pcos_engagement_documents",
            "pcos_company_registrations", "pcos_insurance_policies",
            "pcos_safety_policies", "pcos_locations", "pcos_permit_packets",
            "pcos_form_templates", "pcos_generated_forms",
            "pcos_budgets", "pcos_budget_line_items",
            "pcos_tax_credit_applications", "pcos_tax_credit_rules",
            "pcos_qualified_spend_categories",
            "pcos_classification_analyses", "pcos_abc_questionnaire_responses",
            "pcos_classification_exemptions",
            "pcos_visa_categories", "pcos_person_visa_status",
            "pcos_extracted_facts", "pcos_fact_citations", "pcos_analysis_runs",
            "pcos_compliance_snapshots", "pcos_audit_events", "pcos_task_events",
            "pcos_rule_evaluations", "pcos_gate_evaluations",
            "pcos_union_rate_checks",
        )
    ],
    ("vertical_projects", "vertical_projects_tenant_isolation", "FOR ALL", "authenticated"),
    ("vertical_rule_instances", "vertical_rule_instances_tenant_isolation", "FOR ALL", "authenticated"),

    # ------------------------------------------------------------------
    # V12 special case — pcos_contract_templates (NULL tenant = system
    # template, otherwise fail-hard)
    # ------------------------------------------------------------------
]


# Dedupe preserving order — V12 and V28 both define policies on the same
# tables under different names; DROP IF EXISTS handles that, but we
# want unique (table, policy) pairs for the CREATE loop.
def _dedupe(rows):
    seen = set()
    out = []
    for row in rows:
        key = (row[0], row[1])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


_POLICIES = _dedupe(_POLICIES)


# Tables that need FORCE ROW LEVEL SECURITY re-asserted. Superset of the
# policy targets above — include a few that V27/V28_5 already covered so
# this migration is a single source of truth for "these tables are
# fail-closed post-v059".
_FORCE_RLS_TABLES = sorted({row[0] for row in _POLICIES} | {
    # V27 / V28_5 — core security (already fail-closed but re-assert FORCE)
    "tenants", "users", "memberships", "roles", "sessions", "invites",
    "api_keys", "audit_logs", "evidence_logs", "compliance_snapshots",
    "tenant_compliance_status", "tenant_product_profile", "compliance_alerts",
    "compliance_status_log", "review_items",
    # V12 special
    "pcos_contract_templates",
})


FALLBACK_TENANT_UUID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0. Re-assert get_tenant_context() as fail-hard.
    # v056 already created this; recreating here is idempotent (CREATE OR
    # REPLACE). Safety net in case v056 is rolled back or the prior
    # V29-shape fail-open COALESCE function has been restored.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION get_tenant_context()
        RETURNS UUID AS $fn$
        DECLARE
            tid TEXT;
        BEGIN
            tid := NULLIF(current_setting('app.tenant_id', TRUE), '');
            IF tid IS NULL THEN
                RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN tid::UUID;
        END;
        $fn$ LANGUAGE plpgsql STABLE
    """)

    # ------------------------------------------------------------------
    # 1. Pre-check: count rows with the fallback sandbox UUID across all
    #    affected tables. Those are, by definition, the rows that the
    #    old policies leaked to any context-less connection.
    #
    #    Default behaviour: log a NOTICE with the per-table count.
    #    Set REGENGINE_RLS_PURGE_FALLBACK_ROWS=1 to delete them instead.
    # ------------------------------------------------------------------
    purge = os.environ.get("REGENGINE_RLS_PURGE_FALLBACK_ROWS", "").lower() in ("1", "true", "yes")
    affected_tables = sorted({row[0] for row in _POLICIES})

    # Produce one anonymous block per table to keep the output readable
    # and so one missing table doesn't abort the whole loop.
    for tbl in affected_tables:
        action = "DELETE" if purge else "NOTICE"
        op.execute(f"""
            DO $$
            DECLARE
                cnt BIGINT;
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = '{tbl}' AND table_schema IN ('public', current_schema())
                ) THEN
                    RAISE NOTICE 'v059: table {tbl} does not exist - skipping pre-check';
                    RETURN;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{tbl}' AND column_name = 'tenant_id'
                ) THEN
                    RAISE NOTICE 'v059: table {tbl} has no tenant_id column - skipping pre-check';
                    RETURN;
                END IF;
                EXECUTE format(
                    'SELECT COUNT(*) FROM %I WHERE tenant_id = %L',
                    '{tbl}', '{FALLBACK_TENANT_UUID}'
                ) INTO cnt;
                IF cnt > 0 THEN
                    IF '{action}' = 'DELETE' THEN
                        EXECUTE format(
                            'DELETE FROM %I WHERE tenant_id = %L',
                            '{tbl}', '{FALLBACK_TENANT_UUID}'
                        );
                        RAISE WARNING 'v059: purged % leaked fallback-tenant rows from %', cnt, '{tbl}';
                    ELSE
                        RAISE WARNING 'v059: table % has % rows with tenant_id=% '
                                      '(fallback sandbox UUID). These were visible to every '
                                      'context-less connection under the old policies. '
                                      'Set REGENGINE_RLS_PURGE_FALLBACK_ROWS=1 to delete, '
                                      'or reassign them manually before proceeding.',
                                      '{tbl}', cnt, '{FALLBACK_TENANT_UUID}';
                    END IF;
                END IF;
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'v059: pre-check on {tbl} failed: %', SQLERRM;
            END $$
        """)

    # ------------------------------------------------------------------
    # 2. FORCE ROW LEVEL SECURITY on every affected table. Without FORCE
    #    the table owner bypasses policies entirely (a subtle default).
    # ------------------------------------------------------------------
    for tbl in _FORCE_RLS_TABLES:
        op.execute(f"""
            DO $$ BEGIN
                EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', '{tbl}');
                EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', '{tbl}');
            EXCEPTION WHEN undefined_table THEN
                RAISE NOTICE 'v059: table {tbl} does not exist - skipping FORCE RLS';
            END $$
        """)

    # ------------------------------------------------------------------
    # 3. Rewrite every affected policy to use get_tenant_context().
    # ------------------------------------------------------------------
    for tbl, policy, kind, role in _POLICIES:
        using_clause = "tenant_id = get_tenant_context()"

        if kind == "FOR INSERT":
            create_stmt = (
                f'CREATE POLICY "{policy}" ON {tbl} '
                f'FOR INSERT TO {role} '
                f'WITH CHECK ({using_clause})'
            )
        else:
            create_stmt = (
                f'CREATE POLICY "{policy}" ON {tbl} '
                f'{kind} TO {role} '
                f'USING ({using_clause})'
            )

        op.execute(f"""
            DO $$ BEGIN
                EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{policy}', '{tbl}');
                EXECUTE $pol${create_stmt}$pol$;
            EXCEPTION WHEN undefined_table THEN
                RAISE NOTICE 'v059: table {tbl} does not exist - skipping policy {policy}';
            WHEN undefined_object THEN
                RAISE NOTICE 'v059: role or object missing for {tbl}.{policy}: %', SQLERRM;
            END $$
        """)

    # ------------------------------------------------------------------
    # 4. V12 special case: pcos_contract_templates allows NULL tenant_id
    #    (system templates visible to all). Preserve that intent but
    #    remove the fallback-UUID clause.
    # ------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_policy ON pcos_contract_templates';
            EXECUTE 'CREATE POLICY tenant_isolation_policy ON pcos_contract_templates
                FOR ALL TO authenticated
                USING (tenant_id IS NULL OR tenant_id = get_tenant_context())';
        EXCEPTION WHEN undefined_table THEN
            RAISE NOTICE 'v059: pcos_contract_templates does not exist - skipping';
        END $$
    """)

    # ------------------------------------------------------------------
    # 5. Retire the V29 fail-open helper (get_user_tenant_id falls back
    #    to the sandbox UUID via COALESCE; superseded by
    #    get_tenant_context()). Drop if it still exists.
    # ------------------------------------------------------------------
    op.execute("DROP FUNCTION IF EXISTS get_user_tenant_id()")

    # Leave set_tenant_from_jwt() alone — it only sets the GUC, doesn't
    # introduce a fallback.

    op.execute("""
        DO $$ BEGIN
            RAISE NOTICE 'v059: RLS fail-closed hardening complete. '
                         '% tables FORCE-RLS, % policies rewritten to use '
                         'get_tenant_context() (fail-hard on unset context).',
                         %s, %s;
        END $$
    """ % (len(_FORCE_RLS_TABLES), len(_POLICIES)))


def downgrade() -> None:
    # Downgrade restores the V28-era fail-open policy shape on affected
    # tables. We do NOT restore the column DEFAULTs or reseed the fallback
    # tenant — those are a V3/V27_5 concern.
    #
    # WARNING: this downgrade restores the known-vulnerable pattern. Only
    # use it to roll back in an emergency; a forward-fix is strongly
    # preferred.
    coalesce_expr = (
        "tenant_id = COALESCE("
        "NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID, "
        f"'{FALLBACK_TENANT_UUID}'::UUID)"
    )
    for tbl, policy, kind, role in _POLICIES:
        if kind == "FOR INSERT":
            create_stmt = (
                f'CREATE POLICY "{policy}" ON {tbl} '
                f'FOR INSERT TO {role} '
                f'WITH CHECK ({coalesce_expr})'
            )
        else:
            create_stmt = (
                f'CREATE POLICY "{policy}" ON {tbl} '
                f'{kind} TO {role} '
                f'USING ({coalesce_expr})'
            )
        op.execute(f"""
            DO $$ BEGIN
                EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{policy}', '{tbl}');
                EXECUTE $pol${create_stmt}$pol$;
            EXCEPTION WHEN undefined_table THEN NULL;
            END $$
        """)

    # Recreate V29's fail-open get_user_tenant_id() (superseded by
    # get_tenant_context in upgrade).
    op.execute("""
        CREATE OR REPLACE FUNCTION get_user_tenant_id()
        RETURNS UUID AS $fn$
        DECLARE
            user_tenant_id UUID;
        BEGIN
            SELECT tenant_id INTO user_tenant_id
            FROM memberships
            WHERE user_id = auth.uid()
            LIMIT 1;
            RETURN COALESCE(user_tenant_id, '00000000-0000-0000-0000-000000000001'::UUID);
        END;
        $fn$ LANGUAGE plpgsql SECURITY DEFINER
    """)

    # get_tenant_context() stays fail-hard — v056 owns it, not us.
