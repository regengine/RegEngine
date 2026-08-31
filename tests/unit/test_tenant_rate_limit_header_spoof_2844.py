"""#2844 — ``TenantRateLimitMiddleware`` must not bucket on the raw client header.

Two attacks are reproduced here with nothing but a forged ``X-Tenant-ID``:

1. **Evasion** — vary the header per request and every request lands in a
   fresh bucket, so the global throttle never fires. Because
   ``services/shared/rate_limit.py`` builds its slowapi ``Limiter`` with no
   ``default_limits``, this middleware is the *only* global limiter on
   undecorated routes, so nullifying it leaves them unthrottled.
2. **Cross-tenant bucket exhaustion** — send the victim's tenant id and drain
   the shared ``tenant:{id}`` counter the victim's own traffic depends on,
   producing 429s for them.

Both run before any authentication: the middleware is registered in
``server/main.py`` outside every route dependency, and ``TenantContextMiddleware``
is *inner* of it, so ``request.state.tenant_id`` is unset here.
"""

from __future__ import annotations

from typing import Dict, List

import pytest
from fastapi import FastAPI
from shared.tenant_rate_limiting import TenantRateLimitMiddleware, _InMemoryBucket
from starlette.testclient import TestClient

_VICTIM = "11111111-1111-4111-8111-111111111111"
_INTERNAL_SECRET = "s3cr3t-internal-2844"


@pytest.fixture(autouse=True)
def _fresh_bucket(monkeypatch):
    """Isolate from rate-limit state created by other suites."""
    import shared.tenant_rate_limiting as trl

    monkeypatch.setattr(trl, "_bucket", _InMemoryBucket())


class _RecordingBucket:
    """Records every bucket key consumed so tests can assert on selection."""

    def __init__(self, limit_override: int | None = None) -> None:
        self.keys: List[str] = []
        self._inner = _InMemoryBucket()
        self._limit_override = limit_override

    def is_allowed(self, key: str, limit: int, window: int = 60):
        self.keys.append(key)
        return self._inner.is_allowed(key, self._limit_override or limit, window)


def _app(default_rpm: int = 3, tenant_overrides: Dict[str, int] | None = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        TenantRateLimitMiddleware,
        default_rpm=default_rpm,
        tenant_overrides=tenant_overrides or {},
    )

    @app.get("/api/data")
    async def data():
        return {"data": "value"}

    return app


# ---------------------------------------------------------------------------
# Attack 1 — evasion by varying the header
# ---------------------------------------------------------------------------


def test_varying_tenant_header_cannot_mint_a_fresh_budget():
    """A single client must not escape the throttle by rotating the header.

    Pre-fix all 12 requests returned 200 because each forged value selected a
    brand-new ``tenant:{id}`` bucket. The control was fully nullified.
    """
    client = TestClient(_app(default_rpm=3))

    statuses = [
        client.get("/api/data", headers={"X-Tenant-ID": f"forged-{i}"}).status_code
        for i in range(12)
    ]

    assert 429 in statuses, (
        "RATE-LIMIT EVASION: 12 requests from one client all passed a 3/min "
        f"throttle by rotating X-Tenant-ID (statuses={statuses})"
    )
    assert statuses.count(200) <= 3, statuses


def test_rotating_header_shares_one_bucket_with_the_bare_client(monkeypatch):
    """The forged-header request and the header-less request are one client."""
    import shared.tenant_rate_limiting as trl

    rec = _RecordingBucket()
    monkeypatch.setattr(trl, "_bucket", rec)
    client = TestClient(_app(default_rpm=50))

    client.get("/api/data")
    client.get("/api/data", headers={"X-Tenant-ID": "forged-a"})
    client.get("/api/data", headers={"X-Tenant-ID": "forged-b"})

    assert len(set(rec.keys)) == 1, (
        f"forged headers selected distinct buckets: {rec.keys}"
    )
    assert all(k.startswith("ip:") for k in rec.keys), rec.keys


# ---------------------------------------------------------------------------
# Attack 2 — draining a victim tenant's shared bucket
# ---------------------------------------------------------------------------


def test_forged_header_cannot_drain_a_victim_tenants_bucket(monkeypatch):
    """An unauthenticated attacker must not consume the victim's counter.

    Pre-fix: the attacker's 3 spoofed requests exhausted ``tenant:<victim>``,
    and the victim's own next request — from a *different* client — got 429.
    """
    import shared.tenant_rate_limiting as trl

    rec = _RecordingBucket()
    monkeypatch.setattr(trl, "_bucket", rec)
    app = _app(default_rpm=3)

    attacker = TestClient(app)
    for _ in range(5):
        attacker.get("/api/data", headers={"X-Tenant-ID": _VICTIM})

    assert not any(
        key == f"tenant:{_VICTIM}" for key in rec.keys
    ), f"CROSS-TENANT DoS: attacker consumed the victim's bucket: {rec.keys}"


