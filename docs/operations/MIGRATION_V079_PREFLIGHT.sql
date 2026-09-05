-- Read-only catalog evidence. Run with psql -X -v ON_ERROR_STOP=1.
-- Contains no customer rows, credential values, or ownership changes.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SELECT jsonb_pretty(jsonb_build_object(
    'revision', (SELECT jsonb_agg(version_num) FROM public.alembic_version),
    'server_version', current_setting('server_version'),
    'timezone', current_setting('TimeZone'),
    'search_path', current_setting('search_path'),
    'database_owner', (
        SELECT pg_get_userbyid(datdba)
        FROM pg_database WHERE datname = current_database()
    ),
    'roles', (
        SELECT jsonb_agg(jsonb_build_object(
            'name', rolname, 'login', rolcanlogin, 'superuser', rolsuper,
            'bypassrls', rolbypassrls, 'createdb', rolcreatedb,
            'createrole', rolcreaterole, 'replication', rolreplication
        ) ORDER BY rolname)
        FROM pg_roles
        WHERE rolname IN ('regengine', 'regengine_sysadmin', 'regengine_migrator')
    ),
    'role_memberships', (
        SELECT jsonb_agg(jsonb_build_object(
            'member', member_role.rolname, 'granted_role', granted_role.rolname
        ) ORDER BY member_role.rolname, granted_role.rolname)
        FROM pg_auth_members membership
        JOIN pg_roles member_role ON member_role.oid = membership.member
        JOIN pg_roles granted_role ON granted_role.oid = membership.roleid
        WHERE member_role.rolname IN ('regengine', 'regengine_sysadmin', 'regengine_migrator')
           OR granted_role.rolname IN ('regengine', 'regengine_sysadmin', 'regengine_migrator')
    ),
    'extensions', (
        SELECT jsonb_agg(jsonb_build_object(
            'name', e.extname, 'schema', n.nspname,
            'owner', pg_get_userbyid(e.extowner)
        ) ORDER BY e.extname)
        FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
    ),
    'protected_relation_owners', (
        SELECT jsonb_agg(owners ORDER BY owners.schema_name, owners.owner_name)
        FROM (
            SELECT n.nspname AS schema_name,
                   pg_get_userbyid(c.relowner) AS owner_name, count(*) AS object_count
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
              AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f', 'i', 'I')
            GROUP BY 1, 2
        ) owners
    ),
    'rls', (
        SELECT jsonb_agg(jsonb_build_object(
            'schema', n.nspname, 'table', c.relname,
            'enabled', c.relrowsecurity, 'forced', c.relforcerowsecurity
        ) ORDER BY n.nspname, c.relname)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('public', 'fsma')
          AND c.relname IN (
              'cte_events', 'traceability_events', 'hash_chain', 'rule_definitions',
              'rule_evaluations', 'rule_audit_log', 'audit_logs', 'audit_log_buffer'
          )
    ),
    'objects', jsonb_build_object(
        'receipts', to_regclass('fsma.ingestion_run_receipts'),
        'rule_deadletter', to_regclass('fsma.rule_evaluation_deadletter'),
        'snapshots', to_regclass('fsma.compliance_evidence_snapshots'),
        'password_reset_tokens', to_regclass('public.password_reset_tokens'),
        'password_hash_column', EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users'
              AND column_name = 'password_hash'
        )
    )
)) AS migration_preflight;
ROLLBACK;
