"""
Regression coverage for ``app/sandbox/rate_limiting.py``.

The module provides a sandbox-tier rate limiter with:
* A Redis-backed sorted-set sliding window (primary path).
* An in-memory list-based sliding window (fallback when Redis is down).
* A public ``_check_sandbox_rate_limit`` that raises 429 w/ Retry-After.

The three dimensions we must exercise are:

1. **In-memory sliding window** — retention, eviction, and retry-after
   math for both the at-limit and empty-bucket cases.
2. **Redis lazy init caching** — ``_redis_client`` memoized, ``_redis_failed``
   latched, and both paths short-circuit on subsequent calls.
3. **Redis happy/unhappy paths** — normal add, at-limit with `zrange`,
   at-limit with empty `zrange`, Redis exceptions propagating into the
   in-memory fallback.

Tracks GitHub issue #1342 (ingestion test coverage).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.sandbox import rate_limiting
from app.sandbox.rate_limiting import (
    _SANDBOX_RATE_LIMIT,
    _SANDBOX_WINDOW,
    _check_in_memory,
    _check_redis,
    _check_sandbox_rate_limit,
    _get_redis,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state before each test.

    The module caches Redis client + failure flag and holds the in-memory
    bucket dict. Leaking any of these across tests yields flaky runs.
    """
    rate_limiting._redis_client = None
    rate_limiting._redis_failed = False
    rate_limiting._rate_buckets.clear()
    yield
    rate_limiting._redis_client = None
    rate_limiting._redis_failed = False
    rate_limiting._rate_buckets.clear()


# ===========================================================================
# _check_in_memory
# ===========================================================================

class TestCheckInMemory:
    """Sliding-window accounting entirely in-process."""

    def test_first_request_is_under_limit(self):
        assert _check_in_memory("1.2.3.4", now=1000.0) == 0

    def test_bucket_records_timestamp(self):
        _check_in_memory("1.2.3.4", now=1000.0)
        assert rate_limiting._rate_buckets["1.2.3.4"] == [1000.0]

    def test_requests_below_limit_accepted(self):
        """Below-limit calls all return 0 (not rate-limited)."""
        for i in range(_SANDBOX_RATE_LIMIT - 1):
            assert _check_in_memory("1.2.3.4", now=1000.0 + i) == 0

    def test_request_at_limit_returns_retry_seconds(self):
        """The (LIMIT+1)th request returns the seconds-until-oldest-expires."""
        # Fill the bucket at t=0..LIMIT-1
        for i in range(_SANDBOX_RATE_LIMIT):
            assert _check_in_memory("5.5.5.5", now=float(i)) == 0
        # Now at t=LIMIT, oldest entry is at t=0 → retry_after = WINDOW - LIMIT
        retry = _check_in_memory("5.5.5.5", now=float(_SANDBOX_RATE_LIMIT))
        expected = int(_SANDBOX_WINDOW - (_SANDBOX_RATE_LIMIT - 0))
        assert retry == max(expected, 1)

    def test_retry_after_is_at_least_one_second(self):
        """Boundary: when computed remaining is 0 or negative, return 1."""
        # Fill bucket; the oldest entry is exactly (WINDOW - 1) in the past
        for _ in range(_SANDBOX_RATE_LIMIT):
            rate_limiting._rate_buckets.setdefault("6.6.6.6", []).append(1000.0)
        # At now=1000 + (WINDOW - 1), remaining = WINDOW - (WINDOW - 1) = 1
        retry = _check_in_memory("6.6.6.6", now=1000.0 + (_SANDBOX_WINDOW - 1))
        assert retry >= 1

    def test_retry_after_floors_to_one_when_inner_is_zero(self):
        """The ``or 1`` guard promotes an int-0 remaining to 1."""
        for _ in range(_SANDBOX_RATE_LIMIT):
            rate_limiting._rate_buckets.setdefault("7.7.7.7", []).append(1000.0)
        # Set now just under the window — integer truncation gives 0
        # and the `or 1` branch must kick in.
        retry = _check_in_memory("7.7.7.7", now=1000.0 + _SANDBOX_WINDOW - 0.5)
        assert retry == 1

    def test_expired_entries_evicted_and_room_reopens(self):
        """After enough time passes, old entries drop and new ones accepted."""
        # Fill the bucket
        for i in range(_SANDBOX_RATE_LIMIT):
            _check_in_memory("8.8.8.8", now=float(i))
        # Jump forward past the window — every old entry should be evicted
        assert _check_in_memory("8.8.8.8", now=1000.0 + _SANDBOX_WINDOW) == 0

    def test_distinct_ips_get_independent_buckets(self):
        """Two IPs can each burst up to the limit without interfering."""
        for i in range(_SANDBOX_RATE_LIMIT):
            assert _check_in_memory("10.0.0.1", now=float(i)) == 0
        # Other IP unaffected
        assert _check_in_memory("10.0.0.2", now=float(_SANDBOX_RATE_LIMIT)) == 0

    def test_exactly_expired_entry_is_evicted(self):
        """An entry at exactly (now - WINDOW) has ``now - t == WINDOW`` → NOT strictly <, so evicted."""
        rate_limiting._rate_buckets["9.9.9.9"] = [0.0]
        assert _check_in_memory("9.9.9.9", now=float(_SANDBOX_WINDOW)) == 0
        # Original entry gone, replaced by the new one
        assert rate_limiting._rate_buckets["9.9.9.9"] == [float(_SANDBOX_WINDOW)]


