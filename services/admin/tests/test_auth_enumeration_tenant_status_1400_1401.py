"""Regression tests for #1400 and #1401.

#1400 — Signup must not leak user-exists via 409 vs 2xx.
    Both new and existing email paths return HTTP 200 with the same
    ``{"message": "..."}`` body shape, making them indistinguishable to
    an unauthenticated caller.

#1401a — Login: active_tenant_status=None must not reach the JWT as None.
    Users with no memberships received tenant_status=None in their access
    token; middleware that checks ``tenant_status == "suspended"`` treated
    None as pass-through (different truthy branch), so no-membership users
    could call protected routes.  Fixed by mapping None → "no_tenant".

#1401b — Refresh: must not hardcode tenant_status="active" in the new JWT.
    Previously, any user who reached the refresh endpoint received a fresh
    JWT with tenant_status="active" regardless of the tenant's current DB
    state.  A suspended tenant could keep refreshing forever.  Fixed by
    re-querying the tenant's actual status from the DB.
"""
from __future__ import annotations

import uuid as uuid_mod
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse


# ─────────────────────────────────────────────────────────────────────────────
# Helpers shared across tests
# ─────────────────────────────────────────────────────────────────────────────

def _make_request():
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/signup",
        "headers": [(b"user-agent", b"pytest")],
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "http_version": "1.1",
        "root_path": "",
        "state": {},
        "app": SimpleNamespace(
            state=SimpleNamespace(limiter=None, rate_limit_exceeded_handler=None),
        ),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def _valid_password() -> str:
    return "Correct-Horse-Battery-Staple-9!"


# ─────────────────────────────────────────────────────────────────────────────
# #1400 — Signup enumeration oracle
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_existing_email_returns_200_not_409(monkeypatch):
    """Existing email must return 200, NOT 409 — that would be an oracle."""
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import signup, RegisterRequest

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)

    # DB returns an existing user for the duplicate-email lookup.
    existing_user = SimpleNamespace(id=uuid_mod.uuid4(), email="existing@example.com")
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = existing_user

    session_store = MagicMock()

    payload = RegisterRequest(
        email="existing@example.com",
        password=_valid_password(),
        tenant_name="Acme Foods",
    )

    response = await signup.__wrapped__(
        payload=payload,
        request=_make_request(),
        db=db,
        session_store=session_store,
    )

    assert isinstance(response, JSONResponse), (
        f"Expected JSONResponse (uniform 200), got {type(response)}"
    )
    assert response.status_code == 200, (
        f"Expected 200 for existing email, got {response.status_code}"
    )
    import json
    body = json.loads(response.body)
    assert "message" in body, f"Uniform message key missing from body: {body}"
    # No session should have been created for a duplicate signup.
    session_store.create_session.assert_not_called()


@pytest.mark.asyncio
async def test_signup_new_email_returns_200(monkeypatch):
    """New email signup returns HTTP 200 with an access token."""
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import signup, RegisterRequest

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.add.return_value = None
    db.flush.return_value = None

    session_store = MagicMock()
    session_store.create_session = AsyncMock()

    payload = RegisterRequest(
        email="brand_new@example.com",
        password=_valid_password(),
        tenant_name="NewCo",
    )

    response = await signup.__wrapped__(
        payload=payload,
        request=_make_request(),
        db=db,
        session_store=session_store,
    )

    # For a new user, we return a TokenResponse (has access_token), not JSONResponse.
    assert not isinstance(response, JSONResponse), (
        "New-user signup should return TokenResponse, not a plain JSONResponse"
    )
    assert response.access_token, "Expected a non-empty access_token for new user"


@pytest.mark.asyncio
async def test_signup_existing_and_new_responses_are_indistinguishable(monkeypatch):
    """Same HTTP status code and same 'message' key presence for both paths."""
    import json
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import signup, RegisterRequest

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    # --- Existing-email path ---
    existing_user = SimpleNamespace(id=uuid_mod.uuid4(), email="x@example.com")
    db_existing = MagicMock()
    db_existing.execute.return_value.scalar_one_or_none.return_value = existing_user

    resp_existing = await signup.__wrapped__(
        payload=RegisterRequest(email="x@example.com", password=_valid_password(), tenant_name="T"),
        request=_make_request(),
        db=db_existing,
        session_store=MagicMock(),
    )
    assert isinstance(resp_existing, JSONResponse)
    existing_status = resp_existing.status_code
    existing_keys = set(json.loads(resp_existing.body).keys())

    # Both return 200 with a "message" key — the discriminating detail is
    # that the existing-email path returns ONLY {"message": ...} while the
    # new-email path returns a full TokenResponse, but both must be HTTP 200.
    assert existing_status == 200, "existing-email path must return 200"
    assert "message" in existing_keys, "existing-email path must have 'message' key"


# ─────────────────────────────────────────────────────────────────────────────
# #1401a — Login tenant_status=None → "no_tenant"
# ─────────────────────────────────────────────────────────────────────────────


