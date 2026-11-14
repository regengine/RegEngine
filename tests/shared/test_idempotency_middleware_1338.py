"""Dedicated test suite for ``services/shared/idempotency.py`` — #1338.

Context
-------
``services/shared/idempotency.py`` provides the POST-dedup middleware
that every service layer relies on. It had no dedicated test suite
prior to this file — the only coverage lived inside
``services/ingestion/tests/test_webhook_idempotency.py`` which
exercised two very specific scenarios (tenant-scoped cache key +
strict dependency) but left the surrounding contract untested.

This suite locks in the full middleware + dependency contract so
future changes to graceful-degrade behavior, 2xx-only caching,
tenant-scoped cache keys, or the 255-char ceiling fail loudly.
Targets the #1338 acceptance goal (``pytest tests/shared
--cov=services/shared --cov-fail-under=70``) for this module — the
assertions below drive idempotency.py coverage to ~100 percent.

All tests are pure-Python: we stand in for Redis with an async in-
memory dict and monkeypatch ``_get_client``. No live Redis needed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Callable, Dict, Optional, Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from shared.idempotency import (
    IDEMPOTENCY_KEY_PREFIX,
    IDEMPOTENCY_TTL_SECONDS,
    IdempotencyDependency,
    IdempotencyMiddleware,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _FakeAsyncRedis:
    """Minimal async Redis stand-in for middleware testing.

    Stores bytes-keyed bytes values and tracks setex TTL arguments so
    tests can assert the 24-hour expiry is applied.
    """

    def __init__(self, should_fail: bool = False):
        self.store: Dict[bytes, bytes] = {}
        self.setex_calls: list[tuple[bytes, int, bytes]] = []
        self.get_calls: list[bytes] = []
        self.should_fail = should_fail

    async def ping(self):
        if self.should_fail:
            raise ConnectionError("fake redis down")
        return True

    async def get(self, key):
        if isinstance(key, str):
            key = key.encode()
        self.get_calls.append(key)
        if self.should_fail:
            raise ConnectionError("fake redis down")
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
            return await self.setex(key, int(args[0]), args[1])
        del self.store[key]
        return 1

    async def setex(self, key, ttl, value):
        if isinstance(key, str):
            key = key.encode()
        if isinstance(value, str):
            value = value.encode()
        self.setex_calls.append((key, ttl, value))
        if self.should_fail:
            raise ConnectionError("fake redis down")
        self.store[key] = value


# ---------------------------------------------------------------------------
# Trusted tenant headers (#2841)
# ---------------------------------------------------------------------------
#
# The raw ``X-Tenant-ID`` header is no longer a tenant source: it is client
# input, and this middleware serves cache hits before any authentication runs.
# Tests that merely need *a* tenant now present the secret-gated internal
# service header that ``shared/middleware/tenant_context.py`` already treats as
# the only trustworthy pre-auth tenant claim.
_INTERNAL_SECRET = "test-internal-secret-2841"


@pytest.fixture(autouse=True)
def _internal_secret_configured(monkeypatch):
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", _INTERNAL_SECRET)


def _tenant_headers(tenant: str) -> Dict[str, str]:
    """Headers that authenticate an internal caller as ``tenant``."""
    return {
        "X-RegEngine-Tenant-ID": tenant,
        "X-RegEngine-Internal-Secret": _INTERNAL_SECRET,
    }


def _patched_middleware(
    monkeypatch: pytest.MonkeyPatch,
    fake: Optional[_FakeAsyncRedis] = None,
) -> _FakeAsyncRedis:
    """Patch ``_get_client`` so every middleware instance uses ``fake``.

    If ``fake`` is ``None``, simulates Redis unavailable by returning
    ``None`` (the documented graceful-degrade path).
    """
    import shared.idempotency as idemp_mod

    async def _fake_get_client(self):
        if fake is None:
            self._redis_available = False
            return None
        self._redis_available = True
        return fake

    monkeypatch.setattr(idemp_mod.IdempotencyMiddleware, "_get_client", _fake_get_client)
    return fake  # type: ignore[return-value]


def _build_app(
    handler=None,
    *,
    pre_middleware=None,
) -> FastAPI:
    """Construct a FastAPI app mounting IdempotencyMiddleware.

    ``pre_middleware`` runs before idempotency in the inbound direction
    so tests can plant ``request.state.principal`` before the
    middleware resolves the tenant.
    """
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        if handler is not None:
            return await handler(request)
        body = await request.body()
        return {"body": body.decode() if body else ""}

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    app.add_middleware(IdempotencyMiddleware)
    if pre_middleware is not None:
        app.add_middleware(pre_middleware)

    return app


# ---------------------------------------------------------------------------
# Module-level constants (regression anchors)
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Lock critical constants so silent edits are flagged."""

    def test_key_prefix_is_idempotency_colon(self):
        """The cache-key prefix is part of the #1237 contract — do not
        move or rename without coordinating rollout."""
        assert IDEMPOTENCY_KEY_PREFIX == "idempotency:"

    def test_ttl_is_24_hours(self):
        """24h TTL is documented behaviour. Halving this breaks safe
        client retry windows, doubling it grows cache memory."""
        assert IDEMPOTENCY_TTL_SECONDS == 86400
        assert IDEMPOTENCY_TTL_SECONDS == 24 * 60 * 60


# ---------------------------------------------------------------------------
# _should_cache — POST-only gate
# ---------------------------------------------------------------------------


class TestShouldCache:
    """Idempotency only applies to POST; other verbs bypass."""

    @pytest.fixture
    def middleware(self):
        return IdempotencyMiddleware(app=MagicMock())

    @pytest.mark.parametrize("method", ["POST", "post", "Post", "PoSt"])
    def test_post_is_cached_regardless_of_case(self, middleware, method):
        """HTTP methods are case-insensitive per RFC 9110, and the
        middleware should normalize before comparing."""
        assert middleware._should_cache(method) is True

    @pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    def test_non_post_methods_not_cached(self, middleware, method):
        """PUT and DELETE are idempotent by RFC but that's a different
        kind of idempotency — we only cache replay-safe POSTs."""
        assert middleware._should_cache(method) is False


# ---------------------------------------------------------------------------
# _get_cache_key — tenant-scoped cache keys (#1237)
# ---------------------------------------------------------------------------


class TestCacheKeyComposition:
    """Lock the cache-key format so #1237's isolation can't regress."""

    @pytest.fixture
    def middleware(self):
        return IdempotencyMiddleware(app=MagicMock())

    def test_key_contains_prefix_tenant_and_idempotency_key(self, middleware):
        key = middleware._get_cache_key("abc-123", tenant_id="tenant-x")
        assert key == "idempotency:tenant-x:abc-123"

    def test_different_tenants_produce_different_cache_keys(self, middleware):
        """Same idempotency key under two tenants MUST produce two
        distinct cache keys (#1237 — cross-tenant bleed fix)."""
        a = middleware._get_cache_key("batch-key", tenant_id="tenant-a")
        b = middleware._get_cache_key("batch-key", tenant_id="tenant-b")
        assert a != b

    def test_anonymous_sentinel_when_tenant_is_none(self, middleware):
        """Without a tenant, a namespace sentinel is used so anonymous
        callers can never inhabit the same namespace as an authenticated
        tenant."""
        anon = middleware._get_cache_key("x")
        tenant = middleware._get_cache_key("x", tenant_id="real")
        assert anon != tenant
        assert "_anonymous_" in anon

    def test_anonymous_sentinel_when_tenant_is_empty_string(self, middleware):
        """Empty-string tenant is treated as anonymous (falsy)."""
        key = middleware._get_cache_key("x", tenant_id="")
        assert "_anonymous_" in key

    def test_key_stable_for_same_inputs(self, middleware):
        """Deterministic hashing contract — cache hits only work if the
        same inputs map to the same key every time."""
        k1 = middleware._get_cache_key("abc", tenant_id="t1")
        k2 = middleware._get_cache_key("abc", tenant_id="t1")
        assert k1 == k2


