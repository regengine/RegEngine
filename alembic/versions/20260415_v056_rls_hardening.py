"""RLS hardening — sysadmin defense-in-depth, reference table policies, variable standardization

Consolidates raw SQL migrations:
  - SQL_V048: Sysadmin dual session+role verification, audit.sysadmin_access_log
  - V054: get_tenant_context() fail-hard, PCOS table policy fixes
  - SQL_V050: RLS on food_traceability_list, obligations, obligation_cte_rules (Supabase auth)
  - V056: RLS on obligations, controls, regulations, ftl (regengine roles)

Known overlap with v051 — #1247
---------------------------------
Parts 1/3/4 below re-state work that v051 already performed (SQL_V048
sysadmin role/audit schema/trigger function/set_admin_context helper,
plus RLS policies on core tables). Every CREATE in Part 1 is guarded
(``IF NOT EXISTS`` / ``CREATE OR REPLACE`` / ``DO $$ IF NOT EXISTS``),
so running v056 on a database where v051 already applied is a no-op for
the sysadmin/audit infrastructure. The only non-idempotent statement is
the ``DROP FUNCTION get_tenant_context() CASCADE`` at line ~120, which
is now guarded (see inline comment) to only drop-and-recreate when the
function's return type differs from UUID — on a DB where the UUID
signature is already in place, the CASCADE is skipped and dependent
policies are preserved.

v063 (``20260417_v063_restore_memberships_policy.py``) + v065
(``20260417_v065_audit_orphan_rls_tables.py``) are the backstops for any
policies historically dropped by the pre-guard CASCADE behavior; this
file's guard prevents **future** re-runs from tripping the same issue.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-15
"""
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ================================================================
    # Part 1: SQL_V048 — Sysadmin defense-in-depth
    # ================================================================

    # 1a. Create regengine_sysadmin role
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin LOGIN INHERIT;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT pg_has_role('regengine_sysadmin', 'regengine', 'MEMBER') THEN
                EXECUTE 'GRANT regengine TO regengine_sysadmin';
            END IF;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Could not grant regengine to regengine_sysadmin: %', SQLERRM;
        END $$;
    """)

    # 1b. Audit schema and sysadmin access log
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit.sysadmin_access_log (
            id BIGSERIAL PRIMARY KEY,
            accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            table_name TEXT NOT NULL,
            operation TEXT NOT NULL,
            connection_info JSONB,
            session_user_name TEXT NOT NULL DEFAULT session_user,
            client_addr TEXT DEFAULT inet_client_addr()::TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sysadmin_access_log_accessed_at
            ON audit.sysadmin_access_log (accessed_at DESC)
    """)

    # Grants for audit table
    for role in ("regengine_sysadmin", "regengine"):
        op.execute(f"GRANT USAGE ON SCHEMA audit TO {role}")
        op.execute(f"GRANT INSERT ON audit.sysadmin_access_log TO {role}")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE audit.sysadmin_access_log_id_seq TO {role}")
    op.execute("GRANT SELECT ON audit.sysadmin_access_log TO regengine_sysadmin")

    # 1c. Audit trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION audit.log_sysadmin_access()
        RETURNS TRIGGER AS $fn$
        BEGIN
            IF current_setting('regengine.is_sysadmin', true) = 'true'
               AND current_user = 'regengine_sysadmin' THEN
                INSERT INTO audit.sysadmin_access_log (table_name, operation, connection_info)
                VALUES (
                    TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
                    TG_OP,
                    jsonb_build_object(
                        'current_user', current_user,
                        'session_user', session_user,
                        'client_addr', inet_client_addr()::TEXT,
                        'application_name', current_setting('application_name', true),
                        'backend_pid', pg_backend_pid()
                    )
                );
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $fn$ LANGUAGE plpgsql SECURITY DEFINER
    """)

    # 1d. set_admin_context helper
    op.execute("""
        CREATE OR REPLACE FUNCTION set_admin_context(p_is_sysadmin boolean) RETURNS void AS $fn$
        BEGIN
            IF p_is_sysadmin AND current_user != 'regengine_sysadmin' THEN
                RAISE WARNING 'set_admin_context(true) called by role "%" - '
                               'RLS bypass requires regengine_sysadmin role.', current_user;
            END IF;
            PERFORM set_config('regengine.is_sysadmin', p_is_sysadmin::text, false);
        END;
        $fn$ LANGUAGE plpgsql
    """)

    # ================================================================
    # Part 2 (moved early): V054 — get_tenant_context() fail-hard
    # ================================================================
    # Must run BEFORE creating policies, because policies on UUID columns
    # need get_tenant_context() to return UUID, not TEXT.
    #
    # Guard (#1247): the original code was an unconditional
    #   DROP FUNCTION IF EXISTS get_tenant_context() CASCADE
    # which silently dropped every dependent RLS policy — including
    # v051's policies (see #1227). We now only DROP+CREATE when the
    # function is absent or has the legacy TEXT return type. If the
    # UUID-returning version is already in place (common on a DB where
    # v056 previously applied, or where a future migration recreated
    # it), we skip the destructive path entirely and dependent policies
    # are preserved.
    op.execute("""
        DO $v056_fn$
        DECLARE
            v_needs_recreate boolean;
        BEGIN
            SELECT NOT EXISTS (
                SELECT 1
                FROM pg_proc p
                JOIN pg_type t ON p.prorettype = t.oid
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE p.proname = 'get_tenant_context'
                  AND p.pronargs = 0
                  AND t.typname = 'uuid'
                  AND n.nspname = ANY (current_schemas(true))
            ) INTO v_needs_recreate;

            IF v_needs_recreate THEN
                -- Function absent or returns TEXT — must recreate.
                -- CASCADE is still needed here because changing return
                -- type requires DROP, and any dependent policies will
                -- be re-established by the loops below (and by the
                -- v063/v065 backstops for tables outside those lists).
                EXECUTE 'DROP FUNCTION IF EXISTS get_tenant_context() CASCADE';
                EXECUTE $fn_body$
                    CREATE FUNCTION get_tenant_context()
                    RETURNS UUID AS $fn$
                    DECLARE
                        tid TEXT;
                    BEGIN
                        tid := NULLIF(current_setting('app.tenant_id', TRUE), '');
                        IF tid IS NULL THEN
                            RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS';
                        END IF;
                        RETURN tid::UUID;
                    END;
                    $fn$ LANGUAGE plpgsql
                $fn_body$;
            END IF;
            -- else: function exists with UUID signature, leave it and
            -- its dependent policies alone.
        END $v056_fn$;
    """)

    # 1e. Update RLS policies with dual session+role check + audit triggers
    _rls_tables = [
        ("ingestion.documents", "tenant_isolation_docs", "trg_audit_sysadmin_docs",
         "tenant_id = get_tenant_context()"),
        ("vertical_projects", "tenant_isolation_projects", "trg_audit_sysadmin_projects",
         "tenant_id = get_tenant_context()"),
        ("evidence_logs", "tenant_isolation_evidence", "trg_audit_sysadmin_evidence",
         "tenant_id = get_tenant_context()"),
        ("audit_logs", "tenant_isolation_audit", "trg_audit_sysadmin_audit_logs",
         "tenant_id::uuid = get_tenant_context()"),
        ("memberships", "tenant_isolation_memberships", "trg_audit_sysadmin_memberships",
         "tenant_id = get_tenant_context()"),
    ]
    for table, policy, trigger, using_clause in _rls_tables:
        op.execute(f"""
            DO $$ BEGIN
                DROP POLICY IF EXISTS {policy} ON {table};
                CREATE POLICY {policy} ON {table}
                    FOR ALL TO regengine, regengine_sysadmin
                    USING (
                        {using_clause}
                        OR (current_setting('regengine.is_sysadmin', true) = 'true'
                            AND current_user = 'regengine_sysadmin')
                    );
                DROP TRIGGER IF EXISTS {trigger} ON {table};
                CREATE TRIGGER {trigger}
                    AFTER INSERT OR UPDATE OR DELETE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();
            EXCEPTION WHEN undefined_table THEN
                RAISE NOTICE 'Table {table} does not exist - skipping RLS';
            END $$
        """)

    # Users table — self-isolation + sysadmin bypass
    op.execute("""
        DO $$ BEGIN
            DROP POLICY IF EXISTS user_self_isolation ON users;
            CREATE POLICY user_self_isolation ON users
                FOR ALL TO regengine, regengine_sysadmin
                USING (
                    id = current_setting('regengine.user_id', true)::uuid
                    OR (current_setting('regengine.is_sysadmin', true) = 'true'
                        AND current_user = 'regengine_sysadmin')
                );
            DROP TRIGGER IF EXISTS trg_audit_sysadmin_users ON users;
            CREATE TRIGGER trg_audit_sysadmin_users
                AFTER INSERT OR UPDATE OR DELETE ON users
                FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();
        EXCEPTION WHEN undefined_table THEN
            RAISE NOTICE 'Table users does not exist - skipping RLS';
        END $$
    """)

    # ================================================================
    # Part 2 (continued): V054 — PCOS policy fixes
    # ================================================================

    # Fix PCOS table policies (were using wrong session variable)
    for table in ("pcos_authority_documents", "pcos_extracted_facts",
                  "pcos_fact_citations", "pcos_analysis_runs"):
        policy = f"{table}_tenant_isolation"
        op.execute(f"""
            DO $$ BEGIN
                DROP POLICY IF EXISTS {policy} ON {table};
                CREATE POLICY {policy} ON {table}
                    FOR ALL USING (tenant_id = get_tenant_context());
                ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            EXCEPTION WHEN undefined_table THEN
                RAISE NOTICE 'Table {table} does not exist - skipping';
            END $$
        """)

    # Drop stale memberships policy
    op.execute("DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships")

    # ================================================================
    # Part 3: SQL_V050 — RLS on reference tables (Supabase auth roles)
    # ================================================================

    # food_traceability_list (global reference, no tenant_id)
    op.execute("ALTER TABLE public.food_traceability_list ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.food_traceability_list FORCE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'CREATE POLICY food_traceability_list_select_authenticated
                    ON public.food_traceability_list FOR SELECT TO authenticated USING (true)';
            END IF;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # obligations (tenant-scoped via memberships)
    op.execute("ALTER TABLE public.obligations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.obligations FORCE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE $exec$CREATE POLICY obligations_select_tenant_scoped
                    ON public.obligations FOR SELECT TO authenticated
                    USING (tenant_id::uuid IN (
                        SELECT m.tenant_id FROM public.memberships m
                        WHERE m.user_id = auth.uid()
                    ))$exec$;
            END IF;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # obligation_cte_rules (scoped via parent obligation)
    op.execute("ALTER TABLE public.obligation_cte_rules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.obligation_cte_rules FORCE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE $exec$CREATE POLICY obligation_cte_rules_select_via_obligation
                    ON public.obligation_cte_rules FOR SELECT TO authenticated
                    USING (obligation_id IN (
                        SELECT o.id FROM public.obligations o
                        INNER JOIN public.memberships m ON o.tenant_id::uuid = m.tenant_id
                        WHERE m.user_id = auth.uid()
                    ))$exec$;
            END IF;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # ================================================================
    # Part 4: V056 — RLS on obligations/controls/regulations/ftl (regengine roles)
    # ================================================================

    _rls_v056 = [
        ("obligations", "tenant_isolation_obligations", "trg_audit_sysadmin_obligations"),
        ("controls", "tenant_isolation_controls", "trg_audit_sysadmin_controls"),
        ("regulations", "tenant_isolation_regulations", "trg_audit_sysadmin_regulations"),
    ]
    for table, policy, trigger in _rls_v056:
        # Guard: table may not exist on all databases
        op.execute(f"""
            DO $$ BEGIN
                ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS {policy} ON {table};
                CREATE POLICY {policy} ON {table}
                    FOR ALL TO regengine, regengine_sysadmin
                    USING (
                        tenant_id::uuid = get_tenant_context()
                        OR (current_setting('regengine.is_sysadmin', true) = 'true'
                            AND current_user = 'regengine_sysadmin')
                    );
                DROP TRIGGER IF EXISTS {trigger} ON {table};
                CREATE TRIGGER {trigger}
                    AFTER INSERT OR UPDATE OR DELETE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();
            EXCEPTION WHEN undefined_table THEN
                RAISE NOTICE 'Table {table} does not exist - skipping RLS';
            END $$
        """)

    # food_traceability_list — read-only for regengine roles
    op.execute("ALTER TABLE food_traceability_list ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS ftl_read_only ON food_traceability_list")
    op.execute("""
        CREATE POLICY ftl_read_only ON food_traceability_list
            FOR SELECT TO regengine, regengine_sysadmin USING (true)
    """)
    op.execute("DROP POLICY IF EXISTS ftl_sysadmin_write ON food_traceability_list")
    op.execute("""
        CREATE POLICY ftl_sysadmin_write ON food_traceability_list
            FOR ALL TO regengine_sysadmin USING (true) WITH CHECK (true)
    """)


def downgrade() -> None:
    # RLS policy and trigger removal (reverse of upgrade)
    for table, policy, trigger in [
        ("obligations", "tenant_isolation_obligations", "trg_audit_sysadmin_obligations"),
        ("controls", "tenant_isolation_controls", "trg_audit_sysadmin_controls"),
        ("regulations", "tenant_isolation_regulations", "trg_audit_sysadmin_regulations"),
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")

    op.execute("DROP POLICY IF EXISTS ftl_read_only ON food_traceability_list")
    op.execute("DROP POLICY IF EXISTS ftl_sysadmin_write ON food_traceability_list")

    op.execute("DROP POLICY IF EXISTS food_traceability_list_select_authenticated ON public.food_traceability_list")
    op.execute("DROP POLICY IF EXISTS obligations_select_tenant_scoped ON public.obligations")
    op.execute("DROP POLICY IF EXISTS obligation_cte_rules_select_via_obligation ON public.obligation_cte_rules")

    for table in ("pcos_authority_documents", "pcos_extracted_facts",
                  "pcos_fact_citations", "pcos_analysis_runs"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.execute("DROP POLICY IF EXISTS user_self_isolation ON users")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_sysadmin_users ON users")

    for table, policy, trigger in [
        ("ingestion.documents", "tenant_isolation_docs", "trg_audit_sysadmin_docs"),
        ("vertical_projects", "tenant_isolation_projects", "trg_audit_sysadmin_projects"),
        ("evidence_logs", "tenant_isolation_evidence", "trg_audit_sysadmin_evidence"),
        ("audit_logs", "tenant_isolation_audit", "trg_audit_sysadmin_audit_logs"),
        ("memberships", "tenant_isolation_memberships", "trg_audit_sysadmin_memberships"),
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")

    op.execute("DROP FUNCTION IF EXISTS set_admin_context(boolean)")
    op.execute("DROP FUNCTION IF EXISTS audit.log_sysadmin_access()")
    op.execute("DROP TABLE IF EXISTS audit.sysadmin_access_log")
    op.execute("DROP SCHEMA IF EXISTS audit")
