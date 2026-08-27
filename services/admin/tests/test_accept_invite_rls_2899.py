"""#2899 — POST /auth/accept-invite must resolve its tenant before it reads.

``accept_invite`` is a public, unauthenticated route. Every existing test for
it runs on the SQLite fixture (``services/admin/conftest.py`` pins
``ADMIN_DATABASE_URL=sqlite:///:memory:``) where RLS never evaluates, so none
of them exercise what production does.

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
counterpart is ``tests/shared/test_invite_token_lookup_live.py``.
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

    # -- the RLS behaviour under test -----------------------------------
    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)

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
        for obj in self.added:
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


async def _call(db):
    from app.invite_routes import AcceptInviteRequest, accept_invite

    payload = AcceptInviteRequest(token="raw-token", name="Invitee")
    with (
        patch("app.invite_routes.ensure_passwordless_identity"),
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