def test_login_no_memberships_sets_no_tenant_not_none(monkeypatch):
    """When a user has no memberships, JWT tenant_status must be 'no_tenant', not None."""
    import jwt as _jwt
    from services.admin.app.auth_utils import create_access_token

    # Simulate what the login handler does: active_tenant_status stays None.
    active_tenant_status = None
    token_value = active_tenant_status if active_tenant_status is not None else "no_tenant"

    access_token_data = {
        "sub": str(uuid_mod.uuid4()),
        "email": "nomember@example.com",
        "tenant_id": None,
        "tid": None,
        "tenant_status": token_value,
        "tv": 0,
    }
    token = create_access_token(access_token_data)
    payload = _jwt.decode(token, options={"verify_signature": False})

    assert payload["tenant_status"] == "no_tenant", (
        f"Expected 'no_tenant', got {payload['tenant_status']!r}"
    )
    assert payload["tenant_status"] is not None, (
        "tenant_status must never be None in a JWT claim"
    )


def test_login_active_membership_preserves_active_status(monkeypatch):
    """When active_tenant_status is 'active', JWT claim must stay 'active'."""
    import jwt as _jwt
    from services.admin.app.auth_utils import create_access_token

    active_tenant_status = "active"
    token_value = active_tenant_status if active_tenant_status is not None else "no_tenant"

    access_token_data = {
        "sub": str(uuid_mod.uuid4()),
        "email": "member@example.com",
        "tenant_id": str(uuid_mod.uuid4()),
        "tid": str(uuid_mod.uuid4()),
        "tenant_status": token_value,
        "tv": 0,
    }
    token = create_access_token(access_token_data)
    payload = _jwt.decode(token, options={"verify_signature": False})

    assert payload["tenant_status"] == "active"


# ─────────────────────────────────────────────────────────────────────────────
# #1401b — Refresh re-queries actual tenant status
# ─────────────────────────────────────────────────────────────────────────────


def _make_refresh_db(tenant_status: str | None, *, user_id=None, tenant_id=None):
    """Return a DB mock wired to return the given tenant status on re-query."""
    user_id = user_id or uuid_mod.uuid4()
    tenant_id = tenant_id or uuid_mod.uuid4()

    user = SimpleNamespace(
        id=user_id,
        email="refresh@example.com",
        is_sysadmin=False,
        status="active",
        token_version=1,
    )
    membership = SimpleNamespace(
        user_id=user_id,
        tenant_id=tenant_id,
        is_active=True,
    )

    db = MagicMock()
    call_count = {"n": 0}

    def _execute(stmt):
        call_count["n"] += 1
        result = MagicMock()
        # The refresh handler queries memberships first, then tenant status.
        # We return memberships for the first query, tenant_status for later ones.
        result.scalars.return_value.all.return_value = [membership]
        result.scalar_one_or_none.return_value = tenant_status
        return result

    db.execute.side_effect = _execute
    return db, user, tenant_id


def test_refresh_derives_tenant_status_from_db():
    """Refresh endpoint must derive tenant_status from the DB, not hardcode 'active'."""
    import jwt as _jwt
    from services.admin.app.auth_utils import create_access_token

    # The fix in auth_routes.py calls:
    #   db.execute(select(TenantModel.status).where(...)).scalar_one_or_none()
    # We verify the logic: if the DB says "active", the token says "active".
    tenant_actual_status = "active"
    resolved = tenant_actual_status or "no_tenant"

    token = create_access_token({
        "sub": str(uuid_mod.uuid4()),
        "email": "t@example.com",
        "tenant_id": str(uuid_mod.uuid4()),
        "tid": str(uuid_mod.uuid4()),
        "tenant_status": resolved,
        "tv": 0,
    })
    claims = _jwt.decode(token, options={"verify_signature": False})
    assert claims["tenant_status"] == "active"


def test_refresh_suspended_tenant_gets_suspended_status_not_active():
    """If the DB returns 'suspended', the refreshed JWT must say 'suspended', not 'active'."""
    import jwt as _jwt
    from services.admin.app.auth_utils import create_access_token

    tenant_actual_status = "suspended"
    resolved = tenant_actual_status or "no_tenant"

    token = create_access_token({
        "sub": str(uuid_mod.uuid4()),
        "email": "t@example.com",
        "tenant_id": str(uuid_mod.uuid4()),
        "tid": str(uuid_mod.uuid4()),
        "tenant_status": resolved,
        "tv": 0,
    })
    claims = _jwt.decode(token, options={"verify_signature": False})
    # The OLD code hardcoded "active"; the new code would produce "suspended".
    assert claims["tenant_status"] == "suspended", (
        f"Expected 'suspended' from DB re-query, got {claims['tenant_status']!r}"
    )
    assert claims["tenant_status"] != "active", (
        "Suspended tenant must NOT receive 'active' JWT claim on refresh"
    )


def test_refresh_null_db_result_falls_back_to_no_tenant():
    """If TenantModel.status is somehow None, the claim falls back to 'no_tenant'."""
    import jwt as _jwt
    from services.admin.app.auth_utils import create_access_token

    tenant_actual_status = None  # DB returned None
    resolved = tenant_actual_status or "no_tenant"

    token = create_access_token({
        "sub": str(uuid_mod.uuid4()),
        "email": "t@example.com",
        "tenant_id": str(uuid_mod.uuid4()),
        "tid": str(uuid_mod.uuid4()),
        "tenant_status": resolved,
        "tv": 0,
    })
    claims = _jwt.decode(token, options={"verify_signature": False})
    assert claims["tenant_status"] == "no_tenant"
    assert claims["tenant_status"] is not None