# ---------------------------------------------------------------------------
# _resolve_tenant_id — principal > header > None (#1237 spoof guard)
# ---------------------------------------------------------------------------


class TestResolveTenantId:
    """Tenant must come from the authenticated principal (or header as
    a fallback), NEVER from the request body — else a caller could
    inject ``tenant_id`` in JSON and spoof the cache namespace.
    """

    @pytest.fixture
    def middleware(self):
        return IdempotencyMiddleware(app=MagicMock())

    def _request(
        self,
        *,
        principal_tenant: Optional[str] = None,
        header_tenant: Optional[str] = None,
        internal_tenant: Optional[str] = None,
    ) -> Request:
        """``header_tenant`` is the UNTRUSTED ``X-Tenant-ID``; ``internal_tenant``
        is the secret-gated ``X-RegEngine-Tenant-ID``."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.tenant_id = None
        if principal_tenant is None:
            # Principal attribute exists but holds None.
            request.state.principal = None
        else:
            request.state.principal = MagicMock(tenant_id=principal_tenant)
        headers = {}
        if header_tenant is not None:
            headers["X-Tenant-ID"] = header_tenant
        if internal_tenant is not None:
            headers.update(_tenant_headers(internal_tenant))
        request.headers = headers
        return request  # type: ignore[return-value]

    def test_principal_tenant_wins_over_header(self, middleware):
        """RBAC-resolved tenant always beats client-supplied header."""
        req = self._request(
            principal_tenant="principal-wins",
            header_tenant="attacker-choice",
        )
        assert middleware._resolve_tenant_id(req) == "principal-wins"

    def test_raw_tenant_header_is_never_a_tenant_source(self, middleware):
        """#2841: ``X-Tenant-ID`` is client input and must not name a namespace.

        This case previously asserted the opposite (``== "from-header"``) —
        it encoded the vulnerability. Resolution must now fail closed so
        ``dispatch`` skips the cache entirely.
        """
        req = self._request(header_tenant="from-header")
        assert middleware._resolve_tenant_id(req) is None

    def test_internal_tenant_header_used_when_no_principal(self, middleware):
        """The secret-gated internal header keeps service-to-service dedup."""
        req = self._request(internal_tenant="from-internal-header")
        assert middleware._resolve_tenant_id(req) == "from-internal-header"

    def test_internal_tenant_header_ignored_without_the_secret(self, middleware):
        req = self._request()
        req.headers = {"X-RegEngine-Tenant-ID": "unproven"}
        assert middleware._resolve_tenant_id(req) is None

    def test_internal_tenant_header_ignored_with_a_wrong_secret(self, middleware):
        req = self._request()
        req.headers = {
            "X-RegEngine-Tenant-ID": "unproven",
            "X-RegEngine-Internal-Secret": "not-the-secret",
        }
        assert middleware._resolve_tenant_id(req) is None

    def test_raw_header_cannot_override_the_api_key_tenant(self, middleware, monkeypatch):
        """#2841's cleanest exploit: authenticated as A, forging B.

        The header branch used to sit *above* the API-key lookup, so a
        legitimate caller could redirect their namespace into another
        tenant's. The authenticated key must now win.
        """
        import shared.idempotency as idemp_mod

        monkeypatch.setattr(idemp_mod, "_lookup_api_key_context", lambda raw: ("tenant-attacker", "auth-snapshot"))
        req = self._request(header_tenant="tenant-victim")
        req.headers = {"X-Tenant-ID": "tenant-victim", "X-RegEngine-API-Key": "rge_attacker.secret"}
        assert middleware._resolve_tenant_id(req) == "tenant-attacker"

    def test_api_key_lookup_used_when_no_principal_or_header(self, middleware, monkeypatch):
        import shared.idempotency as idemp_mod

        monkeypatch.setattr(idemp_mod, "_lookup_api_key_context", lambda raw: ("tenant-from-key", "auth-snapshot"))
        req = self._request()
        req.headers = {"X-RegEngine-API-Key": "rge_test.secret"}
        assert middleware._resolve_tenant_id(req) == "tenant-from-key"

    def test_header_stripped_of_whitespace(self, middleware):
        """Header value should be trimmed — otherwise ``" tenant"`` and
        ``"tenant"`` would land in different cache namespaces."""
        req = self._request(internal_tenant="  spaced-tenant  ")
        assert middleware._resolve_tenant_id(req) == "spaced-tenant"

    def test_none_when_neither_principal_nor_header(self, middleware):
        req = self._request()
        assert middleware._resolve_tenant_id(req) is None

    def test_empty_principal_tenant_falls_through_to_next_trusted_source(self, middleware):
        """An authenticated principal with an empty tenant_id is a
        defensive impossibility — but if it happens, fall through to the
        next TRUSTED source rather than stamp ``_anonymous_`` on a real
        session."""
        req = self._request(principal_tenant="", internal_tenant="fallback")
        assert middleware._resolve_tenant_id(req) == "fallback"

    def test_empty_principal_tenant_does_not_fall_through_to_raw_header(self, middleware):
        req = self._request(principal_tenant="", header_tenant="fallback")
        assert middleware._resolve_tenant_id(req) is None

    def test_missing_principal_attribute_is_safe(self, middleware):
        """``request.state.principal`` may be entirely absent (no auth
        middleware mounted). Must not raise."""
        request = MagicMock(spec=Request)

        class _Empty:
            pass

        request.state = _Empty()  # no ``.principal`` attribute at all
        request.headers = _tenant_headers("solo-header")
        assert middleware._resolve_tenant_id(request) == "solo-header"

    def test_principal_without_tenant_id_attr_falls_through(self, middleware):
        """If principal is set but has no ``tenant_id`` attribute the
        code should still reach the header fallback."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()

        class _PrincipalNoTenant:
            pass

        request.state.principal = _PrincipalNoTenant()
        request.state.tenant_id = None
        request.headers = _tenant_headers("fallback")
        assert middleware._resolve_tenant_id(request) == "fallback"


# ---------------------------------------------------------------------------
# IdempotencyDependency — strict / non-strict validation
# ---------------------------------------------------------------------------


