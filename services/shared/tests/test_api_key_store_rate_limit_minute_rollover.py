"""Regression test for #1887: reset_at must not overflow at :59.

The previous implementation of ``check_rate_limit`` computed the next
rate-limit bucket boundary as ``now.replace(minute=now.minute + 1)``.
When ``now.minute == 59``, this raises ``ValueError: minute must be in
0..59`` — Python's built-in datetime constructor error. The global
``ValueError`` handler then returned HTTP 400 with that exact message
for every authenticated ingest call during the 59th minute of any hour.

The fix uses ``timedelta(minutes=1)`` arithmetic, which correctly rolls
the minute, hour, and day boundaries without raising.

This test pins the correct behavior at :59, at every 10-minute
boundary (sanity), and at the new year midnight boundary (roll over
year, month, day, hour, minute simultaneously).

The second half of the file pins the time-bucketed counter (developer portal
Phase 5). The old counter re-applied EXPIRE on every request, so a client that
never paused for a full window was never reset: a steady client below its
limit eventually crossed it and stayed blocked. Those tests drive the limiter
with a TTL-aware fake Redis and an injectable clock so windows roll by advancing
time rather than sleeping.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from shared.api_key_store import DatabaseAPIKeyStore


def _make_store(monkeypatch):
    """Build a DatabaseAPIKeyStore without opening real DB or Redis."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:6543/d")
    with patch("shared.api_key_store.create_async_engine") as _e, patch("shared.api_key_store.sessionmaker") as _s:
        _e.return_value = object()
        _s.return_value = lambda: None
        return DatabaseAPIKeyStore()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "now_str,expected_reset_str",
    [
        # :59 used to ValueError — this is the bug the test pins.
        ("2026-04-22T20:59:30+00:00", "2026-04-22T21:00:00+00:00"),
        # 23:59 rolls the day.
        ("2026-04-22T23:59:15+00:00", "2026-04-23T00:00:00+00:00"),
        # Last day of month rolls the month.
        ("2026-04-30T23:59:59+00:00", "2026-05-01T00:00:00+00:00"),
        # New Year's Eve rolls year/month/day/hour/minute in one shot.
        ("2026-12-31T23:59:45+00:00", "2027-01-01T00:00:00+00:00"),
        # Ordinary minute is unaffected.
        ("2026-04-22T14:27:11+00:00", "2026-04-22T14:28:00+00:00"),
        # :00 — next bucket is :01.
        ("2026-04-22T14:00:03+00:00", "2026-04-22T14:01:00+00:00"),
    ],
)
async def test_reset_at_rolls_over_correctly(monkeypatch, now_str, expected_reset_str):
    store = _make_store(monkeypatch)

    class _FakePipeline:
        def incr(self, key):
            pass

        def expire(self, key, sec):
            pass

        async def execute(self):
            # Simulated counter: return below limit so allowed=True
            return [1, True]

    class _FakeRedis:
        def pipeline(self):
            return _FakePipeline()

    store._redis = _FakeRedis()

    fixed_now = datetime.fromisoformat(now_str)
    expected_reset = datetime.fromisoformat(expected_reset_str)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    with patch("shared.api_key_store.datetime", _FixedDatetime):
        info = await store.check_rate_limit(key_id="test", limit=60)

    assert info.reset_at == expected_reset, (
        f"at {now_str}, reset_at should be {expected_reset_str}, got {info.reset_at}"
    )
    # The old code raised ValueError at :59 — getting here at all proves
    # the rollover is now safe.


@pytest.mark.asyncio
async def test_reset_at_is_tz_aware(monkeypatch):
    """reset_at must carry tzinfo so JSON serialization is deterministic."""
    store = _make_store(monkeypatch)

    class _FakePipeline:
        def incr(self, key):
            pass

        def expire(self, key, sec):
            pass

        async def execute(self):
            return [1, True]

    class _FakeRedis:
        def pipeline(self):
            return _FakePipeline()

    store._redis = _FakeRedis()

    info = await store.check_rate_limit(key_id="test", limit=60)
    assert info.reset_at.tzinfo is not None
    assert info.reset_at.tzinfo.utcoffset(info.reset_at) == timezone.utc.utcoffset(info.reset_at)


