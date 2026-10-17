"""Restore runtime RLS policies on FSMA tables.

The production catalog export showed 22 RLS-enabled tables without
policies.  The v111 runtime ACL permits regengine on 18 of them and permits
regengine_sysadmin only a tenant-scoped SELECT on ingestion_runs.  The other
four have no runtime grant and remain closed.

Existing policies are left intact on databases where earlier migrations
installed them.  A restrictive policy blocks the client roles even if one
of those older permissive policies targets PUBLIC.  On ingestion_runs, which
the boot-time runtime catalog canary fingerprints, that guard is created
only where a permissive policy reaches a denied role (see _CANARY_TABLES).

Revision ID: a5e7c9b2d341
Revises: ed902d03df45
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a5e7c9b2d341"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "ed902d03df45"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror only the operations granted by v111's closed runtime ACL inventory.
# No GRANT is issued here.  The control-plane role reads only ingestion_runs.
_RUNTIME_ACCESS = {
    "canonical_entities": ("SELECT",),
    "cte_events": ("SELECT", "INSERT", "DELETE"),
    "cte_kdes": ("SELECT", "INSERT"),
    "entity_aliases": ("SELECT",),
    "exception_cases": ("SELECT", "INSERT", "UPDATE"),
    "exception_comments": ("SELECT", "INSERT"),
    "exception_signoffs": ("SELECT", "INSERT"),
    "fda_export_log": ("SELECT", "INSERT"),
    "hash_chain": ("SELECT", "INSERT"),
    "identity_review_queue": ("SELECT",),
    "ingestion_runs": ("SELECT", "INSERT", "UPDATE"),
    "request_cases": ("SELECT", "INSERT", "UPDATE"),
    "request_signoffs": ("SELECT", "INSERT"),
    "response_packages": ("SELECT", "INSERT"),
    "rule_evaluations": ("SELECT", "INSERT"),
    "submission_log": ("SELECT", "INSERT"),
    "tenant_suppliers": ("SELECT",),
    "traceability_events": ("SELECT", "INSERT", "UPDATE"),
}

# Migration-only or legacy tables with no v111 runtime ACL.  In particular,
# cte_kdes_backfill_log_v059 is a migration quarantine log, not an app table.
_CLOSED_TABLES = (
    "cte_kdes_backfill_log_v059",
    "entity_merge_history",
    "exception_attachments",
    "key_data_elements",
)
_TENANTLESS_CLOSED_TABLES = frozenset({"cte_kdes_backfill_log_v059", "key_data_elements"})

_TABLES = tuple(_RUNTIME_ACCESS) + _CLOSED_TABLES
_TEXT_TENANT_TABLES = frozenset(
    {
        "cte_events",
        "cte_kdes",
        "fda_export_log",
        "hash_chain",
        "ingestion_runs",
        "tenant_suppliers",
        "traceability_events",
    }
)
_COMMAND_CODES = {"SELECT": "r", "INSERT": "a", "UPDATE": "w", "DELETE": "d"}

# The runtime catalog canary (_RUNTIME_CUTOVER_CANARY_SQL in
# services/shared/database.py) fingerprints every policy on its required
# relations whose roles include the runtime role or PUBLIC.  ingestion_runs
# is the only v128 table on that list.  A TO PUBLIC guard there changes both
# runtime fingerprints, and containers then refuse to boot against the
# migrated database.  On these tables the guard is created only where a
# permissive policy can reach a denied role.  Where none can, RLS already
# denies those roles direct access by default.  A view owned by another role
# is checked as its owner and bypasses the guard either way.
_CANARY_TABLES = frozenset({"ingestion_runs"})

# CREATE POLICY takes ACCESS EXCLUSIVE, and the deploy runs the whole chain in
# one transaction while the previous container still serves.  As in v126, a
# busy table fails the deploy fast and rolls back instead of queueing every
# query on the tables already locked.
_LOCK_TIMEOUT = "10s"


def _tenant_predicate(table: str) -> str:
    cast = "::text" if table in _TEXT_TENANT_TABLES else ""
    return f"tenant_id = public.get_tenant_context(){cast}"


def _execute(table: str, statement: str) -> str:
    # The production catalog stores tenant_id as text on _TEXT_TENANT_TABLES,
    # but a database built by this alembic chain stores uuid there.  On a uuid
    # column the ::text cast would fail with uuid = text, so it is dropped at
    # run time (tenant_cast, set in upgrade()).  Text columns are unchanged.
    if table not in _TEXT_TENANT_TABLES:
        return f"EXECUTE $policy${statement}$policy$;"
    return f"EXECUTE replace($policy${statement}$policy$, '()::text', tenant_cast);"


def _app_policy(table: str, command: str, role: str) -> str:
    name = f"v128_{table}_{command.lower()}_{role}"
    tenant = _tenant_predicate(table)
    using = f"USING ({tenant})" if command != "INSERT" else ""
    check = f"WITH CHECK ({tenant})" if command in ("INSERT", "UPDATE") else ""
    create = _execute(
        table,
        f"""
                CREATE POLICY {name} ON fsma.{table}
                    FOR {command} TO {role}
                    {using} {check}
            """,
    )
    return f"""
        IF NOT EXISTS (
            SELECT 1 FROM pg_policy p
            JOIN pg_roles r ON r.rolname = '{role}'
            WHERE p.polrelid = 'fsma.{table}'::regclass
              AND p.polpermissive
              AND p.polcmd IN ('*', '{_COMMAND_CODES[command]}')
              AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
        ) AND NOT EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = 'fsma.{table}'::regclass
              AND polname = '{name}'
        ) THEN
            {create}
        END IF;
    """


def _app_operations(table: str) -> tuple[tuple[str, str], ...]:
    operations = tuple((command, "regengine") for command in _RUNTIME_ACCESS.get(table, ()))
    if table == "ingestion_runs":
        operations += (("SELECT", "regengine_sysadmin"),)
    return operations


def upgrade() -> None:
    for table in _TABLES:
        # Avoid OR-ing another permissive policy into an existing grant for
        # the same role/command.  A partial policy loss still gets repaired.
        app_repair = "\n".join(_app_policy(table, command, role) for command, role in _app_operations(table))
        # A restrictive policy never supplies access by itself.  It also
        # blocks direct client access where a legacy FOR ALL TO PUBLIC policy
        # survives from the old migration chain.  Closed tables additionally
        # deny both runtime roles, even if a historical policy still exists.
        denied_roles = ["anon", "authenticated"]
        if table in _CLOSED_TABLES:
            denied_roles += ["regengine", "regengine_sysadmin"]
        guard = f"v128_client_guard_{table}"
        denied = ", ".join(f"'{role}'" for role in denied_roles)
        role_check = f"current_user NOT IN ({denied})"
        # RLS applies a policy to PUBLIC or to roles whose privileges the
        # current user has (pg_has_role USAGE).
        guard_reaches = ""
        if table in _CANARY_TABLES:
            guard_reaches = f"""
                  AND EXISTS (
                    SELECT 1 FROM pg_policy p
                    WHERE p.polrelid = 'fsma.{table}'::regclass
                      AND p.polpermissive
                      AND (0::oid = ANY(p.polroles) OR EXISTS (
                        SELECT 1 FROM pg_roles d, unnest(p.polroles) AS t(role_oid)
                        WHERE d.rolname IN ({denied})
                          AND t.role_oid <> 0
                          AND pg_has_role(d.oid, t.role_oid, 'USAGE')
                      ))
                  )"""
        predicate = (
            role_check if table in _TENANTLESS_CLOSED_TABLES else f"({_tenant_predicate(table)}) AND {role_check}"
        )
        # v078 creates this quarantine log only when a legacy KDE conversion
        # is needed.  Every other listed table is required at this head.
        restore_lock_timeout = "PERFORM set_config('lock_timeout', previous_lock_timeout, true);"
        missing_table = (
            f"{restore_lock_timeout} RETURN;"
            if table == "cte_kdes_backfill_log_v059"
            else f"RAISE EXCEPTION 'Expected fsma.{table} at v128';"
        )
        declare = "DECLARE previous_lock_timeout text := pg_catalog.current_setting('lock_timeout');"
        set_cast = ""
        if table in _TEXT_TENANT_TABLES:
            declare += " tenant_cast text;"
            set_cast = f"""
                SELECT CASE WHEN atttypid = 'uuid'::regtype THEN '()' ELSE '()::text' END
                INTO tenant_cast FROM pg_attribute
                WHERE attrelid = 'fsma.{table}'::regclass AND attname = 'tenant_id';"""
        guard_sql = f"""
                        CREATE POLICY {guard} ON fsma.{table}
                            AS RESTRICTIVE FOR ALL TO PUBLIC
                            USING ({predicate})
                            WITH CHECK ({predicate})
                    """
        op.execute(
            f"""
            DO $repair$
            {declare}
            BEGIN
                PERFORM set_config('lock_timeout', '{_LOCK_TIMEOUT}', true);
                IF to_regclass('fsma.{table}') IS NULL THEN
                    {missing_table}
                END IF;
                IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.{table}'::regclass) THEN
                    RAISE EXCEPTION 'Expected RLS on fsma.{table} at v128';
                END IF;{set_cast}
                {app_repair}
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policy
                    WHERE polrelid = 'fsma.{table}'::regclass
                      AND polname = '{guard}'
                ) THEN
                    {_execute(table, guard_sql)}
                END IF;
                {restore_lock_timeout}
            END
            $repair$;
            """
        )


def downgrade() -> None:
    # Drop only v128's policies.  Earlier migrations' policies, where
    # present, remain untouched; no table ACLs or columns were changed.
    for table in reversed(_TABLES):
        drops = "\n".join(
            f"EXECUTE 'DROP POLICY IF EXISTS v128_{table}_{command.lower()}_{role} ON fsma.{table}';"
            for command, role in _app_operations(table)
        )
        op.execute(
            f"""
            DO $rollback$
            BEGIN
                IF to_regclass('fsma.{table}') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS v128_client_guard_{table} ON fsma.{table}';
                    {drops}
                END IF;
            END
            $rollback$;
            """
        )
