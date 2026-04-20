"""Regression tests for #1065 — ``PermissionChecker`` must not let a sysadmin
through tenant-scoped routes without a resolvable tenant context.

Previously ``PermissionChecker.__call__`` short-circuited to ``return True``
when ``TenantContext.get_tenant_context(db)`` returned ``None`` AND
``user.is_sysadmin`` was set. That broke the fail-closed invariant: the
endpoint is about to operate on some tenant's resource, and the check has
no idea which tenant — yet it silently permitted. The fix removes the
bypass entirely. Sysadmins are still globally authorized, but only once a
tenant context IS bound (the normal RBAC path below evaluates the sysadmin
privilege there).

See services/admin/app/dependencies.py ``PermissionChecker`` and #1065.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, is_sysadmin: bool = False):
        self.id = uuid.uuid4()
        self.is_sysadmin = is_sysadmin


def _make_db_with_tenant_context(tenant_uuid):
    """Return a MagicMock db whose ``TenantContext.get_tenant_context`` will
    be patched to return ``tenant_uuid`` (or ``None``)."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sysadmin_without_tenant_context_is_rejected(monkeypatch):
    """A sysadmin user with NO tenant context bound must be rejected with
    403 ``E_NO_TENANT_CONTEXT`` — the pre-#1065 bypass is gone."""
    from services.admin.app import dependencies as deps

    # No tenant context -> get_tenant_context returns None.
    monkeypatch.setattr(
        deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: None)
    )

    checker = deps.PermissionChecker("users.read")
    user = _FakeUser(is_sysadmin=True)
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        checker(user=user, db=db)

    assert exc.value.status_code == 403
    assert "E_NO_TENANT_CONTEXT" in exc.value.detail


def test_sysadmin_with_tenant_context_passes_rbac_check(monkeypatch):
    """Sysadmin + bound tenant context must reach the normal RBAC path. We
    model that by returning a role with the required permission so the
    check resolves to ``True`` (i.e. didn't short-circuit at the
    no-context branch)."""
    from services.admin.app import dependencies as deps

    tenant_id = uuid.uuid4()
    monkeypatch.setattr(
        deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: tenant_id)
    )

    # Stub out ``has_permission`` so we don't need a real RoleModel graph.
    monkeypatch.setattr(deps, "has_permission", lambda perms, required: True)

    # Build a db mock whose ``db.execute(...).scalar_one_or_none()`` returns a
    # role object — any truthy object with a ``permissions`` attribute works
    # because ``has_permission`` is stubbed above.
    role = MagicMock()
    role.permissions = ["users.read"]
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = role
    db = MagicMock()
    db.execute.return_value = execute_result

    checker = deps.PermissionChecker("users.read")
    user = _FakeUser(is_sysadmin=True)

    # Must NOT raise — the normal RBAC path permits.
    assert checker(user=user, db=db) is True


def test_non_sysadmin_without_tenant_context_still_rejected(monkeypatch):
    """Regression guard: non-sysadmin + no tenant context was already
    rejected before #1065 and must remain so — same 403,
    ``E_NO_TENANT_CONTEXT``."""
    from services.admin.app import dependencies as deps

    monkeypatch.setattr(
        deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: None)
    )

    checker = deps.PermissionChecker("users.read")
    user = _FakeUser(is_sysadmin=False)
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        checker(user=user, db=db)

    assert exc.value.status_code == 403
    assert "E_NO_TENANT_CONTEXT" in exc.value.detail
