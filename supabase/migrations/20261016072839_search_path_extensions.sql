-- Migration 0: put schema `extensions` on the app roles' search_path before Migration A.
-- Migration A moves pg_trgm, hypopg and index_advisor from public to extensions. Unqualified
-- calls (similarity(), %, word_similarity(), hypopg_*(), index_advisor()) only resolve if
-- `extensions` is on search_path, so this runs first.
-- regengine and regengine_sysadmin currently have no role-level search_path (effective
-- "$user", public); this sets "$user", public, extensions. Takes effect on new sessions.
-- authenticator: only pgrst.db_extra_search_path is changed ('public, fsma' -> 'public, fsma,
-- extensions'); its other role settings are left untouched. NOTIFY makes PostgREST reload it.
-- Generated 2026-10-16 from TASK2.md. Not applied.

ALTER ROLE regengine SET search_path = "$user", public, extensions;
ALTER ROLE regengine_sysadmin SET search_path = "$user", public, extensions;
ALTER ROLE authenticator SET pgrst.db_extra_search_path = 'public, fsma, extensions';
-- search_path alone does not let these roles resolve objects in a schema they lack USAGE on.
GRANT USAGE ON SCHEMA extensions TO regengine, regengine_sysadmin;

NOTIFY pgrst, 'reload config';

-- Rollback (run only after reverting Migration A):
-- ALTER ROLE regengine RESET search_path;
-- ALTER ROLE regengine_sysadmin RESET search_path;
-- ALTER ROLE authenticator SET pgrst.db_extra_search_path = 'public, fsma';
-- REVOKE USAGE ON SCHEMA extensions FROM regengine, regengine_sysadmin;
-- NOTIFY pgrst, 'reload config';
;
