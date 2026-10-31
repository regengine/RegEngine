"""Live-Postgres: list_users returns only the caller's tenant members.

After #3749, list_users arms regengine.is_sysadmin so public.users FORCE RLS
(users_self_or_admin) can see co-members. That arm must not widen the
directory across tenants: MembershipModel.tenant_id still filters the join,
and the admin GUC is transaction-local (SET LOCAL via arm/disarm).

This test seeds two tenants with disjoint synthetic members, invokes
list_users under each tenant context as regengine_sysadmin, and asserts
each call returns only that tenant's emails. Requires a designated live
test DB (same guards as the other tests/shared/*_live.py suite).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from shared.db_url import sync_postgres_url
from shared.pagination import PaginationParams
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason=(
        "no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) "
        "— skipping list_users tenant isolation live test"
    ),
)


def _engine():
    return create_engine(sync_postgres_url(DATABASE_URL))


def _seed_tenant(conn, *, label: str) -> tuple[uuid.UUID, set[str]]:
    """Insert one tenant with two active members. Caller rolls back."""
    tenant_id = uuid.uuid4()
    role_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:12]
    emails: set[str] = set()

    conn.execute(
        text("INSERT INTO public.tenants (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": str(tenant_id), "name": f"{label}-{suffix}", "slug": f"{label}-{suffix}"},
    )
    conn.execute(
        text("INSERT INTO public.roles (id, tenant_id, name) VALUES (:id, :tid, 'Member')"),
        {"id": str(role_id), "tid": str(tenant_id)},
    )

    for idx in (1, 2):
        user_id = uuid.uuid4()
        email = f"{label}-user{idx}-{suffix}@example.test"
        emails.add(email)
        conn.execute(
            text(
                "INSERT INTO public.users (id, email, status) VALUES (:id, :email, 'active')"
            ),
            {"id": str(user_id), "email": email},
        )
        conn.execute(
            text(
                """
                INSERT INTO public.memberships (user_id, tenant_id, role_id, is_active)
                VALUES (:uid, :tid, :rid, true)
                """
            ),
            {"uid": str(user_id), "tid": str(tenant_id), "rid": str(role_id)},
        )

    return tenant_id, emails


def test_list_users_returns_only_caller_tenant_members() -> None:
    from services.admin.app import user_routes as ur
    from services.admin.app.models import TenantContext

    engine = _engine()
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                role_exists = conn.execute(
                    text("SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin'")
                ).scalar()
                if not role_exists:
                    pytest.skip("regengine_sysadmin role not present in this database")

                policy_exists = conn.execute(
                    text(
                        "SELECT 1 FROM pg_policies WHERE schemaname = 'public' "
                        "AND tablename = 'users' "
                        "AND policyname = 'users_self_or_admin'"
                    )
                ).scalar()
                assert policy_exists, (
                    "users_self_or_admin policy missing — list_users peer visibility "
                    "depends on that FORCE RLS arm"
                )

                tenant_a, emails_a = _seed_tenant(conn, label="lista")
                tenant_b, emails_b = _seed_tenant(conn, label="listb")
                assert emails_a.isdisjoint(emails_b)

                # Seed as the migration owner; evaluate RLS as the admin engine role.
                conn.execute(text("SET LOCAL ROLE regengine_sysadmin"))

                db = Session(bind=conn)

                TenantContext.set_tenant_context(db, tenant_a)
                result_a = asyncio.run(
                    ur.list_users(
                        pagination=PaginationParams(skip=0, limit=50),
                        db=db,
                    )
                )
                got_a = {item.email for item in result_a.items}
                assert got_a == emails_a, (
                    f"tenant A directory leaked or missed members: got={got_a} expected={emails_a}"
                )
                assert result_a.total == len(emails_a)
                assert got_a.isdisjoint(emails_b)

                TenantContext.set_tenant_context(db, tenant_b)
                result_b = asyncio.run(
                    ur.list_users(
                        pagination=PaginationParams(skip=0, limit=50),
                        db=db,
                    )
                )
                got_b = {item.email for item in result_b.items}
                assert got_b == emails_b, (
                    f"tenant B directory leaked or missed members: got={got_b} expected={emails_b}"
                )
                assert result_b.total == len(emails_b)
                assert got_b.isdisjoint(emails_a)
            finally:
                trans.rollback()
    finally:
        engine.dispose()
