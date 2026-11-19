"""v144: client tenant/catalog access follows authenticated memberships.

The behavioral cases use the existing disposable-database helper and reproduce
the observed pre-migration policies. A second fixture variant retains v111's
backend policies to prove the repair also works on Alembic-managed databases.
No application configuration or hosted database is used by this module.
"""

from __future__ import annotations

import importlib.util
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.migrations.scratch_db import scratch_database_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "alembic/versions/20261119_d8f3a1c6b902_v144_anon_tenant_catalog_rls.py"
MIRROR = REPO_ROOT / "supabase/migrations/20261119120000_v144_anon_tenant_catalog_rls.sql"
REVISION = "d8f3a1c6b902"  # pragma: allowlist secret
PARENT_REVISION = "c4a9d2e761b0"  # pragma: allowlist secret
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
SYSTEM_TENANT = "00000000-0000-0000-0000-000000000001"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_WITHOUT_MEMBERSHIP = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ROLES = ("anon", "authenticated", "regengine", "regengine_sysadmin", "service_role")
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES")


def _load():
    spec = importlib.util.spec_from_file_location(MIGRATION.stem, MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _render(direction: str) -> str:
    migration = _load()
    statements: list[str] = []
    migration.op = SimpleNamespace(execute=statements.append)
    getattr(migration, direction)()
    return "\n".join(statements)


def _normalized_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", sql)).strip()


def test_revision_and_supabase_mirror_match_executed_upgrade():
    migration = _load()
    assert migration.revision == REVISION
    assert migration.down_revision == PARENT_REVISION
    mirror = MIRROR.read_text()
    assert re.search(rf"alembic-revision:\s*{REVISION}\b", mirror, re.IGNORECASE)
    assert _normalized_sql(mirror) == _normalized_sql(_render("upgrade"))


def test_upgrade_establishes_membership_self_read_before_client_reads():
    sql = _render("upgrade")
    self_read = sql.index("CREATE POLICY memberships_authenticated_self_read")
    assert self_read < sql.index("CREATE POLICY tenants_authenticated_member_read")
    assert self_read < sql.index("CREATE POLICY product_catalog_authenticated_member_read")
    assert "DROP POLICY IF EXISTS tenants_read_all ON public.tenants" in sql
    assert "DROP POLICY IF EXISTS public_read_product_catalog ON public.product_catalog" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert SYSTEM_TENANT not in sql
    assert not re.search(r"GRANT\s+SELECT\s+ON\s+(?:TABLE\s+)?public\.tenants\s+TO\s+(?:anon|regengine)\b", sql, re.I)
    assert not re.search(r"(?:DROP|ALTER)\s+POLICY\s+service_role_full_access\b", sql, re.I)
    assert not re.search(r"(?:GRANT|REVOKE)[^;]*\bservice_role\b", sql, re.I)


def test_supabase_only_objects_are_guarded_without_skipping_tenant_hardening():
    sql = _render("upgrade")
    assert "to_regclass('public.product_catalog') IS NOT NULL" in sql
    assert "rolname = 'authenticated'" in sql
    assert "rolname = 'anon'" in sql
    # Missing optional client roles/catalog must not silently skip hardening
    # the tenants and memberships tables shared with app-only databases.
    assert not re.search(r"\bRETURN\s*;", sql, re.IGNORECASE)


def _apply(conn, direction: str) -> None:
    migration = _load()
    migration.op = SimpleNamespace(execute=lambda statement: conn.execute(text(statement)))
    getattr(migration, direction)()


def _snapshot(conn):
    """Capture policy definitions, row-security flags, and table/column ACLs."""
    statements = (
        """
        SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check
          FROM pg_policies
         WHERE schemaname = 'public'
           AND tablename IN ('tenants', 'memberships', 'product_catalog')
         ORDER BY tablename, policyname
        """,
        """
        SELECT relname, relrowsecurity, relforcerowsecurity
          FROM pg_class
         WHERE oid IN (to_regclass('public.tenants'), to_regclass('public.memberships'),
                       to_regclass('public.product_catalog'))
         ORDER BY relname
        """,
        """
        SELECT c.relname, a.grantee, a.privilege_type, a.is_grantable
          FROM pg_class AS c CROSS JOIN LATERAL aclexplode(c.relacl) AS a
         WHERE c.oid IN (to_regclass('public.tenants'), to_regclass('public.memberships'),
                         to_regclass('public.product_catalog'))
         ORDER BY 1, 2, 3, 4
        """,
        """
        SELECT c.relname, col.attname, a.grantee, a.privilege_type, a.is_grantable
          FROM pg_class AS c
          JOIN pg_attribute AS col ON col.attrelid = c.oid
          CROSS JOIN LATERAL aclexplode(col.attacl) AS a
         WHERE c.oid IN (to_regclass('public.tenants'), to_regclass('public.memberships'),
                         to_regclass('public.product_catalog'))
         ORDER BY 1, 2, 3, 4, 5
        """,
    )
    return tuple(tuple(tuple(row) for row in conn.execute(text(sql))) for sql in statements)


def _bootstrap(conn, *, with_v111_policies: bool) -> None:
    # Roles are cluster-wide: create missing roles only; never alter or drop
    # existing ones on a shared local/CI server. All grants are scratch-local.
    for role in ROLES:
        conn.execute(
            text(f"""
            DO $role$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role} NOLOGIN;
                END IF;
            END $role$;
        """)
        )
    unsafe_roles = (
        conn.execute(
            text("""
        SELECT rolname FROM pg_roles
         WHERE rolname IN ('anon', 'authenticated', 'regengine', 'regengine_sysadmin')
           AND (rolsuper OR rolbypassrls)
    """)
        )
        .scalars()
        .all()
    )
    assert not unsafe_roles, f"client/backend test roles must enforce RLS: {unsafe_roles}"
    conn.execute(
        text("""
        CREATE SCHEMA auth;
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $fn$
            SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid
        $fn$;
        CREATE FUNCTION public.get_tenant_context() RETURNS uuid
        LANGUAGE plpgsql STABLE AS $fn$
        DECLARE tenant text;
        BEGIN
            tenant := NULLIF(current_setting('app.tenant_id', true), '');
            IF tenant IS NULL THEN
                RAISE EXCEPTION 'tenant context required' USING ERRCODE = '42501';
            END IF;
            RETURN tenant::uuid;
        END $fn$;
        CREATE TABLE public.tenants (
            id uuid PRIMARY KEY, name text NOT NULL, slug text NOT NULL UNIQUE,
            status text NOT NULL DEFAULT 'active', settings jsonb NOT NULL DEFAULT '{}'
        );
        CREATE TABLE public.memberships (
            tenant_id uuid NOT NULL REFERENCES public.tenants(id),
            user_id uuid NOT NULL, PRIMARY KEY (tenant_id, user_id)
        );
        CREATE TABLE public.product_catalog (id text PRIMARY KEY, tenant_id text, name text);
        ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.tenants FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.memberships ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.memberships FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.product_catalog ENABLE ROW LEVEL SECURITY;
        CREATE POLICY tenants_read_all ON public.tenants FOR SELECT TO PUBLIC USING (true);
        CREATE POLICY tenants_write_own ON public.tenants FOR UPDATE TO PUBLIC
            USING (id = public.get_tenant_context())
            WITH CHECK (id = public.get_tenant_context());
        CREATE POLICY tenant_isolation_memberships ON public.memberships FOR ALL TO PUBLIC
            USING (tenant_id = public.get_tenant_context());
        CREATE POLICY public_read_product_catalog ON public.product_catalog
            FOR SELECT TO anon, authenticated USING (true);
        CREATE POLICY service_role_full_access ON public.product_catalog
            FOR ALL TO service_role USING (true) WITH CHECK (true);
        GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, regengine,
            regengine_sysadmin, service_role;
        GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES
            ON public.tenants TO anon, authenticated, service_role;
        GRANT SELECT ON public.product_catalog TO anon, authenticated;
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.product_catalog TO service_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.memberships
            TO authenticated, regengine, regengine_sysadmin;
        GRANT SELECT (id, status) ON public.tenants TO regengine;
        GRANT SELECT, INSERT ON public.tenants TO regengine_sysadmin;
        GRANT UPDATE (name, settings) ON public.tenants TO regengine_sysadmin;
    """)
    )
    if with_v111_policies:
        conn.execute(
            text("""
            CREATE POLICY tenants_runtime_own ON public.tenants FOR SELECT TO regengine
                USING (id::text = NULLIF(current_setting('app.tenant_id', true), ''));
            CREATE POLICY tenants_sysadmin_select ON public.tenants FOR SELECT TO regengine_sysadmin
                USING (current_user = 'regengine_sysadmin'
                    AND current_setting('regengine.is_sysadmin', true) = 'true');
            CREATE POLICY tenants_sysadmin_tenant_select ON public.tenants FOR SELECT TO regengine_sysadmin
                USING (current_user = 'regengine_sysadmin'
                    AND id::text = NULLIF(current_setting('app.tenant_id', true), ''));
            CREATE POLICY tenants_sysadmin_insert ON public.tenants FOR INSERT TO regengine_sysadmin
                WITH CHECK (current_user = 'regengine_sysadmin'
                    AND current_setting('regengine.is_sysadmin', true) = 'true');
            CREATE POLICY tenants_sysadmin_update ON public.tenants FOR UPDATE TO regengine_sysadmin
                USING (current_user = 'regengine_sysadmin'
                    AND current_setting('regengine.is_sysadmin', true) = 'true')
                WITH CHECK (current_user = 'regengine_sysadmin'
                    AND current_setting('regengine.is_sysadmin', true) = 'true');
        """)
        )
    for tenant, name in ((TENANT_A, "A"), (TENANT_B, "B"), (SYSTEM_TENANT, "System")):
        conn.execute(
            text("INSERT INTO public.tenants (id, name, slug) VALUES (:id, :name, :name)"), {"id": tenant, "name": name}
        )
    for tenant, user in ((TENANT_A, USER_A), (TENANT_A, USER_B), (TENANT_B, USER_B)):
        conn.execute(text("INSERT INTO public.memberships VALUES (:tenant, :user)"), {"tenant": tenant, "user": user})
    for product, tenant in (
        ("a", TENANT_A),
        ("b", TENANT_B),
        ("system", SYSTEM_TENANT),
        ("malformed", "not-a-uuid"),
        ("null", None),
    ):
        conn.execute(
            text("INSERT INTO public.product_catalog VALUES (:id, :tenant, :id)"), {"id": product, "tenant": tenant}
        )


@pytest.fixture(scope="module", params=[False, True], ids=["observed", "existing-v111"])
def hardened_db(request):
    with scratch_database_engine("v144_scratch_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            _bootstrap(conn, with_v111_policies=request.param)
            before = _snapshot(conn)
            _apply(conn, "upgrade")
            after = _snapshot(conn)
        yield SimpleNamespace(engine=engine, before=before, after=after, with_v111=request.param)


@contextmanager
def _as_role(db, role: str, *, user: str | None = None, tenant: str | None = None, sysadmin: bool = False):
    assert role in ROLES
    # A fresh physical connection distinguishes an unset GUC from a previously
    # SET LOCAL value restored to the empty string after transaction rollback.
    db.engine.dispose()
    with db.engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text(f"SET LOCAL ROLE {role}"))
            for setting, value in (
                ("request.jwt.claim.sub", user),
                ("app.tenant_id", tenant),
                ("regengine.is_sysadmin", "true" if sysadmin else None),
            ):
                if value is not None:
                    conn.execute(
                        text("SELECT set_config(:setting, :value, true)"), {"setting": setting, "value": value}
                    )
            yield conn
        finally:
            transaction.rollback()


@pytest.mark.parametrize("table", ["tenants", "product_catalog"])
def test_anon_cannot_select_live_rows(hardened_db, table):
    with _as_role(hardened_db, "anon", user=USER_A, tenant=TENANT_A, sysadmin=True) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text(f"SELECT * FROM public.{table}")).all()


