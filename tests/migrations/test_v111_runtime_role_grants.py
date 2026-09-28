"""Live proof for the v111 runtime-role and API-key bootstrap cutover.

CI supplies three direct PostgreSQL credentials for the same migrated scratch
database. No ``SET ROLE`` and no test-only GRANT statements are used here.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4

import pytest
from shared.api_key_store import APIKeyModel, DatabaseAPIKeyStore
from shared.tenant_context import set_rls_tenant_id
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from starlette.requests import Request

OWNER_URL = os.getenv("MIGRATIONS_DATABASE_URL")
RUNTIME_URL = os.getenv("DATABASE_URL")
ADMIN_URL = os.getenv("ADMIN_DATABASE_URL")
ROLE_ADMIN_URL = os.getenv("ROLE_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not (OWNER_URL and RUNTIME_URL and ADMIN_URL and ROLE_ADMIN_URL),
    reason=("direct migration, runtime, admin, and provider role-admin PostgreSQL URLs are required"),
)

TARGET_SCHEMAS = ("public", "fsma", "audit", "dlq", "ingestion")
SENSITIVE_RUNTIME_TABLES = (
    "public.admin_mfa_recovery_codes",
    "public.auth_challenges",
    "public.memberships",
    "public.organization_memberships",
    "public.organizations",
    "public.review_items",
    "public.roles",
    "public.sessions",
    "public.tool_leads",
    "public.user_emails",
    "public.users",
    "public.webauthn_challenges",
    "public.webauthn_credentials",
)


def _sync_url(url: str) -> str:
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        .replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        .replace("postgresql://", "postgresql+psycopg://", 1)
    )


def _apply_v111(connection, migration_module, monkeypatch) -> None:
    """Execute the cutover with the dedicated schema-owner connection."""

    class _Operations:
        @staticmethod
        def execute(statement: str) -> None:
            connection.execute(text(statement))

    monkeypatch.setattr(migration_module, "op", _Operations())
    migration_module.upgrade()


def _load_v111_module(module_name: str | None = None):
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
    )
    spec = importlib.util.spec_from_file_location(
        module_name or f"regengine_v111_cutover_{uuid4().hex}",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.fixture(scope="module")
def migration_owner_engine():
    engine = create_engine(_sync_url(OWNER_URL), pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def owner_engine():
    """Provider test seam for fixture DML through FORCE-RLS tables."""

    engine = create_engine(_sync_url(ROLE_ADMIN_URL), pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def role_admin_engine(owner_engine):
    """Provider-level seam used only to create/remove hostile role topology.

    The migration credential is deliberately NOCREATEROLE and must never be
    made powerful enough to construct this negative fixture itself.
    """

    return owner_engine


@pytest.fixture(scope="module")
def migration_module():
    return _load_v111_module("regengine_v111_cutover_test")


@pytest.fixture(scope="module")
def review_permission_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260803_6f4c2a9d8b17_v110_review_permissions.py"
    )
    spec = importlib.util.spec_from_file_location(
        "regengine_v110_review_permissions_test",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.fixture
def tenant_control_rows(owner_engine):
    tenant_a = uuid4()
    tenant_b = uuid4()
    marker = uuid4().hex
    role_ids = {
        "owner": uuid4(),
        "admin": uuid4(),
        "a": uuid4(),
        "b": uuid4(),
        "global": uuid4(),
    }
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO public.tenants (id, name, slug, status, settings)
                VALUES
                    (:a, 'ACL tenant A', :slug_a, 'active', :settings_a),
                    (:b, 'ACL tenant B', :slug_b, 'active', :settings_b)
                """
            ),
            {
                "a": tenant_a,
                "b": tenant_b,
                "slug_a": f"acl-a-{marker}",
                "slug_b": f"acl-b-{marker}",
                "settings_a": json.dumps({"marker": f"a-{marker}"}),
                "settings_b": json.dumps({"marker": f"b-{marker}"}),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO public.roles (id, tenant_id, name, permissions)
                VALUES
                    (:owner, NULL, 'Owner', '["review.read", "review.decide"]'::jsonb),
                    (:admin, NULL, 'Admin', '["review.read", "review.decide"]'::jsonb),
                    (:role_a, :a, :name_a, '["review.read"]'::jsonb),
                    (:role_b, :b, :name_b, '[]'::jsonb),
                    (:global_role, NULL, :global_name, '[]'::jsonb)
                """
            ),
            {
                **role_ids,
                "role_a": role_ids["a"],
                "role_b": role_ids["b"],
                "global_role": role_ids["global"],
                "a": tenant_a,
                "b": tenant_b,
                "name_a": f"Tenant A {marker}",
                "name_b": f"Tenant B {marker}",
                "global_name": f"Global {marker}",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO fsma.tenant_settings (tenant_id, settings)
                VALUES
                    (:a, :settings_a),
                    (:b, :settings_b)
                """
            ),
            {
                "a": tenant_a,
                "b": tenant_b,
                "settings_a": json.dumps({"marker": f"a-{marker}"}),
                "settings_b": json.dumps({"marker": f"b-{marker}"}),
            },
        )

    yield {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "marker": marker,
        "role_ids": role_ids,
    }

    with owner_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM public.audit_log_buffer WHERE tenant_id IN (:a, :b)"),
            {"a": tenant_a, "b": tenant_b},
        )
        connection.execute(
            text("DELETE FROM fsma.tenant_settings WHERE tenant_id IN (:a, :b)"),
            {"a": tenant_a, "b": tenant_b},
        )
        connection.execute(
            text("DELETE FROM public.roles WHERE id = ANY(:role_ids)"),
            {"role_ids": list(role_ids.values())},
        )
        connection.execute(
            text("DELETE FROM public.tenants WHERE id IN (:a, :b)"),
            {"a": tenant_a, "b": tenant_b},
        )


@pytest.fixture
async def key_stores(owner_engine):
    set_rls_tenant_id(None)
    runtime = DatabaseAPIKeyStore(database_url=RUNTIME_URL)
    admin = DatabaseAPIKeyStore(
        database_url=ADMIN_URL,
        arm_sysadmin_rls=True,
    )
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    marker = f"v111-{uuid4()}"

    active = await admin.create_key(
        name=f"{marker}-active",
        tenant_id=tenant_a,
        scopes=["read"],
    )
    other = await admin.create_key(
        name=f"{marker}-other",
        tenant_id=tenant_b,
        scopes=["read"],
    )
    expired = await admin.create_key(
        name=f"{marker}-expired",
        tenant_id=tenant_a,
        scopes=["read"],
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    revoked = await admin.create_key(
        name=f"{marker}-revoked",
        tenant_id=tenant_a,
        scopes=["read"],
    )
    assert await admin.revoke_key(revoked.key_id, revoked_by="v111-test")

    try:
        yield runtime, admin, active, other, expired, revoked
    finally:
        await runtime.close()
        await admin.close()
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM public.api_keys WHERE name LIKE :marker"),
                {"marker": f"{marker}%"},
            )
        set_rls_tenant_id(None)


def test_cutover_is_reapplicable_by_schema_owner(
    migration_owner_engine,
    migration_module,
    monkeypatch,
):
    with migration_owner_engine.begin() as connection:
        # Seed a stale column ACL that a prior cutover/runbook could have left.
        # A table-level REVOKE alone does not remove pg_attribute.attacl.
        connection.execute(text("GRANT UPDATE (email) ON public.users TO regengine"))

        _apply_v111(connection, migration_module, monkeypatch)
        _apply_v111(connection, migration_module, monkeypatch)
        assert not connection.execute(
            text("SELECT has_column_privilege('regengine', 'public.users', 'email', 'UPDATE')")
        ).scalar_one()


def test_enforced_lane_uses_exact_dedicated_migration_owner(
    migration_owner_engine,
    migration_module,
):
    """Prove identity, attributes, topology, and ownership on the live login."""

    expected_role = unquote(urlsplit(OWNER_URL).username or "")
    assert expected_role
    assert migration_module.MIGRATION_OWNER_ENFORCEMENT_REQUIRED is True
    assert migration_module.EXPECTED_MIGRATION_ROLE == expected_role

    with migration_owner_engine.connect() as connection:
        identity = connection.execute(
            text(
                """
                SELECT session_user, current_user, rolcanlogin, rolsuper,
                       rolbypassrls, rolcreatedb, rolcreaterole, rolreplication
                  FROM pg_roles
                 WHERE rolname = current_user
                """
            )
        ).one()
        assert identity == (
            expected_role,
            expected_role,
            True,
            False,
            False,
            False,
            False,
            False,
        )

        memberships = connection.execute(
            text(
                """
                SELECT member_role.rolname, granted_role.rolname
                  FROM pg_auth_members AS membership
                  JOIN pg_roles AS member_role
                    ON member_role.oid = membership.member
                  JOIN pg_roles AS granted_role
                    ON granted_role.oid = membership.roleid
                 WHERE member_role.rolname = :role
                    OR granted_role.rolname = :role
                """
            ),
            {"role": expected_role},
        ).all()
        assert memberships == []

        assert (
            connection.execute(
                text(
                    """
                SELECT pg_get_userbyid(datdba)
                  FROM pg_database
                 WHERE datname = current_database()
                """
                )
            ).scalar_one()
            == expected_role
        )

        schema_owners = dict(
            connection.execute(
                text(
                    """
                    SELECT nspname, pg_get_userbyid(nspowner)
                      FROM pg_namespace
                     WHERE nspname = ANY(:schemas)
                    """
                ),
                {"schemas": list(TARGET_SCHEMAS)},
            ).all()
        )
        assert set(schema_owners) == set(TARGET_SCHEMAS)
        assert schema_owners["public"] in {expected_role, "pg_database_owner"}
        assert {owner for schema, owner in schema_owners.items() if schema != "public"} == {expected_role}

        wrong_relations = connection.execute(
            text(
                """
                SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner)
                  FROM pg_class AS c
                  JOIN pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = ANY(:schemas)
                   AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f', 'i', 'I')
                   AND pg_get_userbyid(c.relowner) <> :role
                """
            ),
            {"schemas": list(TARGET_SCHEMAS), "role": expected_role},
        ).all()
        assert wrong_relations == []

        wrong_extensions = connection.execute(
            text(
                """
                SELECT e.extname, pg_get_userbyid(e.extowner)
                  FROM pg_extension AS e
                  JOIN pg_namespace AS n ON n.oid = e.extnamespace
                 WHERE n.nspname = ANY(:schemas)
                   AND pg_get_userbyid(e.extowner) <> :role
                """
            ),
            {"schemas": list(TARGET_SCHEMAS), "role": expected_role},
        ).all()
        assert wrong_extensions == []

        wrong_functions = connection.execute(
            text(
                """
                SELECT n.nspname, p.proname, pg_get_userbyid(p.proowner)
                  FROM pg_proc AS p
                  JOIN pg_namespace AS n ON n.oid = p.pronamespace
                 WHERE n.nspname = ANY(:schemas)
                   AND pg_get_userbyid(p.proowner) <> :role
                   AND NOT EXISTS (
                       SELECT 1
                         FROM pg_depend AS dependency
                         JOIN pg_extension AS extension
                           ON extension.oid = dependency.refobjid
                        WHERE dependency.classid = 'pg_proc'::regclass
                          AND dependency.objid = p.oid
                          AND dependency.deptype = 'e'
                          AND pg_get_userbyid(extension.extowner) = :role
                   )
                """
            ),
            {"schemas": list(TARGET_SCHEMAS), "role": expected_role},
        ).all()
        assert wrong_functions == []


