"""Regression tests for GDPR issue #1095.

Problem pre-fix
---------------
``services/admin/app/tool_verification_routes.py`` writes rows to
``tool_leads`` whenever a public visitor verifies their email on a
marketing tool. Those visitors are GDPR data subjects (Art. 17) but
have **no account** -- so the authenticated ``/v1/account/erasure``
endpoint (gated by ``get_current_user``) is unreachable to them.
Requiring a support ticket violates GDPR Art. 12(2) ease-of-exercise.

Fix
---
Two public endpoints mirror the existing verify/confirm email-control
pattern:

* ``POST /api/v1/tools/lead-erasure/request`` -- sends a 6-digit code.
* ``POST /api/v1/tools/lead-erasure/confirm`` -- deletes the
  ``tool_leads`` row once the code round-trips.

The ``/request`` endpoint returns ``202 code_sent`` regardless of
whether the email is in ``tool_leads`` so it cannot be used as an
enumeration oracle. Erasure codes are stored under a dedicated
``lead_erasure:`` key namespace so a verification code cannot be
cross-presented at the erasure confirm endpoint (or vice versa).

Tests below lock in the behavior:

1. /request with a valid email returns 202 and invokes the sender.
2. /request with an unknown (never-seen) email ALSO returns 202 -- no
   enumeration oracle.
3. /confirm with the wrong code returns 400.
4. /confirm with the correct code deletes the tool_leads row and
   returns 200.
5. Audit log uses ``mask_email`` so raw PII is not written.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

# Make services/admin importable -- mirrors the pattern in
# tests/test_tool_access_jwt_separation.py.
_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))


# slowapi's @limiter.limit decorator pulls ``request.client.host`` out of
# the Request object to key rate-limit buckets; it insists on a real
# starlette.Request instance. Build the minimum viable scope so endpoint
# handlers can be invoked directly from unit tests without spinning up a
# full TestClient.
def _stub_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }
    req = Request(scope)
    # slowapi's async_wrapper reads request.state.view_rate_limit after
    # calling _check_request_limit (which we patch to a no-op). Pre-set the
    # attribute so the wrapper does not raise AttributeError.
    req.state.view_rate_limit = None
    return req


# ----------------------------------------------------------------------
# Rate-limit bypass
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def disable_slowapi(monkeypatch):
    """Patch slowapi's request-level check so it never raises RateLimitExceeded.

    Unit tests invoke endpoint handler functions directly (not through a
    TestClient), so the @limiter.limit decorator fires against a stub
    Request whose IP is always 127.0.0.1. Without this bypass the shared
    MemoryStorage accumulates hits and trips the 3/min bucket on the fourth
    test in the suite. Patching at the Limiter class level means the patch
    is guaranteed to cover every endpoint touched in the file.
    """
    try:
        import slowapi.extension as _se
        monkeypatch.setattr(_se.Limiter, "_check_request_limit", lambda *a, **k: None)
    except Exception:
        pass


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def tvr(monkeypatch):
    """Re-import tool_verification_routes with a known TOOL_ACCESS_SECRET.

    The module resolves ``TOOL_ACCESS_SECRET`` at import time; tests
    that need a predictable value re-import after setting the env var.
    This also ensures RESEND_API_KEY is unset so ``_send_erasure_email``
    falls through to the dev-mode log path, decoupling the endpoint
    from external HTTP.
    """
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "lead-erasure-test-secret")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    for modname in [
        "app.tool_verification_routes",
        "services.admin.app.tool_verification_routes",
    ]:
        if modname in sys.modules:
            del sys.modules[modname]
    module = importlib.import_module("app.tool_verification_routes")
    # Clear the module-level in-memory store so state does not leak
    # across tests.
    module._memory_store.clear()
    # Force the redis-available flag off so the in-memory code store
    # is used regardless of the host's Redis availability.
    module._redis_available = False
    module._redis_client = None
    # Re-import clears the RESEND_API_KEY at module scope as well.
    module.RESEND_API_KEY = None
    # Reset the slowapi rate-limiter storage between tests -- the
    # module-level ``limiter`` keys buckets on client IP, and our
    # stub Request always reports ``127.0.0.1``, so without a reset
    # the third /request invocation in the suite trips the 3/min limit.
    # slowapi.Limiter does not expose reset() directly; the actual counter
    # store lives at limiter._storage (a limits.MemoryStorage instance).
    # We also clear via limiter._storage.clear() per-key as a belt-and-
    # suspenders approach -- the shared singleton must be clean before
    # each test so the 3/min bucket does not trip cross-test.
    try:
        module.limiter._storage.reset()
    except Exception:
        pass
    try:
        # limits >= 3.x renamed reset() → clear() on MemoryStorage
        module.limiter._storage.clear()
    except Exception:
        pass
    # Belt-and-suspenders: directly wipe the internal dicts when the
    # above methods are absent (different limits library version).
    try:
        module.limiter._storage.storage.clear()  # MemoryStorage.storage dict
    except Exception:
        pass
    try:
        module.limiter._storage.expirations.clear()
    except Exception:
        pass
    return module


# ----------------------------------------------------------------------
# Request endpoint
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_lead_erasure_valid_email_returns_202_and_sends_code(tvr):
    """/request with a well-formed email stores a code and invokes the sender."""
    payload = tvr.LeadErasureRequest(email="lead@corp.com")

    with patch.object(tvr, "_send_erasure_email") as mock_send:
        result = await tvr.request_lead_erasure(request=_stub_request(), payload=payload)

    assert result == {"status": "code_sent"}
    mock_send.assert_called_once()
    # The sender is invoked with (email, code); both are positional.
    args, _ = mock_send.call_args
    assert args[0] == "lead@corp.com"
    assert len(args[1]) == 6 and args[1].isdigit()

    # Code was persisted under the dedicated lead_erasure namespace.
    assert "lead_erasure:lead@corp.com" in tvr._memory_store
    # And NOT under the tool_verify namespace -- the whole point of the
    # separate keyspace (#1095).
    assert "tool_verify:lead@corp.com" not in tvr._memory_store


@pytest.mark.asyncio
async def test_request_lead_erasure_unknown_email_also_returns_202(tvr):
    """No enumeration oracle: unknown emails get the same 202 response.

    The endpoint never reads ``tool_leads`` on /request, so it cannot
    differentiate between "email is a known lead" and "we've never seen
    you". This test pins that contract: we pass an email that was
    never inserted into tool_leads and still get ``code_sent``.
    """
    payload = tvr.LeadErasureRequest(email="never-heard-of@unknown.com")

    with patch.object(tvr, "_send_erasure_email") as mock_send:
        result = await tvr.request_lead_erasure(request=_stub_request(), payload=payload)

    assert result == {"status": "code_sent"}
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_request_lead_erasure_lowercases_email(tvr):
    """Email is normalized to lower-case before storage, matching the
    ``_save_lead`` insert path above.  This keeps the same lookup key
    regardless of how the user typed their address on /request vs
    /confirm."""
    payload = tvr.LeadErasureRequest(email="Mixed.Case@CORP.COM")

    with patch.object(tvr, "_send_erasure_email"):
        await tvr.request_lead_erasure(request=_stub_request(), payload=payload)

    assert "lead_erasure:mixed.case@corp.com" in tvr._memory_store
    assert "lead_erasure:Mixed.Case@CORP.COM" not in tvr._memory_store


# ----------------------------------------------------------------------
# Confirm endpoint
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirm_lead_erasure_wrong_code_returns_400(tvr):
    """An invalid code must not trigger DELETE."""
    from fastapi import HTTPException

    # Store a code for lead@corp.com
    with patch.object(tvr, "_send_erasure_email"):
        await tvr.request_lead_erasure(
            request=_stub_request(), payload=tvr.LeadErasureRequest(email="lead@corp.com")
        )

    # Submit the wrong code and expect a 400.
    wrong = tvr.ConfirmLeadErasureRequest(email="lead@corp.com", code="000000")

    delete_called = []

    class _FakeSession:
        def execute(self, *args, **kwargs):  # pragma: no cover - not reached
            delete_called.append(args)
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    with patch("app.database.SessionLocal", lambda: _FakeSession()):
        with pytest.raises(HTTPException) as excinfo:
            await tvr.confirm_lead_erasure(request=_stub_request(), payload=wrong)

    assert excinfo.value.status_code == 400
    assert not delete_called, "DELETE must not run when the code is wrong"


@pytest.mark.asyncio
async def test_confirm_lead_erasure_missing_code_returns_400(tvr):
    """Presenting a code for an email that never went through /request
    must be rejected -- no session, no erasure."""
    from fastapi import HTTPException

    payload = tvr.ConfirmLeadErasureRequest(
        email="no-session@corp.com", code="123456"
    )

    with pytest.raises(HTTPException) as excinfo:
        await tvr.confirm_lead_erasure(request=_stub_request(), payload=payload)

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_lead_erasure_correct_code_deletes_and_returns_200(tvr):
    """Happy path: a correct code deletes the tool_leads row."""
    # Store a code via /request and capture it from the in-memory store.
    with patch.object(tvr, "_send_erasure_email"):
        await tvr.request_lead_erasure(
            request=_stub_request(), payload=tvr.LeadErasureRequest(email="lead@corp.com")
        )
    stored_code = tvr._memory_store["lead_erasure:lead@corp.com"]["code"]

    # Capture the DELETE statement text + bound params without hitting
    # an actual Postgres. The endpoint's contract is:
    #   DELETE FROM tool_leads WHERE LOWER(email) = :email
    executed = []

    class _FakeSession:
        def execute(self, stmt, params=None):
            # stmt is a SQLAlchemy TextClause; str() gives the raw SQL.
            executed.append((str(stmt), params))
            return None

        def commit(self):
            executed.append(("COMMIT", None))

        def rollback(self):
            executed.append(("ROLLBACK", None))

        def close(self):
            executed.append(("CLOSE", None))

    payload = tvr.ConfirmLeadErasureRequest(
        email="lead@corp.com", code=stored_code
    )

    with patch("app.database.SessionLocal", lambda: _FakeSession()):
        result = await tvr.confirm_lead_erasure(request=_stub_request(), payload=payload)

    assert result == {"status": "erased"}

    # The DELETE must have run before commit.
    sqls = [s for s, _ in executed]
    assert any("DELETE FROM tool_leads" in s for s in sqls), sqls
    assert "COMMIT" in sqls
    # And the param is the lower-cased email -- matches LOWER(email) on
    # the WHERE side so any cased variant inserted originally is
    # still captured.
    delete_params = next(
        p for s, p in executed if "DELETE FROM tool_leads" in s
    )
    assert delete_params == {"email": "lead@corp.com"}


@pytest.mark.asyncio
async def test_confirm_lead_erasure_consumes_code_single_use(tvr):
    """After a successful /confirm the code is deleted from the store,
    so replaying it yields a fresh 400. This is a property of the
    shared ``_check_code`` helper but regression-pinned here to
    guarantee nobody wires /confirm to a read-without-delete helper."""
    from fastapi import HTTPException

    with patch.object(tvr, "_send_erasure_email"):
        await tvr.request_lead_erasure(
            request=_stub_request(), payload=tvr.LeadErasureRequest(email="lead@corp.com")
        )
    stored_code = tvr._memory_store["lead_erasure:lead@corp.com"]["code"]

    class _FakeSession:
        def execute(self, *a, **k): return None
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    with patch("app.database.SessionLocal", lambda: _FakeSession()):
        await tvr.confirm_lead_erasure(
            request=_stub_request(),
            payload=tvr.ConfirmLeadErasureRequest(
                email="lead@corp.com", code=stored_code
            ),
        )

        # Replay -- the code is now gone.
        with pytest.raises(HTTPException) as excinfo:
            await tvr.confirm_lead_erasure(
                request=_stub_request(),
                payload=tvr.ConfirmLeadErasureRequest(
                    email="lead@corp.com", code=stored_code
                ),
            )
    assert excinfo.value.status_code == 400


# ----------------------------------------------------------------------
# Cross-namespace isolation (#1095 core security property)
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verification_code_cannot_be_used_for_erasure(tvr):
    """A code issued by the verify-email flow lives under
    ``tool_verify:<email>`` and MUST NOT authenticate the erasure flow.
    This test plants a code in the verify namespace and confirms that
    /lead-erasure/confirm still rejects it."""
    from fastapi import HTTPException

    await tvr._store_code("lead@corp.com", "654321")  # verify namespace

    class _FakeSession:
        def execute(self, *a, **k): return None
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    with patch("app.database.SessionLocal", lambda: _FakeSession()):
        with pytest.raises(HTTPException) as excinfo:
            await tvr.confirm_lead_erasure(
                request=_stub_request(),
                payload=tvr.ConfirmLeadErasureRequest(
                    email="lead@corp.com", code="654321"
                ),
            )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_erasure_code_cannot_be_used_for_verification(tvr):
    """Symmetric counterpart: an erasure code must not authenticate
    /confirm-code. This keeps a leaked lead-erasure code from being
    laundered into a valid tool-access JWT."""
    from fastapi import HTTPException

    await tvr._store_erasure_code("lead@corp.com", "987654")

    payload = tvr.ConfirmCodeRequest(
        email="lead@corp.com", code="987654", tool_name="unit-test"
    )
    with pytest.raises(HTTPException) as excinfo:
        await tvr.confirm_code(payload=payload, request=_stub_request())
    assert excinfo.value.status_code == 400


# ----------------------------------------------------------------------
# Audit-log hygiene (mask_email)
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lead_erasure_logs_use_mask_email(tvr):
    """Neither /request nor /confirm may dump the raw email into the
    structured log. The audit signal uses ``mask_email``."""
    from shared.pii import mask_email

    seen_values: list[str] = []

    class _CaptureLogger:
        def info(self, event, **kw):
            seen_values.extend(str(v) for v in kw.values())

        def warning(self, *a, **kw):
            # Dev-mode emit -- also covered by mask_email.
            seen_values.extend(str(v) for v in kw.values())

        def error(self, *a, **kw):
            seen_values.extend(str(v) for v in kw.values())

    with patch.object(tvr, "logger", _CaptureLogger()):
        with patch.object(tvr, "_send_erasure_email"):
            await tvr.request_lead_erasure(
                request=_stub_request(),
                payload=tvr.LeadErasureRequest(email="lead@corp.com"),
            )
        stored_code = tvr._memory_store["lead_erasure:lead@corp.com"]["code"]

        class _FakeSession:
            def execute(self, *a, **k): return None
            def commit(self): pass
            def rollback(self): pass
            def close(self): pass

        with patch("app.database.SessionLocal", lambda: _FakeSession()):
            await tvr.confirm_lead_erasure(
                request=_stub_request(),
                payload=tvr.ConfirmLeadErasureRequest(
                    email="lead@corp.com", code=stored_code
                ),
            )

    # Raw email must never reach the log.
    assert "lead@corp.com" not in seen_values
    # The masked form must appear in at least one log event.
    masked = mask_email("lead@corp.com")
    assert any(masked in v for v in seen_values), (masked, seen_values)
