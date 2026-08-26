"""Live PostgreSQL proof for identity-global account erasure authority.

The route may arm the reviewed global RLS context, but every durable effect
must remain bound to ``current_user.id``. Both identities are deliberately
members of both tenants so a tenant-only predicate cannot pass vacuously.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

_DIRECT_ROLE_URL_NAMES = (
    "MIGRATIONS_DATABASE_URL",
    "DATABASE_URL",
    "ADMIN_DATABASE_URL",
    "ROLE_ADMIN_DATABASE_URL",
)
_POSTGRES_DRIVERS = frozenset(
    {
        "postgresql",
        "postgresql+asyncpg",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_DEV_STACK_DATABASES = frozenset({"regengine", "regengine_admin"})
_CI_SCRATCH_DATABASE = "live_suite"


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def _database_target(variable: str, value: str) -> tuple[str, int, str]:
    """Parse a credential-free database target or fail before any connection."""

    try:
        parsed = make_url(value)
        port = parsed.port or 5432
    except Exception:
        pytest.fail(f"{variable} must be a valid PostgreSQL URL", pytrace=False)
    if parsed.drivername not in _POSTGRES_DRIVERS:
        pytest.fail(f"{variable} must be a valid PostgreSQL URL", pytrace=False)
    if not parsed.username or not parsed.host or not parsed.database:
        pytest.fail(
            f"{variable} must identify a direct PostgreSQL role and database target",
            pytrace=False,
        )
    return (parsed.host.rstrip(".").lower(), port, parsed.database)


def _validated_direct_role_urls() -> tuple[str, ...]:
    """Admit only four credentials targeting one designated scratch database.

    GitHub Actions may use the known local ``live_suite`` database. Every
    other invocation requires both a destructive-test acknowledgement and a
    matching ``REGENGINE_MIGRATION_TEST_DB`` designation. Error text names
    variables and policy only; it never renders credential-bearing URLs.
    """

    urls = tuple(os.getenv(name, "").strip() for name in _DIRECT_ROLE_URL_NAMES)
    if not all(urls):
        pytest.fail(
            "all four direct migration, runtime, admin, and provider PostgreSQL URLs are required",
            pytrace=False,
        )

    targets = tuple(
        _database_target(name, url)
        for name, url in zip(_DIRECT_ROLE_URL_NAMES, urls, strict=True)
    )
    if len(set(targets)) != 1:
        pytest.fail(
            "all four direct role URLs must target the same PostgreSQL database target",
            pytrace=False,
        )

    target = targets[0]
    host, port, database = target
    if database.lower() in _DEV_STACK_DATABASES:
        pytest.fail(
            "account-erasure proof refuses ordinary dev-stack databases",
            pytrace=False,
        )

    known_ci_scratch = (
        _truthy_env("CI")
        and _truthy_env("GITHUB_ACTIONS")
        and host in _LOCAL_HOSTS
        and port == 5432
        and database == _CI_SCRATCH_DATABASE
    )
    if known_ci_scratch:
        return urls

    if not _truthy_env("REGENGINE_ALLOW_DESTRUCTIVE_DB_TESTS"):
        pytest.fail(
            "database target requires an explicit destructive-test opt-in and matching "
            "REGENGINE_MIGRATION_TEST_DB designation",
            pytrace=False,
        )

    designated_url = os.getenv("REGENGINE_MIGRATION_TEST_DB", "").strip()
    if not designated_url:
        pytest.fail(
            "REGENGINE_MIGRATION_TEST_DB must designate the opted-in disposable database",
            pytrace=False,
        )
    designated_target = _database_target("REGENGINE_MIGRATION_TEST_DB", designated_url)
    if designated_target[2].lower() in _DEV_STACK_DATABASES:
        pytest.fail(
            "account-erasure proof refuses ordinary dev-stack databases",
            pytrace=False,
        )
    if designated_target != target:
        pytest.fail(
            "REGENGINE_MIGRATION_TEST_DB must match all four direct role URL targets",
            pytrace=False,
        )
    return urls


def _sync_url(url: str) -> str:
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        .replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        .replace("postgresql://", "postgresql+psycopg://", 1)
    )


def _rows(connection, statement: str, params: dict) -> list[dict]:
    return [dict(row._mapping) for row in connection.execute(text(statement), params)]


def _seed_fixture(provider, fixture: dict) -> None:
    provider.execute(
        text(
            """
            INSERT INTO public.tenants (id, name, slug, status, settings)
            VALUES
                (:tenant_a, 'Erasure tenant A', :slug_a, 'active', '{}'::jsonb),
                (:tenant_b, 'Erasure tenant B', :slug_b, 'active', '{}'::jsonb),
                (:tenant_c, 'Erasure audit-history tenant', :slug_c, 'active', '{}'::jsonb)
            """
        ),
        fixture,
    )
    provider.execute(
        text(
            """
            INSERT INTO public.roles (id, tenant_id, name, permissions)
            VALUES
                (:role_a, :tenant_a, 'Erasure role A', '[]'::jsonb),
                (:role_b, :tenant_b, 'Erasure role B', '[]'::jsonb)
            """
        ),
        fixture,
    )
    provider.execute(
        text(
            """
            INSERT INTO public.users
                (id, email, global_status, status, is_sysadmin, token_version)
            VALUES
                (:user_a, :email_a, 'active', 'active', false, 7),
                (:user_b, :email_b, 'active', 'active', false, 11)
            """
        ),
        fixture,
    )
    provider.execute(
        text(
            """
            INSERT INTO public.user_emails
                (id, user_id, email, email_fingerprint, is_verified)
            VALUES
                (:user_email_a, :user_a, :email_a, :fingerprint_a, true),
                (:user_email_b, :user_b, :email_b, :fingerprint_b, true)
            """
        ),
        fixture,
    )
    provider.execute(
        text(
            """
            INSERT INTO public.memberships (user_id, tenant_id, role_id, is_active)
            VALUES
                (:user_a, :tenant_a, :role_a, true),
                (:user_a, :tenant_b, :role_b, true),
                (:user_b, :tenant_a, :role_a, true),
                (:user_b, :tenant_b, :role_b, true)
            """
        ),
        fixture,
    )
    provider.execute(
        text(
            """
            INSERT INTO public.organizations (id, name)
            VALUES
                (:tenant_a, 'Erasure tenant A'),
                (:tenant_b, 'Erasure tenant B')
            """
        ),
        fixture,
    )
    provider.execute(
        text(
            """
            INSERT INTO public.organization_memberships
                (id, user_id, organization_id, role)
            VALUES
                (:org_membership_a1, :user_a, :tenant_a, 'member'),
                (:org_membership_a2, :user_a, :tenant_b, 'member'),
                (:org_membership_b1, :user_b, :tenant_a, 'member'),
                (:org_membership_b2, :user_b, :tenant_b, 'member')
            """
        ),
        fixture,
    )
    provider.execute(
        text(
            """
            INSERT INTO public.sessions
                (id, user_id, active_membership_id, token_hash, auth_method,
                 authenticated_at, refresh_token_hash, family_id, is_revoked, expires_at,
                 user_agent, ip_address)
            VALUES
                (:session_a, :user_a, :org_membership_a1, :token_a, 'email_otp',
                 now(), :refresh_a, :family_a, false, :expires_at, 'A browser', '192.0.2.10'),
                (:session_b, :user_b, :org_membership_b1, :token_b, 'email_otp',
                 now(), :refresh_b, :family_b, false, :expires_at, 'B browser', '192.0.2.20')
            """
        ),
        fixture,
    )
    for tenant_key in ("tenant_a", "tenant_b"):
        provider.execute(
            text(
                """
                INSERT INTO public.audit_logs
                    (tenant_id, actor_id, actor_email, event_type,
                     event_category, action, severity, resource_type,
                     resource_id, metadata, integrity_hash, sequence_num)
                VALUES
                    (:tenant_id, :user_a, :email_a, 'data.read',
                     'data_access', 'seed_a', 'info', 'profile', :resource_a,
                     :metadata_a, :hash_a, 1),
                    (:tenant_id, :user_b, :email_b, 'data.read',
                     'data_access', 'seed_b', 'info', 'profile', :resource_b,
                     :metadata_b, :hash_b, 2)
                """
            ),
            {
                **fixture,
                "tenant_id": fixture[tenant_key],
                "resource_a": str(fixture["user_a"]),
                "resource_b": str(fixture["user_b"]),
                "metadata_a": json.dumps({"owner": str(fixture["user_a"])}),
                "metadata_b": json.dumps({"owner": str(fixture["user_b"])}),
                "hash_a": f"seed-a-{tenant_key}-{fixture['marker']}",
                "hash_b": f"seed-b-{tenant_key}-{fixture['marker']}",
            },
        )

        provider.execute(
            text(
                """
                INSERT INTO public.graph_outbox
                    (tenant_id, operation, cypher, params, dedupe_key,
                     max_attempts, status, attempts, enqueued_at, next_attempt_at)
                VALUES
                    (:tenant_id, 'seed_b', 'RETURN $user_id',
                     CAST(:params AS jsonb), :dedupe_key,
                     10, 'pending', 0, now(), now())
                """
            ),
            {
                "tenant_id": fixture[tenant_key],
                "params": json.dumps({"user_id": str(fixture["user_b"])}),
                "dedupe_key": f"{fixture['marker']}:b:{tenant_key}",
            },
        )

    provider.execute(
        text(
            """
            INSERT INTO public.audit_logs
                (tenant_id, actor_id, actor_email, event_type,
                 event_category, action, severity, resource_type,
                 resource_id, metadata, integrity_hash, sequence_num)
            VALUES
                (:tenant_c, :user_a, :email_a, 'data.read',
                 'data_access', 'seed_a_history_only', 'info', 'profile', :resource_a,
                 CAST(:metadata_a AS jsonb), :hash_a, 1)
            """
        ),
        {
            **fixture,
            "resource_a": str(fixture["user_a"]),
            "metadata_a": json.dumps({"owner": str(fixture["user_a"])}),
            "hash_a": f"seed-a-tenant-c-{fixture['marker']}",
        },
    )


def _cleanup_fixture(provider, fixture: dict) -> None:
    provider.execute(text("SELECT set_config('audit.allow_break_glass', 'true', true)"))
    provider.execute(
        text("DELETE FROM public.graph_outbox WHERE dedupe_key LIKE :prefix"),
        {"prefix": f"{fixture['marker']}%"},
    )
    provider.execute(
        text(
            """
            DELETE FROM public.graph_outbox
             WHERE operation = 'user_erasure'
               AND params ->> 'user_id' = :user_a
            """
        ),
        {"user_a": str(fixture["user_a"])},
    )
    provider.execute(
        text("DELETE FROM public.audit_logs WHERE actor_id IN (:user_a, :user_b)"),
        fixture,
    )
    for table_name in (
        "public.sessions",
        "public.organization_memberships",
        "public.user_emails",
        "public.memberships",
    ):
        provider.execute(
            text(f"DELETE FROM {table_name} WHERE user_id IN (:user_a, :user_b)"),
            fixture,
        )
    provider.execute(
        text("DELETE FROM public.organizations WHERE id IN (:tenant_a, :tenant_b, :tenant_c)"),
        fixture,
    )
    provider.execute(
        text("DELETE FROM public.users WHERE id IN (:user_a, :user_b)"),
        fixture,
    )
    provider.execute(
        text("DELETE FROM public.roles WHERE id IN (:role_a, :role_b)"),
        fixture,
    )
    provider.execute(
        text("DELETE FROM public.tenants WHERE id IN (:tenant_a, :tenant_b, :tenant_c)"),
        fixture,
    )


@pytest.mark.asyncio
async def test_request_erasure_cannot_mutate_another_identity():
    _migrations_url, _runtime_url, admin_url, role_admin_url = (
        _validated_direct_role_urls()
    )
    from services.admin.app import dependencies, erasure_routes as erasure
    from services.admin.app.auth_utils import create_access_token
    from services.admin.app.session_store import SessionData

    marker = f"erasure-isolation-{uuid4().hex}"
    fixture = {
        "marker": marker,
        "tenant_a": uuid4(),
        "tenant_b": uuid4(),
        "tenant_c": uuid4(),
        "slug_a": f"{marker}-tenant-a",
        "slug_b": f"{marker}-tenant-b",
        "slug_c": f"{marker}-tenant-c",
        "role_a": uuid4(),
        "role_b": uuid4(),
        "user_a": uuid4(),
        "user_b": uuid4(),
        "user_email_a": uuid4(),
        "user_email_b": uuid4(),
        "org_membership_a1": uuid4(),
        "org_membership_a2": uuid4(),
        "org_membership_b1": uuid4(),
        "org_membership_b2": uuid4(),
        "session_a": uuid4(),
        "session_b": uuid4(),
        "family_a": uuid4(),
        "family_b": uuid4(),
        "email_a": f"{marker}-a@example.test",
        "email_b": f"{marker}-b@example.test",
        "fingerprint_a": f"{marker}-fingerprint-a",
        "fingerprint_b": f"{marker}-fingerprint-b",
        "token_a": f"{marker}-token-a",
        "token_b": f"{marker}-token-b",
        "refresh_a": f"{marker}-refresh-a",
        "refresh_b": f"{marker}-refresh-b",
        "jti_a": f"{marker}-jti-a",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    provider_engine = create_engine(_sync_url(role_admin_url), pool_pre_ping=True)
    admin_engine = create_engine(_sync_url(admin_url), pool_pre_ping=True)

    try:
        with provider_engine.begin() as provider:
            _seed_fixture(provider, fixture)

        with provider_engine.connect() as provider:
            before_audit_id = provider.execute(text("SELECT COALESCE(max(id), 0) FROM public.audit_logs")).scalar_one()
            before_outbox_id = provider.execute(text("SELECT COALESCE(max(id), 0) FROM public.graph_outbox")).scalar_one()
            b_user_before = _rows(
                provider,
                "SELECT * FROM public.users WHERE id=:user_b",
                fixture,
            )
            b_user_emails_before = _rows(
                provider,
                "SELECT * FROM public.user_emails WHERE user_id=:user_b ORDER BY id",
                fixture,
            )
            a_memberships_before = _rows(
                provider,
                """
                SELECT user_id, tenant_id, role_id, is_active
                  FROM public.memberships
                 WHERE user_id=:user_a ORDER BY tenant_id
                """,
                fixture,
            )
            b_memberships_before = _rows(
                provider,
                "SELECT * FROM public.memberships WHERE user_id=:user_b ORDER BY tenant_id",
                fixture,
            )
            b_org_memberships_before = _rows(
                provider,
                "SELECT * FROM public.organization_memberships WHERE user_id=:user_b ORDER BY organization_id",
                fixture,
            )
            b_sessions_before = _rows(
                provider,
                "SELECT * FROM public.sessions WHERE user_id=:user_b ORDER BY id",
                fixture,
            )
            b_audits_before = _rows(
                provider,
                "SELECT * FROM public.audit_logs WHERE actor_id=:user_b ORDER BY id",
                fixture,
            )
            b_outbox_before = _rows(
                provider,
                "SELECT * FROM public.graph_outbox WHERE dedupe_key LIKE :prefix ORDER BY id",
                {"prefix": f"{marker}:b:%"},
            )

        redis_client = SimpleNamespace(
            scan=AsyncMock(return_value=(0, [])),
            get=AsyncMock(return_value=None),
            delete=AsyncMock(return_value=0),
        )
        session_store = SimpleNamespace(
            get_session=AsyncMock(
                return_value=SessionData(
                    id=fixture["session_a"],
                    user_id=fixture["user_a"],
                    refresh_token_hash=fixture["refresh_a"],
                    family_id=fixture["family_a"],
                    token_version=7,
                    is_revoked=False,
                    created_at=datetime.now(timezone.utc),
                    last_used_at=datetime.now(timezone.utc),
                    expires_at=fixture["expires_at"],
                    user_agent="A browser",
                    ip_address="192.0.2.10",
                )
            ),
            revoke_all_user_sessions=AsyncMock(return_value=1),
            _get_client=AsyncMock(return_value=redis_client),
        )
        app = FastAPI()
        app.include_router(erasure.router)
        issued_sessions: list[Session] = []

        def _admin_session():
            db = Session(admin_engine, expire_on_commit=False)
            issued_sessions.append(db)
            try:
                assert db.execute(text("SELECT current_user")).scalar_one() == "regengine_sysadmin"
                yield db
            finally:
                db.rollback()
                db.close()

        app.dependency_overrides[erasure.get_session] = _admin_session
        app.dependency_overrides[erasure.get_session_store] = lambda: session_store
        bearer_token = create_access_token(
            {
                "sub": str(fixture["user_a"]),
                "tenant_id": str(fixture["tenant_a"]),
                "tv": 7,
                "sid": str(fixture["session_a"]),
                "jti": fixture["jti_a"],
            }
        )

        with (
            patch.object(dependencies, "get_supabase", return_value=None),
            patch.object(
                dependencies,
                "check_revoked_async",
                new_callable=AsyncMock,
                return_value=False,
            ) as revocation_verdict,
            patch.object(
                erasure,
                "_delete_neo4j_user_graph_data",
                new_callable=AsyncMock,
            ) as immediate_graph_delete,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://regengine.test",
            ) as client:
                response = await client.post(
                    "/v1/account/erasure",
                    headers={"Authorization": f"Bearer {bearer_token}"},
                    json={"confirm": True, "reason": "identity-isolation-proof"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        assert len(issued_sessions) == 1
        revocation_verdict.assert_awaited_once_with(fixture["jti_a"])
        session_store.get_session.assert_awaited_once_with(fixture["session_a"])
        session_store.revoke_all_user_sessions.assert_awaited_once_with(fixture["user_a"])
        immediate_graph_delete.assert_awaited_once_with(
            str(fixture["tenant_a"]),
            str(fixture["user_a"]),
        )

        with provider_engine.connect() as provider:
            erased_a = provider.execute(
                text(
                    """
                    SELECT email, global_status, status, token_version, is_sysadmin
                      FROM public.users WHERE id=:user_a
                    """
                ),
                fixture,
            ).one()
            assert erased_a.email.endswith("@invalid.regengine.local")
            assert erased_a.global_status == "erased"
            assert erased_a.status == "erased"
            assert erased_a.token_version == 8
            assert erased_a.is_sysadmin is False
            a_memberships_after = _rows(
                provider,
                """
                SELECT user_id, tenant_id, role_id, is_active
                  FROM public.memberships
                 WHERE user_id=:user_a ORDER BY tenant_id
                """,
                fixture,
            )
            assert len(a_memberships_after) == 2
            assert a_memberships_after == [
                {**membership, "is_active": False}
                for membership in a_memberships_before
            ]

            b_user_after = _rows(provider, "SELECT * FROM public.users WHERE id=:user_b", fixture)
            b_user_emails_after = _rows(
                provider,
                "SELECT * FROM public.user_emails WHERE user_id=:user_b ORDER BY id",
                fixture,
            )
            b_memberships_after = _rows(
                provider,
                "SELECT * FROM public.memberships WHERE user_id=:user_b ORDER BY tenant_id",
                fixture,
            )
            b_org_memberships_after = _rows(
                provider,
                "SELECT * FROM public.organization_memberships WHERE user_id=:user_b ORDER BY organization_id",
                fixture,
            )
            b_sessions_after = _rows(
                provider,
                "SELECT * FROM public.sessions WHERE user_id=:user_b ORDER BY id",
                fixture,
            )
            b_audits_after = _rows(
                provider,
                "SELECT * FROM public.audit_logs WHERE actor_id=:user_b ORDER BY id",
                fixture,
            )
            b_outbox_after = _rows(
                provider,
                "SELECT * FROM public.graph_outbox WHERE dedupe_key LIKE :prefix ORDER BY id",
                {"prefix": f"{marker}:b:%"},
            )
            assert b_user_after == b_user_before
            assert b_user_emails_after == b_user_emails_before
            assert b_memberships_after == b_memberships_before
            assert b_org_memberships_after == b_org_memberships_before
            assert b_sessions_after == b_sessions_before
            assert b_audits_after == b_audits_before
            assert b_outbox_after == b_outbox_before

            new_markers = _rows(
                provider,
                """
                SELECT actor_id, tenant_id, metadata
                  FROM public.audit_logs
                 WHERE id > :before_id AND action='gdpr_anonymize_user'
                 ORDER BY tenant_id
                """,
                {"before_id": before_audit_id},
            )
            assert len(new_markers) == 3
            assert {row["tenant_id"] for row in new_markers} == {
                fixture["tenant_a"],
                fixture["tenant_b"],
                fixture["tenant_c"],
            }
            assert all(row["actor_id"] == fixture["user_a"] for row in new_markers)
            assert all(
                row["metadata"]["redacted_user_id"] == str(fixture["user_a"])
                for row in new_markers
            )
            assert str(fixture["user_b"]) not in json.dumps(new_markers, default=str)

            new_outbox = _rows(
                provider,
                """
                SELECT tenant_id, operation, params, dedupe_key
                  FROM public.graph_outbox
                 WHERE id > :before_id AND operation='user_erasure'
                 ORDER BY tenant_id
                """,
                {"before_id": before_outbox_id},
            )
            assert len(new_outbox) == 3
            assert {row["tenant_id"] for row in new_outbox} == {
                fixture["tenant_a"],
                fixture["tenant_b"],
                fixture["tenant_c"],
            }
            assert all(row["params"] == {"user_id": str(fixture["user_a"])} for row in new_outbox)
            assert str(fixture["user_b"]) not in json.dumps(new_outbox, default=str)
    finally:
        try:
            with provider_engine.begin() as provider:
                _cleanup_fixture(provider, fixture)
        finally:
            admin_engine.dispose()
            provider_engine.dispose()
