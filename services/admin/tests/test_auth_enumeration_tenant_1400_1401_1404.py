"""Tests for auth security fixes — #1400, #1401, #1404.

#1400 — /auth/signup email enumeration via 409 vs 2xx
#1401 — login vs refresh tenant_status divergence
#1404 — rate-limit 429 is an enumeration oracle
"""
from __future__ import annotations

import hashlib
import uuid as uuid_mod
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# Helpers shared across tests
# ─────────────────────────────────────────────────────────────────────────────


def _make_request(headers=None):
    from starlette.requests import Request

    raw_headers = []
    for k, v in (headers or {"user-agent": "pytest"}).items():
        raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/signup",
        "headers": raw_headers,
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


def _make_session_store() -> MagicMock:
    """Session store mock where rate-limit checks always pass (no counter)."""
    store = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.ttl = AsyncMock(return_value=0)

    pipe = MagicMock()
    pipe.incr = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.execute = AsyncMock(return_value=[0, True])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=None)

    client.pipeline = MagicMock(return_value=pipe)
    client.delete = AsyncMock(return_value=True)
    client.setex = AsyncMock(return_value=True)

    store._get_client = AsyncMock(return_value=client)
    store.create_session = AsyncMock(side_effect=lambda sd: sd)
    store.delete_session = AsyncMock(return_value=True)
    return store


# ─────────────────────────────────────────────────────────────────────────────
# #1400 — signup email enumeration
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_existing_email_returns_200_not_409(monkeypatch):
    """#1400 — an already-registered email must return 200, not 409.

    Before the fix, ``POST /auth/signup`` returned HTTP 409 when the email
    already existed. An attacker could distinguish registered from
    unregistered addresses by checking the status code.  The fix returns
    the same 200 + opaque message for both branches.
    """
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import RegisterRequest

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    # DB returns an existing user for the email lookup.
    db = MagicMock()
    existing = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = existing

    session_store = _make_session_store()

    payload = RegisterRequest(
        email="existing@example.com",
        password=_valid_password(),
        tenant_name="Acme Foods",
    )

    result = await auth_routes.signup.__wrapped__(
        payload=payload,
        request=_make_request(),
        db=db,
        session_store=session_store,
    )

    # Must be a JSONResponse (or similar) with status_code 200, not an HTTPException.
    from fastapi.responses import JSONResponse
    assert isinstance(result, JSONResponse), (
        f"expected JSONResponse for duplicate email, got {type(result)}"
    )
    assert result.status_code == 200, (
        f"expected 200 for duplicate email, got {result.status_code}"
    )


@pytest.mark.asyncio
async def test_signup_new_email_also_returns_200(monkeypatch):
    """#1400 — new email must also return 200 (status codes are identical).

    The happy path has always returned 200; this test documents it so a
    future change that makes the new-email path return 201 is caught as a
    potential enumeration regression.
    """
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import RegisterRequest

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
    monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

    db = MagicMock()
    # No existing user — signup proceeds normally.
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.add.return_value = None
    db.flush.return_value = None

    session_store = _make_session_store()

    payload = RegisterRequest(
        email="newuser@example.com",
        password=_valid_password(),
        tenant_name="Acme Foods",
    )

    result = await auth_routes.signup.__wrapped__(
        payload=payload,
        request=_make_request(),
        db=db,
        session_store=session_store,
    )

    # Happy path returns a TokenResponse — check it is not an error response.
    from fastapi.responses import JSONResponse
    assert not isinstance(result, JSONResponse) or result.status_code == 200, (
        f"new-user signup must not return a non-200 JSONResponse"
    )
    # TokenResponse has an access_token attribute.
    if not isinstance(result, JSONResponse):
        assert result.access_token


@pytest.mark.asyncio
async def test_signup_existing_email_response_body_is_opaque(monkeypatch):
    """#1400 — the duplicate-email response body must not mention 'exists'."""
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import RegisterRequest
    import json

    monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)

    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

    session_store = _make_session_store()
    payload = RegisterRequest(
        email="taken@example.com",
        password=_valid_password(),
        tenant_name="Acme",
    )

    from fastapi.responses import JSONResponse
    result = await auth_routes.signup.__wrapped__(
        payload=payload,
        request=_make_request(),
        db=db,
        session_store=session_store,
    )

    assert isinstance(result, JSONResponse)
    body = json.loads(result.body)
    body_str = str(body).lower()
    assert "already" not in body_str, "response body leaks existence of account"
    assert "exist" not in body_str, "response body leaks existence of account"
    # Must contain some message.
    assert "message" in body