def test_client_and_backend_tenant_grants_remain_least_privilege(hardened_db):
    with hardened_db.engine.connect() as conn:
        for role, expected in (("anon", set()), ("authenticated", {"SELECT"}), ("regengine", set())):
            actual = {
                privilege
                for privilege in PRIVILEGES
                if conn.execute(
                    text("SELECT has_table_privilege(:role, 'public.tenants', :privilege)"),
                    {"role": role, "privilege": privilege},
                ).scalar_one()
            }
            assert actual == expected
        columns = set(
            conn.execute(
                text("""
            SELECT column_name FROM information_schema.column_privileges
             WHERE grantee = 'regengine' AND table_schema = 'public'
               AND table_name = 'tenants' AND privilege_type = 'SELECT'
        """)
            ).scalars()
        )
        assert columns == {"id", "status"}
        policies = {
            row.policyname: row
            for row in conn.execute(
                text("""
            SELECT policyname, roles, cmd, qual, with_check FROM pg_policies
             WHERE schemaname = 'public' AND tablename = 'memberships'
        """)
            )
        }
        backend = policies["tenant_isolation_memberships"]
        assert set(backend.roles) == {"regengine", "regengine_sysadmin"}
        assert backend.cmd == "ALL"
        assert "get_tenant_context()" in backend.qual
        self_read = policies["memberships_authenticated_self_read"]
        assert set(self_read.roles) == {"authenticated"}
        assert self_read.cmd == "SELECT"
        assert self_read.with_check is None