# ===========================================================================
# _get_redis
# ===========================================================================

class TestGetRedis:
    """Lazy Redis-client caching + failure latching."""

    def test_returns_none_once_failed_flag_set(self):
        """After a failure, subsequent calls short-circuit to None."""
        rate_limiting._redis_failed = True
        assert _get_redis() is None

    def test_reuses_cached_client(self):
        """A prior successful client is returned unchanged."""
        sentinel = object()
        rate_limiting._redis_client = sentinel
        assert _get_redis() is sentinel

    def test_successful_init_caches_client(self, monkeypatch):
        """Ping succeeds → client memoized and returned."""
        fake_client = MagicMock()
        fake_client.ping.return_value = True

        class FakeRedisModule:
            @staticmethod
            def from_url(url, **kwargs):
                fake_client._url = url
                fake_client._kwargs = kwargs
                return fake_client

        def fake_get_settings():
            return SimpleNamespace(redis_url="redis://test-host:6379/0")

        monkeypatch.setattr(
            "app.config.get_settings", fake_get_settings, raising=False
        )
        # ``import redis as redis_lib`` happens inside the function;
        # monkeypatch sys.modules so that import resolves to our fake.
        monkeypatch.setitem(
            __import__("sys").modules, "redis", FakeRedisModule
        )

        result = _get_redis()
        assert result is fake_client
        # Cached on second call
        assert _get_redis() is fake_client
        # Ping called exactly once (not on the cached second call)
        assert fake_client.ping.call_count == 1
        # URL + timeouts wired up
        assert fake_client._url == "redis://test-host:6379/0"
        assert fake_client._kwargs["decode_responses"] is True
        assert fake_client._kwargs["socket_connect_timeout"] == 2
        assert fake_client._kwargs["socket_timeout"] == 2

    def test_ping_failure_latches_failed_flag(self, monkeypatch):
        """If ping raises, the failed flag prevents future attempts."""
        fake_client = MagicMock()
        fake_client.ping.side_effect = ConnectionError("nope")

        class FakeRedisModule:
            @staticmethod
            def from_url(url, **kwargs):
                return fake_client

        def fake_get_settings():
            return SimpleNamespace(redis_url="redis://broken:6379/0")

        monkeypatch.setattr(
            "app.config.get_settings", fake_get_settings, raising=False
        )
        monkeypatch.setitem(
            __import__("sys").modules, "redis", FakeRedisModule
        )

        assert _get_redis() is None
        assert rate_limiting._redis_failed is True
        # Second call short-circuits without touching fake_client
        fake_client.ping.reset_mock()
        assert _get_redis() is None
        assert fake_client.ping.call_count == 0

    def test_import_failure_latches_failed_flag(self, monkeypatch):
        """If the redis module can't be imported, fail gracefully."""
        def fake_get_settings():
            return SimpleNamespace(redis_url="redis://x/0")

        monkeypatch.setattr(
            "app.config.get_settings", fake_get_settings, raising=False
        )
        # Force import failure by dropping ``redis`` from sys.modules
        # and replacing with a module that raises on attribute access.
        import sys

        class _ExplosiveModule:
            def __getattr__(self, name):
                raise ImportError(f"redis has no {name}")

        monkeypatch.setitem(sys.modules, "redis", _ExplosiveModule())
        assert _get_redis() is None
        assert rate_limiting._redis_failed is True


