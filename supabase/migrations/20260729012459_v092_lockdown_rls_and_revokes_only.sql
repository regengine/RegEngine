-- alembic-revision: b3c8e1f4a627
-- rendered-from: alembic/versions/20260709_b3c8e1f4a627_v092_client_role_lockdown.py (upgrade)
DO $$
DECLARE
    tbl record;
BEGIN
    FOR tbl IN
        SELECT * FROM (VALUES
            ('fsma', 'rule_definitions', true),
            ('fsma', 'rule_audit_log', true),
            ('fsma', 'incidents', true),
            ('public', 'funnel_events', true),
            ('public', 'audit_log_buffer', true),
            ('public', 'admin_mfa_recovery_codes', true),
            ('public', 'password_reset_tokens', true),
            ('public', 'tool_leads', true),
            ('public', 'sandbox_shares', true),
            ('public', 'alembic_version', false),
            ('public', 'schema_migrations', false)
        ) AS t(sch, tab, force_rls)
    LOOP
        IF to_regclass(tbl.sch || '.' || tbl.tab) IS NULL THEN
            CONTINUE;
        END IF;

        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', tbl.sch, tbl.tab);
        IF tbl.force_rls THEN
            EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', tbl.sch, tbl.tab);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = tbl.sch AND tablename = tbl.tab
              AND policyname = 'app_only_' || tbl.tab
        ) THEN
            EXECUTE format(
                'CREATE POLICY %I ON %I.%I FOR ALL TO regengine, regengine_sysadmin USING (true) WITH CHECK (true)',
                'app_only_' || tbl.tab, tbl.sch, tbl.tab);
        END IF;

        EXECUTE format('REVOKE ALL ON %I.%I FROM PUBLIC', tbl.sch, tbl.tab);
        EXECUTE format('REVOKE ALL ON %I.%I FROM anon', tbl.sch, tbl.tab);
        EXECUTE format('REVOKE ALL ON %I.%I FROM authenticated', tbl.sch, tbl.tab);
    END LOOP;
END $$;

ALTER TABLE ingestion.documents ENABLE ROW LEVEL SECURITY;;