@pytest.mark.parametrize("context", [None, "", TENANT_B, SYSTEM_TENANT])
def test_membership_self_read_does_not_require_or_trust_tenant_context(hardened_db, context):
    with _as_role(hardened_db, "authenticated", user=USER_A, tenant=context, sysadmin=True) as conn:
        rows = conn.execute(text("SELECT tenant_id::text, user_id::text FROM public.memberships")).all()
        assert rows == [(TENANT_A, USER_A)]


@pytest.mark.parametrize(
    "user,expected_tenants,expected_products",
    [
        (USER_A, {TENANT_A}, {"a"}),
        (USER_B, {TENANT_A, TENANT_B}, {"a", "b"}),
        (USER_WITHOUT_MEMBERSHIP, set(), set()),
        (None, set(), set()),
    ],
)
@pytest.mark.parametrize("context", [None, "", SYSTEM_TENANT])
def test_authenticated_reads_follow_membership_only(hardened_db, user, expected_tenants, expected_products, context):
    with _as_role(hardened_db, "authenticated", user=user, tenant=context, sysadmin=True) as conn:
        assert set(conn.execute(text("SELECT id::text FROM public.tenants")).scalars()) == expected_tenants
        assert set(conn.execute(text("SELECT id FROM public.product_catalog")).scalars()) == expected_products
        if not expected_tenants:
            assert conn.execute(text("SELECT * FROM public.memberships")).all() == []