@pytest.mark.parametrize(
    ("environment_variable", "environment_value"),
    (
        ("REGENGINE_ENV", "production"),
        ("REGENGINE_ENV", "staging"),
        ("RAILWAY_ENVIRONMENT_NAME", "preview"),
    ),
)
def test_deployed_module_import_forces_migration_owner_enforcement(
    monkeypatch,
    environment_variable,
    environment_value,
):
    monkeypatch.delenv("REGENGINE_ENFORCE_MIGRATION_ROLE", raising=False)
    monkeypatch.delenv("REGENGINE_MIGRATIONS_ROLE", raising=False)
    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", OWNER_URL)
    monkeypatch.setenv(environment_variable, environment_value)

    deployed_module = _load_v111_module()
    assert deployed_module.MIGRATION_OWNER_ENFORCEMENT_REQUIRED is True
    assert deployed_module.EXPECTED_MIGRATION_ROLE == unquote(urlsplit(OWNER_URL).username or "")


def test_enforcement_derives_identity_when_optional_role_pin_is_missing(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENFORCE_MIGRATION_ROLE", "1")
    monkeypatch.delenv("REGENGINE_MIGRATIONS_ROLE", raising=False)
    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", OWNER_URL)

    derived_module = _load_v111_module()
    assert derived_module.EXPECTED_MIGRATION_ROLE == unquote(urlsplit(OWNER_URL).username or "")


def test_enforcement_rejects_missing_or_mismatched_migration_identity(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENFORCE_MIGRATION_ROLE", "1")
    monkeypatch.delenv("MIGRATIONS_DATABASE_URL", raising=False)
    monkeypatch.delenv("REGENGINE_MIGRATIONS_ROLE", raising=False)
    with pytest.raises(RuntimeError, match="cannot determine the required migration role"):
        _load_v111_module()

    monkeypatch.setenv("REGENGINE_MIGRATIONS_ROLE", "role_without_url_identity")
    with pytest.raises(RuntimeError, match="MIGRATIONS_DATABASE_URL must contain"):
        _load_v111_module()

    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", OWNER_URL)
    monkeypatch.setenv("REGENGINE_MIGRATIONS_ROLE", "wrong_migration_role")
    with pytest.raises(RuntimeError, match="must match the login identity"):
        _load_v111_module()


def test_cloud_enforcement_rejects_provider_superuser_without_explicit_flag(
    owner_engine,
    monkeypatch,
):
    monkeypatch.delenv("REGENGINE_ENFORCE_MIGRATION_ROLE", raising=False)
    monkeypatch.delenv("REGENGINE_MIGRATIONS_ROLE", raising=False)
    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", ROLE_ADMIN_URL)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "v111-owner-negative")
    provider_module = _load_v111_module()
    assert provider_module.MIGRATION_OWNER_ENFORCEMENT_REQUIRED is True

    with pytest.raises(Exception, match="forbidden elevated attributes"):
        with owner_engine.begin() as connection:
            _apply_v111(connection, provider_module, monkeypatch)


def test_provider_session_cannot_set_role_to_bypass_owner_guard(
    owner_engine,
    migration_module,
    monkeypatch,
):
    expected_role = migration_module.EXPECTED_MIGRATION_ROLE
    quoted_role = expected_role.replace('"', '""')

    with pytest.raises(Exception, match="expected session login and effective role"):
        with owner_engine.begin() as connection:
            connection.exec_driver_sql(f'SET LOCAL ROLE "{quoted_role}"')
            _apply_v111(connection, migration_module, monkeypatch)


def test_v110_duplicate_role_failure_rolls_back_temporary_no_force(
    owner_engine,
    migration_owner_engine,
    review_permission_migration_module,
    tenant_control_rows,
    monkeypatch,
):
    """A failed data backfill must leave roles under FORCE RLS."""

    duplicate_role_id = uuid4()
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO public.roles (id, tenant_id, name, permissions)
                VALUES (:id, NULL, 'Owner', '[]'::jsonb)
                """
            ),
            {"id": duplicate_role_id},
        )

    try:
        with pytest.raises(Exception, match="duplicate canonical system role"):
            with migration_owner_engine.begin() as connection:

                class _Operations:
                    @staticmethod
                    def execute(statement: str) -> None:
                        connection.execute(text(statement))

                monkeypatch.setattr(
                    review_permission_migration_module,
                    "op",
                    _Operations(),
                )
                review_permission_migration_module.upgrade()

        with owner_engine.connect() as connection:
            assert connection.execute(
                text(
                    """
                    SELECT relrowsecurity AND relforcerowsecurity
                      FROM pg_class
                     WHERE oid = 'public.roles'::regclass
                    """
                )
            ).scalar_one()
    finally:
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM public.roles WHERE id = :id"),
                {"id": duplicate_role_id},
            )


def test_actual_runtime_credentials_have_exact_non_bypass_posture():
    expected = (
        (RUNTIME_URL, "regengine"),
        (ADMIN_URL, "regengine_sysadmin"),
    )
    for url, role in expected:
        engine = create_engine(_sync_url(url), pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                row = connection.execute(
                    text(
                        """
                        SELECT current_user, rolsuper, rolbypassrls,
                               rolcreatedb, rolcreaterole, rolreplication
                          FROM pg_roles
                         WHERE rolname = current_user
                        """
                    )
                ).one()
                assert row == (role, False, False, False, False, False)
        finally:
            engine.dispose()


def test_live_startup_rejects_provider_credential_using_set_role(monkeypatch):
    """An elevated session login cannot hide behind a safe effective role."""

    from shared.database import check_rls_posture, regengine_rls_enforcement_inert

    label = "v111-provider-set-role"
    monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1")
    disguised_provider = create_engine(
        _sync_url(ROLE_ADMIN_URL),
        pool_pre_ping=True,
        connect_args={"options": "-c role=regengine_sysadmin"},
    )
    try:
        with pytest.raises(RuntimeError, match="session role .* effective role"):
            check_rls_posture(
                disguised_provider,
                label=label,
                expected_role="regengine_sysadmin",
            )
        assert regengine_rls_enforcement_inert.labels(engine=label)._value.get() == 1
    finally:
        disguised_provider.dispose()


def test_live_startup_canary_reports_enforced_for_both_runtime_roles(monkeypatch):
    """The protected metric may report zero only for the exact migrated state."""

    from shared.database import check_rls_posture, regengine_rls_enforcement_inert

    monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1")
    for url, role, label in (
        (RUNTIME_URL, "regengine", "v111-live-runtime"),
        (ADMIN_URL, "regengine_sysadmin", "v111-live-admin"),
    ):
        engine = create_engine(_sync_url(url), pool_pre_ping=True)
        try:
            assert check_rls_posture(engine, label=label, expected_role=role) == "enforced"
            assert regengine_rls_enforcement_inert.labels(engine=label)._value.get() == 0
        finally:
            engine.dispose()


@pytest.mark.parametrize(
    ("case_name", "target_url", "expected_role", "mutation_sql", "cleanup_sql"),
    (
        (
            "weakened-operator",
            ADMIN_URL,
            "regengine_sysadmin",
            """
            ALTER POLICY tenants_sysadmin_select ON public.tenants
            USING (
                current_user = 'regengine_sysadmin'
                AND current_setting('regengine.is_sysadmin', true) IS NOT NULL
            )
            """,
            None,
        ),
        (
            "extra-permissive-policy",
            RUNTIME_URL,
            "regengine",
            """
            CREATE POLICY v111_canary_extra_runtime_select ON public.tenants
            FOR SELECT TO regengine USING (true)
            """,
            "DROP POLICY IF EXISTS v111_canary_extra_runtime_select ON public.tenants",
        ),
        (
            "force-rls-disabled",
            RUNTIME_URL,
            "regengine",
            "ALTER TABLE public.tenants NO FORCE ROW LEVEL SECURITY",
            None,
        ),
    ),
)
def test_live_startup_canary_rejects_catalog_drift_and_sets_metric(
    owner_engine,
    migration_owner_engine,
    migration_module,
    monkeypatch,
    case_name,
    target_url,
    expected_role,
    mutation_sql,
    cleanup_sql,
):
    """Exact policy tuples and FORCE RLS are blocking, not advisory checks."""

    from shared.database import check_rls_posture, regengine_rls_enforcement_inert

    label = f"v111-drift-{case_name}"
    target = create_engine(_sync_url(target_url), pool_pre_ping=True)
    monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1")
    try:
        with owner_engine.begin() as connection:
            connection.execute(text(mutation_sql))

        with pytest.raises(RuntimeError, match="failed the v111 catalog canary"):
            check_rls_posture(
                target,
                label=label,
                expected_role=expected_role,
            )
        assert regengine_rls_enforcement_inert.labels(engine=label)._value.get() == 1
    finally:
        target.dispose()
        if cleanup_sql:
            with owner_engine.begin() as connection:
                connection.execute(text(cleanup_sql))
        # Re-apply the source-of-truth DDL even when the assertion above fails;
        # no mutation may poison later direct-role tests.
        with migration_owner_engine.begin() as connection:
            _apply_v111(connection, migration_module, monkeypatch)

    restored = create_engine(_sync_url(target_url), pool_pre_ping=True)
    try:
        assert (
            check_rls_posture(
                restored,
                label=label,
                expected_role=expected_role,
            )
            == "enforced"
        )
        assert regengine_rls_enforcement_inert.labels(engine=label)._value.get() == 0
    finally:
        restored.dispose()


def test_live_startup_canary_rejects_incoming_runtime_role_membership(
    owner_engine,
    monkeypatch,
):
    """No other principal may inherit the sysadmin runtime authority."""

    from shared.database import check_rls_posture, regengine_rls_enforcement_inert

    leaked_principal = f"v111_runtime_grantee_{uuid4().hex}"
    label = "v111-drift-incoming-runtime-membership"
    target = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1")
    try:
        with owner_engine.begin() as connection:
            connection.execute(text(f'CREATE ROLE "{leaked_principal}" NOLOGIN'))
            connection.execute(text(f'GRANT regengine_sysadmin TO "{leaked_principal}"'))

        with pytest.raises(RuntimeError, match="failed the v111 catalog canary"):
            check_rls_posture(
                target,
                label=label,
                expected_role="regengine_sysadmin",
            )
        assert regengine_rls_enforcement_inert.labels(engine=label)._value.get() == 1
    finally:
        target.dispose()
        with owner_engine.begin() as connection:
            if connection.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
                {"role_name": leaked_principal},
            ).scalar_one_or_none():
                connection.execute(text(f'REVOKE regengine_sysadmin FROM "{leaked_principal}"'))
                connection.execute(text(f'DROP ROLE "{leaked_principal}"'))

    restored = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    try:
        assert (
            check_rls_posture(
                restored,
                label=label,
                expected_role="regengine_sysadmin",
            )
            == "enforced"
        )
        assert regengine_rls_enforcement_inert.labels(engine=label)._value.get() == 0
    finally:
        restored.dispose()


def test_admin_checkout_reset_is_committed_and_survives_request_rollback():
    """A stale session GUC cannot reappear after the reset transaction rolls back."""

    from services.admin.app import database as admin_database

    engine = create_engine(
        _sync_url(ADMIN_URL),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )
    event.listen(engine, "checkout", admin_database._reset_tenant_guc_on_checkout)

    stale_tenant = str(uuid4())
    try:
        first = engine.raw_connection()
        try:
            cursor = first.cursor()
            cursor.execute("SELECT pg_backend_pid()")
            first_backend = cursor.fetchone()[0]
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, false)",
                (stale_tenant,),
            )
            cursor.execute(
                "SELECT set_config('regengine.user_id', %s, false)",
                (str(uuid4()),),
            )
            cursor.execute("SELECT set_config('regengine.is_sysadmin', 'true', false)")
            cursor.close()
            first.commit()
        finally:
            first.close()

        second = engine.raw_connection()
        try:
            cursor = second.cursor()
            cursor.execute(
                """
                SELECT pg_backend_pid(),
                       COALESCE(current_setting('app.tenant_id', true), ''),
                       COALESCE(current_setting('regengine.user_id', true), ''),
                       COALESCE(current_setting('regengine.is_sysadmin', true), '')
                """
            )
            second_backend, tenant, user_id, is_sysadmin = cursor.fetchone()
            assert second_backend == first_backend
            assert (tenant, user_id, is_sysadmin) == ("", "", "false")

            # Simulate a request rollback after checkout.  The listener's
            # reset used and committed its own proved-idle transaction, so the
            # reset remains the durable session baseline.
            second.rollback()
            cursor.execute(
                """
                SELECT COALESCE(current_setting('app.tenant_id', true), ''),
                       COALESCE(current_setting('regengine.user_id', true), ''),
                       COALESCE(current_setting('regengine.is_sysadmin', true), '')
                """
            )
            assert cursor.fetchone() == ("", "", "false")
            cursor.close()
            second.rollback()
        finally:
            second.close()

        third = engine.raw_connection()
        try:
            cursor = third.cursor()
            cursor.execute(
                """
                SELECT pg_backend_pid(),
                       COALESCE(current_setting('app.tenant_id', true), ''),
                       COALESCE(current_setting('regengine.user_id', true), ''),
                       COALESCE(current_setting('regengine.is_sysadmin', true), '')
                """
            )
            backend, tenant, user_id, is_sysadmin = cursor.fetchone()
            assert backend == first_backend
            assert (tenant, user_id, is_sysadmin) == ("", "", "false")
            cursor.close()
            third.rollback()
        finally:
            third.close()
    finally:
        event.remove(engine, "checkout", admin_database._reset_tenant_guc_on_checkout)
        engine.dispose()


class _AlwaysAvailableThrottle:
    """Minimal cross-replica throttle seam for live database auth tests."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.resets: list[str] = []

    async def is_limited(self, _subject: str) -> bool:
        return False

    async def record_failure(self, subject: str) -> int:
        self.failures.append(subject)
        return len(self.failures)

    async def reset(self, subject: str) -> None:
        self.resets.append(subject)


def _cookie_request(path: str, session_token: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [
                (
                    b"cookie",
                    f"__Host-regengine_session={session_token}".encode("ascii"),
                )
            ],
            "client": ("127.0.0.1", 49152),
            "server": ("regengine.test", 443),
        }
    )


@pytest.mark.asyncio
async def test_live_session_auth_bootstrap_disarms_before_tenant_work(
    owner_engine,
    tenant_control_rows,
):
    """Exercise the real cookie lookup, global membership lookup, and tenant path."""

    from services.admin.app.auth_crypto import AuthCryptoService
    from services.admin.app.privileged_auth import (
        require_review_read,
        require_sysadmin_high_assurance,
    )

    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    role_a = tenant_control_rows["role_ids"]["a"]
    marker = uuid4().hex
    user_id = uuid4()
    organization_membership_id = uuid4()
    session_id = uuid4()
    session_token = f"v111-session-{marker}"
    crypto = AuthCryptoService("v111-live-auth-secret-material-32-bytes")
    token_hash = crypto.hash_session_token(session_token)

    with owner_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO public.organizations (id, name, enforced_auth_policy)
                VALUES (:tenant, :name, 'standard')
                """
            ),
            {"tenant": tenant_a, "name": f"v111 org {marker}"},
        )
        connection.execute(
            text(
                """
                INSERT INTO public.users (
                    id, email, global_status, is_sysadmin, status
                ) VALUES (
                    :user_id, :email, 'active', true, 'active'
                )
                """
            ),
            {"user_id": user_id, "email": f"v111-{marker}@example.test"},
        )
        connection.execute(
            text(
                """
                INSERT INTO public.organization_memberships (
                    id, user_id, organization_id, role
                ) VALUES (
                    :membership_id, :user_id, :tenant, 'admin'
                )
                """
            ),
            {
                "membership_id": organization_membership_id,
                "user_id": user_id,
                "tenant": tenant_a,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO public.memberships (user_id, tenant_id, role_id, is_active)
                VALUES (:user_id, :tenant, :role_id, true)
                """
            ),
            {"user_id": user_id, "tenant": tenant_a, "role_id": role_a},
        )
        connection.execute(
            text(
                """
                INSERT INTO public.sessions (
                    id, user_id, active_membership_id, token_hash,
                    auth_method, authenticated_at, refresh_token_hash,
                    family_id, is_revoked, expires_at
                ) VALUES (
                    :session_id, :user_id, :membership_id, :token_hash,
                    'webauthn', now(), :refresh_hash,
                    :family_id, false, now() + interval '1 hour'
                )
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "membership_id": organization_membership_id,
                "token_hash": token_hash,
                "refresh_hash": f"refresh-{marker}",
                "family_id": uuid4(),
            },
        )

    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    throttle = _AlwaysAvailableThrottle()
    try:
        with Session(admin, expire_on_commit=False) as db:
            # An unarmed checkout cannot enumerate control-plane membership.
            assert (
                db.execute(
                    text("SELECT count(*) FROM public.memberships WHERE user_id = :user_id"),
                    {"user_id": user_id},
                ).scalar_one()
                == 0
            )

            actor = await require_sysadmin_high_assurance(
                _cookie_request("/v1/admin/keys", session_token),
                db,
                crypto,
                throttle,
            )
            assert actor.actor_id == str(user_id)
            assert actor.session_id == str(session_id)
            assert actor.auth_method == "webauthn"
            assert throttle.failures == []

            # Bootstrap authority has been removed. Only the authenticated
            # user's self-policy remains active in the current transaction.
            gucs = db.execute(
                text(
                    """
                    SELECT current_setting('regengine.user_id', true),
                           current_setting('regengine.is_sysadmin', true)
                    """
                )
            ).one()
            assert gucs == (str(user_id), "false")
            assert db.execute(
                text("SELECT tenant_id FROM public.memberships WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).scalars().all() == [tenant_a]
            db.rollback()

        with Session(admin, expire_on_commit=False) as db:
            review_actor = await require_review_read(
                _cookie_request("/v1/review/items", session_token),
                db,
                crypto,
                throttle,
            )
            assert review_actor.actor_id == str(user_id)
            assert review_actor.tenant_id == str(tenant_a)
            assert "review.read" in review_actor.permissions
            assert db.execute(text("SELECT current_setting('regengine.is_sysadmin', true)")).scalar_one() == "false"

            # Route work re-enters only its derived tenant. Canonical roles
            # plus tenant A are visible; tenant B remains outside the policy.
            db.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            visible_role_ids = set(db.execute(text("SELECT id FROM public.roles")).scalars())
            assert role_a in visible_role_ids
            assert tenant_control_rows["role_ids"]["b"] not in visible_role_ids
            assert (
                db.execute(
                    text("SELECT count(*) FROM public.tenants WHERE id = :tenant"),
                    {"tenant": tenant_b},
                ).scalar_one()
                == 0
            )
            db.rollback()
    finally:
        admin.dispose()
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM public.sessions WHERE id = :session_id"),
                {"session_id": session_id},
            )
            connection.execute(
                text("DELETE FROM public.memberships WHERE user_id = :user_id AND tenant_id = :tenant"),
                {"user_id": user_id, "tenant": tenant_a},
            )
            connection.execute(
                text("DELETE FROM public.organization_memberships WHERE id = :membership_id"),
                {"membership_id": organization_membership_id},
            )
            connection.execute(
                text("DELETE FROM public.users WHERE id = :user_id"),
                {"user_id": user_id},
            )
            connection.execute(
                text("DELETE FROM public.organizations WHERE id = :tenant"),
                {"tenant": tenant_a},
            )


def test_runtime_roles_have_no_inherited_or_owned_authority(owner_engine):
    with owner_engine.connect() as connection:
        memberships = connection.execute(
            text(
                """
                SELECT member_role.rolname, granted_role.rolname
                  FROM pg_auth_members AS membership
                  JOIN pg_roles AS member_role
                    ON member_role.oid = membership.member
                 JOIN pg_roles AS granted_role
                    ON granted_role.oid = membership.roleid
                 WHERE member_role.rolname IN ('regengine', 'regengine_sysadmin')
                    OR granted_role.rolname IN ('regengine', 'regengine_sysadmin')
                """
            )
        ).all()
        assert memberships == []

        owned_relations = connection.execute(
            text(
                """
                SELECT n.nspname, c.relname
                  FROM pg_class AS c
                  JOIN pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = ANY(:schemas)
                   AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
                   AND pg_get_userbyid(c.relowner) IN (
                       'regengine', 'regengine_sysadmin'
                   )
                """
            ),
            {"schemas": list(TARGET_SCHEMAS)},
        ).all()
        assert owned_relations == []


def test_cutover_rejects_inherited_or_owned_implicit_authority(
    migration_owner_engine,
    role_admin_engine,
    migration_module,
    monkeypatch,
):
    inherited_role = f"v111_inherited_{uuid4().hex}"
    owned_table = f"v111_owned_{uuid4().hex}"

    def _run_cutover(connection) -> None:
        _apply_v111(connection, migration_module, monkeypatch)

    try:
        with role_admin_engine.begin() as connection:
            connection.execute(text(f'CREATE ROLE "{inherited_role}" NOLOGIN'))
            connection.execute(text(f'GRANT "{inherited_role}" TO regengine'))
        with (
            migration_owner_engine.begin() as connection,
            pytest.raises(
                Exception,
                match="no incoming or outgoing memberships",
            ),
        ):
            _run_cutover(connection)
        with role_admin_engine.begin() as connection:
            connection.execute(text(f'REVOKE "{inherited_role}" FROM regengine'))
            connection.execute(text(f'GRANT regengine_sysadmin TO "{inherited_role}"'))
        with (
            migration_owner_engine.begin() as connection,
            pytest.raises(
                Exception,
                match="no incoming or outgoing memberships",
            ),
        ):
            _run_cutover(connection)
        with role_admin_engine.begin() as connection:
            connection.execute(text(f'REVOKE regengine_sysadmin FROM "{inherited_role}"'))
            connection.execute(text(f'CREATE TABLE public."{owned_table}" (id integer)'))
            connection.execute(text(f'ALTER TABLE public."{owned_table}" OWNER TO regengine'))
        with (
            migration_owner_engine.begin() as connection,
            pytest.raises(
                Exception,
                match="protected relation .* is owned by regengine",
            ),
        ):
            _run_cutover(connection)
    finally:
        with role_admin_engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS public."{owned_table}"'))
            role_exists = connection.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
                {"role_name": inherited_role},
            ).scalar_one_or_none()
            if role_exists:
                connection.execute(text(f'REVOKE "{inherited_role}" FROM regengine'))
                connection.execute(text(f'REVOKE regengine_sysadmin FROM "{inherited_role}"'))
                connection.execute(text(f'DROP ROLE "{inherited_role}"'))


def test_runtime_object_grants_match_closed_inventory(
    owner_engine,
    migration_module,
):
    with owner_engine.connect() as connection:
        actual_tables: dict[str, dict[str, set[str]]] = {
            "regengine": {},
            "regengine_sysadmin": {},
        }
        for row in connection.execute(
            text(
                """
                SELECT grantee,
                       table_schema || '.' || table_name AS object_name,
                       privilege_type
                  FROM information_schema.table_privileges
                 WHERE grantee IN ('regengine', 'regengine_sysadmin')
                   AND table_schema = ANY(:schemas)
                 ORDER BY grantee, object_name, privilege_type
                """
            ),
            {"schemas": list(TARGET_SCHEMAS)},
        ):
            actual_tables[row.grantee].setdefault(row.object_name, set()).add(row.privilege_type)

        runtime_expected = {
            name: set(privileges) for name, privileges in migration_module.REGENGINE_TABLE_GRANTS.items()
        }
        sysadmin_expected = {
            name: set(privileges) for name, privileges in migration_module.REGENGINE_SYSADMIN_TABLE_GRANTS.items()
        }
        assert actual_tables["regengine"] == runtime_expected
        assert actual_tables["regengine_sysadmin"] == sysadmin_expected

        actual_columns: dict[str, set[tuple[str, str, str]]] = {
            "regengine": set(),
            "regengine_sysadmin": set(),
        }
        for row in connection.execute(
            text(
                """
                    SELECT r.rolname,
                           n.nspname || '.' || c.relname AS object_name,
                           a.attname,
                           acl.privilege_type
                      FROM pg_attribute AS a
                      JOIN pg_class AS c ON c.oid = a.attrelid
                      JOIN pg_namespace AS n ON n.oid = c.relnamespace
                      CROSS JOIN LATERAL aclexplode(a.attacl) AS acl
                      JOIN pg_roles AS r ON r.oid = acl.grantee
                     WHERE r.rolname IN ('regengine', 'regengine_sysadmin')
                       AND n.nspname = ANY(:schemas)
                    """
            ),
            {"schemas": list(TARGET_SCHEMAS)},
        ):
            actual_columns[row.rolname].add((row.object_name, row.attname, row.privilege_type))
        runtime_expected_columns = {
            (object_name, column, privilege)
            for object_name, privilege_map in migration_module.REGENGINE_COLUMN_GRANTS.items()
            for privilege, columns in privilege_map.items()
            for column in columns
        }
        sysadmin_expected_columns = {
            (object_name, column, privilege)
            for object_name, privilege_map in migration_module.REGENGINE_SYSADMIN_COLUMN_GRANTS.items()
            for privilege, columns in privilege_map.items()
            for column in columns
        }
        assert actual_columns["regengine"] == runtime_expected_columns
        assert actual_columns["regengine_sysadmin"] == sysadmin_expected_columns

        actual_sequences: dict[str, dict[str, set[str]]] = {
            "regengine": {},
            "regengine_sysadmin": {},
        }
        for row in connection.execute(
            text(
                """
                SELECT r.rolname,
                       n.nspname || '.' || c.relname AS object_name,
                       acl.privilege_type
                  FROM pg_class AS c
                  JOIN pg_namespace AS n ON n.oid = c.relnamespace
                  CROSS JOIN LATERAL aclexplode(c.relacl) AS acl
                  JOIN pg_roles AS r ON r.oid = acl.grantee
                 WHERE c.relkind = 'S'
                   AND r.rolname IN ('regengine', 'regengine_sysadmin')
                   AND n.nspname = ANY(:schemas)
                """
            ),
            {"schemas": list(TARGET_SCHEMAS)},
        ):
            actual_sequences[row.rolname].setdefault(row.object_name, set()).add(row.privilege_type)
        runtime_sequence_expected = {
            name: set(privileges) for name, privileges in migration_module.REGENGINE_SEQUENCE_GRANTS.items()
        }
        sysadmin_sequence_expected = {
            name: set(privileges) for name, privileges in migration_module.REGENGINE_SYSADMIN_SEQUENCE_GRANTS.items()
        }
        assert actual_sequences["regengine"] == runtime_sequence_expected
        assert actual_sequences["regengine_sysadmin"] == sysadmin_sequence_expected

        for role in ("regengine", "regengine_sysadmin"):
            for schema in TARGET_SCHEMAS:
                assert not connection.execute(
                    text("SELECT has_schema_privilege(:role, :schema, 'CREATE')"),
                    {"role": role, "schema": schema},
                ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege(:role, 'public.alembic_version', 'SELECT') "
                    "OR has_table_privilege(:role, 'public.alembic_version', 'INSERT') "
                    "OR has_table_privilege(:role, 'public.alembic_version', 'UPDATE') "
                    "OR has_table_privilege(:role, 'public.alembic_version', 'DELETE')"
                ),
                {"role": role},
            ).scalar_one()


def test_no_public_or_future_object_grants_remain(owner_engine):
    with owner_engine.connect() as connection:
        public_objects = connection.execute(
            text(
                """
                SELECT n.nspname, c.relname, acl.privilege_type
                  FROM pg_class AS c
                  JOIN pg_namespace AS n ON n.oid = c.relnamespace
                  CROSS JOIN LATERAL aclexplode(c.relacl) AS acl
                 WHERE acl.grantee = 0
                   AND n.nspname = ANY(:schemas)
                   AND c.relkind IN ('r', 'p', 'S')
                """
            ),
            {"schemas": list(TARGET_SCHEMAS)},
        ).all()
        assert public_objects == []

        default_grants = connection.execute(
            text(
                """
                SELECT pg_get_userbyid(d.defaclrole),
                       COALESCE(n.nspname, ''),
                       d.defaclobjtype,
                       COALESCE(r.rolname, 'PUBLIC'),
                       acl.privilege_type
                  FROM pg_default_acl AS d
                  LEFT JOIN pg_namespace AS n ON n.oid = d.defaclnamespace
                  CROSS JOIN LATERAL aclexplode(d.defaclacl) AS acl
                  LEFT JOIN pg_roles AS r ON r.oid = acl.grantee
                 WHERE COALESCE(n.nspname, '') = ANY(:schemas)
                   AND d.defaclobjtype IN ('r', 'S', 'f')
                   AND (acl.grantee = 0 OR r.rolname IN ('regengine', 'regengine_sysadmin'))
                """
            ),
            {"schemas": list(TARGET_SCHEMAS)},
        ).all()
        assert default_grants == []


def test_every_sysadmin_guc_policy_is_role_pinned(owner_engine):
    with owner_engine.connect() as connection:
        unsafe = connection.execute(
            text(
                """
                SELECT schemaname, tablename, policyname
                  FROM pg_policies
                 WHERE (
                           COALESCE(qual, '') LIKE '%regengine.is_sysadmin%'
                           AND (
                               lower(COALESCE(qual, '')) NOT LIKE '%current_user%'
                               OR lower(COALESCE(qual, '')) NOT LIKE '%regengine_sysadmin%'
                           )
                       )
                    OR (
                           COALESCE(with_check, '') LIKE '%regengine.is_sysadmin%'
                           AND (
                               lower(COALESCE(with_check, '')) NOT LIKE '%current_user%'
                               OR lower(COALESCE(with_check, '')) NOT LIKE '%regengine_sysadmin%'
                           )
                       )
                """
            )
        ).all()
        assert unsafe == []

        retired_system_arms = connection.execute(
            text(
                """
                SELECT schemaname, tablename, policyname
                  FROM pg_policies
                 WHERE COALESCE(qual, '') LIKE '%regengine.system_context%'
                    OR COALESCE(with_check, '') LIKE '%regengine.system_context%'
                """
            )
        ).all()
        assert retired_system_arms == []


def test_tenant_roots_and_roles_obey_actual_role_boundaries(tenant_control_rows):
    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    marker = tenant_control_rows["marker"]
    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    try:
        with runtime.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            assert connection.execute(text("SELECT id FROM public.tenants ORDER BY id")).scalars().all() == [tenant_a]

        with runtime.connect() as connection:
            assert connection.execute(text("SELECT id FROM public.tenants")).scalars().all() == []
        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            connection.execute(text("SELECT settings FROM public.tenants"))

        with admin.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            rows = connection.execute(
                text(
                    """
                    SELECT name, permissions
                      FROM public.roles
                     ORDER BY name
                    """
                )
            ).all()
            names = {row.name for row in rows}
            assert {"Owner", "Admin", f"Tenant A {marker}"} <= names
            assert f"Tenant B {marker}" not in names
            for row in rows:
                if row.name in {"Owner", "Admin"}:
                    assert {"review.read", "review.decide"} <= set(row.permissions)

        with admin.begin() as connection:
            connection.execute(text("SELECT set_config('regengine.is_sysadmin', 'true', true)"))
            global_names = set(connection.execute(text("SELECT name FROM public.roles ORDER BY name")).scalars())
            assert f"Tenant A {marker}" in global_names
            assert f"Tenant B {marker}" in global_names
            assert set(
                connection.execute(
                    text("SELECT id FROM public.tenants WHERE id IN (:a, :b)"),
                    {"a": tenant_a, "b": tenant_b},
                ).scalars()
            ) == {tenant_a, tenant_b}

        # Live role/permission mutation is migration-owned; the admin runtime
        # can read canonical and selected-tenant roles but cannot rewrite the
        # global catalog.
        with (
            admin.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            connection.execute(
                text("UPDATE public.roles SET permissions = '[\"review.read\"]'::jsonb WHERE id = :role_id"),
                {"role_id": tenant_control_rows["role_ids"]["global"]},
            )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            connection.execute(text("SELECT * FROM public.roles"))

        # A caller-controlled GUC cannot spoof the exact-role sysadmin arm.
        with runtime.begin() as connection:
            connection.execute(text("SELECT set_config('regengine.is_sysadmin', 'true', true)"))
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            visible = connection.execute(text("SELECT id FROM public.tenants ORDER BY id")).scalars().all()
            assert visible == [tenant_a]
            assert tenant_b not in visible
    finally:
        runtime.dispose()
        admin.dispose()


def test_funnel_events_are_tenant_bound_and_pool_safe(tenant_control_rows):
    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    try:
        with runtime.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO public.funnel_events (tenant_id, event_name, metadata)
                    VALUES (:tenant, 'first_ingest', '{}'::jsonb)
                    """
                ),
                {"tenant": tenant_a},
            )

        with runtime.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            assert connection.execute(text("SELECT tenant_id FROM public.funnel_events")).scalars().all() == [tenant_a]

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="row-level security",
            ),
        ):
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO public.funnel_events (tenant_id, event_name, metadata)
                    VALUES (:tenant, 'first_ingest', '{}'::jsonb)
                    """
                ),
                {"tenant": tenant_b},
            )

        with runtime.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM public.funnel_events")).scalar_one() == 0
            assert connection.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar_one() in (None, "")
    finally:
        runtime.dispose()


def test_disabled_graph_buffer_is_admin_reconcile_only(
    owner_engine,
    tenant_control_rows,
):
    tenant_a = tenant_control_rows["tenant_a"]
    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    try:
        with owner_engine.begin() as connection:
            row_id = connection.execute(
                text(
                    """
                    INSERT INTO public.audit_log_buffer (
                        tenant_id, actor, event_type, payload,
                        originally_failed_at, primary_error
                    ) VALUES (
                        :tenant, 'v111-test', 'kde_read', '{}'::jsonb,
                        now(), 'test'
                    ) RETURNING id
                    """
                ),
                {"tenant": tenant_a},
            ).scalar_one()

        with runtime.connect() as connection, pytest.raises(Exception, match="permission denied"):
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO public.audit_log_buffer (
                        tenant_id, actor, event_type, payload,
                        originally_failed_at
                    ) VALUES (:tenant, 'v111-test', 'kde_read', '{}'::jsonb, now())
                    """
                ),
                {"tenant": tenant_a},
            )
        with runtime.connect() as connection, pytest.raises(Exception, match="permission denied"):
            connection.execute(text("SELECT * FROM public.audit_log_buffer"))

        from services.graph.app.audit_buffer_reconciler import reconcile_audit_buffer

        result = reconcile_audit_buffer(
            batch_size=1000,
            primary_writer=lambda **_kwargs: None,
        )
        assert result.replayed >= 1

        admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
        try:
            with admin.begin() as connection:
                connection.execute(text("SELECT set_config('regengine.is_sysadmin', 'true', true)"))
                assert connection.execute(
                    text("SELECT replayed_at IS NOT NULL FROM public.audit_log_buffer WHERE id = :row_id"),
                    {"row_id": row_id},
                ).scalar_one()
        finally:
            admin.dispose()
    finally:
        runtime.dispose()