# ---------------------------------------------------------------------------
# Time-bucketed counter: TTL-aware fake Redis + injectable clock
# ---------------------------------------------------------------------------

# Aligned to every window used below (10, 30, 60, 120, 3600 seconds), so a test
# that advances N seconds from here lands N seconds into a bucket.
_T0 = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc).timestamp()


class _FakeClock:
    """Wall clock shared by the patched ``datetime`` and the fake Redis.

    ``epoch`` is true time and is what Redis expires keys against. ``skew`` is
    the calling worker's clock error: the limiter sees ``epoch + skew``. Tests
    set it before a worker's calls to model workers whose clocks disagree.
    """

    def __init__(self, epoch: float) -> None:
        self.epoch = epoch
        self.skew = 0.0

    def advance(self, seconds: float) -> None:
        self.epoch += seconds

    def datetime_class(self) -> type:
        clock = self

        class _ClockDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                value = datetime.fromtimestamp(clock.epoch + clock.skew, tz=timezone.utc)
                return value if tz is None else value.astimezone(tz)

        return _ClockDatetime


class _TTLPipeline:
    def __init__(self, redis: "_TTLRedis") -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def incr(self, key):
        self._ops.append(("incr", key))

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))

    async def execute(self):
        return self._redis.run(self._ops)


class _TTLRedis:
    """INCR/EXPIRE pipelines with real TTL semantics, driven by the fake clock.

    Mirrors the Redis behaviour the limiter depends on: INCR creates a key with
    no TTL and keeps an existing TTL; EXPIRE sets a TTL on an existing key; EXPIRE
    with a non-positive value deletes the key; expired keys vanish.
    """

    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock
        self._values: dict[str, int] = {}
        self._expires_at: dict[str, float] = {}
        self.round_trips = 0
        self.executed: list[tuple] = []

    def _purge(self) -> None:
        for key, expires_at in list(self._expires_at.items()):
            if expires_at <= self._clock.epoch:
                self._values.pop(key, None)
                del self._expires_at[key]

    def pipeline(self) -> _TTLPipeline:
        return _TTLPipeline(self)

    def run(self, ops: list[tuple]) -> list:
        self.round_trips += 1
        self._purge()
        results: list = []
        for op in ops:
            self.executed.append(op)
            if op[0] == "incr":
                self._values[op[1]] = self._values.get(op[1], 0) + 1
                results.append(self._values[op[1]])
            elif op[0] == "expire":
                _, key, seconds = op
                if key not in self._values:
                    results.append(False)
                elif seconds <= 0:
                    del self._values[key]
                    self._expires_at.pop(key, None)
                    results.append(True)
                else:
                    self._expires_at[key] = self._clock.epoch + seconds
                    results.append(True)
            else:  # pragma: no cover - the limiter only issues INCR and EXPIRE
                raise AssertionError(f"unexpected command {op!r}")
        return results

    def seed(self, key: str, value: int, ttl: float | None = None) -> None:
        self._values[key] = value
        if ttl is not None:
            self._expires_at[key] = self._clock.epoch + ttl

    def live_keys(self) -> list[str]:
        self._purge()
        return sorted(self._values)

    def ttl(self, key: str) -> float | None:
        self._purge()
        expires_at = self._expires_at.get(key)
        return None if expires_at is None else expires_at - self._clock.epoch


@pytest.fixture
def clock(monkeypatch):
    fake = _FakeClock(_T0)
    monkeypatch.setattr("shared.api_key_store.datetime", fake.datetime_class())
    return fake


@pytest.fixture
def redis(clock):
    return _TTLRedis(clock)


