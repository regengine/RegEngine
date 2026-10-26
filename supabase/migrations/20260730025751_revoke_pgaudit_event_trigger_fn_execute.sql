-- pgaudit's event-trigger functions are exposed over PostgREST RPC via the
-- default PUBLIC EXECUTE grant. Event triggers fire without consulting the
-- invoker's EXECUTE privilege, so revoking is safe.
REVOKE EXECUTE ON FUNCTION public.pgaudit_ddl_command_end() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.pgaudit_sql_drop() FROM PUBLIC, anon, authenticated;;
