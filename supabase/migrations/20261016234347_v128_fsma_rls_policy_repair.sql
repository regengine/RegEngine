-- v128 FSMA RLS policy repair, rendered from upgrade() in
-- alembic/versions/20261016_a5e7c9b2d341_v128_fsma_rls_policy_repair.py.
-- DROP IF EXISTS stays within each original creation branch so existing
-- matching permissive policies and existing guard policies are preserved.

BEGIN;

DO $repair$
    BEGIN
        IF to_regclass('fsma.canonical_entities') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.canonical_entities at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.canonical_entities'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.canonical_entities at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.canonical_entities'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.canonical_entities'::regclass
          AND polname = 'v128_canonical_entities_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_canonical_entities_select_regengine', 'canonical_entities'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_canonical_entities_select_regengine ON fsma.canonical_entities
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_canonical_entities_select_regengine ON fsma.canonical_entities
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.canonical_entities'::regclass
              AND polname = 'v128_client_guard_canonical_entities'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_canonical_entities ON fsma.canonical_entities
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_canonical_entities ON fsma.canonical_entities
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.cte_events') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.cte_events at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.cte_events'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.cte_events at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.cte_events'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.cte_events'::regclass
          AND polname = 'v128_cte_events_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_cte_events_select_regengine', 'cte_events'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_cte_events_select_regengine ON fsma.cte_events
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_cte_events_select_regengine ON fsma.cte_events
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.cte_events'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.cte_events'::regclass
          AND polname = 'v128_cte_events_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_cte_events_insert_regengine', 'cte_events'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_cte_events_insert_regengine ON fsma.cte_events
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_cte_events_insert_regengine ON fsma.cte_events
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.cte_events'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'd')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.cte_events'::regclass
          AND polname = 'v128_cte_events_delete_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_cte_events_delete_regengine', 'cte_events'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_cte_events_delete_regengine ON fsma.cte_events
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_cte_events_delete_regengine ON fsma.cte_events
            FOR DELETE TO regengine
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.cte_events'::regclass
              AND polname = 'v128_client_guard_cte_events'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_cte_events ON fsma.cte_events
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_cte_events ON fsma.cte_events
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.cte_kdes') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.cte_kdes at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.cte_kdes'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.cte_kdes at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.cte_kdes'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.cte_kdes'::regclass
          AND polname = 'v128_cte_kdes_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_cte_kdes_select_regengine', 'cte_kdes'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_cte_kdes_select_regengine ON fsma.cte_kdes
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_cte_kdes_select_regengine ON fsma.cte_kdes
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.cte_kdes'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.cte_kdes'::regclass
          AND polname = 'v128_cte_kdes_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_cte_kdes_insert_regengine', 'cte_kdes'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_cte_kdes_insert_regengine ON fsma.cte_kdes
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_cte_kdes_insert_regengine ON fsma.cte_kdes
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.cte_kdes'::regclass
              AND polname = 'v128_client_guard_cte_kdes'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_cte_kdes ON fsma.cte_kdes
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_cte_kdes ON fsma.cte_kdes
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.entity_aliases') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.entity_aliases at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.entity_aliases'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.entity_aliases at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.entity_aliases'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.entity_aliases'::regclass
          AND polname = 'v128_entity_aliases_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_entity_aliases_select_regengine', 'entity_aliases'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_entity_aliases_select_regengine ON fsma.entity_aliases
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_entity_aliases_select_regengine ON fsma.entity_aliases
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.entity_aliases'::regclass
              AND polname = 'v128_client_guard_entity_aliases'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_entity_aliases ON fsma.entity_aliases
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_entity_aliases ON fsma.entity_aliases
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.exception_cases') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.exception_cases at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.exception_cases'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.exception_cases at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.exception_cases'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.exception_cases'::regclass
          AND polname = 'v128_exception_cases_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_exception_cases_select_regengine', 'exception_cases'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_exception_cases_select_regengine ON fsma.exception_cases
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_exception_cases_select_regengine ON fsma.exception_cases
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.exception_cases'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.exception_cases'::regclass
          AND polname = 'v128_exception_cases_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_exception_cases_insert_regengine', 'exception_cases'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_exception_cases_insert_regengine ON fsma.exception_cases
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_exception_cases_insert_regengine ON fsma.exception_cases
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.exception_cases'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'w')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.exception_cases'::regclass
          AND polname = 'v128_exception_cases_update_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_exception_cases_update_regengine', 'exception_cases'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_exception_cases_update_regengine ON fsma.exception_cases
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_exception_cases_update_regengine ON fsma.exception_cases
            FOR UPDATE TO regengine
            USING (tenant_id = public.get_tenant_context()) WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.exception_cases'::regclass
              AND polname = 'v128_client_guard_exception_cases'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_exception_cases ON fsma.exception_cases
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_exception_cases ON fsma.exception_cases
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.exception_comments') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.exception_comments at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.exception_comments'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.exception_comments at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.exception_comments'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.exception_comments'::regclass
          AND polname = 'v128_exception_comments_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_exception_comments_select_regengine', 'exception_comments'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_exception_comments_select_regengine ON fsma.exception_comments
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_exception_comments_select_regengine ON fsma.exception_comments
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.exception_comments'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.exception_comments'::regclass
          AND polname = 'v128_exception_comments_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_exception_comments_insert_regengine', 'exception_comments'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_exception_comments_insert_regengine ON fsma.exception_comments
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_exception_comments_insert_regengine ON fsma.exception_comments
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.exception_comments'::regclass
              AND polname = 'v128_client_guard_exception_comments'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_exception_comments ON fsma.exception_comments
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_exception_comments ON fsma.exception_comments
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.exception_signoffs') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.exception_signoffs at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.exception_signoffs'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.exception_signoffs at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.exception_signoffs'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.exception_signoffs'::regclass
          AND polname = 'v128_exception_signoffs_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_exception_signoffs_select_regengine', 'exception_signoffs'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_exception_signoffs_select_regengine ON fsma.exception_signoffs
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_exception_signoffs_select_regengine ON fsma.exception_signoffs
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.exception_signoffs'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.exception_signoffs'::regclass
          AND polname = 'v128_exception_signoffs_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_exception_signoffs_insert_regengine', 'exception_signoffs'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_exception_signoffs_insert_regengine ON fsma.exception_signoffs
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_exception_signoffs_insert_regengine ON fsma.exception_signoffs
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.exception_signoffs'::regclass
              AND polname = 'v128_client_guard_exception_signoffs'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_exception_signoffs ON fsma.exception_signoffs
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_exception_signoffs ON fsma.exception_signoffs
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.fda_export_log') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.fda_export_log at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.fda_export_log'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.fda_export_log at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.fda_export_log'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.fda_export_log'::regclass
          AND polname = 'v128_fda_export_log_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_fda_export_log_select_regengine', 'fda_export_log'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_fda_export_log_select_regengine ON fsma.fda_export_log
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_fda_export_log_select_regengine ON fsma.fda_export_log
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.fda_export_log'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.fda_export_log'::regclass
          AND polname = 'v128_fda_export_log_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_fda_export_log_insert_regengine', 'fda_export_log'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_fda_export_log_insert_regengine ON fsma.fda_export_log
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_fda_export_log_insert_regengine ON fsma.fda_export_log
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.fda_export_log'::regclass
              AND polname = 'v128_client_guard_fda_export_log'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_fda_export_log ON fsma.fda_export_log
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_fda_export_log ON fsma.fda_export_log
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.hash_chain') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.hash_chain at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.hash_chain'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.hash_chain at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.hash_chain'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.hash_chain'::regclass
          AND polname = 'v128_hash_chain_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_hash_chain_select_regengine', 'hash_chain'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_hash_chain_select_regengine ON fsma.hash_chain
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_hash_chain_select_regengine ON fsma.hash_chain
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.hash_chain'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.hash_chain'::regclass
          AND polname = 'v128_hash_chain_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_hash_chain_insert_regengine', 'hash_chain'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_hash_chain_insert_regengine ON fsma.hash_chain
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_hash_chain_insert_regengine ON fsma.hash_chain
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.hash_chain'::regclass
              AND polname = 'v128_client_guard_hash_chain'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_hash_chain ON fsma.hash_chain
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_hash_chain ON fsma.hash_chain
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.identity_review_queue') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.identity_review_queue at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.identity_review_queue'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.identity_review_queue at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.identity_review_queue'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.identity_review_queue'::regclass
          AND polname = 'v128_identity_review_queue_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_identity_review_queue_select_regengine', 'identity_review_queue'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_identity_review_queue_select_regengine ON fsma.identity_review_queue
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_identity_review_queue_select_regengine ON fsma.identity_review_queue
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.identity_review_queue'::regclass
              AND polname = 'v128_client_guard_identity_review_queue'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_identity_review_queue ON fsma.identity_review_queue
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_identity_review_queue ON fsma.identity_review_queue
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.ingestion_runs') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.ingestion_runs at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.ingestion_runs'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.ingestion_runs at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.ingestion_runs'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.ingestion_runs'::regclass
          AND polname = 'v128_ingestion_runs_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_ingestion_runs_select_regengine', 'ingestion_runs'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_ingestion_runs_select_regengine ON fsma.ingestion_runs
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_ingestion_runs_select_regengine ON fsma.ingestion_runs
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.ingestion_runs'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.ingestion_runs'::regclass
          AND polname = 'v128_ingestion_runs_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_ingestion_runs_insert_regengine', 'ingestion_runs'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_ingestion_runs_insert_regengine ON fsma.ingestion_runs
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_ingestion_runs_insert_regengine ON fsma.ingestion_runs
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.ingestion_runs'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'w')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.ingestion_runs'::regclass
          AND polname = 'v128_ingestion_runs_update_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_ingestion_runs_update_regengine', 'ingestion_runs'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_ingestion_runs_update_regengine ON fsma.ingestion_runs
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_ingestion_runs_update_regengine ON fsma.ingestion_runs
            FOR UPDATE TO regengine
            USING (tenant_id = public.get_tenant_context()::text) WITH CHECK (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine_sysadmin'
    WHERE p.polrelid = 'fsma.ingestion_runs'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.ingestion_runs'::regclass
          AND polname = 'v128_ingestion_runs_select_regengine_sysadmin'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_ingestion_runs_select_regengine_sysadmin', 'ingestion_runs'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_ingestion_runs_select_regengine_sysadmin ON fsma.ingestion_runs
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_ingestion_runs_select_regengine_sysadmin ON fsma.ingestion_runs
            FOR SELECT TO regengine_sysadmin
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.ingestion_runs'::regclass
              AND polname = 'v128_client_guard_ingestion_runs'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_ingestion_runs ON fsma.ingestion_runs
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_ingestion_runs ON fsma.ingestion_runs
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.request_cases') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.request_cases at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.request_cases'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.request_cases at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.request_cases'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.request_cases'::regclass
          AND polname = 'v128_request_cases_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_request_cases_select_regengine', 'request_cases'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_request_cases_select_regengine ON fsma.request_cases
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_request_cases_select_regengine ON fsma.request_cases
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.request_cases'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.request_cases'::regclass
          AND polname = 'v128_request_cases_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_request_cases_insert_regengine', 'request_cases'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_request_cases_insert_regengine ON fsma.request_cases
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_request_cases_insert_regengine ON fsma.request_cases
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.request_cases'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'w')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.request_cases'::regclass
          AND polname = 'v128_request_cases_update_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_request_cases_update_regengine', 'request_cases'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_request_cases_update_regengine ON fsma.request_cases
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_request_cases_update_regengine ON fsma.request_cases
            FOR UPDATE TO regengine
            USING (tenant_id = public.get_tenant_context()) WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.request_cases'::regclass
              AND polname = 'v128_client_guard_request_cases'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_request_cases ON fsma.request_cases
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_request_cases ON fsma.request_cases
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.request_signoffs') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.request_signoffs at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.request_signoffs'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.request_signoffs at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.request_signoffs'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.request_signoffs'::regclass
          AND polname = 'v128_request_signoffs_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_request_signoffs_select_regengine', 'request_signoffs'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_request_signoffs_select_regengine ON fsma.request_signoffs
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_request_signoffs_select_regengine ON fsma.request_signoffs
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.request_signoffs'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.request_signoffs'::regclass
          AND polname = 'v128_request_signoffs_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_request_signoffs_insert_regengine', 'request_signoffs'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_request_signoffs_insert_regengine ON fsma.request_signoffs
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_request_signoffs_insert_regengine ON fsma.request_signoffs
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.request_signoffs'::regclass
              AND polname = 'v128_client_guard_request_signoffs'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_request_signoffs ON fsma.request_signoffs
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_request_signoffs ON fsma.request_signoffs
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.response_packages') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.response_packages at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.response_packages'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.response_packages at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.response_packages'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.response_packages'::regclass
          AND polname = 'v128_response_packages_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_response_packages_select_regengine', 'response_packages'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_response_packages_select_regengine ON fsma.response_packages
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_response_packages_select_regengine ON fsma.response_packages
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.response_packages'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.response_packages'::regclass
          AND polname = 'v128_response_packages_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_response_packages_insert_regengine', 'response_packages'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_response_packages_insert_regengine ON fsma.response_packages
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_response_packages_insert_regengine ON fsma.response_packages
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.response_packages'::regclass
              AND polname = 'v128_client_guard_response_packages'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_response_packages ON fsma.response_packages
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_response_packages ON fsma.response_packages
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.rule_evaluations') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.rule_evaluations at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.rule_evaluations'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.rule_evaluations at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.rule_evaluations'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.rule_evaluations'::regclass
          AND polname = 'v128_rule_evaluations_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_rule_evaluations_select_regengine', 'rule_evaluations'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_rule_evaluations_select_regengine ON fsma.rule_evaluations
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_rule_evaluations_select_regengine ON fsma.rule_evaluations
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.rule_evaluations'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.rule_evaluations'::regclass
          AND polname = 'v128_rule_evaluations_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_rule_evaluations_insert_regengine', 'rule_evaluations'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_rule_evaluations_insert_regengine ON fsma.rule_evaluations
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_rule_evaluations_insert_regengine ON fsma.rule_evaluations
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.rule_evaluations'::regclass
              AND polname = 'v128_client_guard_rule_evaluations'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_rule_evaluations ON fsma.rule_evaluations
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_rule_evaluations ON fsma.rule_evaluations
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.submission_log') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.submission_log at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.submission_log'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.submission_log at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.submission_log'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.submission_log'::regclass
          AND polname = 'v128_submission_log_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_submission_log_select_regengine', 'submission_log'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_submission_log_select_regengine ON fsma.submission_log
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_submission_log_select_regengine ON fsma.submission_log
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context())
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.submission_log'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.submission_log'::regclass
          AND polname = 'v128_submission_log_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_submission_log_insert_regengine', 'submission_log'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_submission_log_insert_regengine ON fsma.submission_log
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_submission_log_insert_regengine ON fsma.submission_log
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context())
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.submission_log'::regclass
              AND polname = 'v128_client_guard_submission_log'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_submission_log ON fsma.submission_log
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_submission_log ON fsma.submission_log
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.tenant_suppliers') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.tenant_suppliers at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.tenant_suppliers'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.tenant_suppliers at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.tenant_suppliers'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.tenant_suppliers'::regclass
          AND polname = 'v128_tenant_suppliers_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_tenant_suppliers_select_regengine', 'tenant_suppliers'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_tenant_suppliers_select_regengine ON fsma.tenant_suppliers
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_tenant_suppliers_select_regengine ON fsma.tenant_suppliers
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.tenant_suppliers'::regclass
              AND polname = 'v128_client_guard_tenant_suppliers'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_tenant_suppliers ON fsma.tenant_suppliers
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_tenant_suppliers ON fsma.tenant_suppliers
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
    BEGIN
        IF to_regclass('fsma.traceability_events') IS NULL THEN
            RAISE EXCEPTION 'Expected fsma.traceability_events at v128';
        END IF;
        IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.traceability_events'::regclass) THEN
            RAISE EXCEPTION 'Expected RLS on fsma.traceability_events at v128';
        END IF;

IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.traceability_events'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'r')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.traceability_events'::regclass
          AND polname = 'v128_traceability_events_select_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_traceability_events_select_regengine', 'traceability_events'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_traceability_events_select_regengine ON fsma.traceability_events
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_traceability_events_select_regengine ON fsma.traceability_events
            FOR SELECT TO regengine
            USING (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.traceability_events'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'a')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.traceability_events'::regclass
          AND polname = 'v128_traceability_events_insert_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_traceability_events_insert_regengine', 'traceability_events'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_traceability_events_insert_regengine ON fsma.traceability_events
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_traceability_events_insert_regengine ON fsma.traceability_events
            FOR INSERT TO regengine
             WITH CHECK (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;


IF NOT EXISTS (
    SELECT 1 FROM pg_policy p
    JOIN pg_roles r ON r.rolname = 'regengine'
    WHERE p.polrelid = 'fsma.traceability_events'::regclass
      AND p.polpermissive
      AND p.polcmd IN ('*', 'w')
      AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
) THEN
    IF EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.traceability_events'::regclass
          AND polname = 'v128_traceability_events_update_regengine'
    ) THEN
        RAISE EXCEPTION 'policy "%" for table "%" already exists', 'v128_traceability_events_update_regengine', 'traceability_events'
            USING ERRCODE = '42710';
    END IF;
    EXECUTE $policy$
        DROP POLICY IF EXISTS v128_traceability_events_update_regengine ON fsma.traceability_events
    $policy$;
    EXECUTE $policy$
        CREATE POLICY v128_traceability_events_update_regengine ON fsma.traceability_events
            FOR UPDATE TO regengine
            USING (tenant_id = public.get_tenant_context()::text) WITH CHECK (tenant_id = public.get_tenant_context()::text)
    $policy$;
END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.traceability_events'::regclass
              AND polname = 'v128_client_guard_traceability_events'
        ) THEN
            EXECUTE $policy$
                DROP POLICY IF EXISTS v128_client_guard_traceability_events ON fsma.traceability_events
            $policy$;
            EXECUTE $policy$
                CREATE POLICY v128_client_guard_traceability_events ON fsma.traceability_events
                    AS RESTRICTIVE FOR ALL TO PUBLIC
                    USING ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
                    WITH CHECK ((tenant_id = public.get_tenant_context()::text) AND current_user NOT IN ('anon', 'authenticated'))
            $policy$;
        END IF;
    END
    $repair$;