@pytest.fixture
def store(monkeypatch, redis):
    limiter = _make_store(monkeypatch)
    limiter._redis = redis
    return limiter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("limit", "period", "offset"),
    [
        # One request every 2 seconds against 60/min: the reproduced bug. The old
        # counter blocked this client after about two minutes and kept it blocked.
        (60, 2.0, 0),
        (60, 2.0, 31),
        # Exactly limit-per-window, starting at different points inside a bucket.
        (30, 2.0, 0),
        (30, 2.0, 17),
        (30, 2.0, 59),
    ],
)
async def test_steady_client_within_its_limit_is_never_blocked(store, clock, limit, period, offset):
    clock.advance(offset)
    denied_at: list[float] = []
    for _ in range(int(10 * 60 / period)):  # ten windows of traffic, never pausing
        info = await store.check_rate_limit("steady", limit, 60)
        if not info.allowed:
            denied_at.append(clock.epoch - _T0)
        clock.advance(period)

    assert denied_at == [], f"steady client was blocked at t+{denied_at[:3]}s"


@pytest.mark.asyncio
async def test_burst_over_the_limit_is_denied_then_recovers_when_the_window_rolls(store, clock):
    limit = 5
    clock.advance(10)

    first = [await store.check_rate_limit("burst", limit) for _ in range(limit + 3)]
    assert [info.allowed for info in first] == [True] * limit + [False] * 3
    assert first[limit - 1].remaining == 0
    assert all(info.remaining == 0 for info in first[limit:])

    # Hammering while blocked must not push the end of the block out.
    while clock.epoch - _T0 < 58:
        clock.advance(6)
        assert not (await store.check_rate_limit("burst", limit)).allowed
    clock.advance(1.9)  # t+59.9: still inside the bucket
    assert not (await store.check_rate_limit("burst", limit)).allowed

    clock.advance(0.1)  # t+60.0: next bucket
    info = await store.check_rate_limit("burst", limit)
    assert info.allowed is True
    assert info.remaining == limit - 1
    assert info.retry_after is None


@pytest.mark.asyncio
async def test_client_that_waits_the_advertised_retry_after_is_admitted(store, clock):
    limit = 3
    clock.advance(10)
    for _ in range(limit):
        assert (await store.check_rate_limit("polite", limit)).allowed
    denied = await store.check_rate_limit("polite", limit)
    assert denied.allowed is False

    clock.advance(denied.retry_after - 0.5)
    assert not (await store.check_rate_limit("polite", limit)).allowed, "retry_after was not conservative"

    clock.advance(0.5)
    assert (await store.check_rate_limit("polite", limit)).allowed, "retry_after overstated the wait"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("window", "offset", "expected"),
    [
        (60, 0, 60),
        (60, 10, 50),
        (60, 10.5, 50),  # 49.5s left rounds up: never promise a retry that is too early
        (60, 59, 1),
        (60, 59.999, 1),  # never 0: Retry-After 0 invites an immediate retry storm
        (30, 0, 30),
        (30, 12, 18),
        (3600, 100, 3500),
        (3600, 3599.2, 1),
    ],
)
async def test_retry_after_is_whole_seconds_until_the_bucket_ends(store, clock, window, offset, expected):
    clock.advance(offset)
    assert (await store.check_rate_limit("ra", 1, window)).allowed
    info = await store.check_rate_limit("ra", 1, window)

    assert info.allowed is False
    assert isinstance(info.retry_after, int)
    assert info.retry_after == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("window", "offset", "seconds_to_reset"),
    [(60, 10, 60), (30, 10, 30), (30, 40, 60), (3600, 100, 3600)],
)
async def test_reset_at_is_the_end_of_the_bucket_for_any_window(store, clock, window, offset, seconds_to_reset):
    clock.advance(offset)
    info = await store.check_rate_limit("reset", 5, window)

    assert info.reset_at == datetime.fromtimestamp(_T0 + seconds_to_reset, tz=timezone.utc)


