"""Regression tests for #1383 — ``get_current_user`` must not let a request
through tenant-scoped routes without a resolvable tenant.

Previously a JWT missing ``tenant_id`` / ``tid`` would:

  * skip ``TenantContext.set_tenant_context``
  * skip ``TenantContext.clear_tenant_context`` too
  * return the user as if authenticated

On a pooled connection that had served a prior request in tenant X, the
``app.tenant_id`` setting would still be set to X, and RLS policies would
happily scope the current (different) user's reads into tenant X.

PR #1436 closed the multi-membership ambiguity. PR #1444 / migration v056
made RLS fail closed when ``app.tenant_id`` is empty. This test locks down
the remaining gap at the auth layer:

  1. Pooled connection scrubbed before any tenant logic runs.
  2. Zero-membership non-sysadmin with no claim -> 401.
  3. Sysadmins may proceed without a tenant (cross-tenant admin path).
  4. Exactly-one-membership derivation still works (PR #1436 regression).
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, is_sysadmin=False):
        self.id = uuid.uuid4()
        self.is_sysadmin = is_sysadmin


def _make_db(dialect_name="sqlite", memberships=None, user_exists=True, is_sysadmin=False):
    """Build a MagicMock session that behaves enough like a SQLAlchemy
    ``Session`` for ``get_current_user`` to exercise its control flow."""
    memberships = memberships or []
    user = _FakeUser(is_sysadmin=is_sysadmin) if user_exists else None
    db = MagicMock()
    db.bind = MagicMock()
    db.bind.dialect = MagicMock()
    db.bind.dialect.name = dialect_name

    # Track every TenantContext-related SQL so tests can assert scrub order.
    db._executed = []

    def _execute(stmt, params=None):
        db._executed.append((getattr(stmt, "text", None) or str(stmt), params))
        # get_current_user issues three kinds of execute():
        #   1. clear_tenant_context -> SELECT set_config('app.tenant_id','',FALSE)
        #   2. SELECT set_config('regengine.user_id',...)
        #   3. select(MembershipModel) for memberships
        #   4. select(MembershipModel).where tenant_id= ...
        # The MagicMock return value must support .scalars().all() and
        # .scalar_one_or_none(). We branch by arg count.
        result = MagicMock()
        # Memberships query: return the list we were constructed with.
        if memberships and hasattr(stmt, "compile"):
            result.scalars.return_value.all.return_value = memberships
            # Scalar lookup (single membership check): match when params match.
            if params and "tenant_id" not in (params or {}):
                result.scalar_one_or_none.return_value = memberships[0] if memberships else None
            else:
                result.scalar_one_or_none.return_value = memberships[0] if memberships else None
        else:
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
        return result

    db.execute.side_effect = _execute
    db.get.return_value = user
    return db, user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _invoke_get_current_user(token, db, monkeypatch):
    """Call get_current_user() with a stubbed Supabase + JWT decode.

    We drive the async function synchronously using ``asyncio.run`` which
    creates a fresh event loop each time, avoiding loop-reuse warnings
    on Python 3.12 and test-order-pollution where a prior test closed
    the default loop.
    """
    from services.admin.app import dependencies

    # Disable Supabase so we hit the local-JWT branch.
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    # Decode returns whatever ``token`` (a dict) is.
    monkeypatch.setattr(dependencies, "decode_access_token", lambda t: t)

    return asyncio.run(
        dependencies.get_current_user(token=token, db=db)  # type: ignore[arg-type]
    )


def test_zero_memberships_no_tenant_claim_rejected_at_auth_layer(monkeypatch):
    """The core #1383 scenario: token has ``sub`` but no tenant claim,
    user has no memberships, not a sysadmin -> 401."""
    db, _ = _make_db(memberships=[], is_sysadmin=False)
    token = {"sub": str(uuid.uuid4())}

    with pytest.raises(HTTPException) as exc:
        _invoke_get_current_user(token, db, monkeypatch)

    assert exc.value.status_code == 401
    # Must be the tenant-required path specifically, not the generic
    # credentials failure.
    assert "Tenant required" in exc.value.detail or "tenant" in exc.value.detail.lower()


def test_zero_memberships_sysadmin_is_allowed_through(monkeypatch):
    """Sysadmins without a tenant continue to work — they use a separate
    cross-tenant admin path and don't get an ``app.tenant_id`` set."""
    db, user = _make_db(memberships=[], is_sysadmin=True)
    token = {"sub": str(uuid.uuid4())}

    result = _invoke_get_current_user(token, db, monkeypatch)
    assert result is user


def test_single_membership_still_derived_as_tenant(monkeypatch):
    """Regression guard on #1345: one-active-membership users with no
    claim still have tenant derived from the DB."""
    membership = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        is_active=True,
        user_id=uuid.uuid4(),
    )
    db, user = _make_db(memberships=[membership], is_sysadmin=False)
    token = {"sub": str(membership.user_id)}

    result = _invoke_get_current_user(token, db, monkeypatch)
    assert result is user


def test_clear_tenant_context_called_before_user_set_on_postgres(monkeypatch):
    """On PostgreSQL, the first tenant-context SQL statement must be the
    CLEAR, so stale pooled-connection state cannot leak into this
    request's read path."""
    membership = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        is_active=True,
        user_id=uuid.uuid4(),
    )
    db, _ = _make_db(
        dialect_name="postgresql",
        memberships=[membership],
        is_sysadmin=False,
    )
    token = {"sub": str(membership.user_id), "tenant_id": str(membership.tenant_id)}

    _invoke_get_current_user(token, db, monkeypatch)

    # At least one executed statement should look like the clear call.
    rendered = " ".join(str(row[0]) for row in db._executed)
    assert "app.tenant_id" in rendered or "set_config" in rendered
    # And the CLEAR should happen before the user_id set.
    clear_idx = next(
        (i for i, r in enumerate(db._executed)
         if "app.tenant_id" in str(r[0]) and "''" in str(r[0])),
        None,
    )
    set_user_idx = next(
        (i for i, r in enumerate(db._executed)
         if "regengine.user_id" in str(r[0])),
        None,
    )
    assert clear_idx is not None, "expected clear_tenant_context to run first"
    assert set_user_idx is not None
    assert clear_idx < set_user_idx, (
        "clear_tenant_context must precede set_config('regengine.user_id'); "
        "otherwise a stale tenant can scope the user lookup itself"
    )


def test_sqlite_fallback_skips_tenant_setters_but_still_returns_user(monkeypatch):
    """SQLite dev fallback has no RLS — we skip the SET/CLEAR SQL entirely
    but still return the user when a single active membership exists."""
    membership = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        is_active=True,
        user_id=uuid.uuid4(),
    )
    db, user = _make_db(
        dialect_name="sqlite",
        memberships=[membership],
        is_sysadmin=False,
    )
    token = {"sub": str(membership.user_id)}

    result = _invoke_get_current_user(token, db, monkeypatch)
    assert result is user
    # No app.tenant_id related SQL should have run on sqlite.
    for stmt, _ in db._executed:
        assert "app.tenant_id" not in str(stmt)
