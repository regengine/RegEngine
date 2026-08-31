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
    monkeypatch.setattr(TenantContext, "get_tenant_context", staticmethod(lambda _db: AUTH_TENANT))
    with pytest.raises(HTTPException) as exc:
        verify_path_tenant_matches(tenant_id=str(OTHER_TENANT), user=_user(), db=MagicMock())
    assert exc.value.status_code == 403
    assert "Tenant mismatch" in exc.value.detail


@pytest.mark.security
def test_path_tenant_match_allowed(monkeypatch):
    """Caller in tenant A passing tenant A's UUID succeeds."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(TenantContext, "get_tenant_context", staticmethod(lambda _db: AUTH_TENANT))
    result = verify_path_tenant_matches(tenant_id=str(AUTH_TENANT), user=_user(), db=MagicMock())
    assert result == AUTH_TENANT


@pytest.mark.security
def test_invalid_tenant_uuid_rejected(monkeypatch):
    """Malformed tenant_id string is rejected with 400."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(TenantContext, "get_tenant_context", staticmethod(lambda _db: AUTH_TENANT))
    with pytest.raises(HTTPException) as exc:
        verify_path_tenant_matches(tenant_id="not-a-uuid", user=_user(), db=MagicMock())
    assert exc.value.status_code == 400


@pytest.mark.security
def test_no_tenant_context_rejected(monkeypatch):
    """Session with no tenant context is rejected (non-sysadmin)."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(TenantContext, "get_tenant_context", staticmethod(lambda _db: None))
    with pytest.raises(HTTPException) as exc:
        verify_path_tenant_matches(tenant_id=str(AUTH_TENANT), user=_user(), db=MagicMock())
    assert exc.value.status_code == 403
    assert "No tenant context active" in exc.value.detail


@pytest.mark.security
def test_low_assurance_sysadmin_cross_tenant_rejected(monkeypatch):
    """Global status never bypasses a tenant-scoped path binding."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(TenantContext, "get_tenant_context", staticmethod(lambda _db: AUTH_TENANT))
    with pytest.raises(HTTPException) as exc:
        verify_path_tenant_matches(tenant_id=str(OTHER_TENANT), user=_user(is_sysadmin=True), db=MagicMock())
    assert exc.value.status_code == 403
    assert "Tenant mismatch" in exc.value.detail


@pytest.mark.security
def test_low_assurance_sysadmin_without_context_rejected(monkeypatch):
    """Tenant-scoped routes require a bound tenant for every caller."""
    verify_path_tenant_matches, TenantContext = _load_dep()
    monkeypatch.setattr(TenantContext, "get_tenant_context", staticmethod(lambda _db: None))
    with pytest.raises(HTTPException) as exc:
        verify_path_tenant_matches(tenant_id=str(OTHER_TENANT), user=_user(is_sysadmin=True), db=MagicMock())
    assert exc.value.status_code == 403
    assert "No tenant context active" in exc.value.detail


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
        "Bare POST /v1/compliance/alerts is the pre-fix shape and must not exist alongside the tenant-scoped path."
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
            if getattr(r, "path", "") == "/v1/compliance/alerts/{tenant_id}" and "POST" in getattr(r, "methods", set())
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
def test_every_compliance_route_uses_tenant_scoped_session():
    """Every route in compliance_routes.router must resolve its
    ``session`` parameter to ``get_tenant_scoped_session``.

    Anchors the per-route adoption from #2159 + the batch conversion of
    the remaining 7 routes. Catches three classes of regression:

      1. A new route added with ``Depends(get_session)`` drops RLS
         enforcement on a write surface.
      2. A merge that reverts the conversion (this exact scenario
         silently happened to #2159 because of the squash-merge
         ordering — the test IS the lock-in).
      3. An accidental rename that removes the ``session`` param entirely.

    Routes without a ``session`` parameter (e.g. pure metadata endpoints)
    are skipped. We assert at least the known set of session-bearing
    routes IS covered, so a future refactor that drops this list to
    zero fails this test.
    """
    compliance_routes = _load_alerts_route()
    from services.admin.app.dependencies import get_tenant_scoped_session

    session_bearing = []
    misbound = []
    for route in compliance_routes.router.routes:
        if not hasattr(route, "dependant"):
            continue
        session_dep = next(
            (d for d in route.dependant.dependencies if getattr(d, "name", None) == "session"),
            None,
        )
        if session_dep is None:
            continue
        session_bearing.append(route.path)
        if session_dep.call is not get_tenant_scoped_session:
            misbound.append(
                f"{sorted(route.methods)} {route.path}: session resolves to {session_dep.call.__qualname__}"
            )

    assert misbound == [], (
        "Every session-bearing route in compliance_routes must use "
        "Depends(get_tenant_scoped_session) so RLS is enforced on the "
        "session for the duration of the request. Misbound routes:\n"
        "  - " + "\n  - ".join(misbound)
    )

    # Sanity: the route set hasn't accidentally collapsed to nothing.
    assert len(session_bearing) >= 8, (
        f"Expected at least 8 session-bearing routes in compliance_routes; "
        f"got {len(session_bearing)}: {session_bearing}. A refactor likely "
        f"removed routes — confirm that's intentional."
    )