@pytest.mark.asyncio
async def test_one_pipeline_round_trip_incr_then_expire_on_the_bucket_key(store, clock, redis):
    clock.advance(75)  # second bucket of the hour
    await store.check_rate_limit("rge_live_abc", 10)

    bucket_key = f"ratelimit:rge_live_abc:60:{int((_T0 + 75) // 60)}"
    assert redis.round_trips == 1
    assert redis.executed == [("incr", bucket_key), ("expire", bucket_key, 120)]


@pytest.mark.asyncio
async def test_every_counter_key_has_a_ttl_and_expires(store, clock, redis):
    for _ in range(6 * 60):  # six windows, with the budget exhausted in each
        await store.check_rate_limit("ttl", 5)
        for key in redis.live_keys():
            ttl = redis.ttl(key)
            assert ttl is not None, f"{key} has no TTL"
            assert 0 < ttl <= 120
        assert len(redis.live_keys()) <= 3  # current bucket plus at most two older ones
        clock.advance(1)

    clock.advance(121)
    assert redis.live_keys() == []


@pytest.mark.asyncio
async def test_a_counter_that_lost_its_ttl_cannot_block_beyond_its_own_bucket(store, clock, redis):
    # If EXPIRE ever failed, or a key came back from a restore without its TTL,
    # the old single key per (key, window) would have blocked that key forever.
    # A bucketed key only ever affects its own bucket.
    clock.advance(10)
    redis.seed(f"ratelimit:k:60:{int((_T0 + 10) // 60)}", 10**6)  # no TTL

    assert not (await store.check_rate_limit("k", 5)).allowed

    clock.advance(50)
    assert (await store.check_rate_limit("k", 5)).allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("other", ["k2", "K1", "k1 ", "k1:60", "k1:60:1", "k1*"])
async def test_one_key_cannot_consume_another_keys_budget(store, other):
    limit = 3
    for _ in range(limit):
        assert (await store.check_rate_limit("k1", limit)).allowed
    assert not (await store.check_rate_limit("k1", limit)).allowed

    info = await store.check_rate_limit(other, limit)
    assert info.allowed is True
    assert info.remaining == limit - 1


@pytest.mark.asyncio
async def test_different_window_seconds_do_not_share_a_counter(store):
    limit = 2
    for _ in range(limit):
        assert (await store.check_rate_limit("k", limit)).allowed
    assert not (await store.check_rate_limit("k", limit)).allowed  # per-minute budget spent

    for window in (10, 30, 120, 3600):
        info = await store.check_rate_limit("k", limit, window_seconds=window)
        assert info.allowed is True, f"window {window} shared the per-minute counter"
        assert info.remaining == limit - 1

    assert not (await store.check_rate_limit("k", limit)).allowed  # and it stayed spent


@pytest.mark.asyncio
async def test_legacy_unbucketed_counter_is_ignored(store, redis):
    # During a rolling deploy an old worker may still write the pre-bucket key,
    # and a counter pinned by the old sliding TTL may linger. The new code must
    # not read it.
    redis.seed("ratelimit:k:60", 10**9)

    info = await store.check_rate_limit("k", 5)

    assert info.allowed is True
    assert info.remaining == 4


@pytest.mark.asyncio
async def test_fixed_window_edge_can_admit_twice_the_limit_but_never_more_inside_a_bucket(store, clock):
    # Known trade-off of a fixed window: a client can spend the whole budget in
    # the last second of one bucket and again in the first second of the next.
    limit = 4
    clock.advance(59)
    before_edge = [(await store.check_rate_limit("edge", limit)).allowed for _ in range(limit)]
    clock.advance(1)
    after_edge = [(await store.check_rate_limit("edge", limit)).allowed for _ in range(limit)]

    assert before_edge == [True] * limit
    assert after_edge == [True] * limit
    assert not (await store.check_rate_limit("edge", limit)).allowed


async def _check_as_worker(worker, clock, skew, *args):
    """Run one limiter call on a worker whose clock is ``skew`` seconds off."""
    clock.skew = skew
    try:
        return await worker.check_rate_limit(*args)
    finally:
        clock.skew = 0.0