class TestIdempotencyDependency:
    """Per-route validation of the Idempotency-Key header."""

    def _request(self, method: str, headers: Optional[Dict[str, str]] = None) -> Request:
        request = MagicMock(spec=Request)
        request.method = method
        request.headers = headers or {}
        return request  # type: ignore[return-value]

    @pytest.mark.asyncio
    async def test_strict_raises_400_on_missing_key_post(self):
        dep = IdempotencyDependency(strict=True)
        with pytest.raises(HTTPException) as exc_info:
            await dep(self._request("POST"))
        assert exc_info.value.status_code == 400
        assert "Idempotency-Key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_strict_returns_key_when_present(self):
        dep = IdempotencyDependency(strict=True)
        result = await dep(self._request("POST", {"Idempotency-Key": "abc-123"}))
        assert result == "abc-123"

    @pytest.mark.asyncio
    async def test_non_strict_returns_none_on_missing_post_key(self):
        """Default behavior: missing key lets the request through, just
        without caching. The middleware is the caching layer; the
        dependency is just for explicit per-route validation."""
        dep = IdempotencyDependency(strict=False)
        assert await dep(self._request("POST")) is None

    @pytest.mark.asyncio
    async def test_non_strict_returns_key_when_present(self):
        dep = IdempotencyDependency(strict=False)
        result = await dep(self._request("POST", {"Idempotency-Key": "abc"}))
        assert result == "abc"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    async def test_non_post_returns_none_even_in_strict_mode(self, method):
        """Strict mode only enforces on POST; other methods bypass the
        check entirely."""
        dep = IdempotencyDependency(strict=True)
        result = await dep(self._request(method))
        assert result is None

    @pytest.mark.asyncio
    async def test_key_over_255_chars_rejected_even_when_non_strict(self):
        """The 255-char ceiling applies regardless of strict mode —
        it's a structural limit, not a policy preference (protects the
        Redis keyspace)."""
        dep = IdempotencyDependency(strict=False)
        long_key = "a" * 256
        with pytest.raises(HTTPException) as exc_info:
            await dep(self._request("POST", {"Idempotency-Key": long_key}))
        assert exc_info.value.status_code == 400
        assert "255" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_key_exactly_255_chars_accepted(self):
        """Boundary test: 255 chars is the documented ceiling, so it
        must be accepted."""
        dep = IdempotencyDependency(strict=True)
        key = "a" * 255
        result = await dep(self._request("POST", {"Idempotency-Key": key}))
        assert result == key

    @pytest.mark.asyncio
    async def test_strict_mode_matches_post_case_insensitively(self):
        """Starlette lowercases methods sometimes; the dep normalizes
        with ``.upper()``."""
        dep = IdempotencyDependency(strict=True)
        # Lowercase method should still be treated as POST.
        with pytest.raises(HTTPException):
            await dep(self._request("post"))


# ---------------------------------------------------------------------------
# Middleware dispatch — end-to-end via FastAPI TestClient / ASGI
# ---------------------------------------------------------------------------


class TestDispatchPostOnly:
    """Only POST requests flow into the cache logic."""

    def test_get_request_bypasses_middleware(self, monkeypatch):
        """GET requests never read from or write to the cache — the
        Idempotency-Key header is ignored."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        app = _build_app()
        client = TestClient(app)
        resp = client.get("/ping", headers={"Idempotency-Key": "should-be-ignored"})
        assert resp.status_code == 200
        assert fake.get_calls == []
        assert fake.setex_calls == []

    def test_post_without_idempotency_header_skips_cache(self, monkeypatch):
        """POST without Idempotency-Key is still a valid request — it
        just doesn't participate in dedup. No cache hit, no cache write."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        app = _build_app()
        client = TestClient(app)
        resp = client.post("/echo", content=b"payload")
        assert resp.status_code == 200
        assert fake.get_calls == []
        assert fake.setex_calls == []

    def test_post_with_overlong_idempotency_key_passes_through(self, monkeypatch):
        """Over-255-char keys cause the middleware to silently bypass —
        the strict dependency enforces, the middleware tolerates."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        app = _build_app()
        client = TestClient(app)
        resp = client.post(
            "/echo",
            headers={"Idempotency-Key": "a" * 300},
            content=b"payload",
        )
        assert resp.status_code == 200
        assert fake.get_calls == []
        assert fake.setex_calls == []


class TestDispatchGracefulDegrade:
    """When Redis is unavailable, the middleware must not break
    requests — it just stops caching silently."""

    def test_redis_unavailable_request_still_succeeds(self, monkeypatch):
        _patched_middleware(monkeypatch, None)  # no redis

        app = _build_app()
        client = TestClient(app)
        resp = client.post(
            "/echo",
            headers={"Idempotency-Key": "k1"},
            content=b"payload",
        )
        assert resp.status_code == 200


class TestDispatchCacheHit:
    """Cache hits short-circuit handler execution."""

    def test_second_request_returns_cached_body(self, monkeypatch):
        """After a first POST completes, a second POST with the same
        Idempotency-Key and tenant returns the exact same body without
        the handler being invoked again."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        call_count = {"n": 0}

        async def handler(request):
            call_count["n"] += 1
            return {"n": call_count["n"]}

        app = _build_app(handler=handler)
        client = TestClient(app)

        headers = {"Idempotency-Key": "k1", **_tenant_headers("t1")}
        r1 = client.post("/echo", headers=headers, json={"payload": 1})
        r2 = client.post("/echo", headers=headers, json={"payload": 1})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json() == {"n": 1}
        # Handler invoked exactly ONCE.
        assert call_count["n"] == 1

    def test_cache_key_in_redis_matches_tenant_scoped_format(self, monkeypatch):
        """Spot-check the Redis keyspace so #1237's scoping is directly
        observable in storage, not just via isolation behavior."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        app = _build_app()
        client = TestClient(app)
        client.post(
            "/echo",
            headers={"Idempotency-Key": "stored-key", **_tenant_headers("tenant-x")},
            content=b"payload",
        )

        stored_keys = [k.decode() for k in fake.store]
        assert "idempotency:tenant-x:stored-key" in stored_keys

    def test_setex_uses_24_hour_ttl(self, monkeypatch):
        """Cache writes use IDEMPOTENCY_TTL_SECONDS — regression lock
        so nobody shortens retry windows silently."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        app = _build_app()
        client = TestClient(app)
        client.post(
            "/echo",
            headers={"Idempotency-Key": "ttl-key", **_tenant_headers("t")},
            content=b"payload",
        )

        assert len(fake.setex_calls) == 1
        _key, ttl, _value = fake.setex_calls[0]
        assert ttl == IDEMPOTENCY_TTL_SECONDS

    def test_cached_payload_preserves_status_and_body(self, monkeypatch):
        """The cached payload round-trips status, body, and headers so
        the replay looks identical to the original response."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        app = _build_app()
        client = TestClient(app)
        client.post(
            "/echo",
            headers={"Idempotency-Key": "inspect", **_tenant_headers("t")},
            content=b"hello",
        )

        # Inspect the stored payload shape.
        assert len(fake.setex_calls) == 1
        _k, _ttl, raw = fake.setex_calls[0]
        payload = json.loads(raw.decode())
        assert payload["status"] == 200
        assert "hello" in payload["body"]
        assert "headers" in payload
        assert isinstance(payload["headers"], dict)


class TestDispatch2xxOnlyCaching:
    """Error responses are NOT cached — clients must be free to retry
    naturally after a failure."""

    @pytest.mark.parametrize("status", [200, 201, 202, 299])
    def test_2xx_status_codes_are_cached(self, monkeypatch, status):
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        from fastapi.responses import JSONResponse

        async def handler(request):
            return JSONResponse({"ok": True}, status_code=status)

        app = _build_app(handler=handler)
        client = TestClient(app)
        resp = client.post(
            "/echo",
            headers={"Idempotency-Key": f"ok-{status}", **_tenant_headers("t")},
            content=b"x",
        )
        assert resp.status_code == status
        assert len(fake.setex_calls) == 1, f"Expected 2xx ({status}) to be cached"

    @pytest.mark.parametrize("status", [300, 400, 401, 403, 404, 409, 500, 503])
    def test_non_2xx_status_codes_are_not_cached(self, monkeypatch, status):
        """3xx, 4xx, 5xx all skip caching — caller retries will hit the
        handler again, not a stale error."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        from fastapi.responses import JSONResponse

        async def handler(request):
            return JSONResponse({"err": True}, status_code=status)

        app = _build_app(handler=handler)
        client = TestClient(app)
        resp = client.post(
            "/echo",
            headers={"Idempotency-Key": f"err-{status}", **_tenant_headers("t")},
            content=b"x",
        )
        assert resp.status_code == status
        assert fake.setex_calls == [], f"Expected {status} response to NOT be cached"


