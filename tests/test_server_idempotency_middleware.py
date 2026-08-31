"""Idempotency-Key dedup against the production monolith entrypoint.

``server/main.py`` mounts ``webhook_router_v2`` from the ingestion
service, but until this change only the legacy
``services/ingestion/main.py`` entrypoint installed
``shared.idempotency.IdempotencyMiddleware`` (#1232) — production
webhook POSTs got no Idempotency-Key dedup. The same gap applied to
``RateLimitHeadersMiddleware`` (#2307) and ``CorrelationIdMiddleware``
(#1316).

These tests lock all three into the ``server.main`` stack and exercise
the dedup behavior end-to-end through the real middleware stack.
"""

from __future__ import annotations

import importlib
from typing import Dict

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient

_ECHO_PATH = "/__test__/idempotency-echo"
_PRINCIPAL_ECHO_PATH = "/__test__/idempotency-principal-echo"


@pytest.fixture(scope="module")
def server_main():
    return importlib.import_module("server.main")


class _FakeAsyncRedis:
    """Minimal async Redis stand-in (mirrors tests/shared/test_idempotency_middleware_1338.py)."""

    def __init__(self):
        self.store: Dict[bytes, bytes] = {}

    async def ping(self):
        return True

    async def get(self, key):
        if isinstance(key, str):
            key = key.encode()
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        if isinstance(key, str):
            key = key.encode()
        if isinstance(value, str):
            value = value.encode()
        self.store[key] = value


@pytest.fixture
def fake_redis(monkeypatch):
    import shared.idempotency as idemp_mod

    fake = _FakeAsyncRedis()

    async def _fake_get_client(self):
        self._redis_available = True
        return fake

    monkeypatch.setattr(idemp_mod.IdempotencyMiddleware, "_get_client", _fake_get_client)
    return fake


@pytest.fixture
def echo_route(server_main):
    """Mount a throwaway POST route on the real server.main app.

    Routing is resolved per-request, so adding a route after the
    middleware stack is built still sends it through the full stack —
    which is exactly what we want to exercise. Removed on teardown so
    other suites never see it.
    """
    app = server_main.app
    calls = {"n": 0}

    @app.post(_ECHO_PATH)
    async def _idempotency_echo():
        calls["n"] += 1
        return {"calls": calls["n"]}

    yield calls
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != _ECHO_PATH]


class _Principal:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id


@pytest.fixture
def principal_echo_route(server_main):
    """Route whose principal is only set by a FastAPI dependency.

    This mirrors production protected routes: IdempotencyMiddleware runs before
    dependencies, so principal-only tenant context is unavailable at cache
    lookup time unless the middleware performs its own scoped-key lookup.
    """
    app = server_main.app
    calls: Dict[str, int] = {}

    async def _principal_dep(request: Request) -> _Principal:
        tenant = request.headers.get("X-Principal-Tenant", "")
        principal = _Principal(tenant)
        request.state.principal = principal
        return principal

    @app.post(_PRINCIPAL_ECHO_PATH)
    async def _idempotency_principal_echo(principal: _Principal = Depends(_principal_dep)):
        calls[principal.tenant_id] = calls.get(principal.tenant_id, 0) + 1
        return {"tenant": principal.tenant_id, "calls": calls[principal.tenant_id]}

    yield calls
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != _PRINCIPAL_ECHO_PATH]


# ---------------------------------------------------------------------------
# Stack composition — the three ported middlewares are present and ordered
# ---------------------------------------------------------------------------


def test_server_stack_contains_ported_middlewares(server_main):
    names = [m.cls.__name__ for m in server_main.app.user_middleware]
    assert "AuditContextMiddleware" in names
    assert "IdempotencyMiddleware" in names
    assert "RateLimitHeadersMiddleware" in names
    assert "CorrelationIdMiddleware" in names


def test_request_id_runs_before_audit_context(server_main):
    """Audit context must reuse the canonical per-hop request ID."""
    names = [m.cls.__name__ for m in server_main.app.user_middleware]
    assert names.index("RequestIDMiddleware") < names.index("AuditContextMiddleware")


def test_server_stack_relative_ordering_matches_ingestion(server_main):
    """``app.user_middleware`` is in execution (outermost-first) order.

    Mirrors services/ingestion/main.py: CorrelationId outermost (runs
    first), Idempotency outside the request-safety pair, and
    RateLimitHeaders between request-safety and TenantRateLimit.
    """
    names = [m.cls.__name__ for m in server_main.app.user_middleware]
    assert (
        names.index("CorrelationIdMiddleware")
        < names.index("IdempotencyMiddleware")
        < names.index("RequestTimeoutMiddleware")
    )
    assert (
        names.index("RequestSizeLimitMiddleware")
        < names.index("RateLimitHeadersMiddleware")
        < names.index("TenantRateLimitMiddleware")
    )