# ===========================================================================
# _check_redis
# ===========================================================================

class _FakePipeline:
    """Stub pipeline recording calls for assertions."""

    def __init__(self):
        self.calls = []

    def zremrangebyscore(self, key, start, end):
        self.calls.append(("zremrangebyscore", key, start, end))

    def zcard(self, key):
        self.calls.append(("zcard", key))

    def execute(self):
        self.calls.append(("execute",))


class _FakeRedis:
    """Redis surrogate exposing only the subset of methods the code uses."""

    def __init__(self, zcard_value=0, zrange_value=None):
        self._zcard = zcard_value
        self._zrange = zrange_value or []
        self.pipeline_calls = []
        self.zadd_calls = []
        self.expire_calls = []

    def pipeline(self):
        pipe = _FakePipeline()
        self.pipeline_calls.append(pipe)
        return pipe

    def zcard(self, key):
        return self._zcard

    def zrange(self, key, start, stop, withscores=False):
        return self._zrange

    def zadd(self, key, mapping):
        self.zadd_calls.append((key, mapping))

    def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))


class TestCheckRedis:
    """Sorted-set sliding-window path."""

    def test_falls_back_to_in_memory_when_redis_missing(self, monkeypatch):
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: None)
        # First call should behave like _check_in_memory: 0 below limit
        assert _check_redis("1.1.1.1", now=1000.0) == 0
        # In-memory bucket populated as evidence
        assert 1000.0 in rate_limiting._rate_buckets["1.1.1.1"]

    def test_under_limit_adds_entry_and_returns_zero(self, monkeypatch):
        fake = _FakeRedis(zcard_value=0)
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: fake)
        assert _check_redis("2.2.2.2", now=1000.0) == 0
        # We added one entry with the current timestamp
        assert len(fake.zadd_calls) == 1
        key, mapping = fake.zadd_calls[0]
        assert key == "sandbox:rate:2.2.2.2"
        assert "1000.0" in mapping
        # Expiry set to window + 1
        assert fake.expire_calls == [("sandbox:rate:2.2.2.2", _SANDBOX_WINDOW + 1)]

    def test_pipeline_prunes_stale_entries_before_count(self, monkeypatch):
        fake = _FakeRedis(zcard_value=0)
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: fake)
        _check_redis("3.3.3.3", now=1000.0)
        pipe = fake.pipeline_calls[0]
        op_names = [c[0] for c in pipe.calls]
        assert op_names == ["zremrangebyscore", "zcard", "execute"]
        # Verify the prune window boundary is now - WINDOW
        assert pipe.calls[0] == (
            "zremrangebyscore", "sandbox:rate:3.3.3.3", 0, 1000.0 - _SANDBOX_WINDOW,
        )

    def test_at_limit_with_oldest_returns_remaining_seconds(self, monkeypatch):
        """When ``zrange`` yields an oldest entry, math is based on that timestamp."""
        fake = _FakeRedis(
            zcard_value=_SANDBOX_RATE_LIMIT,
            zrange_value=[("0", 0.0)],  # oldest at t=0
        )
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: fake)
        retry = _check_redis("4.4.4.4", now=10.0)
        # remaining = WINDOW - (10 - 0) = WINDOW - 10
        assert retry == max(_SANDBOX_WINDOW - 10, 1)
        # Did NOT add a new entry when rate-limited
        assert fake.zadd_calls == []

    def test_at_limit_with_no_oldest_returns_one(self, monkeypatch):
        """Empty zrange at limit — use floor of 1."""
        fake = _FakeRedis(
            zcard_value=_SANDBOX_RATE_LIMIT,
            zrange_value=[],
        )
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: fake)
        assert _check_redis("5.5.5.5", now=100.0) == 1
        assert fake.zadd_calls == []

    def test_at_limit_with_near_expiry_floors_to_one(self, monkeypatch):
        """Computed ``remaining`` of 0 must be promoted to 1 via ``max(.., 1)``."""
        fake = _FakeRedis(
            zcard_value=_SANDBOX_RATE_LIMIT,
            zrange_value=[("0", 1000.0)],
        )
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: fake)
        # now = oldest + WINDOW → remaining = 0 → max(0, 1) = 1
        assert _check_redis("6.6.6.6", now=1000.0 + _SANDBOX_WINDOW) == 1

    def test_redis_exception_falls_back_to_in_memory(self, monkeypatch):
        """Any unhandled Redis error → fall back, don't 500."""
        fake = MagicMock()
        fake.pipeline.side_effect = ConnectionError("redis down mid-request")
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: fake)
        # Should still return 0 (first in-memory call)
        assert _check_redis("7.7.7.7", now=1000.0) == 0
        # Evidence: the in-memory bucket was used
        assert 1000.0 in rate_limiting._rate_buckets["7.7.7.7"]

    def test_redis_zcard_exception_falls_back(self, monkeypatch):
        """Exception after pipeline but before zadd still falls back."""
        fake = MagicMock()
        fake.pipeline.return_value = _FakePipeline()
        fake.zcard.side_effect = RuntimeError("boom")
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: fake)
        assert _check_redis("8.8.8.8", now=2000.0) == 0
        assert 2000.0 in rate_limiting._rate_buckets["8.8.8.8"]


