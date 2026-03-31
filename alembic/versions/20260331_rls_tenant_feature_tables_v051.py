# ============================================================================
# RLS FOR V042 TENANT FEATURE TABLES — V051
# ============================================================================
# Enables Row Level Security on the 8 tenant_* tables created by V042 that
# were missing RLS. Also consolidates the SQL_V048/V049/V050 RLS hardening
# scripts (sysadmin defense-in-depth, obligations/FTL, reference tables) that
# previously existed only as standalone SQL files and were never applied via
# Alembic.
#
# Tables receiving RLS in this migration:
#   fsma.tenant_suppliers, fsma.tenant_products, fsma.tenant_team_members,
#   fsma.tenant_notification_prefs, fsma.tenant_settings,
#   fsma.tenant_onboarding, fsma.tenant_exchanges, fsma.tenant_portal_links
#
# For existing databases:
#     alembic upgrade head
# ============================================================================

"""RLS for V042 tenant feature tables + consolidate SQL RLS hardening

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables from V042 that need RLS enabled.
_TENANT_TABLES = [
    'tenant_suppliers',
    'tenant_products',
    'tenant_team_members',
    'tenant_notification_prefs',
    'tenant_settings',
    'tenant_onboarding',
    'tenant_exchanges',
    'tenant_portal_links',
]


def upgrade() -> None:
    op.execute("SET search_path TO fsma, public;")

    # ----------------------------------------------------------------
    # Part 1: Enable RLS on 8 V042 tenant_* tables
    # ----------------------------------------------------------------
    for table in _TENANT_TABLES:
        qualified = f"fsma.{table}"

        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY;")

        op.execute(f"""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation_select ON {qualified}
                    FOR SELECT
                    USING (tenant_id::text = current_setting('app.tenant_id', true));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

        op.execute(f"""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation_insert ON {qualified}
                    FOR INSERT
                    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

        op.execute(f"""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation_update ON {qualified}
                    FOR UPDATE
                    USING (tenant_id::text = current_setting('app.tenant_id', true))
                    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

        op.execute(f"""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation_delete ON {qualified}
                    FOR DELETE
                    USING (tenant_id::text = current_setting('app.tenant_id', true));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # ----------------------------------------------------------------
    # Part 2: SQL_V048 — Sysadmin defense-in-depth RLS hardening
    # (previously migrations/V048__rls_sysadmin_defense_in_depth.sql)
    # ----------------------------------------------------------------

    # Create the dedicated sysadmin role (if not exists)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin LOGIN INHERIT;
                RAISE NOTICE 'Created role regengine_sysadmin';
            END IF;
        END
        $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT pg_has_role('regengine_sysadmin', 'regengine', 'MEMBER') THEN
                EXECUTE 'GRANT regengine TO regengine_sysadmin';
                RAISE NOTICE 'Granted regengine to regengine_sysadmin';
            END IF;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Could not grant regengine to regengine_sysadmin: %', SQLERRM;
        END
        $$;
    """)

    op.execute("""
        COMMENT ON ROLE regengine_sysadmin IS
            'Dedicated sysadmin role for RLS bypass. Both this role AND the '
            'regengine.is_sysadmin session variable must be present to bypass '
            'tenant isolation. Never use this role for normal application connections.';
    """)

    # Audit schema and sysadmin access log table
    op.execute("CREATE SCHEMA IF NOT EXISTS audit;")

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit.sysadmin_access_log (
            id BIGSERIAL PRIMARY KEY,
            accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            table_name TEXT NOT NULL,
            operation TEXT NOT NULL,
            connection_info JSONB,
            session_user_name TEXT NOT NULL DEFAULT session_user,
            client_addr TEXT DEFAULT inet_client_addr()::TEXT
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sysadmin_access_log_accessed_at
            ON audit.sysadmin_access_log (accessed_at DESC);
    """)

    op.execute("""
        GRANT USAGE ON SCHEMA audit TO regengine_sysadmin;
        GRANT INSERT, SELECT ON audit.sysadmin_access_log TO regengine_sysadmin;
        GRANT USAGE, SELECT ON SEQUENCE audit.sysadmin_access_log_id_seq TO regengine_sysadmin;
        GRANT USAGE ON SCHEMA audit TO regengine;
        GRANT INSERT ON audit.sysadmin_access_log TO regengine;
        GRANT USAGE, SELECT ON SEQUENCE audit.sysadmin_access_log_id_seq TO regengine;
    """)

    op.execute("""
        COMMENT ON TABLE audit.sysadmin_access_log IS
            'Records every row access that used the sysadmin RLS bypass. '
            'Captures who, when, from where, and which table/operation.';
    """)

    # Audit trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION audit.log_sysadmin_access()
        RETURNS TRIGGER AS $$
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
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)

    op.execute("""
        COMMENT ON FUNCTION audit.log_sysadmin_access() IS
            'Trigger function that logs sysadmin RLS bypass usage to audit.sysadmin_access_log';
    """)

    # set_admin_context helper
    op.execute("""
        CREATE OR REPLACE FUNCTION set_admin_context(p_is_sysadmin boolean) RETURNS void AS $$
        BEGIN
            IF p_is_sysadmin AND current_user != 'regengine_sysadmin' THEN
                RAISE WARNING 'set_admin_context(true) called by role "%" — '
                               'RLS bypass requires regengine_sysadmin role. '
                               'The session variable will be set but RLS policies '
                               'will NOT grant sysadmin access.', current_user;
            END IF;
            PERFORM set_config('regengine.is_sysadmin', p_is_sysadmin::text, false);
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Update RLS policies on core tables — require BOTH session var AND role
    op.execute("""
        DROP POLICY IF EXISTS tenant_isolation_docs ON ingestion.documents;
        CREATE POLICY tenant_isolation_docs ON ingestion.documents
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                tenant_id = get_tenant_context()
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_docs ON ingestion.documents;
        CREATE TRIGGER trg_audit_sysadmin_docs
            AFTER INSERT OR UPDATE OR DELETE ON ingestion.documents
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    op.execute("""
        DROP POLICY IF EXISTS tenant_isolation_projects ON vertical_projects;
        CREATE POLICY tenant_isolation_projects ON vertical_projects
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                tenant_id = get_tenant_context()
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_projects ON vertical_projects;
        CREATE TRIGGER trg_audit_sysadmin_projects
            AFTER INSERT OR UPDATE OR DELETE ON vertical_projects
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    op.execute("""
        DROP POLICY IF EXISTS tenant_isolation_evidence ON evidence_logs;
        CREATE POLICY tenant_isolation_evidence ON evidence_logs
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                tenant_id = get_tenant_context()
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_evidence ON evidence_logs;
        CREATE TRIGGER trg_audit_sysadmin_evidence
            AFTER INSERT OR UPDATE OR DELETE ON evidence_logs
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    op.execute("""
        DROP POLICY IF EXISTS tenant_isolation_audit ON audit_logs;
        CREATE POLICY tenant_isolation_audit ON audit_logs
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                tenant_id = get_tenant_context()
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_audit_logs ON audit_logs;
        CREATE TRIGGER trg_audit_sysadmin_audit_logs
            AFTER INSERT OR UPDATE OR DELETE ON audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    op.execute("""
        DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships;
        CREATE POLICY tenant_isolation_memberships ON memberships
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                tenant_id = get_tenant_context()
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_memberships ON memberships;
        CREATE TRIGGER trg_audit_sysadmin_memberships
            AFTER INSERT OR UPDATE OR DELETE ON memberships
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    op.execute("""
        DROP POLICY IF EXISTS user_self_isolation ON users;
        CREATE POLICY user_self_isolation ON users
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                id = current_setting('regengine.user_id', true)::uuid
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_users ON users;
        CREATE TRIGGER trg_audit_sysadmin_users
            AFTER INSERT OR UPDATE OR DELETE ON users
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    # ----------------------------------------------------------------
    # Part 3: SQL_V049 — RLS on obligations and food_traceability_list
    # (previously migrations/V049__rls_obligations_and_ftl.sql)
    # ----------------------------------------------------------------

    op.execute("""
        ALTER TABLE obligations ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation_obligations ON obligations;
        CREATE POLICY tenant_isolation_obligations ON obligations
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                tenant_id = get_tenant_context()
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_obligations ON obligations;
        CREATE TRIGGER trg_audit_sysadmin_obligations
            AFTER INSERT OR UPDATE OR DELETE ON obligations
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    op.execute("""
        ALTER TABLE controls ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation_controls ON controls;
        CREATE POLICY tenant_isolation_controls ON controls
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                tenant_id = get_tenant_context()
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_controls ON controls;
        CREATE TRIGGER trg_audit_sysadmin_controls
            AFTER INSERT OR UPDATE OR DELETE ON controls
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    op.execute("""
        ALTER TABLE food_traceability_list ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS ftl_read_only ON food_traceability_list;
        CREATE POLICY ftl_read_only ON food_traceability_list
            FOR SELECT
            TO regengine, regengine_sysadmin
            USING (true);
        DROP POLICY IF EXISTS ftl_sysadmin_write ON food_traceability_list;
        CREATE POLICY ftl_sysadmin_write ON food_traceability_list
            FOR ALL
            TO regengine_sysadmin
            USING (true)
            WITH CHECK (true);
        COMMENT ON TABLE food_traceability_list IS
            'FDA FSMA 204 Food Traceability List — global reference data (no tenant_id). '
            'RLS: read-only for all roles, writes restricted to regengine_sysadmin. '
            'See V036 for seed data, V051 for RLS enablement.';
    """)

    op.execute("""
        ALTER TABLE regulations ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation_regulations ON regulations;
        CREATE POLICY tenant_isolation_regulations ON regulations
            FOR ALL
            TO regengine, regengine_sysadmin
            USING (
                tenant_id = get_tenant_context()
                OR (current_setting('regengine.is_sysadmin', true) = 'true'
                    AND current_user = 'regengine_sysadmin')
            );
        DROP TRIGGER IF EXISTS trg_audit_sysadmin_regulations ON regulations;
        CREATE TRIGGER trg_audit_sysadmin_regulations
            AFTER INSERT OR UPDATE OR DELETE ON regulations
            FOR EACH ROW
            EXECUTE FUNCTION audit.log_sysadmin_access();
    """)

    # ----------------------------------------------------------------
    # Part 4: SQL_V050 — RLS on reference tables
    # (previously migrations/V050__rls_reference_tables.sql)
    # ----------------------------------------------------------------

    op.execute("""
        ALTER TABLE public.food_traceability_list FORCE ROW LEVEL SECURITY;
        DO $$ BEGIN
            CREATE POLICY "food_traceability_list_select_authenticated"
              ON public.food_traceability_list
              FOR SELECT
              TO authenticated
              USING (true);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        ALTER TABLE public.obligations FORCE ROW LEVEL SECURITY;
        DO $$ BEGIN
            CREATE POLICY "obligations_select_tenant_scoped"
              ON public.obligations
              FOR SELECT
              TO authenticated
              USING (
                tenant_id::uuid IN (
                  SELECT m.tenant_id
                  FROM public.memberships m
                  WHERE m.user_id = auth.uid()
                )
              );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        ALTER TABLE public.obligation_cte_rules ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.obligation_cte_rules FORCE ROW LEVEL SECURITY;
        DO $$ BEGIN
            CREATE POLICY "obligation_cte_rules_select_via_obligation"
              ON public.obligation_cte_rules
              FOR SELECT
              TO authenticated
              USING (
                obligation_id IN (
                  SELECT o.id
                  FROM public.obligations o
                  INNER JOIN public.memberships m ON o.tenant_id::uuid = m.tenant_id
                  WHERE m.user_id = auth.uid()
                )
              );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    op.execute("SET search_path TO fsma, public;")

    # Remove SQL_V050 policies
    op.execute("DROP POLICY IF EXISTS obligation_cte_rules_select_via_obligation ON public.obligation_cte_rules;")
    op.execute("ALTER TABLE public.obligation_cte_rules DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS obligations_select_tenant_scoped ON public.obligations;")
    op.execute("DROP POLICY IF EXISTS food_traceability_list_select_authenticated ON public.food_traceability_list;")

    # Remove SQL_V049 policies
    op.execute("DROP TRIGGER IF EXISTS trg_audit_sysadmin_regulations ON regulations;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_regulations ON regulations;")
    op.execute("ALTER TABLE regulations DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS ftl_sysadmin_write ON food_traceability_list;")
    op.execute("DROP POLICY IF EXISTS ftl_read_only ON food_traceability_list;")
    op.execute("ALTER TABLE food_traceability_list DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_sysadmin_controls ON controls;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_controls ON controls;")
    op.execute("ALTER TABLE controls DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_sysadmin_obligations ON obligations;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_obligations ON obligations;")
    op.execute("ALTER TABLE obligations DISABLE ROW LEVEL SECURITY;")

    # Remove SQL_V048 triggers and policies on core tables
    for tbl in ['ingestion.documents', 'vertical_projects', 'evidence_logs', 'audit_logs', 'memberships', 'users']:
        short = tbl.split('.')[-1]
        op.execute(f"DROP TRIGGER IF EXISTS trg_audit_sysadmin_{short} ON {tbl};")

    op.execute("DROP FUNCTION IF EXISTS set_admin_context(boolean);")
    op.execute("DROP FUNCTION IF EXISTS audit.log_sysadmin_access();")
    op.execute("DROP TABLE IF EXISTS audit.sysadmin_access_log CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE;")

    # Remove RLS from V042 tenant_* tables
    for table in reversed(_TENANT_TABLES):
        qualified = f"fsma.{table}"
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {qualified};")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_update ON {qualified};")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {qualified};")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_select ON {qualified};")
        op.execute(f"ALTER TABLE {qualified} DISABLE ROW LEVEL SECURITY;")