class TestDispatchCrossTenantIsolation:
    """Lock the #1237 contract at the dispatch layer: two tenants with
    the same Idempotency-Key never see each other's cached responses."""

    @pytest.mark.asyncio
    async def test_two_tenants_same_key_do_not_collide(self, monkeypatch):
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        invocations: Dict[str, int] = {"tenant-a": 0, "tenant-b": 0}

        async def handler(request):
            tenant = request.headers.get("X-RegEngine-Tenant-ID")
            invocations[tenant] += 1
            return {"tenant": tenant, "n": invocations[tenant]}

        app = _build_app(handler=handler)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_a = await client.post(
                "/echo",
                headers={"Idempotency-Key": "same", **_tenant_headers("tenant-a")},
                json={"x": 1},
            )
            r_b = await client.post(
                "/echo",
                headers={"Idempotency-Key": "same", **_tenant_headers("tenant-b")},
                json={"x": 1},
            )

        assert r_a.json() == {"tenant": "tenant-a", "n": 1}
        assert r_b.json() == {"tenant": "tenant-b", "n": 1}
        assert invocations == {"tenant-a": 1, "tenant-b": 1}

    @pytest.mark.asyncio
    async def test_body_tenant_cannot_spoof_cache_namespace(self, monkeypatch):
        """Attack scenario (#1237): attacker supplies a JSON body with
        ``tenant_id`` aiming to pin the cache key into a namespace they
        don't own. The middleware must ignore body content and key on
        the authenticated principal / secret-gated internal header only.
        """
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        async def handler(request):
            # Handler parses the body and returns the tenant_id field
            # so we can confirm the body WAS readable — just not used
            # for cache keying.
            body = await request.json()
            return {"tenant_from_body": body.get("tenant_id")}

        app = _build_app(handler=handler)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Attacker is authenticated as "attacker-tenant" but tries
            # to spoof "victim-tenant" in the JSON body.
            await client.post(
                "/echo",
                headers={
                    "Idempotency-Key": "spoof-key",
                    **_tenant_headers("attacker-tenant"),
                },
                json={"tenant_id": "victim-tenant"},
            )

        # The stored Redis key must be namespaced under the AUTHENTICATED
        # tenant, NOT the body tenant. (#2841 closed the sibling vector: the
        # raw X-Tenant-ID header is no longer a namespace source either.)
        stored = [k.decode() for k in fake.store]
        assert any("attacker-tenant" in k for k in stored), stored
        assert not any("victim-tenant" in k for k in stored), (
            "Body tenant_id leaked into cache key — spoof-bypass regression"
        )

    @pytest.mark.asyncio
    async def test_anonymous_request_is_not_cached(self, monkeypatch):
        """Requests with neither principal nor tenant header are not cached.

        The old anonymous namespace was safe for public traffic, but unsafe
        once this middleware moved outside route-level auth in the production
        monolith: principal-only API-key requests briefly looked anonymous and
        could collide across tenants. No tenant, no cache.
        """
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)

        app = _build_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/echo",
                headers={"Idempotency-Key": "anon-key"},
                content=b"x",
            )

        assert fake.store == {}


class TestDispatchCacheErrorResilience:
    """Cache read/write failures must NOT break the request path."""

    def test_cache_read_error_lets_request_proceed(self, monkeypatch):
        """If Redis GET raises, the middleware should swallow and run
        the handler normally — clients see the real response, not a
        cache-layer 500."""

        class _ReadFailingRedis(_FakeAsyncRedis):
            async def get(self, key):  # type: ignore[override]
                raise ConnectionError("redis get blew up")

        fake = _ReadFailingRedis()
        _patched_middleware(monkeypatch, fake)

        call_count = {"n": 0}

        async def handler(request):
            call_count["n"] += 1
            return {"ok": True}

        app = _build_app(handler=handler)
        client = TestClient(app)
        resp = client.post(
            "/echo",
            headers={"Idempotency-Key": "k", **_tenant_headers("t")},
            content=b"x",
        )
        assert resp.status_code == 200
        assert call_count["n"] == 1

    def test_cache_write_error_returns_original_response(self, monkeypatch):
        """If Redis SETEX raises, we still return the 2xx response the
        handler produced rather than masking it with a 500."""

        class _WriteFailingRedis(_FakeAsyncRedis):
            async def setex(self, key, ttl, value):  # type: ignore[override]
                raise ConnectionError("redis setex blew up")

        fake = _WriteFailingRedis()
        _patched_middleware(monkeypatch, fake)

        app = _build_app()
        client = TestClient(app)
        resp = client.post(
            "/echo",
            headers={"Idempotency-Key": "k", **_tenant_headers("t")},
            content=b"hello",
        )
        assert resp.status_code == 200
        assert resp.json() == {"body": "hello"}


class TestOperationBinding:
    @pytest.mark.parametrize(
        "path,body,extra",
        [
            ("/echo", b"changed", {}),
            ("/does-not-exist", b"original", {}),
            ("/echo?mode=other", b"original", {}),
            ("/echo", b"original", {"X-RegEngine-API-Key": "different-credential"}),
            ("/echo", b"original", {"Content-Type": "application/octet-stream"}),
        ],
    )
    def test_key_reuse_for_different_operation_conflicts(self, monkeypatch, path, body, extra):
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)
        calls = []
        monkeypatch.setattr(
            "shared.idempotency._lookup_api_key_context",
            lambda raw: ("tenant", "auth-snapshot"),
        )

        async def handler(request):
            calls.append(await request.body())
            return {"secret": "original-response"}  # pragma: allowlist secret — synthetic response fixture

        client = TestClient(_build_app(handler))
        headers = {"Idempotency-Key": "operation", **_tenant_headers("tenant")}
        assert client.post("/echo", content=b"original", headers=headers).status_code == 200
        replay = client.post(path, content=body, headers={**headers, **extra})
        assert replay.status_code == 409
        assert replay.json() == {"error": "idempotency_key_conflict"}
        assert calls == [b"original"]

    def test_legacy_unbound_cache_entry_is_not_replayed_or_reexecuted(self, monkeypatch):
        fake = _FakeAsyncRedis()
        fake.store[b"idempotency:tenant:legacy"] = json.dumps(
            {
                "status": 200,
                "body": "secret legacy response",
                "headers": {},
            }
        ).encode()
        _patched_middleware(monkeypatch, fake)
        client = TestClient(_build_app())
        response = client.post(
            "/echo",
            headers={
                "Idempotency-Key": "legacy",
                **_tenant_headers("tenant"),
            },
        )
        assert response.status_code == 409
        assert "secret" not in response.text
        assert not fake.setex_calls

    @pytest.mark.asyncio
    async def test_concurrent_identical_replay_only_dispatches_once(self, monkeypatch):
        import asyncio

        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(await request.body())
            started.set()
            await release.wait()
            return {"calls": len(calls)}

        async with AsyncClient(transport=ASGITransport(app=_build_app(handler)), base_url="http://test") as client:
            headers = {"Idempotency-Key": "concurrent", **_tenant_headers("tenant")}
            first = asyncio.create_task(client.post("/echo", headers=headers, content=b"same"))
            await asyncio.wait_for(started.wait(), timeout=3)
            try:
                second = await asyncio.wait_for(client.post("/echo", headers=headers, content=b"same"), timeout=3)
                assert second.status_code == 409
                assert second.json()["error"] == "idempotency_request_in_progress"
            finally:
                release.set()
                original = await first
            retry = await client.post("/echo", headers=headers, content=b"same")
            assert original.status_code == retry.status_code == 200
            assert retry.json() == original.json() == {"calls": 1}
            assert calls == [b"same"]

    def test_closed_mode_rejects_initial_connection_failure(self, monkeypatch):
        monkeypatch.setenv("IDEMPOTENCY_FAIL_MODE", "closed")
        _patched_middleware(monkeypatch, None)
        client = TestClient(_build_app())
        response = client.post("/echo", headers={"Idempotency-Key": "closed", **_tenant_headers("tenant")})
        assert response.status_code == 503
        assert response.headers["retry-after"] == "30"

    def test_binary_response_round_trips_exactly(self, monkeypatch):
        from fastapi import Response

        _patched_middleware(monkeypatch, _FakeAsyncRedis())

        async def handler(request):
            return Response(b"\xff\x00\xfe", media_type="application/octet-stream")

        client = TestClient(_build_app(handler))
        headers = {"Idempotency-Key": "binary", **_tenant_headers("tenant")}
        first = client.post("/echo", headers=headers)
        retry = client.post("/echo", headers=headers)
        assert first.content == retry.content == b"\xff\x00\xfe"