# ===========================================================================
# _check_sandbox_rate_limit — public entry
# ===========================================================================

class TestCheckSandboxRateLimit:
    """Public API: under-limit is silent, at-limit raises 429."""

    def test_no_exception_when_under_limit(self, monkeypatch):
        monkeypatch.setattr(rate_limiting, "_check_redis", lambda ip, now: 0)
        _check_sandbox_rate_limit("1.2.3.4")  # should not raise

    def test_raises_429_when_over_limit(self, monkeypatch):
        monkeypatch.setattr(rate_limiting, "_check_redis", lambda ip, now: 42)
        with pytest.raises(HTTPException) as excinfo:
            _check_sandbox_rate_limit("1.2.3.4")
        assert excinfo.value.status_code == 429
        assert "rate limit exceeded" in excinfo.value.detail.lower()
        assert excinfo.value.headers == {"Retry-After": "42"}

    def test_retry_after_header_value_is_stringified_int(self, monkeypatch):
        """Retry-After must be a string, not an int (HTTP spec)."""
        monkeypatch.setattr(rate_limiting, "_check_redis", lambda ip, now: 7)
        with pytest.raises(HTTPException) as excinfo:
            _check_sandbox_rate_limit("9.9.9.9")
        assert isinstance(excinfo.value.headers["Retry-After"], str)
        assert excinfo.value.headers["Retry-After"] == "7"

    def test_retry_after_passthrough_from_in_memory_fallback(self, monkeypatch):
        """End-to-end: in-memory path at-limit propagates into 429."""
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: None)
        # Fill the in-memory bucket right at the limit
        rate_limiting._rate_buckets["2.2.2.2"] = [1000.0] * _SANDBOX_RATE_LIMIT

        # Freeze ``datetime.now`` so ``_check_sandbox_rate_limit`` sees a
        # timestamp that still places the oldest entry inside the window.
        class _FrozenDT:
            @staticmethod
            def now(tz=None):
                return _RealDT(2000, 1, 1, 0, 0, 5, tzinfo=tz)

        from datetime import datetime as _RealDT, timezone as _RealTZ
        class _FrozenClock:
            @staticmethod
            def now(tz=None):
                # 1 second after bucket fill baseline (1000.0)
                # In UTC epoch terms we just need .timestamp() = 1001.0
                return _Frozen(1001.0)

        class _Frozen:
            def __init__(self, ts):
                self._ts = ts
            def timestamp(self):
                return self._ts

        monkeypatch.setattr(rate_limiting, "datetime", _FrozenClock)
        with pytest.raises(HTTPException) as excinfo:
            _check_sandbox_rate_limit("2.2.2.2")
        assert excinfo.value.status_code == 429
        # Retry-After must be a positive integer-as-string
        assert int(excinfo.value.headers["Retry-After"]) >= 1
