"""Regression tests for #1232 + #1237 — webhook idempotency wiring.

#1232: the IdempotencyMiddleware is mounted and Idempotency-Key is
       required on POST /api/v1/webhooks/ingest.
#1237: cache keys are tenant-scoped so two tenants cannot read each
       other's cached responses.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from shared.idempotency import IdempotencyMiddleware, IDEMPOTENCY_KEY_PREFIX


# ---------------------------------------------------------------------------
# Cache-key composition (#1237)
# ---------------------------------------------------------------------------


def test_cache_key_includes_tenant_id():
    """#1237: cache key must include tenant_id, never be just the header."""
    mw = IdempotencyMiddleware(app=MagicMock())
    key_a = mw._get_cache_key("daily-batch-2026-04-17", tenant_id="tenant-a")
    key_b = mw._get_cache_key("daily-batch-2026-04-17", tenant_id="tenant-b")

    assert key_a != key_b, "Same idempotency key across tenants must produce different cache keys"
    assert "tenant-a" in key_a
    assert "tenant-b" in key_b
    assert key_a.startswith(IDEMPOTENCY_KEY_PREFIX)


def test_cache_key_falls_back_to_anonymous_sentinel_without_tenant():
    """Unauthenticated calls still have distinct keys but never collide
    with any real tenant."""
    mw = IdempotencyMiddleware(app=MagicMock())
    anon_key = mw._get_cache_key("abc")
    tenant_key = mw._get_cache_key("abc", tenant_id="real-tenant")

    assert anon_key != tenant_key
    assert "_anonymous_" in anon_key


def test_resolve_tenant_prefers_principal_over_header():
    """Principal tenant (RBAC-authenticated) wins over X-Tenant-ID header."""
    mw = IdempotencyMiddleware(app=MagicMock())

    # Mock request with both a principal and a header.
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.principal = MagicMock(tenant_id="principal-tenant")
    request.headers = {"X-Tenant-ID": "header-tenant"}

    assert mw._resolve_tenant_id(request) == "principal-tenant"


def test_resolve_tenant_uses_header_when_no_principal():
    mw = IdempotencyMiddleware(app=MagicMock())
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.principal = None
    request.headers = {"X-Tenant-ID": "only-header"}

    assert mw._resolve_tenant_id(request) == "only-header"


def test_resolve_tenant_returns_none_when_nothing_set():
    mw = IdempotencyMiddleware(app=MagicMock())
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.principal = None
    request.headers = {}

    assert mw._resolve_tenant_id(request) is None


# ---------------------------------------------------------------------------
# Strict-required idempotency dependency (#1232)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_dependency_strict_blocks_missing_header():
    """POST requests without Idempotency-Key get a 400 in strict mode."""
    from shared.idempotency import IdempotencyDependency
    from fastapi import HTTPException

    dep = IdempotencyDependency(strict=True)
    request = MagicMock(spec=Request)
    request.method = "POST"
    request.headers = {}

    with pytest.raises(HTTPException) as exc:
        await dep(request)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_idempotency_dependency_strict_accepts_valid_header():
    """Valid Idempotency-Key returns the key value."""
    from shared.idempotency import IdempotencyDependency

    dep = IdempotencyDependency(strict=True)
    request = MagicMock(spec=Request)
    request.method = "POST"
    request.headers = {"Idempotency-Key": "abc-123"}

    result = await dep(request)
    assert result == "abc-123"


# ---------------------------------------------------------------------------
# Cross-tenant cache isolation via full middleware dispatch
# ---------------------------------------------------------------------------


class _FakeAsyncRedis:
    """Very small async-Redis stand-in for middleware testing."""

    def __init__(self):
        self.store: dict[bytes, bytes] = {}

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


@pytest.mark.asyncio
async def test_middleware_isolates_tenants_on_shared_key(monkeypatch):
    """Two requests with the same Idempotency-Key but different tenant
    headers must NOT collide — each gets its own cached response."""
    app = FastAPI()
    call_counts = {"a": 0, "b": 0}

    @app.post("/echo")
    async def echo(body: dict, request: Request):
        tenant = request.headers.get("X-Tenant-ID")
        call_counts[tenant[-1]] += 1  # last char (a/b)
        return {"tenant": tenant, "n": call_counts[tenant[-1]]}

    app.add_middleware(IdempotencyMiddleware)

    fake_redis = _FakeAsyncRedis()

    # Patch _get_client to return the fake redis for every IdempotencyMiddleware instance
    import shared.idempotency as idemp_mod

    async def _fake_get_client(self):
        self._redis_available = True
        return fake_redis

    monkeypatch.setattr(
        idemp_mod.IdempotencyMiddleware, "_get_client", _fake_get_client
    )

    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_a = await client.post(
            "/echo",
            headers={"Idempotency-Key": "same-key", "X-Tenant-ID": "tenant-a"},
            json={"x": 1},
        )
        assert resp_a.status_code == 200
        body_a = resp_a.json()
        assert body_a["tenant"] == "tenant-a"

        # Same Idempotency-Key, different tenant — should NOT return tenant-a's body.
        resp_b = await client.post(
            "/echo",
            headers={"Idempotency-Key": "same-key", "X-Tenant-ID": "tenant-b"},
            json={"x": 1},
        )
        assert resp_b.status_code == 200
        body_b = resp_b.json()
        assert body_b["tenant"] == "tenant-b", (
            "Tenant B received tenant A's cached response — cross-tenant bleed"
        )

        # Tenant A retry: should hit its own cached response (not tenant B's).
        resp_a_retry = await client.post(
            "/echo",
            headers={"Idempotency-Key": "same-key", "X-Tenant-ID": "tenant-a"},
            json={"x": 1},
        )
        assert resp_a_retry.status_code == 200
        assert resp_a_retry.json()["tenant"] == "tenant-a"

    # The underlying handler must have been called exactly once per tenant.
    assert call_counts == {"a": 1, "b": 1}