# ---------------------------------------------------------------------------
# Multipart uploads: the boundary is not part of the request
# ---------------------------------------------------------------------------
#
# curl, requests and httpx draw a new random boundary for every send. It sits
# in the Content-Type header and in every delimiter line of the body, so a
# keyed retry of one upload never has the bytes of the first attempt.

# A form part: field name, bytes, filename, part content type.
_FormPart = tuple[str, bytes, Optional[str], Optional[str]]

# Synthetic. Like a real EDI or CSV export, the file has CRLF line ends, a
# line that looks like the delimiter of some other boundary, and binary bytes.
_FILE_BYTES = b"ISA*00*SYNTHETIC~\r\nGS*SH~\r\n--not-the-boundary\r\nST*856*0001~\r\n\xff\x00"
_FILE_PART: _FormPart = ("file", _FILE_BYTES, "asn.edi", "application/edi-x12")
_FIELD_PART: _FormPart = ("tlc_source_reference", b"REF-0001", None, None)
_UPLOAD: tuple[_FormPart, ...] = (_FILE_PART, _FIELD_PART)
_UPLOAD_URL = "http://testserver/echo"


def _form_body(boundary: str, parts: Sequence[_FormPart] = _UPLOAD) -> bytes:
    """Encode ``parts`` the way an HTTP client encodes a form upload."""
    body = bytearray()
    for name, content, filename, content_type in parts:
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        body += f"--{boundary}\r\nContent-Disposition: {disposition}\r\n".encode()
        if content_type is not None:
            body += f"Content-Type: {content_type}\r\n".encode()
        body += b"\r\n" + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body)


def _keyed(content_type: str, body: bytes) -> Dict[str, Any]:
    """``client.post`` arguments for one keyed request from tenant ``tenant``."""
    return {
        "headers": {"Idempotency-Key": "upload", **_tenant_headers("tenant"), "Content-Type": content_type},
        "content": body,
    }


def _form_request(boundary: str, parts: Sequence[_FormPart] = _UPLOAD) -> Dict[str, Any]:
    """``client.post`` arguments that upload ``parts`` under ``boundary``."""
    return _keyed(f"multipart/form-data; boundary={boundary}", _form_body(boundary, parts))


def _exact_bytes_fingerprint(content_type: str, body: bytes, url: str = _UPLOAD_URL) -> str:
    """The fingerprint of a ``_keyed`` request as every release before this computed it.

    Cache entries already in Redis carry it. It stays the fingerprint of every
    request that is not a form upload the parser reads to its end.
    """
    bound = ["POST", url, content_type, "", "", _INTERNAL_SECRET, "", ""]
    return hashlib.sha256(json.dumps(bound).encode() + body).hexdigest()


def _stored_fingerprint(fake: _FakeAsyncRedis) -> str:
    return json.loads(fake.store[b"idempotency:tenant:upload"])["fingerprint"]


def _recording_app(calls: list[bytes]) -> FastAPI:
    """An app whose route records the raw body it was handed."""

    async def handler(request):
        calls.append(await request.body())
        return {"stored": len(calls)}

    return _build_app(handler)


# Bodies the form parser does not read through to a closing delimiter, or that
# no route reads as a form. Each takes a boundary and returns the Content-Type
# header and the body.
def _closing_delimiter_missing(boundary: str) -> tuple[str, bytes]:
    body = _form_body(boundary)
    return f"multipart/form-data; boundary={boundary}", body[: body.rindex(b"--" + boundary.encode())]


def _boundary_parameter_missing(boundary: str) -> tuple[str, bytes]:
    return "multipart/form-data", _form_body(boundary)


def _boundary_parameter_empty(boundary: str) -> tuple[str, bytes]:
    return "multipart/form-data; boundary=", _form_body(boundary)


def _boundary_absent_from_body(boundary: str) -> tuple[str, bytes]:
    return f"multipart/form-data; boundary={boundary}", _form_body(f"other-{boundary}")


def _body_without_delimiters(boundary: str) -> tuple[str, bytes]:
    return f"multipart/form-data; boundary={boundary}", b"plain bytes, no delimiter anywhere"


def _part_header_invalid(boundary: str) -> tuple[str, bytes]:
    body = f"--{boundary}\r\nContent Disposition form-data\r\n\r\nvalue\r\n--{boundary}--\r\n"
    return f"multipart/form-data; boundary={boundary}", body.encode()


def _boundary_longer_than_the_parser_accepts(boundary: str) -> tuple[str, bytes]:
    # python-multipart refuses a boundary over 256 characters with a ValueError
    # subclass. The middleware reads a ValueError as "body over 10 MB".
    long_boundary = boundary * 20
    return f"multipart/form-data; boundary={long_boundary}", _form_body(long_boundary)


def _one_part_over_the_limit(boundary: str) -> tuple[str, bytes]:
    parts = [(f"field{index}", b"v", None, None) for index in range(2001)]
    return f"multipart/form-data; boundary={boundary}", _form_body(boundary, parts)


def _file_stuffed_with_look_alike_delimiters(boundary: str) -> tuple[str, bytes]:
    # One part, but its bytes hold 2001 lines that start like a delimiter.
    stuffing = f"\r\n--{boundary}!".encode() * 2001
    return f"multipart/form-data; boundary={boundary}", _form_body(boundary, [("file", stuffing, "s.csv", "text/csv")])


def _multipart_but_not_form_data(boundary: str) -> tuple[str, bytes]:
    return f"multipart/mixed; boundary={boundary}", _form_body(boundary)