def test_self_read_does_not_create_membership_write_access(hardened_db):
    with _as_role(hardened_db, "authenticated", user=USER_A, tenant=TENANT_A) as conn:
        with pytest.raises(DBAPIError, match="row-level security"):
            conn.execute(
                text("INSERT INTO public.memberships VALUES (:tenant, :user)"), {"tenant": TENANT_B, "user": USER_A}
            )
    for statement in (
        "UPDATE public.memberships SET user_id = user_id",
        "DELETE FROM public.memberships",
    ):
        with _as_role(hardened_db, "authenticated", user=USER_A, tenant=TENANT_A) as conn:
            assert conn.execute(text(statement)).rowcount == 0


def test_authenticated_tenant_writes_are_denied_even_with_matching_context(hardened_db):
    with _as_role(hardened_db, "authenticated", user=USER_A, tenant=TENANT_A) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text("UPDATE public.tenants SET name = 'changed' WHERE id = :id"), {"id": TENANT_A})


@pytest.mark.parametrize("context", [None, ""])
@pytest.mark.parametrize("role", ["regengine", "regengine_sysadmin"])
def test_missing_backend_context_never_defaults_to_system_tenant(hardened_db, role, context):
    with _as_role(hardened_db, role, tenant=context) as conn:
        with pytest.raises(DBAPIError, match="tenant context required"):
            conn.execute(text("SELECT id, status FROM public.tenants")).all()
    with _as_role(hardened_db, role, tenant=context) as conn:
        with pytest.raises(DBAPIError, match="tenant context required"):
            conn.execute(text("SELECT * FROM public.memberships")).all()
    if role == "regengine_sysadmin":
        with _as_role(hardened_db, role, tenant=context) as conn:
            with pytest.raises(DBAPIError, match="tenant context required"):
                conn.execute(text("UPDATE public.tenants SET name = 'changed'"))