@pytest.mark.parametrize("table_name", SENSITIVE_RUNTIME_TABLES)
def test_actual_runtime_role_has_no_control_plane_crud(owner_engine, table_name):
    schema_name, relation_name = table_name.split(".", 1)
    with owner_engine.connect() as owner_connection:
        first_column = owner_connection.execute(
            text(
                """
                SELECT a.attname
                  FROM pg_attribute AS a
                  JOIN pg_class AS c ON c.oid = a.attrelid
                  JOIN pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = :schema_name
                   AND c.relname = :relation_name
                   AND a.attnum > 0
                   AND NOT a.attisdropped
                 ORDER BY a.attnum
                 LIMIT 1
                """
            ),
            {"schema_name": schema_name, "relation_name": relation_name},
        ).scalar_one()
    quoted_column = '"' + first_column.replace('"', '""') + '"'
    engine = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    try:
        for statement in (
            f"SELECT * FROM {table_name} LIMIT 1",
            f"INSERT INTO {table_name} DEFAULT VALUES",
            f"UPDATE {table_name} SET {quoted_column} = {quoted_column} WHERE false",
            f"DELETE FROM {table_name} WHERE false",
        ):
            with (
                engine.connect() as connection,
                pytest.raises(
                    Exception,
                    match="permission denied|tenant context required",
                ),
            ):
                connection.execute(text(statement))
    finally:
        engine.dispose()