DO $repair$
BEGIN
    IF to_regclass('fsma.cte_kdes_backfill_log_v059') IS NULL THEN
        RETURN;
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.cte_kdes_backfill_log_v059'::regclass) THEN
        RAISE EXCEPTION 'Expected RLS on fsma.cte_kdes_backfill_log_v059 at v128';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.cte_kdes_backfill_log_v059'::regclass
          AND polname = 'v128_client_guard_cte_kdes_backfill_log_v059'
    ) THEN
        EXECUTE $policy$
            DROP POLICY IF EXISTS v128_client_guard_cte_kdes_backfill_log_v059 ON fsma.cte_kdes_backfill_log_v059
        $policy$;
        EXECUTE $policy$
            CREATE POLICY v128_client_guard_cte_kdes_backfill_log_v059 ON fsma.cte_kdes_backfill_log_v059
                AS RESTRICTIVE FOR ALL TO PUBLIC
                USING (current_user NOT IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin'))
                WITH CHECK (current_user NOT IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin'))
        $policy$;
    END IF;
END
$repair$;

DO $repair$
BEGIN
    IF to_regclass('fsma.entity_merge_history') IS NULL THEN
        RAISE EXCEPTION 'Expected fsma.entity_merge_history at v128';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.entity_merge_history'::regclass) THEN
        RAISE EXCEPTION 'Expected RLS on fsma.entity_merge_history at v128';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.entity_merge_history'::regclass
          AND polname = 'v128_client_guard_entity_merge_history'
    ) THEN
        EXECUTE $policy$
            DROP POLICY IF EXISTS v128_client_guard_entity_merge_history ON fsma.entity_merge_history
        $policy$;
        EXECUTE $policy$
            CREATE POLICY v128_client_guard_entity_merge_history ON fsma.entity_merge_history
                AS RESTRICTIVE FOR ALL TO PUBLIC
                USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin'))
                WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin'))
        $policy$;
    END IF;
END
$repair$;

DO $repair$
BEGIN
    IF to_regclass('fsma.exception_attachments') IS NULL THEN
        RAISE EXCEPTION 'Expected fsma.exception_attachments at v128';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.exception_attachments'::regclass) THEN
        RAISE EXCEPTION 'Expected RLS on fsma.exception_attachments at v128';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.exception_attachments'::regclass
          AND polname = 'v128_client_guard_exception_attachments'
    ) THEN
        EXECUTE $policy$
            DROP POLICY IF EXISTS v128_client_guard_exception_attachments ON fsma.exception_attachments
        $policy$;
        EXECUTE $policy$
            CREATE POLICY v128_client_guard_exception_attachments ON fsma.exception_attachments
                AS RESTRICTIVE FOR ALL TO PUBLIC
                USING ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin'))
                WITH CHECK ((tenant_id = public.get_tenant_context()) AND current_user NOT IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin'))
        $policy$;
    END IF;
END
$repair$;

DO $repair$
BEGIN
    IF to_regclass('fsma.key_data_elements') IS NULL THEN
        RAISE EXCEPTION 'Expected fsma.key_data_elements at v128';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.key_data_elements'::regclass) THEN
        RAISE EXCEPTION 'Expected RLS on fsma.key_data_elements at v128';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid = 'fsma.key_data_elements'::regclass
          AND polname = 'v128_client_guard_key_data_elements'
    ) THEN
        EXECUTE $policy$
            DROP POLICY IF EXISTS v128_client_guard_key_data_elements ON fsma.key_data_elements
        $policy$;
        EXECUTE $policy$
            CREATE POLICY v128_client_guard_key_data_elements ON fsma.key_data_elements
                AS RESTRICTIVE FOR ALL TO PUBLIC
                USING (current_user NOT IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin'))
                WITH CHECK (current_user NOT IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin'))
        $policy$;
    END IF;
END
$repair$;

COMMIT;
;
