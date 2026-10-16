"""Restore runtime RLS policies on tenant-scoped FSMA tables.

The production catalog export showed 22 RLS-enabled tables without
policies.  The v111 runtime ACL permits regengine on 18 of them and permits
regengine_sysadmin only a tenant-scoped SELECT on ingestion_runs.  The other
four have no runtime grant and remain closed.

Existing policies are left intact on databases where earlier migrations
installed them.  A restrictive policy blocks the client roles even if one
of those older permissive policies targets PUBLIC.

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

_TABLES = tuple(_RUNTIME_ACCESS) + _CLOSED_TABLES
_TENANT = "tenant_id = get_tenant_context()"
_COMMAND_CODES = {"SELECT": "r", "INSERT": "a", "UPDATE": "w", "DELETE": "d"}


def _app_policy(table: str, command: str, role: str) -> str:
    name = f"v128_{table}_{command.lower()}_{role}"
    using = f"USING ({_TENANT})" if command != "INSERT" else ""
    check = f"WITH CHECK ({_TENANT})" if command in ("INSERT", "UPDATE") else ""
    return f"""
        IF NOT EXISTS (
            SELECT 1 FROM pg_policy p
            JOIN pg_roles r ON r.rolname = '{role}'
            WHERE p.polrelid = 'fsma.{table}'::regclass
              AND p.polpermissive
              AND p.polcmd IN ('*', '{_COMMAND_CODES[command]}')
              AND (0::oid = ANY(p.polroles) OR r.oid = ANY(p.polroles))
        ) THEN
            EXECUTE $policy$
                CREATE POLICY {name} ON fsma.{table}
                    FOR {command} TO {role}
                    {using} {check}
            $policy$;
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
        role_check = "current_user NOT IN (" + ", ".join(f"'{role}'" for role in denied_roles) + ")"
        predicate = f"({_TENANT}) AND {role_check}"
        # v078 creates this quarantine log only when a legacy KDE conversion
        # is needed.  Every other listed table is required at this head.
        missing_table = (
            "RETURN;" if table == "cte_kdes_backfill_log_v059" else f"RAISE EXCEPTION 'Expected fsma.{table} at v128';"
        )
        op.execute(
            f"""
            DO $repair$
            BEGIN
                IF to_regclass('fsma.{table}') IS NULL THEN
                    {missing_table}
                END IF;
                IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'fsma.{table}'::regclass) THEN
                    RAISE EXCEPTION 'Expected RLS on fsma.{table} at v128';
                END IF;
                {app_repair}
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policy
                    WHERE polrelid = 'fsma.{table}'::regclass
                      AND polname = '{guard}'
                ) THEN
                    EXECUTE $policy$
                        CREATE POLICY {guard} ON fsma.{table}
                            AS RESTRICTIVE FOR ALL TO PUBLIC
                            USING ({predicate})
                            WITH CHECK ({predicate})
                    $policy$;
                END IF;
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