def test_function_grants_are_explicit_and_set_admin_is_sysadmin_only(owner_engine):
    expected_direct = {
        "regengine": {
            ("public", "get_tenant_context"),
            ("public", "set_tenant_context"),
            ("public", "seed_obligations_for_tenant"),
            ("fsma", "get_active_portal_link_by_token"),
            ("fsma", "get_team_roster"),
            # email_ingest (v121/v122): created after v111, granted when
            # scripts/run-migrations.sh reapplies the cutover at head.
            ("fsma", "get_tenant_by_inbound_address"),
            ("fsma", "get_inbound_email_audit_by_message_id"),
            ("fsma", "claim_inbound_email_audit"),
            ("fsma", "finalize_inbound_email_audit"),
        },
        "regengine_sysadmin": {
            ("public", "get_tenant_context"),
            ("public", "set_tenant_context"),
            ("public", "set_admin_context"),
        },
    }
    # role_routine_grants is keyed by name, which cannot tell the granted
    # sender-allowlisted lookup from the denied recipient-only overload.
    email_ingest_signatures = (
        "fsma.get_tenant_by_inbound_address(text, text)",
        "fsma.get_inbound_email_audit_by_message_id(text)",
        "fsma.claim_inbound_email_audit(uuid, text, text, text, text, integer)",
        "fsma.finalize_inbound_email_audit(text, uuid, text, text, integer, integer, integer, jsonb)",
    )
    with owner_engine.connect() as connection:
        if connection.execute(text("SELECT to_regprocedure('public.get_invite_tenant_by_token_hash(text)')")).scalar():
            expected_direct["regengine_sysadmin"].add(("public", "get_invite_tenant_by_token_hash"))
        for signature in email_ingest_signatures:
            assert connection.execute(
                text("SELECT has_function_privilege('regengine', :signature, 'EXECUTE')"),
                {"signature": signature},
            ).scalar_one(), signature
            assert not connection.execute(
                text("SELECT has_function_privilege('regengine_sysadmin', :signature, 'EXECUTE')"),
                {"signature": signature},
            ).scalar_one(), signature
        for role, expected in expected_direct.items():
            actual = set(
                connection.execute(
                    text(
                        """
                        SELECT routine_schema, routine_name
                          FROM information_schema.role_routine_grants
                         WHERE grantee = :role
                           AND routine_schema = ANY(:schemas)
                        """
                    ),
                    {"role": role, "schemas": list(TARGET_SCHEMAS)},
                ).tuples()
            )
            assert actual == expected

        function_body = connection.execute(
            text("SELECT lower(pg_get_functiondef('public.set_admin_context(boolean)'::regprocedure))")
        ).scalar_one()
        assert "current_user" in function_body
        assert "regengine_sysadmin" in function_body


