"""#2841 — cross-tenant idempotency replay via the unauthenticated X-Tenant-ID header.

These tests run against the REAL production monolith stack
(``server.main.app``), where ``IdempotencyMiddleware`` is registered
*outside* ``TenantContextMiddleware`` and outside every route dependency
(``server/main.py``: TenantContext added before Idempotency, and Starlette
wraps later-added middleware outermost). That ordering is what makes the
bug exploitable: ``_resolve_tenant_id`` consults the raw ``X-Tenant-ID``
header before the authenticated API-key lookup, and ``dispatch`` returns a
cache hit *before* ``call_next``, so no auth dependency ever runs.

The exploit demonstrated here is a genuine replay, not a description:
a caller with **no credentials at all** — only a forged header — receives
the victim tenant's cached 2xx response body.
"""

from __future__ import annotations

import importlib
from typing import Dict, Optional

import pytest
from fastapi import Depends, HTTPException, Request
from fastapi.testclient import TestClient

_VICTIM_PATH = "/__test__/2841/evidence"

# Real tenant ids are UUIDs; using UUIDs keeps the forged header indistinguishable
# from a legitimate one to every layer that validates format.
_VICTIM_TENANT = "11111111-1111-4111-8111-111111111111"
_ATTACKER_TENANT = "22222222-2222-4222-8222-222222222222"

# Simulated api_keys table: raw key -> tenant it belongs to.
_KEY_TO_TENANT = {
    "victim-key": _VICTIM_TENANT,
    "attacker-key": _ATTACKER_TENANT,
}


@pytest.fixture(scope="module")
def server_main():
    return importlib.import_module("server.main")


class _FakeAsyncRedis:
    def __init__(self) -> None:
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
            return await self.setex(key, int(args[0]), args[1])
        del self.store[key]
        return 1

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
    # Stand in for the real ``api_keys`` DB lookup the middleware performs for
    # API-key-authenticated requests (no principal available pre-auth).
    monkeypatch.setattr(
        idemp_mod,
        "_lookup_api_key_context",
        lambda raw: (_KEY_TO_TENANT[raw], "auth-snapshot") if raw in _KEY_TO_TENANT else None,
    )
    return fake


class _Principal:
    def __init__(self, tenant_id: str, key_id: str) -> None:
        self.tenant_id = tenant_id
        self.key_id = key_id


def _victim_route_count(app) -> int:
    """How many global routes are currently mounted at the test path."""
    return sum(1 for r in app.router.routes if getattr(r, "path", None) == _VICTIM_PATH)


def _remove_victim_routes(app) -> None:
    """Drop every route mounted at the test path, in place."""
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != _VICTIM_PATH]


def _install_victim_route(app):
    """Mount the realistically-protected POST route on the real monolith app.

    The auth dependency 401s without a recognised API key, exactly like the
    production ingest routes guarded by ``require_permission`` — so a 200 for
    an unauthenticated caller can only have come from the idempotency cache.

    Setup first removes any residue at the test path, so an interrupted
    earlier run cannot shadow the fresh handler (Starlette matches routes in
    registration order). Returns the handler call counts plus a snapshot of
    the router to restore at teardown.
    """
    _remove_victim_routes(app)
    snapshot = list(app.router.routes)
    calls: Dict[str, int] = {}

    async def _auth(request: Request) -> _Principal:
        raw = request.headers.get("X-RegEngine-API-Key")
        tenant = _KEY_TO_TENANT.get(raw or "")
        if tenant is None:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        principal = _Principal(tenant_id=tenant, key_id=str(raw))
        request.state.principal = principal
        return principal

    @app.post(_VICTIM_PATH)
    async def _evidence(principal: _Principal = Depends(_auth)):
        calls[principal.tenant_id] = calls.get(principal.tenant_id, 0) + 1
        # Stands in for the FSMA traceability payload a real ingest returns.
        return {
            "tenant": principal.tenant_id,
            "traceability_lot_code": f"LOT-SECRET-{principal.tenant_id}",
            "calls": calls[principal.tenant_id],
        }

    return calls, snapshot


@pytest.fixture
def victim_route(server_main):
    """Mount the test route on the real monolith app with guaranteed cleanup.

    Teardown restores the router to the exact snapshot taken at setup, so the
    test path never leaks into other tests whatever the outcome here.
    """
    app = server_main.app
    calls, snapshot = _install_victim_route(app)
    try:
        yield calls
    finally:
        app.router.routes[:] = snapshot