@pytest.mark.asyncio
async def test_worker_clock_skew_lets_a_burst_reach_three_times_the_limit_in_one_window(monkeypatch, clock, redis):
    # Two workers share one Redis; B's clock is 10 seconds behind. They place the
    # same instant in different buckets, so within 55.5 real seconds (less than
    # one 60 second window) the key is admitted in three buckets: B's old one, the
    # one both share, and the one A opens at the next boundary. Workers that
    # agree on the time are capped at 2 * limit across an edge (test above).
    worker_a, worker_b = _make_store(monkeypatch), _make_store(monkeypatch)
    worker_a._redis = worker_b._redis = redis
    limit, window, behind = 4, 60, -10.0
    started = clock.epoch

    clock.advance(5)  # B's clock reads 11:59:55, one bucket behind A's
    from_b = [(await _check_as_worker(worker_b, clock, behind, "k", limit, window)).allowed for _ in range(limit)]
    clock.advance(1)  # A's bucket is 12:00
    from_a = [(await _check_as_worker(worker_a, clock, 0.0, "k", limit, window)).allowed for _ in range(limit)]
    clock.advance(54.5)  # 12:01:00.5: A has crossed into the next bucket
    from_a_next = [(await _check_as_worker(worker_a, clock, 0.0, "k", limit, window)).allowed for _ in range(limit)]
    span = clock.epoch - (started + 5)

    assert span < window
    assert from_b + from_a + from_a_next == [True] * (3 * limit)
    # Every bucket still enforces its own limit: nothing beyond 3 * limit.
    assert not (await _check_as_worker(worker_a, clock, 0.0, "k", limit, window)).allowed
    assert not (await _check_as_worker(worker_b, clock, behind, "k", limit, window)).allowed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("worker_skews", "most_admitted_in_one_window"),
    [
        # Same clock: the 2x edge burst and no more.
        ((0, 0), 2),
        # Offsets under one window (12 s here), either direction: 3x, the ceiling.
        ((0, -2), 3),
        ((0, -3), 3),
        ((0, -6), 3),
        ((0, -11), 3),
        ((0, 6), 3),
        ((0, -3, 6), 3),
        # Offsets of a window or more spread the key over more buckets still.
        ((0, -25), 4),
    ],
)
async def test_worst_case_burst_in_one_window_grows_with_worker_clock_skew(
    monkeypatch, clock, worker_skews, most_admitted_in_one_window
):
    # A client that holds its requests until it can spend them all inside one
    # window-length interval of real time, then hammers every worker at every
    # second of it, is admitted ``limit`` per distinct bucket the workers reach.
    # Each interval start gets a fresh Redis, so the count is exact.
    limit, window = 2, 12
    workers = [_make_store(monkeypatch) for _ in worker_skews]
    worst = 0
    for start in range(window):
        clock.epoch = _T0 + start
        shared_redis = _TTLRedis(clock)
        for worker in workers:
            worker._redis = shared_redis
        admitted = 0
        for _ in range(window):
            for worker, skew in zip(workers, worker_skews):
                for _ in range(limit):
                    info = await _check_as_worker(worker, clock, skew, "k", limit, window)
                    admitted += info.allowed
            clock.advance(1)
        worst = max(worst, admitted)

    assert worst == most_admitted_in_one_window * limit