def test_disabled_or_admin_only_surfaces_have_no_runtime_grants(owner_engine):
    disabled_tables = (
        "public.compliance_notifications",
        "public.compliance_status_log",
        # inbound_email router (8301f3cad96a): recipient-only tenant mapping.
        "fsma.tenant_inbound_email_addresses",
    )
    disabled_functions = [
        "fsma.get_remediation_token_by_hash(text)",
        "fsma.get_remediation_token_by_session_hash(text)",
    ]
    runtime_statements = [
        "SELECT * FROM public.compliance_notifications LIMIT 1",
        "SELECT * FROM public.compliance_status_log LIMIT 1",
        "SELECT * FROM fsma.tenant_inbound_email_addresses LIMIT 1",
        "SELECT fsma.get_remediation_token_by_hash('disabled')",
        "SELECT fsma.get_remediation_token_by_session_hash('disabled')",
    ]
    with owner_engine.connect() as connection:
        # The recipient-only overload exists only when 8301f3cad96a ran after
        # v122 (incremental upgrades); a fresh chain drops it. Where it exists,
        # it must stay denied: it resolves a tenant without v122's sender check.
        if connection.execute(text("SELECT to_regprocedure('fsma.get_tenant_by_inbound_address(text)')")).scalar():
            disabled_functions.append("fsma.get_tenant_by_inbound_address(text)")
            runtime_statements.append("SELECT * FROM fsma.get_tenant_by_inbound_address('disabled@example.test')")
        for table_name in disabled_tables:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert not connection.execute(
                    text("SELECT has_table_privilege('regengine', :table, :privilege)"),
                    {"table": table_name, "privilege": privilege},
                ).scalar_one(), (table_name, privilege)
        for signature in disabled_functions:
            assert not connection.execute(
                text("SELECT has_function_privilege('regengine', :signature, 'EXECUTE')"),
                {"signature": signature},
            ).scalar_one(), signature

    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    try:
        for statement in runtime_statements:
            with (
                runtime.connect() as connection,
                pytest.raises(
                    Exception,
                    match="permission denied",
                ),
            ):
                _set_local_tenant(connection, uuid4())
                connection.execute(text(statement))
    finally:
        runtime.dispose()