# ---------------------------------------------------------------------------
# Idempotency-Key dedup end-to-end through the server.main stack
# ---------------------------------------------------------------------------


def test_idempotency_key_dedup_through_server_app(server_main, fake_redis, echo_route):
    """Two POSTs with the same Idempotency-Key + tenant hit the handler once."""
    client = TestClient(server_main.app)
    headers = {"Idempotency-Key": "server-dedup-1", "X-Tenant-ID": "tenant-test"}

    r1 = client.post(_ECHO_PATH, headers=headers)
    r2 = client.post(_ECHO_PATH, headers=headers)

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json() == r2.json() == {"calls": 1}
    assert echo_route["n"] == 1

    # Cache key is tenant-scoped (#1237).
    stored = [k.decode() for k in fake_redis.store]
    assert "idempotency:tenant-test:server-dedup-1" in stored


def test_distinct_idempotency_keys_are_not_deduped(server_main, fake_redis, echo_route):
    client = TestClient(server_main.app)

    r1 = client.post(_ECHO_PATH, headers={"Idempotency-Key": "key-a", "X-Tenant-ID": "t"})
    r2 = client.post(_ECHO_PATH, headers={"Idempotency-Key": "key-b", "X-Tenant-ID": "t"})

    assert r1.status_code == r2.status_code == 200
    assert echo_route["n"] == 2


def test_post_without_idempotency_key_is_not_cached(server_main, fake_redis, echo_route):
    client = TestClient(server_main.app)

    client.post(_ECHO_PATH, headers={"X-Tenant-ID": "t"})
    client.post(_ECHO_PATH, headers={"X-Tenant-ID": "t"})

    assert echo_route["n"] == 2
    assert fake_redis.store == {}


def test_principal_only_tenant_context_does_not_use_anonymous_cache(
    server_main, fake_redis, principal_echo_route
):
    client = TestClient(server_main.app)

    r1 = client.post(
        _PRINCIPAL_ECHO_PATH,
        headers={"Idempotency-Key": "same-key", "X-Principal-Tenant": "tenant-a"},
    )
    r2 = client.post(
        _PRINCIPAL_ECHO_PATH,
        headers={"Idempotency-Key": "same-key", "X-Principal-Tenant": "tenant-b"},
    )

    assert r1.status_code == r2.status_code == 200
    assert r1.json() == {"tenant": "tenant-a", "calls": 1}
    assert r2.json() == {"tenant": "tenant-b", "calls": 1}
    assert principal_echo_route == {"tenant-a": 1, "tenant-b": 1}
    assert fake_redis.store == {}


def test_api_key_lookup_scopes_server_idempotency_without_tenant_header(
    server_main, fake_redis, principal_echo_route, monkeypatch
):
    import shared.idempotency as idemp_mod

    tenant_by_key = {
        "api-key-a": "tenant-a",
        "api-key-b": "tenant-b",
    }
    monkeypatch.setattr(idemp_mod, "_lookup_tenant_id_for_api_key", lambda raw: tenant_by_key.get(raw))
    client = TestClient(server_main.app)

    r1 = client.post(
        _PRINCIPAL_ECHO_PATH,
        headers={
            "Idempotency-Key": "same-key",
            "X-RegEngine-API-Key": "api-key-a",
            "X-Principal-Tenant": "tenant-a",
        },
    )
    r2 = client.post(
        _PRINCIPAL_ECHO_PATH,
        headers={
            "Idempotency-Key": "same-key",
            "X-RegEngine-API-Key": "api-key-b",
            "X-Principal-Tenant": "tenant-b",
        },
    )
    r1_retry = client.post(
        _PRINCIPAL_ECHO_PATH,
        headers={
            "Idempotency-Key": "same-key",
            "X-RegEngine-API-Key": "api-key-a",
            "X-Principal-Tenant": "tenant-a",
        },
    )

    assert r1.status_code == r2.status_code == r1_retry.status_code == 200
    assert r1.json() == r1_retry.json() == {"tenant": "tenant-a", "calls": 1}
    assert r2.json() == {"tenant": "tenant-b", "calls": 1}
    assert principal_echo_route == {"tenant-a": 1, "tenant-b": 1}

    stored = [k.decode() for k in fake_redis.store]
    assert "idempotency:tenant-a:same-key" in stored
    assert "idempotency:tenant-b:same-key" in stored
    assert not any("_anonymous_" in key for key in stored)


# ---------------------------------------------------------------------------
# CorrelationIdMiddleware smoke — header echoed on responses
# ---------------------------------------------------------------------------


def test_correlation_id_echoed_on_server_responses(server_main):
    client = TestClient(server_main.app)
    resp = client.get("/health", headers={"X-Correlation-ID": "trace-abc-123"})
    assert resp.headers.get("X-Correlation-ID") == "trace-abc-123"
    # And distinct from the per-hop request ID managed by RequestIDMiddleware.
    assert "X-Request-ID" in resp.headers
