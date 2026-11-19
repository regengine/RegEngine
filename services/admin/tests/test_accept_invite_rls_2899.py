"""#2899 — POST /auth/accept-invite must resolve its tenant before it reads.

``accept_invite`` is a public, unauthenticated route. Its original tests
ran on the SQLite fixture (``services/admin/conftest.py`` pins
``ADMIN_DATABASE_URL=sqlite:///:memory:``) where RLS never evaluates, so none
of them exercised what production does.

On PostgreSQL, ``public.invites`` is ENABLE + FORCE ROW LEVEL SECURITY under
v078's ``tenant_isolation_invites`` (``tenant_id = get_tenant_context()``),
v097 pinned ``get_tenant_context()`` to RAISE when ``app.tenant_id`` is unset,
and ``services/admin/app/database.py``'s checkout listener clears
``app.tenant_id`` on every pool checkout. The handler's first statement was a
plain ``SELECT ... FROM invites WHERE token_hash = ...`` — so it raised
``app.tenant_id not set`` and the endpoint 500'd for every invitee.

``_FailClosedRlsSession`` below reproduces exactly that: any statement against
a tenant-scoped table raises unless a tenant context has been bound on the
session first, which is what a real enforced-RLS connection does. The live
token-lookup counterpart is ``tests/shared/test_invite_token_lookup_live.py``.
The PostgreSQL cases here also exercise the real identity helper against a
designated migrated scratch database under the restricted admin role.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))

# Tables whose reads/writes are gated on app.tenant_id by v078.
_TENANT_SCOPED = ("invites", "memberships", "audit_logs", "roles")

_RAISE = "app.tenant_id not set - tenant context required for RLS"


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value

    def fetchone(self):
        return (self._value,) if self._value is not None else None


class _FailClosedRlsSession:
    """A session that behaves like an enforced-RLS Postgres connection."""

    def __init__(self, invite, user, membership=None, lookup_tenant=None):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        self.info = {}
        self._invite = invite
        self._user = user
        self._membership = membership
        self._lookup_tenant = lookup_tenant
        self.tenant_bound = None
        self.statements: list[str] = []
        self.added = []
        self.committed = False
        self.sysadmin_armed = False
        self.flushed_users = []
        self.flushed_identities = []

    # -- the RLS behaviour under test -----------------------------------
    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)

        if "set_config('regengine.is_sysadmin'" in sql:
            self.sysadmin_armed = "'true'" in sql
            return _Result(None)

        if "get_invite_tenant_by_token_hash" in sql:
            # The SECURITY DEFINER token lookup: readable with no tenant GUC.
            return _Result(self._lookup_tenant)

        if "set_tenant_context" in sql:
            self.tenant_bound = (params or {}).get("tid")
            return _Result(None)

        if any(f" {t}" in sql or f"FROM {t}" in sql for t in _TENANT_SCOPED):
            if self.tenant_bound is None:
                raise RuntimeError(_RAISE)

        if "FROM invites" in sql:
            return _Result(self._invite)
        if "FROM users" in sql:
            if self.bind.dialect.name == "postgresql" and not self.sysadmin_armed:
                raise RuntimeError("users SELECT requires regengine.is_sysadmin=true")
            return _Result(self._user)
        if "FROM memberships" in sql:
            return _Result(self._membership)
        return _Result(None)

    # -- the rest of the Session surface accept_invite touches ----------
    def get(self, _model, _pk):
        return SimpleNamespace(name="Member")

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        from app.sqlalchemy_models import OrganizationMembershipModel, UserEmailModel, UserModel

        for obj in self.added:
            if isinstance(obj, UserModel) and obj not in self.flushed_users:
                if not self.sysadmin_armed:
                    raise RuntimeError("users INSERT requires regengine.is_sysadmin=true")
                self.flushed_users.append(obj)
            if isinstance(obj, (UserEmailModel, OrganizationMembershipModel)) and obj not in self.flushed_identities:
                if not self.sysadmin_armed:
                    raise RuntimeError("identity INSERT requires regengine.is_sysadmin=true")
                self.flushed_identities.append(obj)
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def commit(self):
        self.committed = True


def _make_invite(tenant_id, token_hash, email="invitee@example.com"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=email,
        role_id=uuid.uuid4(),
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        revoked_at=None,
        accepted_at=None,
    )


def _make_user(email="invitee@example.com"):
    return SimpleNamespace(id=uuid.uuid4(), email=email, status="active")


def _starlette_request():
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/accept-invite",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


async def _call(db, identity_effect=None):
    from app.invite_routes import AcceptInviteRequest, accept_invite

    payload = AcceptInviteRequest(token="raw-token", name="Invitee")
    with (
        patch("app.invite_routes.ensure_passwordless_identity", side_effect=identity_effect),
        patch("app.invite_routes.AuditLogger.log_event"),
        patch("app.invite_routes.supplier_graph_sync"),
    ):
        return await accept_invite.__wrapped__(payload=payload, request=_starlette_request(), db=db)


@pytest.mark.asyncio
async def test_accept_invite_succeeds_under_enforced_rls_with_no_tenant_context():
    """The #2899 regression: the whole handler must complete with no inbound
    tenant context. Pre-fix the first ``SELECT ... FROM invites`` raised
    ``app.tenant_id not set`` and the public endpoint 500'd for every invitee.
    """
    tenant_id = uuid.uuid4()
    token_hash = hashlib.sha256(b"raw-token").hexdigest()
    db = _FailClosedRlsSession(
        invite=_make_invite(tenant_id, token_hash),
        user=_make_user(),
        lookup_tenant=tenant_id,
    )

    result = await _call(db)

    assert result["status"] == "success"
    assert db.committed is True
    assert not db.sysadmin_armed


@pytest.mark.asyncio
async def test_tenant_context_is_bound_from_the_invite_before_any_scoped_read():
    """Ordering contract: the token-hash lookup comes first, the tenant GUC is
    bound from the invite's own tenant_id, and only then is ``invites`` read.

    Binding the tenant from the row rather than from anything the caller sent
    is what keeps this fail-closed: an attacker cannot nominate a tenant.
    """
    tenant_id = uuid.uuid4()
    token_hash = hashlib.sha256(b"raw-token").hexdigest()
    db = _FailClosedRlsSession(
        invite=_make_invite(tenant_id, token_hash),
        user=_make_user(),
        lookup_tenant=tenant_id,
    )

    await _call(db)

    assert db.statements, "handler issued no statements"
    assert "get_invite_tenant_by_token_hash" in db.statements[0], (
        "the token-keyed lookup must be the FIRST statement — anything else runs "
        f"without a tenant context under FORCE RLS. Got: {db.statements[0]!r}"
    )
    assert db.tenant_bound == str(tenant_id)

    first_invite_read = next(i for i, s in enumerate(db.statements) if "FROM invites" in s)
    bind_index = next(i for i, s in enumerate(db.statements) if "set_tenant_context" in s)
    assert bind_index < first_invite_read, "tenant context must be bound before invites is read"


@pytest.mark.asyncio
async def test_unresolvable_token_is_a_uniform_400_not_a_500():
    """An unknown/consumed/expired token resolves to no tenant. The handler must
    fail closed with the existing uniform 400 (#1337) rather than proceeding to
    a tenant-less read that would 500 and leak the difference."""
    from fastapi import HTTPException

    db = _FailClosedRlsSession(invite=None, user=None, lookup_tenant=None)

    with pytest.raises(HTTPException) as exc:
        await _call(db)

    assert exc.value.status_code == 400
    assert db.tenant_bound is None, "no tenant context may be bound for an unusable token"


@pytest.mark.asyncio
@pytest.mark.parametrize("unusable", ["expired", "revoked", "accepted"])
async def test_unusable_resolved_invite_never_arms_global_context(unusable):
    """A token lookup racing with expiry/revocation must not elevate the session."""
    from fastapi import HTTPException

    tenant_id = uuid.uuid4()
    invite = _make_invite(tenant_id, hashlib.sha256(b"raw-token").hexdigest())
    now = datetime.now(timezone.utc)
    if unusable == "expired":
        invite.expires_at = now - timedelta(days=1)
    else:
        setattr(invite, f"{unusable}_at", now)
    db = _FailClosedRlsSession(invite=invite, user=None, lookup_tenant=tenant_id)

    with pytest.raises(HTTPException) as exc:
        await _call(db)

    assert exc.value.status_code == 400
    assert not db.sysadmin_armed
    assert not any("regengine.is_sysadmin" in sql or "set_admin_context" in sql for sql in db.statements)


@pytest.mark.asyncio
async def test_sqlite_fixture_path_still_works_without_the_definer_function():
    """The SECURITY DEFINER lookup exists only on PostgreSQL. On the SQLite
    test/dev fixture the handler must fall back to the direct read rather than
    hard-failing on a missing function."""
    tenant_id = uuid.uuid4()
    token_hash = hashlib.sha256(b"raw-token").hexdigest()
    db = _FailClosedRlsSession(
        invite=_make_invite(tenant_id, token_hash),
        user=_make_user(),
        lookup_tenant=None,
    )
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    # SQLite has no RLS: nothing raises for want of a tenant context.
    db.tenant_bound = "sqlite-no-rls"

    result = await _call(db)

    assert result["status"] == "success"
    assert not any("get_invite_tenant_by_token_hash" in s for s in db.statements), (
        "the Postgres-only definer function must not be called on SQLite"
    )


@pytest.mark.asyncio
async def test_new_invitee_user_insert_requires_global_admin_context():
    """SEL-612: tenant binding alone cannot authorize a new global user."""
    tenant_id = uuid.uuid4()
    db = _FailClosedRlsSession(
        invite=_make_invite(tenant_id, hashlib.sha256(b"raw-token").hexdigest()),
        user=None,
        lookup_tenant=tenant_id,
    )

    result = await _call(db)

    assert result["status"] == "success"
    assert len(db.flushed_users) == 1
    assert result["user_id"] == str(db.flushed_users[0].id)
    assert db.flushed_users[0].is_sysadmin is False
    assert db.committed
    assert not db.sysadmin_armed


@pytest.mark.asyncio
async def test_identity_failure_disarms_global_context_without_commit():
    tenant_id = uuid.uuid4()
    db = _FailClosedRlsSession(
        invite=_make_invite(tenant_id, hashlib.sha256(b"raw-token").hexdigest()),
        user=_make_user(),
        lookup_tenant=tenant_id,
    )

    def fail_identity(*args, **kwargs):
        assert db.sysadmin_armed
        raise RuntimeError("identity provisioning failed")

    with pytest.raises(RuntimeError, match="identity provisioning failed"):
        await _call(db, identity_effect=fail_identity)

    assert not db.sysadmin_armed
    assert not db.committed


@pytest.mark.asyncio
async def test_identity_flush_conflict_rolls_back_and_returns_uniform_400():
    """The pre-disarm flush can lose the same membership race as commit."""
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    tenant_id = uuid.uuid4()
    db = _FailClosedRlsSession(
        invite=_make_invite(tenant_id, hashlib.sha256(b"raw-token").hexdigest()),
        user=_make_user(),
        lookup_tenant=tenant_id,
    )
    conflict = IntegrityError("INSERT memberships", {}, Exception("duplicate membership"))
    with (
        patch.object(db, "flush", side_effect=conflict),
        patch.object(db, "rollback", create=True) as rollback,
        pytest.raises(HTTPException) as exc,
    ):
        await _call(db)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invite is not usable"
    rollback.assert_called_once_with()
    assert not db.sysadmin_armed
    assert not db.committed


@pytest.mark.asyncio
async def test_identity_writes_flush_before_disarming():
    from app.sqlalchemy_models import OrganizationMembershipModel, UserEmailModel

    tenant_id = uuid.uuid4()
    db = _FailClosedRlsSession(
        invite=_make_invite(tenant_id, hashlib.sha256(b"raw-token").hexdigest()),
        user=_make_user(),
        lookup_tenant=tenant_id,
    )
    pending_identities = [
        UserEmailModel(user_id=db._user.id, email="invitee@example.com", is_verified=True),
        OrganizationMembershipModel(user_id=db._user.id, organization_id=tenant_id, role="member"),
    ]

    def provision_identity(*args, **kwargs):
        assert db.sysadmin_armed
        for identity in pending_identities:
            db.add(identity)

    await _call(db, identity_effect=provision_identity)

    assert db.flushed_identities == pending_identities
    assert not db.sysadmin_armed


@pytest.fixture
def postgres_invite_connection():
    """Use a designated migrated scratch DB; roll back even handler commits."""
    from shared.db_url import sync_postgres_url
    from sqlalchemy import create_engine, text

    from tests.migrations.rls_db import guarded_live_database_url, skip_or_fail_without_db

    database_url = guarded_live_database_url()
    if not database_url:
        skip_or_fail_without_db("accept-invite RLS needs a designated migrated PostgreSQL database")

    engine = create_engine(sync_postgres_url(database_url))
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                if not connection.execute(
                    text("SELECT to_regprocedure('public.get_invite_tenant_by_token_hash(text)') IS NOT NULL")
                ).scalar_one():
                    skip_or_fail_without_db("accept-invite RLS needs a PostgreSQL database migrated through v113")
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("existing_user", [False, True], ids=["new-user", "existing-user"])
async def test_accept_invite_provisions_real_identity_under_postgres_rls(postgres_invite_connection, existing_user):
    """Run the real helper and migrated policies as NOSUPERUSER/NOBYPASSRLS."""
    from app.auth_crypto import AuthCryptoService
    from app.database import arm_global_admin_context, disarm_global_admin_context
    from app.invite_routes import AcceptInviteRequest, accept_invite
    from app.sqlalchemy_models import (
        InviteModel,
        MembershipModel,
        OrganizationMembershipModel,
        OrganizationModel,
        RoleModel,
        TenantModel,
        UserEmailModel,
        UserModel,
    )
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session

    connection = postgres_invite_connection
    tenant_id, role_id, inviter_id, invite_id = (uuid.uuid4() for _ in range(4))
    suffix = uuid.uuid4().hex
    email = f"invitee-{suffix}@example.test"
    token = f"synthetic-invite-{suffix}"
    existing_user_id = uuid.uuid4() if existing_user else None
    # Match SessionLocal's flush/expiration settings. Savepoints keep both the
    # seed and the route's commit inside the fixture's rollback-only transaction.
    session_options = dict(
        bind=connection, autoflush=False, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    with Session(**session_options) as seed:
        seed.add(TenantModel(id=tenant_id, name="Invite RLS tenant", slug=f"invite-rls-{suffix}"))
        seed.add(RoleModel(id=role_id, tenant_id=tenant_id, name="Viewer"))
        seed.add(UserModel(id=inviter_id, email=f"inviter-{suffix}@example.test", is_sysadmin=False))
        if existing_user:
            seed.add(UserModel(id=existing_user_id, email=email, is_sysadmin=False))
        seed.flush()
        seed.add(
            InviteModel(
                id=invite_id,
                tenant_id=tenant_id,
                email=email.upper(),
                role_id=role_id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                created_by=inviter_id,
            )
        )
        seed.commit()

    connection.execute(text("SET LOCAL ROLE regengine_sysadmin"))
    connection.execute(text("SET LOCAL row_security = on"))
    role = connection.execute(
        text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    ).one()
    assert tuple(role) == ("regengine_sysadmin", False, False)
    for table in ("users", "user_emails", "organization_memberships", "invites", "memberships"):
        rls = connection.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity, row_security_active(oid) "
                "FROM pg_class WHERE oid = to_regclass(:table)"
            ),
            {"table": f"public.{table}"},
        ).one()
        assert tuple(rls) == (True, True, True), table
    connection.execute(
        text(
            "SELECT set_config('app.tenant_id', '', true), "
            "set_config('regengine.user_id', '', true), "
            "set_config('regengine.is_sysadmin', 'false', true)"
        )
    )

    crypto = AuthCryptoService(hmac_secret=b"synthetic-invite-rls-test-only-key")  # pragma: allowlist secret
    with Session(**session_options) as db:
        # Even the seeded inviter/existing invitee must be invisible pre-auth.
        assert db.execute(select(UserModel.id)).all() == []
        with (
            patch("app.auth.identity_helpers.AuthCryptoService", return_value=crypto),
            patch("app.invite_routes.AuditLogger.log_event", return_value=uuid.uuid4()),
            patch("app.invite_routes.supplier_graph_sync"),
        ):
            # Deliberately bypass _call: ensure_passwordless_identity stays real.
            result = await accept_invite.__wrapped__(
                payload=AcceptInviteRequest(token=token, name="Invitee"), request=_starlette_request(), db=db
            )

        assert result["status"] == "success"
        user_id = uuid.UUID(result["user_id"])
        if existing_user:
            assert user_id == existing_user_id
        assert db.execute(text("SELECT current_setting('regengine.is_sysadmin')")).scalar_one() == "false"
        assert db.execute(select(UserModel.id)).all() == []

        arm_global_admin_context(db)
        try:
            user = db.execute(select(UserModel).where(UserModel.id == user_id)).scalar_one()
            assert user.email == email
            assert user.is_sysadmin is False
            identity = db.execute(select(UserEmailModel).where(UserEmailModel.user_id == user_id)).scalar_one()
            assert identity.email == email
            assert identity.is_verified is True
            assert identity.email_fingerprint == crypto.fingerprint_email(email)
            organization = db.get(OrganizationModel, tenant_id)
            assert organization is not None
            assert organization.name == "Invite RLS tenant"
            org_membership = db.execute(
                select(OrganizationMembershipModel).where(OrganizationMembershipModel.user_id == user_id)
            ).scalar_one()
            assert org_membership.organization_id == tenant_id
            assert org_membership.role == "viewer"
            membership = db.get(MembershipModel, (user_id, tenant_id))
            assert membership is not None
            assert membership.role_id == role_id
            assert db.get(InviteModel, invite_id).accepted_at is not None
        finally:
            disarm_global_admin_context(db)