def test_scheduler_remediation_grants_are_tenant_bound(
    owner_engine,
    tenant_control_rows,
):
    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    run_ids = {tenant_a: uuid4(), tenant_b: uuid4()}
    manifest_ids = {tenant_a: uuid4(), tenant_b: uuid4()}
    case_ids = {tenant_a: uuid4(), tenant_b: uuid4()}
    token_ids = {tenant_a: uuid4(), tenant_b: uuid4()}
    reminted_token_id = uuid4()
    outbox_ids = {tenant_a: uuid4(), tenant_b: uuid4()}

    with owner_engine.begin() as connection:
        for row_number, tenant in enumerate((tenant_a, tenant_b), start=1):
            connection.execute(
                text(
                    "INSERT INTO fsma.ingestion_runs "
                    "(id, tenant_id, source_system, source_file_name) "
                    "VALUES (:id, :tenant, 'v111-remediation', :file)"
                ),
                {
                    "id": run_ids[tenant],
                    "tenant": tenant,
                    "file": f"{tenant}.csv",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO fsma.manifest_records "
                    "(id, tenant_id, ingestion_run_id, row_number, raw_row, "
                    "row_fingerprint) VALUES "
                    "(:id, :tenant, :run_id, :row_number, '{}'::jsonb, :fingerprint)"
                ),
                {
                    "id": manifest_ids[tenant],
                    "tenant": tenant,
                    "run_id": run_ids[tenant],
                    "row_number": row_number,
                    "fingerprint": uuid4().hex,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO fsma.remediation_cases "
                    "(id, tenant_id, manifest_record_id, supplier_org) "
                    "VALUES (:id, :tenant, :manifest_id, 'v111-supplier')"
                ),
                {
                    "id": case_ids[tenant],
                    "tenant": tenant,
                    "manifest_id": manifest_ids[tenant],
                },
            )
            connection.execute(
                text(
                    "INSERT INTO fsma.remediation_tokens "
                    "(id, tenant_id, case_id, token_hash, expires_at) "
                    "VALUES (:id, :tenant, :case_id, :token_hash, "
                    "now() + interval '1 hour')"
                ),
                {
                    "id": token_ids[tenant],
                    "tenant": tenant,
                    "case_id": case_ids[tenant],
                    "token_hash": uuid4().hex,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO fsma.notification_outbox "
                    "(id, tenant_id, case_id, subject, body) "
                    "VALUES (:id, :tenant, :case_id, 'v111', 'v111')"
                ),
                {
                    "id": outbox_ids[tenant],
                    "tenant": tenant,
                    "case_id": case_ids[tenant],
                },
            )

    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    try:
        with runtime.begin() as connection:
            _set_local_tenant(connection, tenant_a)
            assert connection.execute(
                text("SELECT id FROM fsma.notification_outbox WHERE id = ANY(:ids)"),
                {"ids": list(outbox_ids.values())},
            ).scalars().all() == [outbox_ids[tenant_a]]
            assert connection.execute(
                text("SELECT id FROM fsma.remediation_tokens WHERE id = ANY(:ids)"),
                {"ids": list(token_ids.values())},
            ).scalars().all() == [token_ids[tenant_a]]
            assert (
                connection.execute(
                    text("UPDATE fsma.notification_outbox SET status='sending', claimed_at=now() WHERE id=:id"),
                    {"id": outbox_ids[tenant_a]},
                ).rowcount
                == 1
            )
            assert (
                connection.execute(
                    text("UPDATE fsma.notification_outbox SET status='sending', claimed_at=now() WHERE id=:id"),
                    {"id": outbox_ids[tenant_b]},
                ).rowcount
                == 0
            )
            assert (
                connection.execute(
                    text("UPDATE fsma.remediation_tokens SET revoked_at=now() WHERE id=:id"),
                    {"id": token_ids[tenant_a]},
                ).rowcount
                == 1
            )
            assert (
                connection.execute(
                    text("UPDATE fsma.remediation_tokens SET revoked_at=now() WHERE id=:id"),
                    {"id": token_ids[tenant_b]},
                ).rowcount
                == 0
            )
            connection.execute(
                text(
                    "INSERT INTO fsma.remediation_tokens "
                    "(id, tenant_id, case_id, token_hash, expires_at) "
                    "VALUES (:id, :tenant, :case_id, :token_hash, "
                    "now() + interval '1 hour')"
                ),
                {
                    "id": reminted_token_id,
                    "tenant": tenant_a,
                    "case_id": case_ids[tenant_a],
                    "token_hash": uuid4().hex,
                },
            )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="row-level security",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text(
                    "INSERT INTO fsma.remediation_tokens "
                    "(tenant_id, case_id, token_hash, expires_at) "
                    "VALUES (:tenant, :case_id, :token_hash, "
                    "now() + interval '1 hour')"
                ),
                {
                    "tenant": tenant_b,
                    "case_id": case_ids[tenant_b],
                    "token_hash": uuid4().hex,
                },
            )

        with owner_engine.connect() as connection:
            states = dict(
                connection.execute(
                    text("SELECT id, status FROM fsma.notification_outbox WHERE id = ANY(:ids)"),
                    {"ids": list(outbox_ids.values())},
                )
                .tuples()
                .all()
            )
            assert states[outbox_ids[tenant_a]] == "sending"
            assert states[outbox_ids[tenant_b]] == "pending"
            token_states = dict(
                connection.execute(
                    text("SELECT id, revoked_at IS NOT NULL FROM fsma.remediation_tokens WHERE id = ANY(:ids)"),
                    {
                        "ids": [
                            *token_ids.values(),
                            reminted_token_id,
                        ]
                    },
                )
                .tuples()
                .all()
            )
            assert token_states[token_ids[tenant_a]] is True
            assert token_states[token_ids[tenant_b]] is False
            assert token_states[reminted_token_id] is False
    finally:
        runtime.dispose()
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM fsma.notification_outbox WHERE id = ANY(:ids)"),
                {"ids": list(outbox_ids.values())},
            )
            connection.execute(
                text("DELETE FROM fsma.remediation_tokens WHERE id = ANY(:ids)"),
                {"ids": [*token_ids.values(), reminted_token_id]},
            )
            connection.execute(
                text("DELETE FROM fsma.remediation_cases WHERE id = ANY(:ids)"),
                {"ids": list(case_ids.values())},
            )
            connection.execute(
                text("DELETE FROM fsma.manifest_records WHERE id = ANY(:ids)"),
                {"ids": list(manifest_ids.values())},
            )
            connection.execute(
                text("DELETE FROM fsma.ingestion_runs WHERE id = ANY(:ids)"),
                {"ids": list(run_ids.values())},
            )


def test_runtime_cannot_update_admin_owned_alert_state(owner_engine):
    with owner_engine.connect() as connection:
        assert not connection.execute(
            text("SELECT has_table_privilege('regengine', 'public.compliance_alerts', 'UPDATE')")
        ).scalar_one()

    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    try:
        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            _set_local_tenant(connection, uuid4())
            connection.execute(text("UPDATE public.compliance_alerts SET status=status WHERE false"))
    finally:
        runtime.dispose()

    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    try:
        with runtime.connect() as connection:
            with pytest.raises(Exception, match="permission denied"):
                connection.execute(text("SELECT public.set_admin_context(true)"))
        with admin.connect() as connection:
            connection.execute(text("SELECT public.set_admin_context(true)"))
            assert connection.execute(text("SELECT current_setting('regengine.is_sysadmin')")).scalar_one() == "true"
    finally:
        runtime.dispose()
        admin.dispose()


@pytest.mark.asyncio
async def test_hash_bound_bootstrap_and_admin_global_management(key_stores):
    runtime, admin, active, other, expired, revoked = key_stores

    valid = await runtime.validate_key(active.raw_key)
    assert valid is not None
    assert valid.key_id == active.key_id
    assert await runtime.validate_key(f"{active.key_id}.wrong-secret") is None
    assert await runtime.validate_key(f"{active.key_id}.") is None
    assert await runtime.validate_key(expired.raw_key) is None
    assert await runtime.validate_key(revoked.raw_key) is None

    # No lookup proof and no tenant context means no global metadata access.
    assert await runtime.list_keys(include_disabled=True) == []
    assert await runtime.get_key(active.key_id) is None

    # The separately-pooled sysadmin store is globally armed and can manage
    # tenant-bound rows without caller-supplied tenant metadata.
    listed_ids = {item.key_id for item in await admin.list_keys(include_disabled=True)}
    assert {active.key_id, other.key_id, expired.key_id, revoked.key_id} <= listed_ids
    assert (await admin.get_key(active.key_id)).key_id == active.key_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "assignment",
    (
        "scopes = ARRAY['internal.tenants.create']::varchar[]",
        "tenant_id = gen_random_uuid()",
        "enabled = false",
        "expires_at = now() + interval '10 years'",
        "key_hash = repeat('0', 64)",
        "rate_limit_per_minute = 1000000",
    ),
)
async def test_valid_runtime_key_cannot_mutate_security_columns(
    key_stores,
    assignment,
):
    runtime, _admin, active, _other, _expired, _revoked = key_stores
    from shared.api_key_store import api_key_hash_candidates

    with pytest.raises(Exception, match="permission denied"):
        async with runtime._session() as session:
            await runtime._set_key_lookup_context(
                session,
                key_id=active.key_id,
                key_hashes=api_key_hash_candidates(active.raw_key),
            )
            await session.execute(
                text(f"UPDATE public.api_keys SET {assignment} WHERE key_id = :key_id"),
                {"key_id": active.key_id},
            )


@pytest.mark.asyncio
async def test_valid_lookup_sees_exactly_one_row_and_pool_reuse_clears_proof(key_stores):
    runtime, _admin, active, other, _expired, _revoked = key_stores
    from shared.api_key_store import api_key_hash_candidates

    async with runtime._session() as session:
        await runtime._set_key_lookup_context(
            session,
            key_id=active.key_id,
            key_hashes=api_key_hash_candidates(active.raw_key),
        )
        visible = (await session.execute(text("SELECT key_id FROM public.api_keys ORDER BY key_id"))).scalars().all()
        assert visible == [active.key_id]
        assert other.key_id not in visible

    async with runtime._session() as reused_session:
        settings = (
            await reused_session.execute(
                text(
                    """
                    SELECT current_setting('regengine.api_key_lookup_id', true),
                           current_setting('regengine.api_key_lookup_hash_current', true),
                           current_setting('regengine.api_key_lookup_hash_legacy', true)
                    """
                )
            )
        ).one()
        assert all(value in (None, "") for value in settings)
        assert (await reused_session.execute(text("SELECT count(*) FROM public.api_keys"))).scalar_one() == 0


@pytest.mark.asyncio
async def test_runtime_url_cannot_be_armed_as_sysadmin():
    wrong_store = DatabaseAPIKeyStore(
        database_url=RUNTIME_URL,
        arm_sysadmin_rls=True,
    )
    try:
        with pytest.raises(RuntimeError, match="connected as 'regengine'"):
            await wrong_store.list_keys()
    finally:
        await wrong_store.close()


def _set_local_tenant(connection, tenant_id) -> None:
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def _arm_admin(connection) -> None:
    connection.execute(text("SELECT set_config('regengine.is_sysadmin', 'true', true)"))