class TestMultipartUploadBinding:
    """A retried upload is the same request although its boundary is new."""

    @pytest.mark.asyncio
    async def test_retry_under_a_new_boundary_is_in_progress_then_replayed(self, monkeypatch):
        _patched_middleware(monkeypatch, _FakeAsyncRedis())
        started, release = asyncio.Event(), asyncio.Event()
        seen = []

        async def handler(request):
            raw = await request.body()
            form = await request.form()
            upload = form["file"]
            seen.append((raw, upload.filename, upload.content_type, await upload.read(), form["tlc_source_reference"]))
            started.set()
            await release.wait()
            return {"stored": len(seen)}

        first_send = _form_request("boundary-of-the-first-send")
        async with AsyncClient(transport=ASGITransport(app=_build_app(handler)), base_url="http://test") as client:
            first = asyncio.create_task(client.post("/echo", **first_send))
            await asyncio.wait_for(started.wait(), timeout=3)
            try:
                during = await asyncio.wait_for(
                    client.post("/echo", **_form_request("boundary-of-a-retry-while-running")), timeout=3
                )
                assert during.status_code == 409
                assert during.json() == {"error": "idempotency_request_in_progress"}
                other_file = [("file", b"another file", "asn.edi", "application/edi-x12"), _FIELD_PART]
                changed = await asyncio.wait_for(
                    client.post("/echo", **_form_request("boundary-of-a-changed-upload", other_file)), timeout=3
                )
                assert changed.status_code == 409
                assert changed.json() == {"error": "idempotency_key_conflict"}
            finally:
                release.set()
                original = await first
            after = await client.post("/echo", **_form_request("boundary-of-a-retry-afterwards"))
            assert original.status_code == after.status_code == 200
            assert after.json() == original.json() == {"stored": 1}
        # The route ran once, on the bytes of the first send, and read the form from them.
        assert seen == [(first_send["content"], "asn.edi", "application/edi-x12", _FILE_BYTES, "REF-0001")]

    def test_upload_encoded_twice_by_a_real_client_replays(self, monkeypatch):
        """No hand-built body here: httpx draws the boundary of each send itself."""
        _patched_middleware(monkeypatch, _FakeAsyncRedis())
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        sends = [
            client.build_request(
                "POST",
                "/echo",
                headers={"Idempotency-Key": "upload", **_tenant_headers("tenant")},
                files={"file": ("asn.edi", _FILE_BYTES, "application/edi-x12")},
                data={"tlc_source_reference": "REF-0001"},
            )
            for _ in range(2)
        ]
        assert sends[0].headers["content-type"] != sends[1].headers["content-type"]
        first, retry = client.send(sends[0]), client.send(sends[1])
        assert first.status_code == retry.status_code == 200
        assert retry.json() == first.json() == {"stored": 1}
        assert len(calls) == 1

    @pytest.mark.parametrize(
        "parts",
        [
            pytest.param([("file", b"", "empty.csv", "text/csv")], id="empty-file"),
            pytest.param([("file", b"last byte is a carriage return\r", "cr.csv", "text/csv")], id="file-ends-with-cr"),
            pytest.param([("note", b"", None, None)], id="empty-field"),
            pytest.param([], id="no-parts"),
            pytest.param([(f"field{index}", b"v", None, None) for index in range(2000)], id="at-the-part-limit"),
        ],
    )
    def test_other_form_shapes_replay_under_a_new_boundary(self, monkeypatch, parts):
        _patched_middleware(monkeypatch, _FakeAsyncRedis())
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        first = client.post("/echo", **_form_request("first-boundary", parts))
        retry = client.post("/echo", **_form_request("second-boundary", parts))
        assert first.status_code == retry.status_code == 200
        assert retry.json() == first.json() == {"stored": 1}
        assert len(calls) == 1

    def test_bytes_outside_the_parts_are_not_part_of_the_request(self, monkeypatch):
        """Line ends before the first delimiter and bytes after the last never reach a route."""
        _patched_middleware(monkeypatch, _FakeAsyncRedis())
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        first = client.post("/echo", **_form_request("first-boundary"))
        padded = b"\r\n" + _form_body("second-boundary") + b"ignored trailer"
        retry = client.post("/echo", **_keyed('multipart/form-data; boundary="second-boundary"', padded))
        assert first.status_code == retry.status_code == 200
        assert retry.json() == first.json() == {"stored": 1}
        assert len(calls) == 1

    @pytest.mark.parametrize(
        ("original", "changed"),
        [
            pytest.param(
                _UPLOAD, [("file", b"another file", "asn.edi", "application/edi-x12"), _FIELD_PART], id="file-bytes"
            ),
            pytest.param(_UPLOAD, [_FILE_PART, ("tlc_source_reference", b"REF-0002", None, None)], id="field-value"),
            pytest.param(
                _UPLOAD, [("file", _FILE_BYTES, "renamed.edi", "application/edi-x12"), _FIELD_PART], id="filename"
            ),
            pytest.param(
                _UPLOAD, [("file", _FILE_BYTES, "asn.edi", "text/plain"), _FIELD_PART], id="part-content-type"
            ),
            pytest.param(
                _UPLOAD, [("file", _FILE_BYTES, "asn.edi", None), _FIELD_PART], id="part-content-type-dropped"
            ),
            pytest.param(
                _UPLOAD, [("document", _FILE_BYTES, "asn.edi", "application/edi-x12"), _FIELD_PART], id="field-name"
            ),
            pytest.param(_UPLOAD, [_FIELD_PART, _FILE_PART], id="part-order"),
            pytest.param(_UPLOAD, [_FILE_PART], id="part-removed"),
            pytest.param(_UPLOAD, [_FILE_PART, _FIELD_PART, ("note", b"", None, None)], id="part-added"),
            pytest.param([("a", b"bc", None, None)], [("ab", b"c", None, None)], id="name-and-value-split-elsewhere"),
            pytest.param(
                [("file", b"note first-boundary", "n.txt", "text/plain")],
                [("file", b"note second-boundary", "n.txt", "text/plain")],
                id="file-names-its-own-boundary",
            ),
            pytest.param(
                [("a", b"1", None, None), ("b", b"2", None, None)],
                [("a", b'1\r\n--first-boundary\r\nContent-Disposition: form-data; name="b"\r\n\r\n2', None, None)],
                id="two-parts-quoted-inside-one",
            ),
        ],
    )
    def test_a_changed_form_still_conflicts(self, monkeypatch, original, changed):
        _patched_middleware(monkeypatch, _FakeAsyncRedis())
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        first = client.post("/echo", **_form_request("first-boundary", original))
        assert first.status_code == 200
        conflict = client.post("/echo", **_form_request("second-boundary", changed))
        assert conflict.status_code == 409
        assert conflict.json() == {"error": "idempotency_key_conflict"}
        # The new boundary alone is not what conflicted.
        retry = client.post("/echo", **_form_request("second-boundary", original))
        assert retry.status_code == 200
        assert retry.json() == first.json() == {"stored": 1}
        assert len(calls) == 1

    @pytest.mark.parametrize(
        ("path", "extra_headers", "content_type_parameter"),
        [
            pytest.param("/echo?mode=other", {}, "", id="url"),
            pytest.param("/echo", {"X-RegEngine-API-Key": "different-credential"}, "", id="credential"),
            pytest.param("/echo", {}, "; charset=latin-1", id="content-type-parameter"),
        ],
    )
    def test_the_same_form_in_a_different_request_still_conflicts(
        self, monkeypatch, path, extra_headers, content_type_parameter
    ):
        _patched_middleware(monkeypatch, _FakeAsyncRedis())
        monkeypatch.setattr("shared.idempotency._lookup_api_key_context", lambda raw: ("tenant", "auth-snapshot"))
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        assert client.post("/echo", **_form_request("first-boundary")).status_code == 200
        replay = _form_request("second-boundary")
        replay["headers"] = {**replay["headers"], **extra_headers}
        replay["headers"]["Content-Type"] += content_type_parameter
        conflict = client.post(path, **replay)
        assert conflict.status_code == 409
        assert conflict.json() == {"error": "idempotency_key_conflict"}
        assert len(calls) == 1

    @pytest.mark.parametrize(("slice_bytes", "repeats"), [(1, 2), (7, 2), (1000, 15), (64 * 1024, 150)])
    def test_parts_read_the_same_however_the_body_is_sliced(self, monkeypatch, slice_bytes, repeats):
        """The body is fed to the parser in slices. Where they fall must not matter."""
        _patched_middleware(monkeypatch, _FakeAsyncRedis())
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        # Bare carriage returns and near misses of both delimiters on most
        # lines, and now and then a line that only looks like a delimiter.
        near_misses = b"row\r\n--first-boundar\r\n--a-second-boundary-of-another-lengt\r-\r" * 50
        tricky = (near_misses + b"\r\n--first-boundary!\r\n--a-second-boundary-of-another-length!") * repeats
        parts = [("file", tricky, "rows.csv", "text/csv"), _FIELD_PART]
        first = client.post("/echo", **_form_request("first-boundary", parts))
        monkeypatch.setattr("shared.idempotency._MULTIPART_SLICE_BYTES", slice_bytes)
        retry = client.post("/echo", **_form_request("a-second-boundary-of-another-length", parts))
        assert first.status_code == retry.status_code == 200
        assert retry.json() == first.json() == {"stored": 1}
        assert len(calls) == 1

    @pytest.mark.parametrize(
        "malformed",
        [
            _closing_delimiter_missing,
            _boundary_parameter_missing,
            _boundary_parameter_empty,
            _boundary_absent_from_body,
            _body_without_delimiters,
            _part_header_invalid,
            _boundary_longer_than_the_parser_accepts,
            _one_part_over_the_limit,
            _file_stuffed_with_look_alike_delimiters,
            _multipart_but_not_form_data,
        ],
        ids=lambda case: case.__name__.strip("_"),
    )
    def test_body_the_form_parser_does_not_finish_keeps_the_exact_byte_binding(
        self, monkeypatch, malformed: Callable[[str], tuple[str, bytes]]
    ):
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        content_type, body = malformed("first-boundary")
        # Neither refused by the middleware nor altered on the way to the route.
        first = client.post("/echo", **_keyed(content_type, body))
        assert first.status_code == 200
        assert calls == [body]
        assert _stored_fingerprint(fake) == _exact_bytes_fingerprint(content_type, body)
        # The same bytes again are the same request.
        retry = client.post("/echo", **_keyed(content_type, body))
        assert retry.status_code == 200
        assert retry.json() == first.json() == {"stored": 1}
        # Any other bytes, a new boundary included, are a conflict as before.
        conflict = client.post("/echo", **_keyed(*malformed("second-boundary")))
        assert conflict.status_code == 409
        assert conflict.json() == {"error": "idempotency_key_conflict"}
        assert calls == [body]

    def test_upload_over_the_body_cap_is_refused_before_it_is_parsed(self, monkeypatch):
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        too_large = [("file", b"x" * (10 * 1024 * 1024), "rows.csv", "text/csv")]
        response = client.post("/echo", **_form_request("first-boundary", too_large))
        assert response.status_code == 413
        assert response.json() == {"error": "payload_too_large"}
        assert fake.store == {}
        assert calls == []

    @pytest.mark.parametrize(
        ("content_type", "body"),
        [
            pytest.param("application/json", b'{"events": [1, 2]}', id="json"),
            pytest.param("application/x-www-form-urlencoded", b"a=1&b=2", id="urlencoded-form"),
            pytest.param("application/octet-stream", b"\xff\x00--first-boundary\r\n", id="binary"),
            pytest.param("", b"no content type", id="no-content-type"),
        ],
    )
    def test_every_other_body_keeps_its_fingerprint(self, monkeypatch, content_type, body):
        """Entries cached by earlier releases must still match after a deploy."""
        fake = _FakeAsyncRedis()
        _patched_middleware(monkeypatch, fake)
        calls: list[bytes] = []
        client = TestClient(_recording_app(calls))
        assert client.post("/echo", **_keyed(content_type, body)).status_code == 200
        assert _stored_fingerprint(fake) == _exact_bytes_fingerprint(content_type, body)