# ─────────────────────────────────────────────────────────────────────────────
# #1401 — tenant_status divergence: login vs refresh
# ─────────────────────────────────────────────────────────────────────────────


def test_assert_tenant_active_raises_403_for_suspended():
    """#1401 — _assert_tenant_active raises 403 when status is 'suspended'."""
    from services.admin.app.auth_routes import _assert_tenant_active

    tenant_id = uuid_mod.uuid4()
    tenant = MagicMock()
    tenant.status = "suspended"

    db = MagicMock()
    db.get.return_value = tenant

    with pytest.raises(HTTPException) as exc_info:
        _assert_tenant_active(tenant_id, db)

    assert exc_info.value.status_code == 403


def test_assert_tenant_active_raises_403_for_none_status():
    """#1401 — _assert_tenant_active treats None status as non-active (fail-closed)."""
    from services.admin.app.auth_routes import _assert_tenant_active

    tenant_id = uuid_mod.uuid4()
    tenant = MagicMock()
    tenant.status = None

    db = MagicMock()
    db.get.return_value = tenant

    with pytest.raises(HTTPException) as exc_info:
        _assert_tenant_active(tenant_id, db)

    assert exc_info.value.status_code == 403


def test_assert_tenant_active_raises_403_when_tenant_missing():
    """#1401 — _assert_tenant_active raises 403 if tenant row is missing."""
    from services.admin.app.auth_routes import _assert_tenant_active

    tenant_id = uuid_mod.uuid4()
    db = MagicMock()
    db.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        _assert_tenant_active(tenant_id, db)

    assert exc_info.value.status_code == 403


def test_assert_tenant_active_returns_tenant_for_active():
    """#1401 — _assert_tenant_active returns tenant when status is 'active'."""
    from services.admin.app.auth_routes import _assert_tenant_active

    tenant_id = uuid_mod.uuid4()
    tenant = MagicMock()
    tenant.status = "active"

    db = MagicMock()
    db.get.return_value = tenant

    result = _assert_tenant_active(tenant_id, db)
    assert result is tenant


@pytest.mark.asyncio
async def test_refresh_suspended_tenant_returns_403(monkeypatch):
    """#1401 — refresh must return 403 when the acting tenant is suspended.

    Before the fix, the membership query silently filtered out suspended
    tenants, causing the refresh to 403 with 'No active tenant available'
    rather than an explicit tenant-suspended rejection — and in some
    edge cases it could produce a token with tenant_status='active' for
    a user whose only tenant was suspended, depending on query ordering.

    This test drives _assert_tenant_active via a mock DB that returns
    a suspended tenant for the acting tenant ID.
    """
    from services.admin.app.auth_routes import _assert_tenant_active

    tenant_id = uuid_mod.uuid4()
    tenant = MagicMock()
    tenant.status = "suspended"

    db = MagicMock()
    db.get.return_value = tenant

    with pytest.raises(HTTPException) as exc_info:
        _assert_tenant_active(tenant_id, db)

    assert exc_info.value.status_code == 403
    assert "not active" in exc_info.value.detail.lower()