def test_ingestion_schema_is_tenant_bound_and_operation_narrow(
    owner_engine,
    tenant_control_rows,
):
    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    job_a, job_b = uuid4(), uuid4()
    doc_a, doc_b = uuid4(), uuid4()
    marker = uuid4().hex
    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)

    def document_params(doc_id, tenant_id, suffix):
        return {
            "id": doc_id,
            "tenant": tenant_id,
            "title": f"v111-{suffix}",
            "sha256": (marker + suffix.encode().hex()).ljust(64, "0")[:64],
            "sha512": (marker * 4)[:128],
            "storage": f"v111/{marker}/{suffix}",
        }

    document_sql = text(
        """
        INSERT INTO ingestion.documents (
            id, tenant_id, title, source_type, document_type, vertical,
            content_sha256, content_sha512, source_url, fetch_timestamp,
            storage_key
        ) VALUES (
            :id, :tenant, :title, 'upload', 'test', 'fsma',
            :sha256, :sha512, 'https://example.test/document', now(), :storage
        )
        """
    )
    try:
        with owner_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ingestion.jobs "
                    "(job_id, tenant_id, vertical, source_type) "
                    "VALUES (:job, :tenant, 'fsma', 'upload')"
                ),
                {"job": job_b, "tenant": tenant_b},
            )
            connection.execute(document_sql, document_params(doc_b, tenant_b, "b"))

        with runtime.begin() as connection:
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text(
                    "INSERT INTO ingestion.jobs "
                    "(job_id, tenant_id, vertical, source_type) "
                    "VALUES (:job, :tenant, 'fsma', 'upload')"
                ),
                {"job": job_a, "tenant": tenant_a},
            )
            connection.execute(document_sql, document_params(doc_a, tenant_a, "a"))
            connection.execute(
                text("UPDATE ingestion.jobs SET status='completed' WHERE job_id=:job"),
                {"job": job_a},
            )
            connection.execute(
                text(
                    "INSERT INTO ingestion.audit_log "
                    "(job_id, action, resource_type, status) "
                    "VALUES (:job, 'created', 'document', 'success')"
                ),
                {"job": job_a},
            )
            assert connection.execute(text("SELECT job_id FROM ingestion.jobs ORDER BY job_id")).scalars().all() == [
                job_a
            ]
            assert connection.execute(text("SELECT id FROM ingestion.documents ORDER BY id")).scalars().all() == [doc_a]
            assert connection.execute(text("SELECT job_id FROM ingestion.audit_log")).scalars().all() == [job_a]

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="row-level security",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text(
                    "INSERT INTO ingestion.jobs "
                    "(job_id, tenant_id, vertical, source_type) "
                    "VALUES (gen_random_uuid(), :tenant, 'fsma', 'upload')"
                ),
                {"tenant": tenant_b},
            )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text("UPDATE ingestion.documents SET title='mutated' WHERE id=:id"),
                {"id": doc_a},
            )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="row-level security",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text(
                    "INSERT INTO ingestion.audit_log "
                    "(job_id, action, resource_type, status) "
                    "VALUES (:job, 'created', 'document', 'success')"
                ),
                {"job": job_b},
            )

        # An unset checkout is empty, and reuse cannot retain tenant A.
        with runtime.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM ingestion.jobs")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM ingestion.documents")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM ingestion.audit_log")).scalar_one() == 0

        # The control-plane credential has no ingestion-schema data access.
        with (
            admin.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            _arm_admin(connection)
            connection.execute(text("SELECT * FROM ingestion.documents"))
    finally:
        runtime.dispose()
        admin.dispose()
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM ingestion.audit_log WHERE job_id IN (:a, :b)"),
                {"a": job_a, "b": job_b},
            )
            connection.execute(
                text("DELETE FROM ingestion.documents WHERE id IN (:a, :b)"),
                {"a": doc_a, "b": doc_b},
            )
            connection.execute(
                text("DELETE FROM ingestion.jobs WHERE job_id IN (:a, :b)"),
                {"a": job_a, "b": job_b},
            )


def test_dlq_is_admin_replay_only(owner_engine, tenant_control_rows):
    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    row_a, row_b = uuid4(), uuid4()
    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    try:
        with owner_engine.begin() as connection:
            for row_id, tenant in ((row_a, tenant_a), (row_b, tenant_b)):
                connection.execute(
                    text(
                        "INSERT INTO dlq.webhook_failures "
                        "(id, payload, error_message, tenant_id) "
                        "VALUES (:id, '{}'::jsonb, 'v111-test', :tenant)"
                    ),
                    {"id": row_id, "tenant": str(tenant)},
                )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(text("SELECT set_config('regengine.system_context', 'true', true)"))
            connection.execute(text("SELECT * FROM dlq.webhook_failures"))

        with admin.begin() as connection:
            _arm_admin(connection)
            assert set(
                connection.execute(
                    text("SELECT id FROM dlq.webhook_failures WHERE id IN (:a, :b)"),
                    {"a": row_a, "b": row_b},
                ).scalars()
            ) == {row_a, row_b}
            connection.execute(
                text(
                    "UPDATE dlq.webhook_failures "
                    "SET status='replayed', replay_attempts=replay_attempts+1, "
                    "replayed_at=now(), updated_at=now() WHERE id=:id"
                ),
                {"id": row_a},
            )

        with (
            admin.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            _arm_admin(connection)
            connection.execute(
                text("UPDATE dlq.webhook_failures SET payload='{}'::jsonb WHERE id=:id"),
                {"id": row_a},
            )
    finally:
        runtime.dispose()
        admin.dispose()
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM dlq.webhook_failures WHERE id IN (:a, :b)"),
                {"a": row_a, "b": row_b},
            )


def test_queue_and_fsma_audit_reject_system_guc_spoof(
    owner_engine,
    tenant_control_rows,
):
    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    marker = uuid4().hex
    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    seeded_task_ids: list[int] = []
    seeded_audit_ids: list[int] = []
    try:
        with owner_engine.begin() as connection:
            for tenant, suffix in ((tenant_a, "a"), (tenant_b, "b")):
                seeded_task_ids.append(
                    connection.execute(
                        text(
                            "INSERT INTO fsma.task_queue "
                            "(task_type, payload, tenant_id) "
                            "VALUES (:task_type, '{}'::jsonb, :tenant) RETURNING id"
                        ),
                        {"task_type": f"v111-{marker}-{suffix}", "tenant": tenant},
                    ).scalar_one()
                )
                seeded_audit_ids.append(
                    connection.execute(
                        text(
                            "INSERT INTO fsma.fsma_audit_trail "
                            "(event_id, actor, actor_type, action, target_type, "
                            "target_id, tenant_id, checksum) "
                            "VALUES (:event, 'v111', 'System', 'CREATED', "
                            "'test', :target, :tenant, :checksum) RETURNING id"
                        ),
                        {
                            "event": f"v111-{marker}-{suffix}",
                            "target": suffix,
                            "tenant": tenant,
                            "checksum": (marker * 2)[:64],
                        },
                    ).scalar_one()
                )

        with runtime.begin() as connection:
            _set_local_tenant(connection, tenant_a)
            assert connection.execute(
                text("SELECT tenant_id FROM fsma.task_queue WHERE id = ANY(:ids)"),
                {"ids": seeded_task_ids},
            ).scalars().all() == [tenant_a]
            assert connection.execute(
                text("SELECT tenant_id FROM fsma.fsma_audit_trail WHERE id = ANY(:ids)"),
                {"ids": seeded_audit_ids},
            ).scalars().all() == [tenant_a]

            task_id = connection.execute(
                text(
                    "INSERT INTO fsma.task_queue "
                    "(task_type, payload, tenant_id) "
                    "VALUES (:task_type, '{}'::jsonb, :tenant) RETURNING id"
                ),
                {"task_type": f"v111-{marker}-runtime", "tenant": tenant_a},
            ).scalar_one()
            audit_id = connection.execute(
                text(
                    "INSERT INTO fsma.fsma_audit_trail "
                    "(event_id, actor, actor_type, action, target_type, "
                    "target_id, tenant_id, checksum) "
                    "VALUES (:event, 'v111', 'System', 'CREATED', 'test', "
                    "'runtime', :tenant, :checksum) RETURNING id"
                ),
                {
                    "event": f"v111-{marker}-runtime",
                    "tenant": tenant_a,
                    "checksum": ("a" + marker * 2)[:64],
                },
            ).scalar_one()
            seeded_task_ids.append(task_id)
            seeded_audit_ids.append(audit_id)

        # The retired GUC is freely settable, but no active policy reads it.
        with runtime.begin() as connection:
            connection.execute(text("SELECT set_config('regengine.system_context', 'true', true)"))
            assert (
                connection.execute(
                    text("SELECT count(*) FROM fsma.task_queue WHERE id = ANY(:ids)"),
                    {"ids": seeded_task_ids},
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM fsma.fsma_audit_trail WHERE id = ANY(:ids)"),
                    {"ids": seeded_audit_ids},
                ).scalar_one()
                == 0
            )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="row-level security",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text(
                    "INSERT INTO fsma.task_queue "
                    "(task_type, payload, tenant_id) "
                    "VALUES ('v111-wrong-tenant', '{}'::jsonb, :tenant)"
                ),
                {"tenant": tenant_b},
            )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="row-level security",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text(
                    "INSERT INTO fsma.fsma_audit_trail "
                    "(event_id, actor, actor_type, action, tenant_id, checksum) "
                    "VALUES ('v111-wrong-tenant', 'v111', 'System', "
                    "'CREATED', :tenant, :checksum)"
                ),
                {"tenant": tenant_b, "checksum": "b" * 64},
            )

        # Ordinary producers may enqueue and read only. Worker state changes
        # and retention both use the dedicated admin engine.
        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text("UPDATE fsma.task_queue SET status='processing' WHERE id=:id"),
                {"id": seeded_task_ids[0]},
            )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text("DELETE FROM fsma.task_queue WHERE id=:id"),
                {"id": seeded_task_ids[0]},
            )

        with admin.begin() as connection:
            _arm_admin(connection)
            assert connection.execute(
                text("SELECT count(*) FROM fsma.task_queue WHERE id = ANY(:ids)"),
                {"ids": seeded_task_ids},
            ).scalar_one() == len(seeded_task_ids)
            assert connection.execute(
                text("SELECT count(*) FROM fsma.fsma_audit_trail WHERE id = ANY(:ids)"),
                {"ids": seeded_audit_ids},
            ).scalar_one() == len(seeded_audit_ids)
            connection.execute(
                text(
                    "UPDATE fsma.task_queue SET status='processing', "
                    "started_at=now(), locked_by='v111-admin' WHERE id=:id"
                ),
                {"id": seeded_task_ids[0]},
            )
    finally:
        runtime.dispose()
        admin.dispose()
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM fsma.task_queue WHERE id = ANY(:ids)"),
                {"ids": seeded_task_ids or [-1]},
            )
            connection.execute(
                text("DELETE FROM fsma.fsma_audit_trail WHERE id = ANY(:ids)"),
                {"ids": seeded_audit_ids or [-1]},
            )


def test_task_worker_claims_with_admin_role(owner_engine, tenant_control_rows):
    from shared.task_queue import TASK_HANDLERS, TaskWorker, register_task_handler

    from services.admin.app.database import get_admin_engine

    tenant_a = tenant_control_rows["tenant_a"]
    task_type = f"v111-worker-{uuid4().hex}"
    observed: list[str] = []
    with owner_engine.begin() as connection:
        task_id = connection.execute(
            text(
                "INSERT INTO fsma.task_queue (task_type, payload, tenant_id) "
                "VALUES (:task_type, :payload, :tenant) RETURNING id"
            ),
            {
                "task_type": task_type,
                "payload": json.dumps({"marker": task_type}),
                "tenant": tenant_a,
            },
        ).scalar_one()

    register_task_handler(task_type, lambda marker: observed.append(marker))
    try:
        worker = TaskWorker(
            get_admin_engine(),
            worker_id=f"v111-{uuid4().hex}",
            task_types=[task_type],
        )
        assert worker.run_once() == task_id
        assert observed == [task_type]
        with owner_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT status FROM fsma.task_queue WHERE id=:id"),
                    {"id": task_id},
                ).scalar_one()
                == "completed"
            )
    finally:
        TASK_HANDLERS.pop(task_type, None)
        with owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM fsma.task_queue WHERE id=:id"),
                {"id": task_id},
            )