@pytest.mark.parametrize("role", ["regengine", "regengine_sysadmin"])
def test_backend_context_reads_and_existing_column_acl_are_preserved(hardened_db, role):
    with _as_role(hardened_db, role, tenant=TENANT_A) as conn:
        assert conn.execute(text("SELECT id::text, status FROM public.tenants")).all() == [(TENANT_A, "active")]
        assert set(conn.execute(text("SELECT user_id::text FROM public.memberships")).scalars()) == {USER_A, USER_B}
    if role == "regengine":
        with _as_role(hardened_db, role, tenant=TENANT_A, sysadmin=True) as conn:
            assert conn.execute(text("SELECT id::text FROM public.tenants")).scalars().all() == [TENANT_A]
            with pytest.raises(DBAPIError, match="permission denied"):
                conn.execute(text("SELECT name, settings FROM public.tenants")).all()
    else:
        with _as_role(hardened_db, role, tenant=TENANT_A) as conn:
            assert conn.execute(
                text("UPDATE public.tenants SET name = 'changed' RETURNING id::text")
            ).scalars().all() == [TENANT_A]


def test_sysadmin_exception_requires_the_existing_database_role(hardened_db):
    with _as_role(hardened_db, "regengine_sysadmin", sysadmin=True) as conn:
        assert set(conn.execute(text("SELECT id::text FROM public.tenants")).scalars()) == {
            TENANT_A,
            TENANT_B,
            SYSTEM_TENANT,
        }
        if hardened_db.with_v111:
            assert conn.execute(text("UPDATE public.tenants SET name = name")).rowcount == 3
        else:
            assert conn.execute(text("UPDATE public.tenants SET name = name")).rowcount == 0


def test_service_role_catalog_access_and_policy_survive_force_rls(hardened_db):
    with _as_role(hardened_db, "service_role") as conn:
        assert set(conn.execute(text("SELECT id FROM public.product_catalog")).scalars()) == {
            "a",
            "b",
            "system",
            "malformed",
            "null",
        }
        conn.execute(text("INSERT INTO public.product_catalog VALUES ('new', :tenant, 'new')"), {"tenant": TENANT_B})
        assert conn.execute(text("UPDATE public.product_catalog SET name = 'updated' WHERE id = 'new'")).rowcount == 1
        assert conn.execute(text("DELETE FROM public.product_catalog WHERE id = 'new'")).rowcount == 1
    before_policies, _, before_grants, _ = hardened_db.before
    after_policies, after_flags, after_grants, _ = hardened_db.after
    assert [row for row in before_policies if row[1] == "service_role_full_access"] == [
        row for row in after_policies if row[1] == "service_role_full_access"
    ]
    with hardened_db.engine.connect() as conn:
        service_oid = conn.execute(text("SELECT oid FROM pg_roles WHERE rolname = 'service_role'")).scalar_one()
    assert [row for row in before_grants if row[1] == service_oid] == [
        row for row in after_grants if row[1] == service_oid
    ]
    assert ("product_catalog", True, True) in after_flags
    assert ("tenants", True, True) in after_flags
    assert ("memberships", True, True) in after_flags


def test_upgrade_is_idempotent_and_downgrade_restores_observed_state(hardened_db):
    with hardened_db.engine.connect() as conn:
        transaction = conn.begin()
        try:
            _apply(conn, "upgrade")
            assert _snapshot(conn) == hardened_db.after
            _apply(conn, "downgrade")
            assert _snapshot(conn) == hardened_db.before
            _apply(conn, "upgrade")
            assert _snapshot(conn) == hardened_db.after
        finally:
            transaction.rollback()


