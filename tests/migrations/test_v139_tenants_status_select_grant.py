"""v139 / SEL-616: column-level SELECT (status) on public.tenants for regengine.

Structural checks cover the alembic + supabase pair and the v111 inventory.
The live scratch suite (when Postgres is available) proves regengine can read
``status``, cannot read other tenant columns, and has no table-level SELECT.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.migrations.scratch_db import scratch_database_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
V139 = (
    REPO_ROOT
    / "alembic/versions/20261028_e7a1c9d2f4b0_v139_tenants_status_select_grant.py"
)
V111 = REPO_ROOT / "alembic/versions/20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
SUPABASE = (
    REPO_ROOT / "supabase/migrations/20261028120000_v139_tenants_status_select_grant.sql"
)


def _load(path: Path, name: str | None = None):
    spec = importlib.util.spec_from_file_location(name or path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_grants_only_status_column_to_regengine(monkeypatch) -> None:
    migration = _load(V139)
    assert migration.down_revision == "a3f7ce361b0e"  # pragma: allowlist secret
    assert migration.revision == "e7a1c9d2f4b0"  # pragma: allowlist secret

    statements: list[str] = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=statements.append))
    migration.upgrade()

    assert len(statements) == 1
    body = statements[0]
    assert "GRANT SELECT (status) ON TABLE public.tenants TO regengine" in body
    # Column-level only — no table-level SELECT for regengine on tenants.
    assert not re.search(
        r"GRANT\s+SELECT\s+ON\s+(TABLE\s+)?public\.tenants\s+TO\s+regengine",
        body,
        flags=re.IGNORECASE,
    )
    assert "GRANT SELECT ON TABLE public.tenants TO regengine" not in body
    assert "regengine_sysadmin" not in body


def test_downgrade_revokes_the_same_column_grant(monkeypatch) -> None:
    migration = _load(V139)
    statements: list[str] = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=statements.append))
    migration.downgrade()

    assert len(statements) == 1
    body = statements[0]
    assert "REVOKE SELECT (status) ON TABLE public.tenants FROM regengine" in body
    assert not re.search(
        r"REVOKE\s+SELECT\s+ON\s+(TABLE\s+)?public\.tenants\s+FROM\s+regengine",
        body,
        flags=re.IGNORECASE,
    )


def test_supabase_pair_matches_column_grant() -> None:
    sql = SUPABASE.read_text()
    assert "GRANT SELECT (status) ON TABLE public.tenants TO regengine" in sql
    assert not re.search(
        r"GRANT\s+SELECT\s+ON\s+(TABLE\s+)?public\.tenants\s+TO\s+regengine",
        sql,
        flags=re.IGNORECASE,
    )
    assert "SEL-616" in sql
    assert "e7a1c9d2f4b0" in sql or "v139" in sql.lower()  # pragma: allowlist secret


def test_v111_inventory_lists_id_and_status_only_no_table_select() -> None:
    """Cutover must keep the column grant and must not promote table SELECT."""
    # Load without executing alembic.op side effects: read source + ast/exec of
    # the grant dicts only is fragile; import via exec after stubbing op.
    import types
    import sys

    stub = types.ModuleType("alembic")
    stub_op = types.ModuleType("alembic.op")
    stub.op = stub_op
    sys.modules["alembic"] = stub
    sys.modules["alembic.op"] = stub_op
    try:
        mod = _load(V111, f"v111_inventory_{uuid4().hex}")
    finally:
        sys.modules.pop("alembic.op", None)
        sys.modules.pop("alembic", None)

    assert mod.REGENGINE_COLUMN_GRANTS["public.tenants"]["SELECT"] == ("id", "status")
    # Runtime must not have table-level SELECT/INSERT/UPDATE/DELETE on tenants.
    assert "public.tenants" not in mod.REGENGINE_TABLE_GRANTS
    # Sysadmin still owns table-level SELECT+INSERT; that is intentional.
    assert mod.REGENGINE_SYSADMIN_TABLE_GRANTS["public.tenants"] == ("SELECT", "INSERT")


def _bootstrap_tenants_and_role(engine) -> None:
    """Scratch-DB only. Never DROP the cluster-wide ``regengine`` role."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        conn.execute(
            text(
                """
                CREATE TABLE public.tenants (
                    id uuid primary key default gen_random_uuid(),
                    name text not null,
                    slug text not null unique,
                    status text not null default 'active',
                    settings jsonb not null default '{}'::jsonb
                )
                """
            )
        )
        # Role is cluster-wide and may own other local DBs — create if missing
        # only; never DROP. Privileges below are scoped to this scratch table.
        conn.execute(
            text(
                """
                DO $role$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                        CREATE ROLE regengine NOINHERIT LOGIN;
                    END IF;
                END
                $role$;
                """
            )
        )
        # Start from a clean ACL on this scratch table, then simulate post-v111:
        # column SELECT (id) only, no table-level SELECT.
        conn.execute(text("REVOKE ALL ON TABLE public.tenants FROM PUBLIC, regengine"))
        conn.execute(
            text(
                """
                DO $col$
                DECLARE
                    col_name text;
                BEGIN
                    FOR col_name IN
                        SELECT a.attname
                          FROM pg_attribute AS a
                          JOIN pg_class AS c ON c.oid = a.attrelid
                          JOIN pg_namespace AS n ON n.oid = c.relnamespace
                         WHERE n.nspname = 'public'
                           AND c.relname = 'tenants'
                           AND a.attnum > 0
                           AND NOT a.attisdropped
                    LOOP
                        EXECUTE format(
                            'REVOKE ALL (%I) ON TABLE public.tenants FROM PUBLIC, regengine',
                            col_name
                        );
                    END LOOP;
                END
                $col$;
                """
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO regengine"))
        conn.execute(text("GRANT SELECT (id) ON TABLE public.tenants TO regengine"))


def test_live_scratch_regengine_reads_status_only_no_table_select() -> None:
    """Apply v139 on a disposable DB and prove the column-only contract."""
    db_name = "inc2_scratch_v139_" + uuid4().hex[:12]
    migration = _load(V139, f"v139_live_{uuid4().hex}")

    with scratch_database_engine(db_name) as engine:
        _bootstrap_tenants_and_role(engine)

        # Apply upgrade through the migration's op.execute path.
        with engine.begin() as conn:

            class _Op:
                @staticmethod
                def execute(statement: str) -> None:
                    conn.execute(text(statement))

            migration.op = _Op  # type: ignore[attr-defined]
            migration.upgrade()

        tenant_id = uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO public.tenants (id, name, slug, status, settings)
                    VALUES (
                        CAST(:id AS uuid),
                        'Scratch tenant',
                        :slug,
                        'active',
                        CAST(:settings AS jsonb)
                    )
                    """
                ),
                {
                    "id": str(tenant_id),
                    "slug": f"scratch-{tenant_id.hex[:8]}",
                    "settings": "{}",
                },
            )

        with engine.connect() as conn:
            # Column privileges: id + status only.
            cols = {
                row.column_name
                for row in conn.execute(
                    text(
                        """
                        SELECT column_name
                          FROM information_schema.column_privileges
                         WHERE grantee = 'regengine'
                           AND table_schema = 'public'
                           AND table_name = 'tenants'
                           AND privilege_type = 'SELECT'
                        """
                    )
                )
            }
            assert cols == {"id", "status"}

            # No table-level SELECT (or any other table privilege) for regengine.
            table_privs = {
                row.privilege_type
                for row in conn.execute(
                    text(
                        """
                        SELECT privilege_type
                          FROM information_schema.table_privileges
                         WHERE grantee = 'regengine'
                           AND table_schema = 'public'
                           AND table_name = 'tenants'
                        """
                    )
                )
            }
            assert table_privs == set()
            assert "SELECT" not in table_privs

            # relacl must not carry a table-level SELECT for regengine either.
            relacl_select = conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                          FROM pg_class AS c
                          JOIN pg_namespace AS n ON n.oid = c.relnamespace
                          CROSS JOIN LATERAL aclexplode(c.relacl) AS acl
                          JOIN pg_roles AS r ON r.oid = acl.grantee
                         WHERE n.nspname = 'public'
                           AND c.relname = 'tenants'
                           AND r.rolname = 'regengine'
                           AND acl.privilege_type = 'SELECT'
                    )
                    """
                )
            ).scalar_one()
            assert relacl_select is False

        # Live SET ROLE: status readable; name/settings denied.
        # Each denied statement gets its own connection so a failed query
        # does not poison the next assertion with InFailedSqlTransaction.
        with engine.connect() as conn:
            conn.execute(text("SET ROLE regengine"))
            status = conn.execute(
                text("SELECT status FROM public.tenants WHERE id = :id"),
                {"id": str(tenant_id)},
            ).scalar_one()
            assert status == "active"
            conn.execute(text("RESET ROLE"))

        for denied_sql in (
            "SELECT name FROM public.tenants",
            "SELECT settings FROM public.tenants",
            "SELECT * FROM public.tenants",
        ):
            with engine.connect() as conn:
                conn.execute(text("SET ROLE regengine"))
                with pytest.raises(Exception, match="permission denied"):
                    conn.execute(text(denied_sql))

        # Downgrade removes status but leaves the pre-existing id grant.
        with engine.begin() as conn:

            class _OpDown:
                @staticmethod
                def execute(statement: str) -> None:
                    conn.execute(text(statement))

            migration.op = _OpDown  # type: ignore[attr-defined]
            migration.downgrade()

        with engine.connect() as conn:
            cols_after = {
                row.column_name
                for row in conn.execute(
                    text(
                        """
                        SELECT column_name
                          FROM information_schema.column_privileges
                         WHERE grantee = 'regengine'
                           AND table_schema = 'public'
                           AND table_name = 'tenants'
                           AND privilege_type = 'SELECT'
                        """
                    )
                )
            }
            assert cols_after == {"id"}