def test_seed_function_is_reapplicable_owner_definer_and_tenant_exact(
    migration_owner_engine,
    role_admin_engine,
    tenant_control_rows,
):
    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    try:
        with migration_owner_engine.connect() as connection:
            metadata = connection.execute(
                text(
                    """
                    SELECT pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig,
                           current_user
                      FROM pg_proc AS p
                     WHERE p.oid =
                           'public.seed_obligations_for_tenant(uuid)'::regprocedure
                    """
                )
            ).one()
            assert metadata[0] == metadata[3]
            assert metadata[1] is True
            assert metadata[2] == ["search_path=pg_catalog, public, fsma, pg_temp"]

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="tenant context required",
            ),
        ):
            connection.execute(
                text("SELECT public.seed_obligations_for_tenant(:tenant)"),
                {"tenant": tenant_a},
            )

        with (
            runtime.connect() as connection,
            pytest.raises(
                Exception,
                match="seed tenant must equal",
            ),
        ):
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text("SELECT public.seed_obligations_for_tenant(:tenant)"),
                {"tenant": tenant_b},
            )

        with runtime.begin() as connection:
            connection.execute(text("CREATE TEMP TABLE regulations (poison text)"))
            connection.execute(text("SET LOCAL search_path = pg_temp, public"))
            _set_local_tenant(connection, tenant_a)
            connection.execute(
                text("SELECT public.seed_obligations_for_tenant(:tenant)"),
                {"tenant": tenant_a},
            )
            assert connection.execute(text("SELECT count(*) FROM public.regulations")).scalar_one() > 0
            assert connection.execute(text("SELECT count(*) FROM public.obligations")).scalar_one() > 0

        with runtime.begin() as connection:
            _set_local_tenant(connection, tenant_b)
            assert connection.execute(text("SELECT count(*) FROM public.regulations")).scalar_one() == 0

        with (
            admin.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            _arm_admin(connection)
            connection.execute(
                text("SELECT public.seed_obligations_for_tenant(:tenant)"),
                {"tenant": tenant_a},
            )
    finally:
        runtime.dispose()
        admin.dispose()
        with role_admin_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM public.controls WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a, "b": tenant_b},
            )
            connection.execute(
                text("DELETE FROM public.obligations WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a, "b": tenant_b},
            )
            connection.execute(
                text("DELETE FROM public.regulations WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a, "b": tenant_b},
            )
            connection.execute(
                text("DELETE FROM fsma.tenant_seed_state WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a, "b": tenant_b},
            )


@pytest.mark.parametrize(
    "table_name",
    ("fsma.incidents", "fsma.exchange_packages", "fsma.organizations"),
)
@pytest.mark.parametrize("role_url", (RUNTIME_URL, ADMIN_URL))
def test_disabled_fsma_surfaces_are_unreachable_by_both_roles(
    table_name,
    role_url,
):
    engine = create_engine(_sync_url(role_url), pool_pre_ping=True)
    try:
        with (
            engine.connect() as connection,
            pytest.raises(
                Exception,
                match="permission denied",
            ),
        ):
            if role_url == ADMIN_URL:
                _arm_admin(connection)
            connection.execute(text(f"SELECT * FROM {table_name} LIMIT 1"))
    finally:
        engine.dispose()


def test_sysadmin_dml_trigger_records_exact_session_role_and_is_immutable(
    owner_engine,
    tenant_control_rows,
):
    tenant_a = tenant_control_rows["tenant_a"]
    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    runtime = create_engine(_sync_url(RUNTIME_URL), pool_pre_ping=True)
    with owner_engine.connect() as connection:
        before_id = connection.execute(text("SELECT COALESCE(max(id), 0) FROM audit.sysadmin_access_log")).scalar_one()
    try:
        with admin.begin() as connection:
            _arm_admin(connection)
            connection.execute(
                text("UPDATE public.tenants SET settings=settings, updated_at=now() WHERE id=:tenant"),
                {"tenant": tenant_a},
            )

        with owner_engine.connect() as connection:
            audit_row = connection.execute(
                text(
                    """
                    SELECT id, table_name, operation, connection_info,
                           session_user_name
                      FROM audit.sysadmin_access_log
                     WHERE id > :before_id
                       AND table_name = 'public.tenants'
                     ORDER BY id DESC
                     LIMIT 1
                    """
                ),
                {"before_id": before_id},
            ).one()
            assert audit_row.table_name == "public.tenants"
            assert audit_row.operation == "UPDATE"
            assert audit_row.connection_info["session_user"] == "regengine_sysadmin"
            assert audit_row.session_user_name == "regengine_sysadmin"

        for engine in (runtime, admin):
            with (
                engine.connect() as connection,
                pytest.raises(
                    Exception,
                    match="permission denied",
                ),
            ):
                if engine is admin:
                    _arm_admin(connection)
                connection.execute(
                    text("UPDATE audit.sysadmin_access_log SET operation='ERASED' WHERE id=:id"),
                    {"id": audit_row.id},
                )
            with (
                engine.connect() as connection,
                pytest.raises(
                    Exception,
                    match="permission denied",
                ),
            ):
                if engine is admin:
                    _arm_admin(connection)
                connection.execute(
                    text("DELETE FROM audit.sysadmin_access_log WHERE id=:id"),
                    {"id": audit_row.id},
                )
    finally:
        runtime.dispose()
        admin.dispose()


def test_sysadmin_delete_capability_is_limited_to_erasure_dependencies():
    allowed = (
        "public.organization_memberships",
        "public.webauthn_credentials",
        "public.webauthn_challenges",
        "public.admin_mfa_recovery_codes",
        "public.auth_challenges",
    )
    denied = (
        "public.users",
        "public.user_emails",
        "public.sessions",
        "public.memberships",
        "public.api_keys",
        "public.audit_logs",
    )
    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    try:
        for table_name in allowed:
            with admin.begin() as connection:
                _arm_admin(connection)
                # No test data is removed; successful planning/execution
                # proves the exact DELETE capability is present.
                connection.execute(text(f"DELETE FROM {table_name} WHERE false"))
        for table_name in denied:
            with (
                admin.connect() as connection,
                pytest.raises(
                    Exception,
                    match="permission denied|tenant context required",
                ),
            ):
                _arm_admin(connection)
                connection.execute(text(f"DELETE FROM {table_name} WHERE false"))
    finally:
        admin.dispose()


def test_agent_review_list_decision_and_timeline_are_tenant_bound(
    owner_engine,
    tenant_control_rows,
):
    from shared.agent_operator_view import (
        fetch_agent_artifact_timeline,
        fetch_agent_review_items,
        upsert_agent_artifact_review,
    )
    from sqlalchemy.orm import sessionmaker

    tenant_a = tenant_control_rows["tenant_a"]
    tenant_b = tenant_control_rows["tenant_b"]
    run_a, run_b = uuid4(), uuid4()
    artifact_a, artifact_b = uuid4(), uuid4()
    reviewer_id = uuid4()

    with owner_engine.begin() as connection:
        for run_id, tenant, suffix in (
            (run_a, tenant_a, "a"),
            (run_b, tenant_b, "b"),
        ):
            connection.execute(
                text(
                    "INSERT INTO fsma.ingestion_runs "
                    "(id, tenant_id, source_system, source_file_name) "
                    "VALUES (:id, :tenant, 'v111-test', :file)"
                ),
                {"id": run_id, "tenant": tenant, "file": f"{suffix}.csv"},
            )
        for artifact_id, run_id, tenant, suffix in (
            (artifact_a, run_a, tenant_a, "a"),
            (artifact_b, run_b, tenant_b, "b"),
        ):
            artifact_json = {
                "artifact_id": str(artifact_id),
                "tenant_id": str(tenant),
                "artifact_type": "validation_explanation",
                "artifact_version": "agent-artifact.v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "agent_name": "v111-agent",
                "agent_version": "1.0",
                "model_name": None,
                "suggestion": f"review-{suffix}",
                "confidence": 0.5,
                "requires_human_review": True,
                "context": {
                    "evidence_ids": [],
                    "canonical_event_ids": [],
                    "ingestion_run_id": str(run_id),
                    "source_hashes": [],
                    "rule_id": None,
                    "rule_version": None,
                    "citation_reference": None,
                    "request_id": None,
                },
                "payload": {
                    "rule_result": "warn",
                    "inspected_fields": [],
                    "explanation": f"review artifact {suffix}",
                    "remediation_suggestion": None,
                },
            }
            connection.execute(
                text(
                    """
                    INSERT INTO fsma.agent_artifacts (
                        artifact_id, tenant_id, artifact_version,
                        artifact_type, created_at, agent_name, agent_version,
                        suggestion, confidence, requires_human_review,
                        ingestion_run_id, artifact, payload, artifact_hash
                    ) VALUES (
                        :artifact_id, :tenant, 'agent-artifact.v1',
                        'validation_explanation', now(), 'v111-agent', '1.0',
                        :suggestion, 0.5, true, :run_id,
                        CAST(:artifact AS jsonb), '{}'::jsonb, :artifact_hash
                    )
                    """
                ),
                {
                    "artifact_id": artifact_id,
                    "tenant": tenant,
                    "suggestion": f"review-{suffix}",
                    "run_id": run_id,
                    "artifact": json.dumps(artifact_json),
                    "artifact_hash": "0" * 64,
                },
            )

    admin = create_engine(_sync_url(ADMIN_URL), pool_pre_ping=True)
    Session = sessionmaker(bind=admin, expire_on_commit=False, future=True)
    session = Session()
    try:
        _arm_admin(session)
        _set_local_tenant(session, tenant_a)
        listed = fetch_agent_review_items(
            session,
            tenant_id=str(tenant_a),
            limit=50,
            offset=0,
        )
        listed_ids = {item.artifact_id for item in listed.items}
        assert str(artifact_a) in listed_ids
        assert str(artifact_b) not in listed_ids

        hidden = fetch_agent_review_items(
            session,
            tenant_id=str(tenant_b),
            limit=50,
            offset=0,
        )
        assert hidden.items == []

        decision = upsert_agent_artifact_review(
            session,
            tenant_id=str(tenant_a),
            artifact_id=str(artifact_a),
            status="accepted",
            reviewed_by=str(reviewer_id),
            review_reason="v111 direct-role proof",
        )
        assert decision.tenant_id == str(tenant_a)
        assert decision.status == "accepted"
        session.commit()

        _arm_admin(session)
        _set_local_tenant(session, tenant_a)
        timeline = fetch_agent_artifact_timeline(
            session,
            tenant_id=str(tenant_a),
            artifact_id=str(artifact_a),
        )
        assert timeline.item.artifact_id == str(artifact_a)
        assert timeline.item.review_status == "accepted"

        with pytest.raises(LookupError):
            upsert_agent_artifact_review(
                session,
                tenant_id=str(tenant_b),
                artifact_id=str(artifact_b),
                status="rejected",
                reviewed_by=str(reviewer_id),
            )
    finally:
        session.rollback()
        session.close()
        admin.dispose()