def test_refreshed_jwt_carries_real_tenant_status(monkeypatch):
    """#1401 — the refreshed access token must carry the tenant's real status.

    We verify that auth_routes.py no longer hardcodes 'active' in the
    access_token_data dict for the refresh path.  We do this by inspecting
    the source of the module for the old hardcoded string inside the
    refresh_session function.
    """
    import inspect
    from services.admin.app import auth_routes

    source = inspect.getsource(auth_routes.refresh_session)
    # The old code had: "tenant_status": "active",
    # The fixed code must reference the tenant object's real status.
    assert '"tenant_status": "active"' not in source, (
        "refresh_session still hardcodes 'active' — "
        "it must use the real tenant.status value (#1401)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# #1404 — rate-limit 429 enumeration oracle
# ─────────────────────────────────────────────────────────────────────────────


def test_email_attempt_key_uses_hash_not_plaintext():
    """#1404 — _email_attempt_key must not store the plaintext email."""
    from services.admin.app.auth_routes import _email_attempt_key

    email = "probe@example.com"
    key = _email_attempt_key(email)

    assert email not in key, (
        f"plaintext email found in Redis key '{key}' — this is an enumeration oracle"
    )
    # Key must contain a SHA-256 hex digest (64 hex chars).
    expected_hash = hashlib.sha256(email.lower().encode()).hexdigest()
    assert expected_hash in key, (
        f"expected SHA-256 hash in key '{key}'"
    )


def test_email_attempt_key_case_insensitive():
    """#1404 — keys for the same email in different cases must be identical."""
    from services.admin.app.auth_routes import _email_attempt_key

    assert _email_attempt_key("User@Example.COM") == _email_attempt_key("user@example.com")


@pytest.mark.asyncio
async def test_rate_limit_fires_for_unknown_email(monkeypatch):
    """#1404 — the rate limiter must reject unknown emails after N attempts.

    Previously only known emails (that matched a DB row) got their attempt
    counter incremented, so an unknown email never hit a 429.  An attacker
    could detect registered emails by watching for 429 vs. no-429 after
    5 failed attempts.

    After the fix, _check_email_rate_limit is keyed by the submitted email
    string and is consulted before any DB lookup, so unknown emails see
    exactly the same 429 behaviour as known ones.
    """
    from services.admin.app.auth_routes import (
        _check_email_rate_limit,
        _record_failed_login_attempt,
        _EMAIL_ATTEMPT_LIMIT,
    )

    # Build a session-store mock whose Redis client returns a count that
    # has already reached the limit.
    store = MagicMock()
    client = MagicMock()

    # Simulate counter at limit.
    client.get = AsyncMock(return_value=str(_EMAIL_ATTEMPT_LIMIT))
    store._get_client = AsyncMock(return_value=client)

    unknown_email = "nobody@unknown-domain.invalid"

    with pytest.raises(HTTPException) as exc_info:
        await _check_email_rate_limit(store, unknown_email)

    assert exc_info.value.status_code == 429, (
        f"expected 429 for unknown email at limit, got {exc_info.value.status_code}"
    )


@pytest.mark.asyncio
async def test_rate_limit_incremented_for_unknown_email_on_failed_login(monkeypatch):
    """#1404 — a failed login against an unknown email must increment the counter.

    We confirm _record_failed_login_attempt is called with the submitted email
    in the login failure branch regardless of whether the user exists.
    """
    from services.admin.app import auth_routes

    # Patch verify_login to always fail (simulates unknown email / wrong password).
    monkeypatch.setattr(auth_routes, "verify_login", lambda pw, user: False)

    # Mock DB — user NOT found.
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    # Track calls to _record_failed_login_attempt.
    recorded: list[str] = []

    original_record = auth_routes._record_failed_login_attempt

    async def _spy_record(store, email):
        recorded.append(email)
        return None  # don't actually hit Redis

    monkeypatch.setattr(auth_routes, "_record_failed_login_attempt", _spy_record)

    # Also patch lockout helpers to be no-ops.
    monkeypatch.setattr(auth_routes, "_check_account_lockout", AsyncMock())
    monkeypatch.setattr(auth_routes, "_check_email_rate_limit", AsyncMock())
    monkeypatch.setattr(auth_routes, "_record_lockout_attempt", AsyncMock())

    from services.admin.app.auth_routes import LoginRequest

    session_store = _make_session_store()

    payload = LoginRequest(email="ghost@nowhere.invalid", password="wrong")
    request = _make_request()

    with pytest.raises(HTTPException) as exc_info:
        await auth_routes.login.__wrapped__(
            payload=payload,
            request=request,
            db=db,
            session_store=session_store,
        )

    assert exc_info.value.status_code == 401
    assert "ghost@nowhere.invalid" in recorded, (
        f"_record_failed_login_attempt was not called for unknown email; "
        f"recorded={recorded}"
    )
