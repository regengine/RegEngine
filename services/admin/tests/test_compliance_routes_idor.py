"""Regression tests for #1328 — compliance routes path-tenant IDOR.

Before the fix, `/v1/compliance/{tenant_id}/...` routes trusted the URL path
tenant_id and forwarded it to the service layer with no comparison against
the authenticated tenant. These tests lock in the fix:
``verify_path_tenant_matches`` rejects any request where the path tenant
differs from the caller's authenticated tenant context.

Written as a direct-call unit test of the dependency function, rather than
a TestClient round-trip, because admin-service TestClient imports are
currently blocked by #1435 (pytest collection stale imports).
"""
from __future__ import annotations

# Admin-test sys.path bootstrap — see services/admin/conftest.py for the
# canonical version. Duplicated here so the test file can load even when the
# parent conftest is bypassed (#1435).
import sys
from pathlib import Path as _Path

_SERVICE_DIR = _Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


AUTH_TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _load_dep():
    """Import lazily so sys.path setup above runs first.

    Uses the fully-qualified ``services.admin.app`` path because pytest
    registers conftest as ``services.admin.conftest`` first, which makes the
    top-level ``app`` alias unreliable.
    """
    from services.admin.app.dependencies import verify_path_tenant_matches
    from services.admin.app.models import TenantContext

    return verify_path_tenant_matches, TenantContext


def _user(is_sysadmin: bool = False):
    u = MagicMock()
    u.id = USER_ID
    u.is_sysadmin = is_sysadmin
    return u


@pytest.mark.security
def test_path_tenant_mismatch_rejected(monkeypatch):
    """Caller in tenant A cannot pass tenant B's UUID in the URL path."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(
        TenantContext, "get_tenant_context", staticmethod(lambda _db: AUTH_TENANT)
    )
    with pytest.raises(HTTPException) as exc:
        verify_path_tenant_matches(
            tenant_id=str(OTHER_TENANT), user=_user(), db=MagicMock()
        )
    assert exc.value.status_code == 403
    assert "Tenant mismatch" in exc.value.detail


@pytest.mark.security
def test_path_tenant_match_allowed(monkeypatch):
    """Caller in tenant A passing tenant A's UUID succeeds."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(
        TenantContext, "get_tenant_context", staticmethod(lambda _db: AUTH_TENANT)
    )
    result = verify_path_tenant_matches(
        tenant_id=str(AUTH_TENANT), user=_user(), db=MagicMock()
    )
    assert result == AUTH_TENANT


@pytest.mark.security
def test_invalid_tenant_uuid_rejected(monkeypatch):
    """Malformed tenant_id string is rejected with 400."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(
        TenantContext, "get_tenant_context", staticmethod(lambda _db: AUTH_TENANT)
    )
    with pytest.raises(HTTPException) as exc:
        verify_path_tenant_matches(
            tenant_id="not-a-uuid", user=_user(), db=MagicMock()
        )
    assert exc.value.status_code == 400


@pytest.mark.security
def test_no_tenant_context_rejected(monkeypatch):
    """Session with no tenant context is rejected (non-sysadmin)."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(
        TenantContext, "get_tenant_context", staticmethod(lambda _db: None)
    )
    with pytest.raises(HTTPException) as exc:
        verify_path_tenant_matches(
            tenant_id=str(AUTH_TENANT), user=_user(), db=MagicMock()
        )
    assert exc.value.status_code == 403
    assert "No tenant context active" in exc.value.detail


@pytest.mark.security
def test_sysadmin_cross_tenant_allowed(monkeypatch):
    """Sysadmin may cross tenant boundaries for support/ops workflows."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(
        TenantContext, "get_tenant_context", staticmethod(lambda _db: AUTH_TENANT)
    )
    result = verify_path_tenant_matches(
        tenant_id=str(OTHER_TENANT), user=_user(is_sysadmin=True), db=MagicMock()
    )
    assert result == OTHER_TENANT


@pytest.mark.security
def test_sysadmin_without_context_allowed(monkeypatch):
    """Sysadmin without a tenant context may still act (cross-tenant ops)."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(
        TenantContext, "get_tenant_context", staticmethod(lambda _db: None)
    )
    result = verify_path_tenant_matches(
        tenant_id=str(OTHER_TENANT), user=_user(is_sysadmin=True), db=MagicMock()
    )
    assert result == OTHER_TENANT