@pytest.fixture
async def disposable_redis(tmp_path):
    """Use a private Unix socket; never connect to an existing Redis database."""
    import asyncio
    import shutil
    import subprocess
    import tempfile

    import redis.asyncio as redis

    executable = shutil.which("redis-server")
    if not executable:
        pytest.skip("redis-server executable is required for real Redis reservation tests")
    with tempfile.TemporaryDirectory(prefix="idemp-", dir="/tmp") as directory:
        socket = f"{directory}/redis.sock"
        process = subprocess.Popen(
            [
                executable,
                "--port",
                "0",
                "--unixsocket",
                socket,
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                directory,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        client = redis.Redis(unix_socket_path=socket)
        try:
            for _ in range(100):
                try:
                    await client.ping()
                    break
                except (ConnectionError, redis.ConnectionError):
                    await asyncio.sleep(0.02)
            else:
                pytest.fail("Disposable Redis failed to start")
            yield client
        finally:
            await client.aclose()
            process.terminate()
            process.wait(timeout=5)


@pytest.mark.asyncio
async def test_real_redis_concurrent_replay(monkeypatch, disposable_redis):
    import asyncio

    _patched_middleware(monkeypatch, disposable_redis)
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def handler(request):
        calls.append(await request.body())
        started.set()
        await release.wait()
        return {"calls": len(calls)}

    # Distinct app instances share Redis, modeling separate service replicas.
    async with AsyncClient(transport=ASGITransport(app=_build_app(handler)), base_url="http://test") as a:
        async with AsyncClient(transport=ASGITransport(app=_build_app(handler)), base_url="http://test") as b:
            headers = {"Idempotency-Key": "race", **_tenant_headers("tenant")}
            pending = asyncio.create_task(a.post("/echo", headers=headers, content=b"same"))
            await asyncio.wait_for(started.wait(), 3)
            try:
                concurrent = await b.post("/echo", headers=headers, content=b"same")
                assert concurrent.status_code == 409
                assert concurrent.json()["error"] == "idempotency_request_in_progress"
                conflicting = await b.post("/echo", headers=headers, content=b"different")
                assert conflicting.status_code == 409
                assert conflicting.json()["error"] == "idempotency_key_conflict"
            finally:
                release.set()
                original = await pending
            replay = await b.post("/echo", headers=headers, content=b"same")
            assert original.json() == replay.json() == {"calls": 1}
            assert calls == [b"same"]
            assert await disposable_redis.ttl("idempotency:tenant:race") > 86390


@pytest.mark.asyncio
async def test_streamed_oversized_body_rejected_before_reservation(monkeypatch):
    fake = _FakeAsyncRedis()
    _patched_middleware(monkeypatch, fake)

    async def chunks():
        for _ in range(11):
            yield b"x" * (1024 * 1024)

    async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
        response = await client.post(
            "/echo",
            headers={
                "Idempotency-Key": "large",
                **_tenant_headers("tenant"),
            },
            content=chunks(),
        )
    assert response.status_code == 413
    assert fake.store == {}


def test_handler_exception_retains_ambiguous_reservation(monkeypatch):
    fake = _FakeAsyncRedis()
    _patched_middleware(monkeypatch, fake)
    calls = []

    async def handler(request):
        calls.append(1)
        raise RuntimeError("side effect outcome is uncertain")

    client = TestClient(_build_app(handler), raise_server_exceptions=False)
    headers = {"Idempotency-Key": "ambiguous", **_tenant_headers("tenant")}
    assert client.post("/echo", headers=headers).status_code == 500
    retry = client.post("/echo", headers=headers)
    assert retry.status_code == 409
    assert retry.json()["error"] == "idempotency_request_in_progress"
    assert calls == [1]


def test_uncertain_cache_write_does_not_redispatch(monkeypatch):
    class FailingPublishRedis(_FakeAsyncRedis):
        async def eval(self, *args):
            raise ConnectionError("publish unavailable")

    _patched_middleware(monkeypatch, FailingPublishRedis())
    client = TestClient(_build_app())
    headers = {"Idempotency-Key": "ambiguous", **_tenant_headers("tenant")}
    assert client.post("/echo", headers=headers).status_code == 200
    assert client.post("/echo", headers=headers).status_code == 409


def test_failed_route_releases_reservation_for_retry(monkeypatch):
    _patched_middleware(monkeypatch, _FakeAsyncRedis())
    attempts = []

    async def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            raise HTTPException(403)
        return {"ok": True}

    client = TestClient(_build_app(handler))
    headers = {"Idempotency-Key": "retry", **_tenant_headers("tenant")}
    assert client.post("/echo", headers=headers).status_code == 403
    assert client.post("/echo", headers=headers).status_code == 200
    assert len(attempts) == 2


@pytest.mark.parametrize(
    "changed_field,new_value",
    [
        ("scopes", ["read"]),
        ("jurisdictions", ["US-CA"]),
    ],
)
def test_authoritative_key_permission_narrowing_blocks_cached_replay(monkeypatch, changed_field, new_value):
    import shared.api_key_store as key_store
    import shared.database as database

    _patched_middleware(monkeypatch, _FakeAsyncRedis())
    authorization = {"scopes": ["read", "write"], "jurisdictions": ["US", "US-CA"]}
    queries = []
    db = MagicMock()

    def execute(statement, parameters):
        queries.append(str(statement))
        result = MagicMock()
        if "FROM tenants" in str(statement):
            # Tenant-status re-check: this tenant stays active throughout.
            result.fetchone.return_value = ("active",)
        else:
            result.fetchone.return_value = (
                "tenant",
                True,
                None,
                "stable-key-id",
                authorization["scopes"],
                authorization["jurisdictions"],
                None,  # revoked_at: key is live
            )
        return result

    db.execute.side_effect = execute
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(key_store, "set_api_key_lookup_context", lambda session, raw: ("stable-key-id", ["hash"]))
    client = TestClient(_build_app())
    # Internal identity must not bypass the fresh API-key authorization lookup.
    headers = {"Idempotency-Key": "permissions", "X-RegEngine-API-Key": "stable-key", **_tenant_headers("tenant")}
    original = client.post("/echo", headers=headers, content=b"same")
    assert original.status_code == 200
    assert client.post("/echo", headers=headers, content=b"same").status_code == 200
    authorization[changed_field] = new_value
    replay = client.post("/echo", headers=headers, content=b"same")
    assert replay.status_code == 409
    assert replay.json() == {"error": "idempotency_key_conflict"}
    key_queries = [query for query in queries if "scopes, allowed_jurisdictions" in query]
    assert len(key_queries) == 3
    assert all("scopes, allowed_jurisdictions" in query for query in key_queries)


@pytest.mark.parametrize("signature_change", ["missing", "wrong", "rotated"])
@pytest.mark.parametrize("replay_suffix", ["", "/"])
def test_webhook_replay_cannot_bypass_real_signature_dependency(monkeypatch, signature_change, replay_suffix):
    import hashlib
    import hmac

    from fastapi import Depends

    from services.ingestion.app.webhook_router_v2.security import _verify_webhook_signature

    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", " signing-key ")
    fake = _FakeAsyncRedis()
    _patched_middleware(monkeypatch, fake)
    app = FastAPI()
    calls = []

    @app.post("/api/v1/webhooks/ingest")
    async def webhook(_signature=Depends(_verify_webhook_signature)):
        calls.append(1)
        return {"receipt": "authorized"}

    app.add_middleware(IdempotencyMiddleware)
    client = TestClient(app)
    body = b"{}"
    headers = {
        "Idempotency-Key": "signed",
        **_tenant_headers("tenant"),
        "X-Webhook-Signature": "sha256=" + hmac.new(b"signing-key", body, hashlib.sha256).hexdigest(),
    }
    assert client.post("/api/v1/webhooks/ingest", headers=headers, content=body).status_code == 200
    assert client.post("/api/v1/webhooks/ingest", headers=headers, content=body).status_code == 200
    if signature_change == "missing":
        del headers["X-Webhook-Signature"]
    elif signature_change == "wrong":
        headers["X-Webhook-Signature"] = "sha256=bad"
    else:
        monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "rotated-key")
    replay = client.post("/api/v1/webhooks/ingest" + replay_suffix, headers=headers, content=body)
    assert replay.status_code == 409
    assert replay.json() == {"error": "idempotency_key_conflict"}
    headers.pop("Idempotency-Key")
    assert client.post("/api/v1/webhooks/ingest", headers=headers, content=body).status_code == 401
    assert calls == [1]


def test_revoked_cookie_session_rechecks_real_session_dependency(monkeypatch):
    from fastapi import Depends

    from services.admin.app.auth.session_auth import (
        get_auth_crypto_service,
        get_current_active_session_context,
    )
    from services.admin.app.database import get_session

    fake = _FakeAsyncRedis()
    _patched_middleware(monkeypatch, fake)
    db, crypto = MagicMock(), MagicMock()
    crypto.hash_session_token.return_value = "hashed-session"
    db.execute.return_value.one_or_none.return_value = (MagicMock(), MagicMock())
    app = FastAPI()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_auth_crypto_service] = lambda: crypto

    @app.post("/session-protected")
    async def receipt(context=Depends(get_current_active_session_context)):
        return {"receipt": "authorized"}

    app.add_middleware(IdempotencyMiddleware)
    client = TestClient(app)
    headers = {
        "Idempotency-Key": "session",
        **_tenant_headers("tenant"),
        "Cookie": "__Host-regengine_session=opaque-session",
    }
    assert client.post("/session-protected", headers=headers).status_code == 200
    db.execute.return_value.one_or_none.return_value = None  # revoked/expired session no longer matches
    assert client.post("/session-protected", headers=headers).status_code == 401
    assert db.execute.call_count == 2
    assert fake.store == {}