def test_victim_traffic_survives_a_spoofing_flood():
    """End-to-end: victim keeps serving while an attacker floods their id.

    The victim here is the real frontend caller described in the issue —
    ``frontend/src/app/api/billing/checkout/route.ts`` sends ``X-Tenant-ID``
    — arriving from its own address. Pre-fix the attacker's flood had already
    exhausted the shared ``tenant:{id}`` counter, so the victim got a 429 it
    did nothing to earn.
    """
    app = _app(default_rpm=3)

    attacker = TestClient(app, client=("198.51.100.7", 40000))
    for _ in range(6):
        attacker.get("/api/data", headers={"X-Tenant-ID": _VICTIM})

    victim = TestClient(app, client=("203.0.113.9", 50000))
    resp = victim.get("/api/data", headers={"X-Tenant-ID": _VICTIM})

    assert resp.status_code == 200, (
        "CROSS-TENANT DoS: victim tenant was throttled by an attacker's "
        f"spoofed X-Tenant-ID flood ({resp.status_code} {resp.text!r})"
    )


# ---------------------------------------------------------------------------
# Attack 3 — stealing a premium tenant's higher override limit
# ---------------------------------------------------------------------------


def test_forged_header_cannot_claim_a_premium_override():
    """``tenant_overrides`` must not be selectable by an untrusted header."""
    app = _app(default_rpm=2, tenant_overrides={"premium": 50})
    client = TestClient(app)

    statuses = [
        client.get("/api/data", headers={"X-Tenant-ID": "premium"}).status_code
        for _ in range(6)
    ]
    assert 429 in statuses, (
        "LIMIT ESCALATION: an untrusted caller claimed the premium tenant's "
        f"50/min override by naming it in X-Tenant-ID (statuses={statuses})"
    )


# ---------------------------------------------------------------------------
# Response/metric surface must not echo the forged value
# ---------------------------------------------------------------------------


def test_ratelimit_tenant_header_does_not_echo_the_forged_value():
    """Echoing the raw header back confirms it drove bucket selection."""
    client = TestClient(_app(default_rpm=5))
    resp = client.get("/api/data", headers={"X-Tenant-ID": "forged-echo"})

    assert resp.headers.get("X-RateLimit-Tenant") != "forged-echo", (
        "X-RateLimit-Tenant reflected the unauthenticated header, so the "
        "bucket was selected from it"
    )


# ---------------------------------------------------------------------------
# Trusted sources still get a per-tenant bucket
# ---------------------------------------------------------------------------


def test_secret_gated_internal_header_still_buckets_per_tenant(monkeypatch):
    import shared.tenant_rate_limiting as trl

    rec = _RecordingBucket()
    monkeypatch.setattr(trl, "_bucket", rec)
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", _INTERNAL_SECRET)
    client = TestClient(_app(default_rpm=5))

    resp = client.get(
        "/api/data",
        headers={
            "X-RegEngine-Tenant-ID": _VICTIM,
            "X-RegEngine-Internal-Secret": _INTERNAL_SECRET,
        },
    )
    assert resp.status_code == 200, resp.text
    assert rec.keys == [f"tenant:{_VICTIM}"], rec.keys
    assert resp.headers["X-RateLimit-Tenant"] == _VICTIM


def test_authenticated_state_tenant_is_used_when_an_outer_auth_layer_set_it(monkeypatch):
    """If the middleware is ever mounted inner of auth, use the real tenant."""
    import shared.tenant_rate_limiting as trl
    from starlette.middleware.base import BaseHTTPMiddleware

    rec = _RecordingBucket()
    monkeypatch.setattr(trl, "_bucket", rec)

    app = _app(default_rpm=5)

    class _FakeAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.tenant_id = _VICTIM
            return await call_next(request)

    # Added last => outermost => runs before TenantRateLimitMiddleware.
    app.add_middleware(_FakeAuth)

    resp = TestClient(app).get("/api/data", headers={"X-Tenant-ID": "forged"})
    assert resp.status_code == 200, resp.text
    assert rec.keys == [f"tenant:{_VICTIM}"], rec.keys


def test_secret_gated_header_without_secret_is_ignored(monkeypatch):
    import shared.tenant_rate_limiting as trl

    rec = _RecordingBucket()
    monkeypatch.setattr(trl, "_bucket", rec)
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", _INTERNAL_SECRET)
    client = TestClient(_app(default_rpm=5))

    resp = client.get("/api/data", headers={"X-RegEngine-Tenant-ID": _VICTIM})
    assert resp.status_code == 200
    assert rec.keys and all(k.startswith("ip:") for k in rec.keys), rec.keys
