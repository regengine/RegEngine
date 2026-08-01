"""#2699: RATE_LIMIT_FAIL_MODE / IDEMPOTENCY_FAIL_MODE — degrade-but-loud
vs fail-closed behavior when the shared Redis backend is uncertain.

See docs/runbooks/RATE_LIMIT_DEGRADATION.md (the decision record).
"""

from unittest.mock import MagicMock

import pytest
import redis as redis_lib
import shared.tenant_rate_limiting as trl
from fastapi import FastAPI
from shared.tenant_rate_limiting import (
    RateLimitBackendUnavailable,
    TenantRateLimitMiddleware,
    _InMemoryBucket,
    _RedisBucket,
    rate_limit_fail_mode,
    rate_limiter_degraded,
)
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_FAIL_MODE", raising=False)
    monkeypatch.delenv("RATE_LIMIT_FALLBACK_DIVISOR", raising=False)
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)


class _FailingRedis:
    def pipeline(self):
        raise redis_lib.RedisError("redis down")


class _OkPipeline:
    def __init__(self):
        self._ops = []

    def zremrangebyscore(self, *a):
        self._ops.append("zrem")

    def zcard(self, *a):
        self._ops.append("zcard")

    def zadd(self, *a):
        self._ops.append("zadd")

    def expire(self, *a):
        self._ops.append("expire")

    def execute(self):
        ops, self._ops = self._ops, []
        return [0 if op != "zcard" else 0 for op in ops]


class _OkRedis:
    def pipeline(self):
        return _OkPipeline()


def _bucket_with(redis_obj) -> _RedisBucket:
    bucket = _RedisBucket.__new__(_RedisBucket)
    bucket.redis = redis_obj
    bucket._fallback_bucket = _InMemoryBucket()
    bucket.degraded = False
    return bucket


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------


class TestFailModeResolution:
    def test_default_is_degrade(self):
        assert rate_limit_fail_mode() == "degrade"

    def test_closed_honored(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
        assert rate_limit_fail_mode() == "closed"

    def test_invalid_value_fails_closed(self, monkeypatch):
        """A present-but-typo'd mode must not silently weaken the control."""
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "degarde")
        assert rate_limit_fail_mode() == "closed"


# ---------------------------------------------------------------------------
# _RedisBucket degrade mode
# ---------------------------------------------------------------------------