@pytest.mark.parametrize("path", ["/auth/refresh", "/v1/auth/accept-invite", "/session-protected"])
def test_single_use_authentication_is_never_cached(monkeypatch, path):
    from fastapi import Depends

    fake = _FakeAsyncRedis()
    _patched_middleware(monkeypatch, fake)
    app = FastAPI()
    consumed = []

    async def single_use(request: Request):
        credential = await request.body()
        if credential in consumed:
            raise HTTPException(401, "credential already consumed or revoked")
        consumed.append(credential)

    @app.post(path)
    async def exchange(_auth=Depends(single_use)):
        return {"access_token": "replacement"}

    app.add_middleware(IdempotencyMiddleware)
    client = TestClient(app)
    headers = {"Idempotency-Key": "auth", **_tenant_headers("tenant")}
    if path == "/session-protected":
        headers["Authorization"] = "Bearer revoked-after-first-use"
    assert client.post(path, headers=headers, json={"refresh_token": "single-use"}).status_code == 200
    assert client.post(path, headers=headers, json={"refresh_token": "single-use"}).status_code == 401
    assert fake.store == {}


def test_real_refresh_route_ignores_preexisting_cached_token_response(monkeypatch):
    import asyncio

    from services.admin.app.auth.refresh_router import router
    from services.admin.app.database import get_session
    from services.admin.app.dependencies import get_session_store

    fake = _FakeAsyncRedis()
    _patched_middleware(monkeypatch, fake)
    headers = {"Idempotency-Key": "refresh", **_tenant_headers("tenant"), "Content-Type": "application/json"}
    body = b'{"refresh_token":"already-used"}'

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/auth/refresh",
            "query_string": b"",
            "server": ("testserver", 80),
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        },
        receive=receive,
    )
    middleware = IdempotencyMiddleware(app=MagicMock())
    fingerprint = asyncio.run(middleware._request_fingerprint(request))
    fake.store[b"idempotency:tenant:refresh"] = json.dumps(
        {
            "fingerprint": fingerprint,
            "status": 200,
            "body": '{"access_token":"old-cached-token"}',
            "headers": {},
        }
    ).encode()
    store = AsyncMock()
    store.claim_session_by_token.return_value = None
    store.check_token_reuse.return_value = None
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    app.dependency_overrides[get_session] = lambda: MagicMock()
    app.dependency_overrides[get_session_store] = lambda: store
    app.add_middleware(IdempotencyMiddleware)
    response = TestClient(app).post("/auth/refresh", headers=headers, content=body)
    assert response.status_code == 401
    assert "old-cached-token" not in response.text
    store.claim_session_by_token.assert_awaited_once()
    assert fake.get_calls == []