def test_upgrade_and_downgrade_without_supabase_catalog():
    """The optional catalog table is absent on fresh app-only Alembic DBs."""
    with scratch_database_engine("v144_app_only_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            _bootstrap(conn, with_v111_policies=False)
            conn.execute(text("DROP TABLE public.product_catalog"))
            before = _snapshot(conn)
            _apply(conn, "upgrade")
            after = _snapshot(conn)
            assert conn.execute(text("SELECT to_regclass('public.product_catalog')")).scalar_one() is None
            names = {row[1] for row in after[0]}
            assert "tenants_read_all" not in names
            assert "tenants_authenticated_member_read" in names
            assert "memberships_authenticated_self_read" in names
            _apply(conn, "upgrade")
            assert _snapshot(conn) == after
            _apply(conn, "downgrade")
            assert _snapshot(conn) == before


def test_upgrade_without_legacy_memberships_policy_preserves_v111_self_read():
    """v111 already replaces the legacy membership policy on app databases."""
    with scratch_database_engine("v144_v111_memberships_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            _bootstrap(conn, with_v111_policies=True)
            conn.execute(text("DROP POLICY tenant_isolation_memberships ON public.memberships"))
            conn.execute(
                text("""
                CREATE POLICY memberships_sysadmin_read ON public.memberships
                    FOR SELECT TO regengine_sysadmin
                    USING (
                        current_user = 'regengine_sysadmin'
                        AND CASE
                            WHEN current_setting('regengine.is_sysadmin', true) = 'true'
                                THEN true
                            WHEN user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
                                THEN true
                            ELSE tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
                        END
                    );
            """)
            )
            before = _snapshot(conn)
            _apply(conn, "upgrade")
            after = _snapshot(conn)
            names = {row[1] for row in after[0]}
            assert "tenant_isolation_memberships" not in names
            assert "memberships_authenticated_self_read" in names
            assert [row for row in before[0] if row[1] == "memberships_sysadmin_read"] == [
                row for row in after[0] if row[1] == "memberships_sysadmin_read"
            ]

        db = SimpleNamespace(engine=engine)
        with _as_role(db, "authenticated", user=USER_A) as conn:
            assert conn.execute(text("SELECT tenant_id::text, user_id::text FROM public.memberships")).all() == [
                (TENANT_A, USER_A)
            ]
            assert conn.execute(text("SELECT id::text FROM public.tenants")).scalars().all() == [TENANT_A]
            assert conn.execute(text("SELECT id FROM public.product_catalog")).scalars().all() == ["a"]
        with _as_role(db, "regengine_sysadmin", sysadmin=True) as conn:
            assert conn.execute(text("SELECT count(*) FROM public.memberships")).scalar_one() == 3

        with engine.begin() as conn:
            _apply(conn, "downgrade")
            assert _snapshot(conn) == before
            assert "tenant_isolation_memberships" not in {row[1] for row in _snapshot(conn)[0]}


def test_missing_database_local_auth_function_denies_clients_but_preserves_backend():
    """Shared server roles can exist on an app DB without Supabase's auth schema."""
    with scratch_database_engine("v144_no_auth_schema_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            _bootstrap(conn, with_v111_policies=False)
            conn.execute(text("DROP FUNCTION auth.uid()"))
            conn.execute(text("DROP SCHEMA auth"))
            before = _snapshot(conn)
            _apply(conn, "upgrade")
            names = {row[1] for row in _snapshot(conn)[0]}
            assert names.isdisjoint(
                {
                    "memberships_authenticated_self_read",
                    "tenants_authenticated_member_read",
                    "product_catalog_authenticated_member_read",
                    "tenants_read_all",
                    "public_read_product_catalog",
                }
            )

        db = SimpleNamespace(engine=engine)
        with _as_role(db, "authenticated", user=USER_A, tenant=TENANT_A, sysadmin=True) as conn:
            for table in ("tenants", "product_catalog", "memberships"):
                assert conn.execute(text(f"SELECT * FROM public.{table}")).all() == []
        for table in ("tenants", "product_catalog"):
            with _as_role(db, "anon", user=USER_A, tenant=TENANT_A) as conn:
                with pytest.raises(DBAPIError, match="permission denied"):
                    conn.execute(text(f"SELECT * FROM public.{table}")).all()
        with _as_role(db, "regengine", tenant=TENANT_A) as conn:
            assert conn.execute(text("SELECT id::text, status FROM public.tenants")).all() == [(TENANT_A, "active")]

        with engine.begin() as conn:
            _apply(conn, "downgrade")
            assert _snapshot(conn) == before
