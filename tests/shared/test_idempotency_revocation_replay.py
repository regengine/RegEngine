"""Revoked API keys must not receive cached idempotent responses.

``services/shared/idempotency.py`` serves a cached 2xx body before route
dependencies run, so its pre-authentication API-key lookup is the
authorization re-check for API-key traffic. The lookup must treat a key
exactly like the canonical validation
(``DatabaseAPIKeyStore.validate_key``): disabled, expired, deleted, or
revoked (``revoked_at`` set) keys resolve no tenant, so the request falls
through to the route, whose own auth dependency answers 401 or 403.

Regression coverage for the Medium finding "cached idempotent responses
outlive permission revocation": a key revoked after its first use (the only
revocation signal a partial or out-of-band update may leave is
``revoked_at`` with ``enabled`` still true) must get 401/403 on retry, never
the day-long cached body.

All fakes are in-memory: an async dict stands in for Redis and a stubbed
DB session stands in for Postgres. No live services needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest
import shared.api_key_store as key_store
import shared.database as database
import shared.idempotency as idemp_mod
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from shared.idempotency import IdempotencyMiddleware

_LIVE_SCOPES = ["read", "write"]
_LIVE_JURISDICTIONS = ["US"]


class _FakeAsyncRedis:
    """Minimal async Redis stand-in (mirrors test_idempotency_middleware_1338)."""

    def __init__(self):
        self.store: Dict[bytes, bytes] = {}

    async def ping(self):
        return True

    async def get(self, key):
        if isinstance(key, str):
            key = key.encode()
        return self.store.get(key)

    async def set(self, key, value, *, nx, ex):
        key = key.encode() if isinstance(key, str) else key
        if nx and key in self.store:
            return False
        self.store[key] = value.encode() if isinstance(value, str) else value
        return True

    async def eval(self, script, numkeys, key, expected, *args):
        key = key.encode() if isinstance(key, str) else key
        if self.store.get(key) != expected.encode():
            return 0
        if args:
            await self.setex(key, int(args[0]), args[1])
        else:
            del self.store[key]
        return 1

    async def setex(self, key, ttl, value):
        if isinstance(key, str):
            key = key.encode()
        if isinstance(value, str):
            value = value.encode()
        self.store[key] = value


def _patch_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeAsyncRedis:
    fake = _FakeAsyncRedis()

    async def _fake_get_client(self):
        self._redis_available = True
        return fake

    monkeypatch.setattr(idemp_mod.IdempotencyMiddleware, "_get_client", _fake_get_client)
    return fake


class _KeyState:
    """Mutable stand-in for one api_keys row; revocation flips it mid-test."""

    def __init__(self):
        self.enabled: Any = True
        self.revoked_at: Optional[datetime] = None
        self.expires_at: Optional[datetime] = None
        self.scopes = list(_LIVE_SCOPES)
        self.jurisdictions = list(_LIVE_JURISDICTIONS)
        self.tenant_status: Optional[str] = "active"

    def row(self):
        return (
            "tenant-revocation",
            self.enabled,
            self.expires_at,
            "stable-key-id",
            self.scopes,
            self.jurisdictions,
            self.revoked_at,
        )


def _patch_key_row(monkeypatch: pytest.MonkeyPatch, state: _KeyState) -> MagicMock:
    """Route the middleware's pre-auth lookup at a stubbed DB row.

    The lookup issues a second query for the key tenant's status; the
    stub answers it from ``state.tenant_status`` so suspension can be
    flipped mid-test exactly like revocation.
    """
    db = MagicMock()

    def execute(statement, parameters):
        result = MagicMock()
        if "FROM tenants" in str(statement):
            result.fetchone.return_value = (
                (state.tenant_status,) if state.tenant_status is not None else None
            )
        else:
            result.fetchone.return_value = state.row()
        return result

    db.execute.side_effect = execute
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        key_store,
        "set_api_key_lookup_context",
        lambda session, raw: ("stable-key-id", ["hash"]) if raw.startswith("rge_") else None,
    )
    return db


def _build_app(revoked: Dict[str, bool]) -> FastAPI:
    """Route whose handler emulates route-level auth like require_api_key.

    Before revocation it serves 200 (cached by the middleware); after the
    key is revoked it answers 401, which is what the real auth dependency
    returns for a dead key.
    """
    app = FastAPI()

    @app.post("/echo")
    async def echo():
        if revoked["flag"]:
            return JSONResponse({"detail": "Invalid API key"}, status_code=401)
        return {"receipt": "original-authorized-body"}

    app.add_middleware(IdempotencyMiddleware)
    return app


def _api_key_headers() -> Dict[str, str]:
    return {"Idempotency-Key": "revocation-key", "X-RegEngine-API-Key": "rge_live.stable-secret"}


def test_revoked_key_retry_gets_401_not_cached_body(monkeypatch):
    """Core regression: revocation between first use and retry.

    First request (live key) returns 200 and populates the cache. After the
    key is revoked, retrying the identical request must reach the route and
    get 401, not the cached 200 body. On the old code the lookup never read
    ``revoked_at``, so the retry replayed the cached body with the handler
    invoked only once.
    """
    fake = _patch_redis(monkeypatch)
    state = _KeyState()
    _patch_key_row(monkeypatch, state)
    revoked = {"flag": False}
    client = TestClient(_build_app(revoked))

    first = client.post("/echo", headers=_api_key_headers(), content=b"same-bytes")
    assert first.status_code == 200
    assert first.json() == {"receipt": "original-authorized-body"}
    assert len(fake.store) == 1

    state.revoked_at = datetime.now(timezone.utc)
    revoked["flag"] = True

    retry = client.post("/echo", headers=_api_key_headers(), content=b"same-bytes")
    assert retry.status_code == 401
    assert "original-authorized-body" not in retry.text


def test_revoked_key_is_never_served_from_cache_even_when_handler_would_200(monkeypatch):
    """A revoked key must not resolve a tenant at all: with no tenant the
    middleware skips the cache entirely (no read, no write)."""
    fake = _patch_redis(monkeypatch)
    state = _KeyState()
    state.revoked_at = datetime.now(timezone.utc)
    _patch_key_row(monkeypatch, state)

    middleware = IdempotencyMiddleware(app=MagicMock())

    class _BareState:
        tenant_id = None

    request = MagicMock()
    request.state = _BareState()
    request.headers = {"X-RegEngine-API-Key": "rge_live.stable-secret"}
    assert middleware._resolve_tenant_id(request) is None
    assert fake.store == {}


def test_lookup_rejects_revoked_disabled_and_missing_keys(monkeypatch):
    """Unit lock on the lookup: every dead-key shape resolves nothing."""
    state = _KeyState()
    db = _patch_key_row(monkeypatch, state)

    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is not None

    state.revoked_at = datetime.now(timezone.utc)
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None

    state.revoked_at = None
    state.enabled = False
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None

    state.enabled = None
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None

    db.execute.side_effect = lambda statement, parameters: MagicMock(fetchone=lambda: None)
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None
    assert db.execute.call_count >= 1


def test_lookup_rejects_expired_keys_including_naive_datetimes(monkeypatch):
    """Expiry uses UTC for naive timestamps instead of raising; either way
    an expired key resolves nothing."""
    state = _KeyState()
    _patch_key_row(monkeypatch, state)

    state.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is not None

    state.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None

    state.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None


def test_lookup_rejects_unparseable_keys_without_touching_db(monkeypatch):
    """Malformed key material fails closed before any DB session opens."""
    db = _patch_key_row(monkeypatch, _KeyState())
    assert idemp_mod._lookup_api_key_context("not-a-key") is None
    assert idemp_mod._lookup_api_key_context("") is None
    assert db.execute.call_count == 0


def test_lookup_rejects_suspended_archived_and_missing_tenants(monkeypatch):
    """A valid key for a non-active tenant resolves nothing to replay."""
    state = _KeyState()
    _patch_key_row(monkeypatch, state)

    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is not None

    state.tenant_status = "suspended"
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None

    state.tenant_status = "archived"
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None

    state.tenant_status = None
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None

    state.tenant_status = "trial"
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is not None


def test_lookup_fails_closed_when_status_read_errors(monkeypatch):
    """A tenant-status lookup error resolves nothing, never a replay."""
    state = _KeyState()
    db = _patch_key_row(monkeypatch, state)

    real_side_effect = db.execute.side_effect

    def execute(statement, parameters):
        if "FROM tenants" in str(statement):
            raise RuntimeError("db down")
        return real_side_effect(statement, parameters)

    db.execute.side_effect = execute
    assert idemp_mod._lookup_api_key_context("rge_live.stable-secret") is None


def test_suspended_tenant_retry_gets_route_verdict_not_cached_body(monkeypatch):
    """Core regression: suspension between first use and retry.

    First request (active tenant) returns 200 and populates the cache.
    After the tenant is suspended, retrying the identical request must
    reach the route (which now answers 403 like the real auth
    dependency) instead of replaying the cached 200 body. On the old
    code the lookup never read tenant status, so the retry replayed the
    cached body with the handler invoked only once.
    """
    fake = _patch_redis(monkeypatch)
    state = _KeyState()
    _patch_key_row(monkeypatch, state)
    suspended = {"flag": False}

    app = FastAPI()

    @app.post("/echo")
    async def echo():
        if suspended["flag"]:
            return JSONResponse({"detail": "Invalid API key"}, status_code=403)
        return {"receipt": "original-authorized-body"}

    app.add_middleware(IdempotencyMiddleware)
    client = TestClient(app)

    first = client.post("/echo", headers=_api_key_headers(), content=b"same-bytes")
    assert first.status_code == 200
    assert first.json() == {"receipt": "original-authorized-body"}
    assert len(fake.store) == 1

    state.tenant_status = "suspended"
    suspended["flag"] = True

    retry = client.post("/echo", headers=_api_key_headers(), content=b"same-bytes")
    assert retry.status_code == 403
    assert "original-authorized-body" not in retry.text