class TestDegradeMode:
    def test_fallback_activates_with_tightened_budget(self, monkeypatch):
        """Redis error → per-process fallback at limit // divisor."""
        monkeypatch.setenv("RATE_LIMIT_FALLBACK_DIVISOR", "2")
        bucket = _bucket_with(_FailingRedis())

        results = [bucket.is_allowed("k", limit=4)[0] for _ in range(3)]
        # Fallback budget = 4 // 2 = 2: first two allowed, third denied.
        assert results == [True, True, False]
        assert bucket.degraded is True

    def test_fallback_budget_never_below_one(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_FALLBACK_DIVISOR", "50")
        bucket = _bucket_with(_FailingRedis())
        allowed, _ = bucket.is_allowed("k", limit=4)
        assert allowed is True  # floor of 1, not 0

    def test_warning_and_metric_once_per_activation(self, monkeypatch):
        fake_logger = MagicMock()
        monkeypatch.setattr(trl, "logger", fake_logger)
        bucket = _bucket_with(_FailingRedis())
        metric = trl.rate_limit_fallback_activations_total.labels(surface="tenant")
        before = metric._value.get()

        bucket.is_allowed("k", limit=10)
        bucket.is_allowed("k", limit=10)
        bucket.is_allowed("k", limit=10)

        warn_calls = [
            c for c in fake_logger.warning.call_args_list if c.args and c.args[0] == "rate_limit_backend_unavailable"
        ]
        assert len(warn_calls) == 1  # per ACTIVATION, not per request
        assert metric._value.get() == before + 1

    def test_recovery_resets_activation(self, monkeypatch):
        fake_logger = MagicMock()
        monkeypatch.setattr(trl, "logger", fake_logger)
        bucket = _bucket_with(_FailingRedis())

        bucket.is_allowed("k", limit=10)
        assert bucket.degraded is True

        bucket.redis = _OkRedis()
        bucket.is_allowed("k", limit=10)
        assert bucket.degraded is False
        assert any(c.args and c.args[0] == "rate_limit_backend_recovered" for c in fake_logger.info.call_args_list)

        # A NEW outage is a new activation → second warning.
        bucket.redis = _FailingRedis()
        bucket.is_allowed("k", limit=10)
        warn_calls = [
            c for c in fake_logger.warning.call_args_list if c.args and c.args[0] == "rate_limit_backend_unavailable"
        ]
        assert len(warn_calls) == 2


# ---------------------------------------------------------------------------
# _RedisBucket closed mode
# ---------------------------------------------------------------------------


class TestClosedMode:
    def test_redis_error_raises_503_with_retry_after(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
        bucket = _bucket_with(_FailingRedis())

        with pytest.raises(RateLimitBackendUnavailable) as exc_info:
            bucket.is_allowed("k", limit=10)
        assert exc_info.value.status_code == 503
        assert exc_info.value.headers["Retry-After"] == "30"

    def test_healthy_redis_unaffected_in_closed_mode(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
        bucket = _bucket_with(_OkRedis())
        allowed, _ = bucket.is_allowed("k", limit=10)
        assert allowed is True


# ---------------------------------------------------------------------------
# Middleware integration
# ---------------------------------------------------------------------------


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

    @app.get("/data")
    async def data():
        return {"ok": True}

    return app


class TestMiddleware:
    def test_closed_mode_returns_503(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
        monkeypatch.setattr(trl, "_bucket", _bucket_with(_FailingRedis()))
        client = TestClient(_app())

        resp = client.get("/data", headers={"X-Tenant-ID": "t1"})
        assert resp.status_code == 503
        assert resp.headers["Retry-After"] == "30"
        assert resp.json()["error"] == "rate_limit_backend_unavailable"

    def test_degrade_mode_serves_with_degraded_header(self, monkeypatch):
        monkeypatch.setattr(trl, "_bucket", _bucket_with(_FailingRedis()))
        client = TestClient(_app())

        resp = client.get("/data", headers={"X-Tenant-ID": "t1"})
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Degraded") == "1"
        assert rate_limiter_degraded() is True

    def test_healthy_backend_has_no_degraded_header(self, monkeypatch):
        monkeypatch.setattr(trl, "_bucket", _InMemoryBucket())
        client = TestClient(_app())

        resp = client.get("/data", headers={"X-Tenant-ID": "t1"})
        assert resp.status_code == 200
        assert "X-RateLimit-Degraded" not in resp.headers


# ---------------------------------------------------------------------------
# BruteForceLimiter
# ---------------------------------------------------------------------------


class _RaisingRedis:
    def get(self, name):
        raise ConnectionError("redis down")

    def incr(self, name):
        raise ConnectionError("redis down")

    def expire(self, name, time):
        raise ConnectionError("redis down")

    def delete(self, name):
        raise ConnectionError("redis down")


class TestBruteForceLimiter:
    def _limiter(self):
        from shared.rate_limit import BruteForceLimiter

        return BruteForceLimiter(
            namespace="test2699",
            max_failures=3,
            window_seconds=60,
            redis_client=_RaisingRedis(),
        )

    def test_closed_mode_treats_uncertainty_as_limited(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
        limiter = self._limiter()
        assert limiter.is_limited("user@example.com") is True

    def test_degrade_mode_falls_back_to_memory_with_warning(self, monkeypatch):
        import shared.rate_limit as rl_mod

        fake_logger = MagicMock()
        monkeypatch.setattr(rl_mod, "logger", fake_logger)
        limiter = self._limiter()

        assert limiter.is_limited("user@example.com") is False  # memory empty
        limiter.is_limited("user@example.com")
        warn_calls = [
            c
            for c in fake_logger.warning.call_args_list
            if c.args and c.args[0] == "brute_force_limiter_backend_unavailable"
        ]
        assert len(warn_calls) == 1  # per activation

    def test_record_failure_still_counts_in_memory(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
        limiter = self._limiter()
        assert limiter.record_failure("s") == 1
        assert limiter.record_failure("s") == 2

    def test_memory_lockout_still_works_in_degrade(self):
        limiter = self._limiter()
        for _ in range(3):
            limiter.record_failure("s2")
        assert limiter.is_limited("s2") is True


# ---------------------------------------------------------------------------
# Circuit-breaker store: explicit redis backend fails loudly
# ---------------------------------------------------------------------------


class TestCircuitStoreExplicitBackend:
    def test_explicit_redis_init_failure_raises(self, monkeypatch):
        import shared.circuit_breaker_store as cbs

        cbs.reset_store()
        monkeypatch.setenv("CIRCUIT_BREAKER_BACKEND", "redis")
        monkeypatch.delenv("CIRCUIT_BREAKER_ALLOW_MEMORY_FALLBACK", raising=False)
        monkeypatch.setattr(cbs, "RedisCircuitStore", MagicMock(side_effect=ConnectionError("no redis")))

        with pytest.raises(RuntimeError, match="explicitly configured"):
            cbs.get_store()
        cbs.reset_store()

    def test_escape_hatch_allows_memory_fallback(self, monkeypatch):
        import shared.circuit_breaker_store as cbs

        cbs.reset_store()
        monkeypatch.setenv("CIRCUIT_BREAKER_BACKEND", "redis")
        monkeypatch.setenv("CIRCUIT_BREAKER_ALLOW_MEMORY_FALLBACK", "1")
        monkeypatch.setattr(cbs, "RedisCircuitStore", MagicMock(side_effect=ConnectionError("no redis")))

        store = cbs.get_store()
        assert isinstance(store, cbs.MemoryCircuitStore)
        cbs.reset_store()

    def test_default_memory_backend_unchanged(self, monkeypatch):
        import shared.circuit_breaker_store as cbs

        cbs.reset_store()
        monkeypatch.delenv("CIRCUIT_BREAKER_BACKEND", raising=False)
        store = cbs.get_store()
        assert isinstance(store, cbs.MemoryCircuitStore)
        cbs.reset_store()


# ---------------------------------------------------------------------------
# Idempotency cache fail mode
# ---------------------------------------------------------------------------


class TestIdempotencyFailMode:
    def _app(self, monkeypatch, mode: str | None):
        from shared.idempotency import IdempotencyMiddleware

        if mode is None:
            monkeypatch.delenv("IDEMPOTENCY_FAIL_MODE", raising=False)
        else:
            monkeypatch.setenv("IDEMPOTENCY_FAIL_MODE", mode)

        app = FastAPI()
        app.add_middleware(IdempotencyMiddleware)

        @app.post("/submit")
        async def submit():
            return {"ok": True}

        client_stub = MagicMock()

        async def _raising_get(key):
            raise ConnectionError("redis down")

        client_stub.get = _raising_get

        async def _get_client(self):
            return client_stub

        monkeypatch.setattr(IdempotencyMiddleware, "_get_client", _get_client)
        return app

    def _headers(self):
        return {
            "Idempotency-Key": "11111111-1111-1111-1111-111111111111",
            "X-Tenant-ID": "tenant-1",
        }

    def test_degrade_reexecutes_request(self, monkeypatch):
        client = TestClient(self._app(monkeypatch, None))
        resp = client.post("/submit", headers=self._headers())
        assert resp.status_code == 200

    def test_closed_returns_503(self, monkeypatch):
        client = TestClient(self._app(monkeypatch, "closed"))
        resp = client.post("/submit", headers=self._headers())
        assert resp.status_code == 503
        assert resp.headers["Retry-After"] == "30"
        assert resp.json()["error"] == "idempotency_backend_unavailable"


# ---------------------------------------------------------------------------
# Entitlement gate: contract untouched (regression tripwire)
# ---------------------------------------------------------------------------


class TestEntitlementGateUntouched:
    def test_subscription_gate_does_not_read_the_knob(self):
        """The 402/503 entitlement contract is fail-closed regardless of
        RATE_LIMIT_FAIL_MODE; the gate must never consult it. Behavior
        regression is covered by the existing subscription-gate suites
        (services/ingestion/tests/test_subscription_gate*.py)."""
        import inspect
        import sys
        from pathlib import Path

        ingestion_dir = Path(__file__).resolve().parent.parent.parent / "services" / "ingestion"
        if str(ingestion_dir) not in sys.path:
            sys.path.insert(0, str(ingestion_dir))
        from app import subscription_gate

        source = inspect.getsource(subscription_gate)
        assert "RATE_LIMIT_FAIL_MODE" not in source
        assert "IDEMPOTENCY_FAIL_MODE" not in source
