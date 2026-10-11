"""QA deep pass: ``shared.rate_limit`` happy path and helpers.

``tests/unit/test_rate_limit_fail_mode_2699.py`` covers Redis failure
modes (degrade vs closed) for ``BruteForceLimiter``. This file covers
the paths taken when the backend is healthy, plus the slowapi helpers:

1. ``record_failure`` / ``is_limited`` / ``reset`` against a working
   backend (counting, TTL arming, threshold, reset).
2. Corrupt and string counter values.
3. In-memory fallback counting, window expiry, and lockout.
4. ``is_redis_backed``, ``requires_shared_backend``, properties.
5. ``slowapi_storage_backend`` and ``add_rate_limiting`` wiring.

Pure Python, no network. Redis is faked in process.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from shared.rate_limit import BruteForceLimiter, add_rate_limiting, slowapi_storage_backend


class _FakeRedis:
    """Minimal healthy Redis stand-in with observable TTL arming."""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expiries: dict[str, int] = {}
        self.deleted: list[str] = []

    def incr(self, name: str) -> int:
        self.counts[name] = self.counts.get(name, 0) + 1
        return self.counts[name]

    def expire(self, name: str, seconds: int) -> bool:
        self.expiries[name] = seconds
        return True

    def get(self, name: str):
        if name not in self.counts:
            return None
        return str(self.counts[name]).encode()

    def delete(self, name: str) -> int:
        self.deleted.append(name)
        return 1 if self.counts.pop(name, None) is not None else 0


def _limiter(redis_client=None, **overrides):
    kwargs = {"namespace": "qa4", "max_failures": 3, "window_seconds": 60}
    kwargs.update(overrides)
    limiter = BruteForceLimiter(redis_client=redis_client, **kwargs)
    if redis_client is None:
        limiter._redis = None
    return limiter


@pytest.fixture(autouse=True)
def _no_redis_env(monkeypatch):
    monkeypatch.delenv("REGENGINE_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("RATE_LIMIT_FAIL_MODE", raising=False)


# ---------------------------------------------------------------------------
# 1. Healthy-backend counting
# ---------------------------------------------------------------------------


class TestHealthyBackend:
    def test_record_increments_and_arms_ttl_once(self):
        fake = _FakeRedis()
        limiter = BruteForceLimiter(namespace="qa4", max_failures=3, window_seconds=60,
                                    redis_client=fake)
        assert limiter.record_failure("user@example.com") == 1
        assert limiter.record_failure("user@example.com") == 2
        assert fake.expiries == {"qa4:user@example.com": 60}

    def test_threshold_trips_at_max(self):
        fake = _FakeRedis()
        limiter = BruteForceLimiter(namespace="qa4", max_failures=3, window_seconds=60,
                                    redis_client=fake)
        assert limiter.is_limited("s") is False
        for _ in range(3):
            limiter.record_failure("s")
        assert limiter.is_limited("s") is True

    def test_subjects_are_isolated(self):
        fake = _FakeRedis()
        limiter = BruteForceLimiter(namespace="qa4", max_failures=1, window_seconds=60,
                                    redis_client=fake)
        limiter.record_failure("a")
        assert limiter.is_limited("a") is True
        assert limiter.is_limited("b") is False

    def test_namespaces_are_isolated(self):
        fake = _FakeRedis()
        one = BruteForceLimiter(namespace="n1", max_failures=1, window_seconds=60,
                                redis_client=fake)
        two = BruteForceLimiter(namespace="n2", max_failures=1, window_seconds=60,
                                redis_client=fake)
        one.record_failure("s")
        assert one.is_limited("s") is True
        assert two.is_limited("s") is False

    def test_reset_clears_redis_and_memory(self):
        fake = _FakeRedis()
        limiter = BruteForceLimiter(namespace="qa4", max_failures=1, window_seconds=60,
                                    redis_client=fake)
        limiter.record_failure("s")
        assert limiter.is_limited("s") is True
        limiter.reset("s")
        assert fake.deleted == ["qa4:s"]
        assert limiter.is_limited("s") is False

    def test_corrupt_counter_is_not_limited(self):
        fake = _FakeRedis()
        fake.counts["qa4:s"] = "not-a-number"  # type: ignore[assignment]
        limiter = BruteForceLimiter(namespace="qa4", max_failures=1, window_seconds=60,
                                    redis_client=fake)
        assert limiter.is_limited("s") is False

    def test_plain_string_counter_value_parses(self):
        class _StrRedis(_FakeRedis):
            def get(self, name):
                return "2"

        limiter = BruteForceLimiter(namespace="qa4", max_failures=2, window_seconds=60,
                                    redis_client=_StrRedis())
        assert limiter.is_limited("s") is True


# ---------------------------------------------------------------------------
# 2. In-memory fallback
# ---------------------------------------------------------------------------


class TestInMemoryFallback:
    def test_counts_failures_to_lockout(self):
        limiter = _limiter()
        assert limiter.is_limited("s") is False
        assert limiter.record_failure("s") == 1
        assert limiter.record_failure("s") == 2
        assert limiter.record_failure("s") == 3
        assert limiter.is_limited("s") is True

    def test_window_expiry_releases_lockout(self):
        limiter = _limiter(window_seconds=60)
        for _ in range(3):
            limiter.record_failure("s")
        assert limiter.is_limited("s") is True
        import time as _time

        for stamp in limiter._mem_failures["s"]:
            assert _time.time() - stamp < 60
        limiter._mem_failures["s"] = [_time.time() - 61] * 3
        assert limiter.is_limited("s") is False

    def test_reset_clears_memory_counter(self):
        limiter = _limiter()
        limiter.record_failure("s")
        limiter.reset("s")
        assert limiter.is_limited("s") is False

    def test_reset_unknown_subject_is_safe(self):
        limiter = _limiter()
        limiter.reset("never-seen")

    def test_unbounded_growth_is_capped(self):
        limiter = _limiter(max_failures=2)
        for _ in range(20):
            limiter.record_failure("s")
        assert len(limiter._mem_failures["s"]) <= 8


# ---------------------------------------------------------------------------
# 3. Backend reporting and properties
# ---------------------------------------------------------------------------


class TestReporting:
    def test_is_redis_backed_reflects_client(self):
        assert _limiter().is_redis_backed is False
        assert BruteForceLimiter(namespace="q", max_failures=1, window_seconds=1,
                                 redis_client=_FakeRedis()).is_redis_backed is True

    def test_properties_expose_config(self):
        limiter = _limiter(max_failures=5, window_seconds=120)
        assert limiter.max_failures == 5
        assert limiter.window_seconds == 120

    def test_requires_shared_backend_defaults_false(self):
        assert _limiter().requires_shared_backend is False

    def test_try_connect_without_url_returns_none(self):
        assert BruteForceLimiter._try_connect_redis() is None


# ---------------------------------------------------------------------------
# 4. slowapi helpers
# ---------------------------------------------------------------------------


class TestSlowapiHelpers:
    def test_storage_backend_reports_memory_by_default(self):
        import shared.rate_limit as rl_mod

        assert rl_mod._SLOWAPI_STORAGE_URI == "memory://"
        assert slowapi_storage_backend() == "memory"

    def test_add_rate_limiting_installs_limiter(self):
        from shared.rate_limit import limiter as shared_limiter

        app = FastAPI()
        add_rate_limiting(app)
        assert app.state.limiter is shared_limiter
