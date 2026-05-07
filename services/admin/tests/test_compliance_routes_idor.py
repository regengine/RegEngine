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


# ---------------------------------------------------------------------------
# Regression: POST /v1/compliance/alerts no longer trusts body tenant_id.
#
# Pre-fix the route was POST /v1/compliance/alerts and CreateAlertRequest
# carried tenant_id as a body field. A caller in tenant A could POST a body
# claiming tenant B and have the alert created there with only the
# analysis.create scope. The fix:
#  - moves tenant_id off the body
#  - moves the route to /alerts/{tenant_id}
#  - binds tenant_id via verify_path_tenant_matches
# ---------------------------------------------------------------------------


def _load_alerts_route():
    """Import the compliance_routes module after sys.path setup."""
    from services.admin.app import compliance_routes

    return compliance_routes


@pytest.mark.security
def test_create_alert_request_has_no_tenant_id_field():
    """CreateAlertRequest must not accept a body tenant_id.

    A leftover body field would re-open the IDOR even with the path-based
    dependency in place — the service layer would silently prefer the body.
    """
    compliance_routes = _load_alerts_route()
    fields = compliance_routes.CreateAlertRequest.model_fields
    assert "tenant_id" not in fields, (
        "CreateAlertRequest.tenant_id was reintroduced — this re-opens the "
        "cross-tenant alert IDOR. Keep tenant binding on the URL path "
        "behind verify_path_tenant_matches."
    )


@pytest.mark.security
def test_create_alert_route_path_is_tenant_scoped():
    """POST /alerts must be /alerts/{tenant_id}, not the bare /alerts."""
    compliance_routes = _load_alerts_route()
    post_alert_paths = {
        r.path
        for r in compliance_routes.router.routes
        if "POST" in getattr(r, "methods", set())
        and (r.path.endswith("/alerts") or r.path.endswith("/alerts/{tenant_id}"))
    }
    assert "/v1/compliance/alerts/{tenant_id}" in post_alert_paths, (
        f"Expected POST /v1/compliance/alerts/{{tenant_id}} (path-bound "
        f"tenant). Found POST alert paths: {post_alert_paths}"
    )
    assert "/v1/compliance/alerts" not in post_alert_paths, (
        "Bare POST /v1/compliance/alerts is the pre-fix shape and must not "
        "exist alongside the tenant-scoped path."
    )


@pytest.mark.security
def test_create_alert_route_uses_verify_path_tenant_matches():
    """The /alerts/{tenant_id} POST route must depend on
    verify_path_tenant_matches — either as a function-signature default
    or in the route's dependencies list. Without it the path tenant_id
    is taken at face value and the IDOR is unfixed.
    """
    compliance_routes = _load_alerts_route()
    verify_path_tenant_matches, _ = _load_dep()

    target = next(
        (
            r
            for r in compliance_routes.router.routes
            if getattr(r, "path", "") == "/v1/compliance/alerts/{tenant_id}"
            and "POST" in getattr(r, "methods", set())
        ),
        None,
    )
    assert target is not None, "POST /v1/compliance/alerts/{tenant_id} not found"

    # Walk the FastAPI dependant graph for any reference to
    # verify_path_tenant_matches. The dependency may be supplied as a
    # function-signature default (Depends(...) in the handler params) or
    # as a route-level dependencies=[...] entry; both end up as nodes in
    # the dependant tree.
    found = False
    if hasattr(target, "dependant"):
        stack = [target.dependant]
        while stack:
            d = stack.pop()
            if getattr(d, "call", None) is verify_path_tenant_matches:
                found = True
                break
            stack.extend(getattr(d, "dependencies", []))
    assert found, (
        "POST /v1/compliance/alerts/{tenant_id} does not depend on "
        "verify_path_tenant_matches; the IDOR fix is incomplete."
    )


@pytest.mark.security
def test_create_alert_route_uses_tenant_scoped_session():
    """The /alerts/{tenant_id} POST route must use get_tenant_scoped_session
    (not the bare get_session) so app.tenant_id is bound on the session
    for the duration of the request and RLS enforces tenant boundaries
    even if a downstream query forgets its WHERE tenant_id predicate.
    Defense-in-depth on top of verify_path_tenant_matches.
    """
    compliance_routes = _load_alerts_route()
    from services.admin.app.database import get_session
    from services.admin.app.dependencies import get_tenant_scoped_session

    target = next(
        (
            r
            for r in compliance_routes.router.routes
            if getattr(r, "path", "") == "/v1/compliance/alerts/{tenant_id}"
            and "POST" in getattr(r, "methods", set())
        ),
        None,
    )
    assert target is not None

    # Inspect the handler's IMMEDIATE deps (target.dependant.dependencies)
    # rather than the whole transitive graph: get_session legitimately
    # appears deeper because verify_path_tenant_matches takes a session
    # for the auth-context lookup. What we care about is what the handler's
    # ``session`` parameter actually resolves to.
    session_param_dep = next(
        (
            d
            for d in target.dependant.dependencies
            if getattr(d, "name", None) == "session"
        ),
        None,
    )
    assert session_param_dep is not None, (
        "Handler must have a ``session`` parameter; signature changed?"
    )
    assert session_param_dep.call is get_tenant_scoped_session, (
        f"Handler's ``session`` must resolve to get_tenant_scoped_session "
        f"(RLS-enforcing); got {session_param_dep.call.__qualname__}. The "
        f"bare get_session does NOT bind app.tenant_id, so a forgotten "
        f"WHERE predicate would leak across tenants."
    )