def _victim_seeds_cache(client: TestClient, key: str) -> dict:
    """Victim authenticates normally; its 2xx response lands in the cache."""
    resp = client.post(
        _VICTIM_PATH,
        headers={"Idempotency-Key": key, "X-RegEngine-API-Key": "victim-key"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant"] == _VICTIM_TENANT
    return resp.json()


# ---------------------------------------------------------------------------
# Route isolation: the test route must not pollute the global app router.
# ---------------------------------------------------------------------------


def test_mount_clears_stale_residue_and_teardown_restores_router(server_main, fake_redis):
    """Residue from an interrupted run must not shadow the fresh handler.

    Plants a stale route at the test path (what a killed run would leave
    behind), then mounts through the same setup path the fixture uses. Fails
    against a plain ``@app.post`` mount with no setup cleanup: the stale
    route was registered first, so Starlette serves it instead of the fresh
    handler and the fresh call counts stay empty.
    """
    app = server_main.app
    assert _victim_route_count(app) == 0

    @app.post(_VICTIM_PATH)
    async def _stale():
        return {"stale": True}

    try:
        calls, snapshot = _install_victim_route(app)
        try:
            assert _victim_route_count(app) == 1
            client = TestClient(app)
            resp = client.post(
                _VICTIM_PATH,
                headers={"Idempotency-Key": "stale-residue-2841", "X-RegEngine-API-Key": "victim-key"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json().get("tenant") == _VICTIM_TENANT, resp.text
            assert calls == {_VICTIM_TENANT: 1}
        finally:
            app.router.routes[:] = snapshot
    finally:
        _remove_victim_routes(app)
    assert _victim_route_count(app) == 0


# ---------------------------------------------------------------------------
# The exploit
# ---------------------------------------------------------------------------


def test_unauthenticated_forged_tenant_header_cannot_replay_victim_response(server_main, fake_redis, victim_route):
    """A caller with NO credentials must not read the victim's cached body.

    Pre-fix this returned 200 with the victim's ``LOT-SECRET-<uuid>``: the header
    branch of ``_resolve_tenant_id`` selected the victim's namespace and the
    cache hit short-circuited before the 401-raising auth dependency ran.
    """
    client = TestClient(server_main.app)
    victim_body = _victim_seeds_cache(client, "replay-2841-a")

    attacker = client.post(
        _VICTIM_PATH,
        headers={
            "Idempotency-Key": "replay-2841-a",
            # The entire attack payload: one forged header, no credential.
            "X-Tenant-ID": _VICTIM_TENANT,
        },
    )

    assert attacker.status_code == 401, (
        "CROSS-TENANT REPLAY: an unauthenticated caller received "
        f"{attacker.status_code} {attacker.text!r} by forging X-Tenant-ID"
    )
    assert f"LOT-SECRET-{_VICTIM_TENANT}" not in attacker.text
    assert attacker.json() != victim_body
    # The handler ran exactly once — for the victim.
    assert victim_route == {_VICTIM_TENANT: 1}


def test_authenticated_tenant_cannot_redirect_cache_namespace_with_header(server_main, fake_redis, victim_route):
    """Tenant A authenticates with its own key but forges ``X-Tenant-ID: B``.

    Pre-fix the header branch outranked the authenticated API-key lookup, so
    A's request was namespaced into B's cache and served B's stored response.
    """
    client = TestClient(server_main.app)
    victim_body = _victim_seeds_cache(client, "replay-2841-b")

    attacker = client.post(
        _VICTIM_PATH,
        headers={
            "Idempotency-Key": "replay-2841-b",
            "X-RegEngine-API-Key": "attacker-key",  # genuinely tenant-attacker
            "X-Tenant-ID": _VICTIM_TENANT,  # forged namespace override
        },
    )

    assert attacker.status_code == 200, attacker.text
    assert attacker.json()["tenant"] == _ATTACKER_TENANT, (
        "CROSS-TENANT REPLAY: the authenticated attacker tenant was served "
        f"the victim's cached response: {attacker.text!r}"
    )
    assert f"LOT-SECRET-{_VICTIM_TENANT}" not in attacker.text
    assert attacker.json() != victim_body
    assert victim_route == {_VICTIM_TENANT: 1, _ATTACKER_TENANT: 1}


def test_forged_header_cannot_poison_another_tenants_namespace(server_main, fake_redis, victim_route):
    """Write side: the attacker's own response must not land in B's namespace.

    Otherwise the attacker could pre-seed a key the victim is about to use and
    have the victim served attacker-authored content.
    """
    client = TestClient(server_main.app)

    resp = client.post(
        _VICTIM_PATH,
        headers={
            "Idempotency-Key": "poison-2841",
            "X-RegEngine-API-Key": "attacker-key",
            "X-Tenant-ID": _VICTIM_TENANT,
        },
    )
    assert resp.status_code == 200, resp.text

    stored = [k.decode() for k in fake_redis.store]
    assert not any(_VICTIM_TENANT in k for k in stored), f"Attacker wrote into the victim's cache namespace: {stored}"
    assert stored == [f"idempotency:{_ATTACKER_TENANT}:poison-2841"], stored


def test_namespace_derives_from_authenticated_key_not_header(server_main, fake_redis, victim_route):
    """The surviving namespace source is the authenticated API-key lookup."""
    client = TestClient(server_main.app)

    first = client.post(
        _VICTIM_PATH,
        headers={"Idempotency-Key": "dedup-2841", "X-RegEngine-API-Key": "victim-key"},
    )
    retry = client.post(
        _VICTIM_PATH,
        headers={"Idempotency-Key": "dedup-2841", "X-RegEngine-API-Key": "victim-key"},
    )

    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert victim_route == {_VICTIM_TENANT: 1}, "legitimate dedup must still work"
    stored = [k.decode() for k in fake_redis.store]
    assert f"idempotency:{_VICTIM_TENANT}:dedup-2841" in stored


def test_bare_tenant_header_alone_does_not_create_a_cache_namespace(server_main, fake_redis, victim_route):
    """No authenticated tenant → no cache read and no cache write (fail closed)."""
    client = TestClient(server_main.app)

    r1 = client.post(_VICTIM_PATH, headers={"Idempotency-Key": "nocache-2841", "X-Tenant-ID": _VICTIM_TENANT})
    r2 = client.post(_VICTIM_PATH, headers={"Idempotency-Key": "nocache-2841", "X-Tenant-ID": _VICTIM_TENANT})

    assert r1.status_code == r2.status_code == 401
    assert fake_redis.store == {}, fake_redis.store


# ---------------------------------------------------------------------------
# Internal service-to-service callers keep a namespace, but only behind the
# secret gate that TenantContextMiddleware already applies (#2841 fix option 3).
# ---------------------------------------------------------------------------


def _internal_headers(secret: Optional[str], tenant: str, key: str) -> Dict[str, str]:
    headers = {"Idempotency-Key": key, "X-RegEngine-Tenant-ID": tenant}
    if secret is not None:
        headers["X-RegEngine-Internal-Secret"] = secret
    return headers


def test_internal_tenant_header_requires_the_internal_secret(server_main, fake_redis, victim_route, monkeypatch):
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", "s3cr3t-internal")
    client = TestClient(server_main.app)

    # Without the secret the internal header is ignored → no namespace, no cache.
    no_secret = client.post(_VICTIM_PATH, headers=_internal_headers(None, _VICTIM_TENANT, "int-2841"))
    assert no_secret.status_code == 401
    assert fake_redis.store == {}

    # A wrong secret is likewise ignored.
    wrong = client.post(_VICTIM_PATH, headers=_internal_headers("nope", _VICTIM_TENANT, "int-2841"))
    assert wrong.status_code == 401
    assert fake_redis.store == {}


def test_internal_tenant_header_with_secret_scopes_the_cache(server_main, fake_redis, victim_route, monkeypatch):
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", "s3cr3t-internal")
    client = TestClient(server_main.app)

    headers = _internal_headers("s3cr3t-internal", _VICTIM_TENANT, "int-ok-2841")
    headers["X-RegEngine-API-Key"] = "victim-key"
    resp = client.post(_VICTIM_PATH, headers=headers)

    assert resp.status_code == 200, resp.text
    stored = [k.decode() for k in fake_redis.store]
    assert f"idempotency:{_VICTIM_TENANT}:int-ok-2841" in stored, stored


def test_same_tenant_different_credential_cannot_read_cached_response(
    server_main, fake_redis, victim_route, monkeypatch
):
    monkeypatch.setitem(_KEY_TO_TENANT, "other-same-tenant-key", _VICTIM_TENANT)
    client = TestClient(server_main.app)
    _victim_seeds_cache(client, "same-tenant-credential")
    replay = client.post(
        _VICTIM_PATH,
        headers={
            "Idempotency-Key": "same-tenant-credential",
            "X-RegEngine-API-Key": "other-same-tenant-key",
        },
    )
    assert replay.status_code == 409
    assert "LOT-SECRET" not in replay.text
    assert victim_route == {_VICTIM_TENANT: 1}


def test_revoked_key_cannot_read_cached_response(server_main, fake_redis, victim_route, monkeypatch):
    client = TestClient(server_main.app)
    _victim_seeds_cache(client, "revoked")
    monkeypatch.delitem(_KEY_TO_TENANT, "victim-key")
    replay = client.post(
        _VICTIM_PATH,
        headers={
            "Idempotency-Key": "revoked",
            "X-RegEngine-API-Key": "victim-key",
        },
    )
    assert replay.status_code == 401
    assert "LOT-SECRET" not in replay.text
    assert victim_route == {_VICTIM_TENANT: 1}
