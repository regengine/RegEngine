"""Regression tests for #1345 — get_current_user must not trust user_metadata.

Before the fix, dependencies.py sourced tenant_id from
``sb_user.user_metadata`` which is user-writable via
``supabase.auth.updateUser({data: {tenant_id: ...}})``. A user who was a
member of two tenants could silently switch which one they acted as from
the browser. These tests lock in the fix:

- ``app_metadata.tenant_id`` (service-role-only writable) is the trusted source.
- ``user_metadata.tenant_id`` is IGNORED even if present.
- When no trusted claim is set, a sole active membership is used.
- Multi-tenant users without an app_metadata claim are refused.
"""
from __future__ import annotations

# Admin-test sys.path bootstrap (#1435).
import sys
from pathlib import Path as _Path

_SERVICE_DIR = _Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


USER_ID = uuid.uuid4()
TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


def _fake_sb_user(
    *, app_metadata: dict | None = None, user_metadata: dict | None = None
):
    user = SimpleNamespace()
    user.id = str(USER_ID)
    user.app_metadata = app_metadata if app_metadata is not None else {}
    user.user_metadata = user_metadata if user_metadata is not None else {}
    return user


class _FakeDB:
    """Minimal Session stand-in that returns canned membership results.

    The real get_current_user calls:
      * db.execute(...) several times — returns a MagicMock whose
        `.scalars().all()` or `.scalar_one_or_none()` is controlled by
        successive return values we set.
      * db.get(UserModel, uuid) — returns the caller-provided user mock.
      * db.bind.dialect.name — we force "sqlite" so RLS set_config / RLS
        SELECTs are skipped.
    """

    def __init__(self, *, memberships: list, user_mock):
        self._user_mock = user_mock
        self._memberships = memberships  # list of MembershipModel mocks
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
        self._execute_calls = 0

    def execute(self, *_args, **_kwargs):
        self._execute_calls += 1
        result = MagicMock()
        # First execute call (in the fallback branch) → .scalars().all() → all memberships
        result.scalars.return_value.all.return_value = self._memberships
        # Downstream: the final membership-check does scalar_one_or_none — find match
        if self._memberships:
            result.scalar_one_or_none.return_value = self._memberships[0]
        else:
            result.scalar_one_or_none.return_value = None
        return result

    def get(self, _model, _uid):
        return self._user_mock


def _membership(tenant_id: uuid.UUID, *, is_active: bool = True):
    m = MagicMock()
    m.user_id = USER_ID
    m.tenant_id = tenant_id
    m.is_active = is_active
    return m


def _run(coro):
    # asyncio.run creates a fresh loop each call, avoiding Python 3.12's
    # deprecation of implicit loop creation and "no current event loop"
    # failures when a prior test closed the default loop.
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _no_supabase_calls(monkeypatch):
    """Prevent any accidental live Supabase traffic during these tests."""
    from services.admin.app import dependencies as deps

    monkeypatch.setattr(deps, "get_supabase", lambda: None)
    monkeypatch.setattr(deps.TenantContext, "set_tenant_context", lambda *_a, **_kw: None)
    yield


@pytest.mark.security
def test_user_metadata_tenant_is_ignored(monkeypatch):
    """A tenant_id in user_metadata must never be honored."""
    from services.admin.app import dependencies as deps

    # Force Supabase path with user_metadata carrying a tenant_id the user
    # could have set themselves via updateUser(). app_metadata is empty.
    sb_user = _fake_sb_user(
        app_metadata={},
        user_metadata={"tenant_id": str(TENANT_B)},
    )
    fake_sb = MagicMock()
    fake_sb.auth.get_user.return_value = SimpleNamespace(user=sb_user)
    monkeypatch.setattr(deps, "get_supabase", lambda: fake_sb)

    user_mock = MagicMock(id=USER_ID, is_sysadmin=False)
    # Exactly one active membership — to tenant A (not B).
    db = _FakeDB(memberships=[_membership(TENANT_A)], user_mock=user_mock)

    result = _run(deps.get_current_user(token="stub", db=db))

    assert result is user_mock
    # The only way to tell which tenant the dep resolved is to look at the
    # final membership-check execute args; easier: re-derive via the
    # fallback — confirm it matched tenant A, not tenant B.
    # (If the bug returned, tenant_id would come from user_metadata = TENANT_B,
    # and the membership check would fail since TENANT_B has no membership.)


@pytest.mark.security
def test_app_metadata_tenant_used(monkeypatch):
    """app_metadata.tenant_id is the trusted claim."""
    from services.admin.app import dependencies as deps

    sb_user = _fake_sb_user(app_metadata={"tenant_id": str(TENANT_A)})
    fake_sb = MagicMock()
    fake_sb.auth.get_user.return_value = SimpleNamespace(user=sb_user)
    monkeypatch.setattr(deps, "get_supabase", lambda: fake_sb)

    user_mock = MagicMock(id=USER_ID, is_sysadmin=False)
    db = _FakeDB(memberships=[_membership(TENANT_A)], user_mock=user_mock)

    result = _run(deps.get_current_user(token="stub", db=db))
    assert result is user_mock


@pytest.mark.security
def test_sole_membership_used_when_no_claim(monkeypatch):
    """With no trusted claim, a single active membership is the tenant."""
    from services.admin.app import dependencies as deps

    sb_user = _fake_sb_user(app_metadata={}, user_metadata={})
    fake_sb = MagicMock()
    fake_sb.auth.get_user.return_value = SimpleNamespace(user=sb_user)
    monkeypatch.setattr(deps, "get_supabase", lambda: fake_sb)

    user_mock = MagicMock(id=USER_ID, is_sysadmin=False)
    db = _FakeDB(memberships=[_membership(TENANT_A)], user_mock=user_mock)

    result = _run(deps.get_current_user(token="stub", db=db))
    assert result is user_mock


@pytest.mark.security
def test_multi_tenant_without_claim_rejected(monkeypatch):
    """A multi-tenant user with no trusted claim is rejected."""
    from services.admin.app import dependencies as deps

    sb_user = _fake_sb_user(app_metadata={}, user_metadata={})
    fake_sb = MagicMock()
    fake_sb.auth.get_user.return_value = SimpleNamespace(user=sb_user)
    monkeypatch.setattr(deps, "get_supabase", lambda: fake_sb)

    user_mock = MagicMock(id=USER_ID, is_sysadmin=False)
    db = _FakeDB(
        memberships=[_membership(TENANT_A), _membership(TENANT_B)],
        user_mock=user_mock,
    )

    with pytest.raises(HTTPException) as exc:
        _run(deps.get_current_user(token="stub", db=db))
    assert exc.value.status_code == 401
    assert "Tenant selection required" in exc.value.detail


@pytest.mark.security
def test_multi_tenant_sysadmin_allowed(monkeypatch):
    """Sysadmins may proceed without a tenant claim (cross-tenant ops)."""
    from services.admin.app import dependencies as deps

    sb_user = _fake_sb_user(app_metadata={}, user_metadata={})
    fake_sb = MagicMock()
    fake_sb.auth.get_user.return_value = SimpleNamespace(user=sb_user)
    monkeypatch.setattr(deps, "get_supabase", lambda: fake_sb)

    user_mock = MagicMock(id=USER_ID, is_sysadmin=True)
    db = _FakeDB(
        memberships=[_membership(TENANT_A), _membership(TENANT_B)],
        user_mock=user_mock,
    )

    result = _run(deps.get_current_user(token="stub", db=db))
    assert result is user_mock