@pytest.mark.asyncio
async def test_limit_is_shared_by_workers_using_the_same_redis(monkeypatch, clock, redis):
    worker_a, worker_b = _make_store(monkeypatch), _make_store(monkeypatch)
    worker_a._redis = worker_b._redis = redis

    allowed = [
        (await worker_a.check_rate_limit("k", 2)).allowed,
        (await worker_b.check_rate_limit("k", 2)).allowed,
        (await worker_a.check_rate_limit("k", 2)).allowed,
        (await worker_b.check_rate_limit("k", 2)).allowed,
    ]

    assert allowed == [True, True, False, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("window", [60, 30])
async def test_redis_absent_fails_closed(monkeypatch, clock, window):
    monkeypatch.delenv("REDIS_URL", raising=False)
    limiter = _make_store(monkeypatch)
    limiter._redis = None

    info = await limiter.check_rate_limit("k", 1000, window)

    assert info.allowed is False
    assert info.remaining == 0
    assert info.retry_after == window


@pytest.mark.asyncio
async def test_redis_error_propagates_and_never_admits(store, redis):
    class _BrokenPipeline:
        def incr(self, key):
            pass

        def expire(self, key, seconds):
            pass

        async def execute(self):
            raise ConnectionError("redis down")

    redis.pipeline = lambda: _BrokenPipeline()

    with pytest.raises(ConnectionError):
        await store.check_rate_limit("k", 5)


@pytest.mark.asyncio
@pytest.mark.parametrize("window", [0, -1, -60, 86_401, 10**12, 1.5])
async def test_invalid_window_is_rejected_before_touching_redis(store, redis, window):
    # EXPIRE with 0 or a negative value deletes the key, which would turn the
    # limiter into "always allow"; a huge value overflows Redis's TTL range.
    with pytest.raises(ValueError):
        await store.check_rate_limit("k", 5, window)

    assert redis.round_trips == 0


@pytest.mark.asyncio
async def test_invalid_window_is_rejected_even_when_redis_is_absent(monkeypatch, clock):
    monkeypatch.delenv("REDIS_URL", raising=False)
    limiter = _make_store(monkeypatch)
    limiter._redis = None

    with pytest.raises(ValueError):
        await limiter.check_rate_limit("k", 5, 0)


def _integrator_client(monkeypatch, store):
    """A ``require_api_key`` route backed by ``store``, behind the shared error handlers."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from shared import auth
    from shared.api_key_store import APIKeyResponse
    from shared.error_handling import install_exception_handlers

    principal = APIKeyResponse(
        key_id="rge_live_e2e",
        key_prefix="rge_live_e2e",
        name="e2e",
        tenant_id="11111111-2222-3333-4444-555555555555",
        scopes=["records.read"],
        rate_limit_per_minute=3,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    store.validate_key = AsyncMock(return_value=principal)
    # The harness bypasses the database for key validation, so it must
    # bypass the live tenant-status read the same way.
    store.get_tenant_status = AsyncMock(return_value="active")
    for var in ("AUTH_TEST_BYPASS_TOKEN", "AUTH_TEST_BYPASS_TENANT_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setattr(auth, "_db_store_instance", store)

    app = FastAPI()

    @app.get("/ping")
    async def ping(_principal=Depends(auth.require_api_key)):
        return {"ok": True}

    install_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


_E2E_HEADERS = {"X-RegEngine-API-Key": "rge_live_e2e.not-a-real-secret"}  # pragma: allowlist secret


def test_per_key_429_tells_the_client_when_to_retry(monkeypatch, store, clock):
    """Limiter -> require_api_key -> exception handler, as an integrator sees it."""
    client = _integrator_client(monkeypatch, store)

    clock.advance(10)
    assert [client.get("/ping", headers=_E2E_HEADERS).status_code for _ in range(3)] == [200, 200, 200]

    blocked = client.get("/ping", headers=_E2E_HEADERS)
    assert blocked.status_code == 429
    assert blocked.json() == {"error": {"type": "http_429", "message": "Rate limit exceeded"}}
    assert blocked.headers["Retry-After"] == "50"  # seconds left in the bucket, not a fixed 60

    clock.advance(50)
    assert client.get("/ping", headers=_E2E_HEADERS).status_code == 200


def test_per_key_429_falls_back_to_the_full_window_without_a_retry_after(monkeypatch, store):
    from shared.api_key_store import RateLimitInfo

    client = _integrator_client(monkeypatch, store)
    store.check_rate_limit = AsyncMock(
        return_value=RateLimitInfo(
            allowed=False, limit=3, remaining=0, reset_at=datetime.now(timezone.utc), retry_after=None
        )
    )

    blocked = client.get("/ping", headers=_E2E_HEADERS)

    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"
