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
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from shared.api_key_store import DatabaseAPIKeyStore


def _make_store(monkeypatch):
    """Build a DatabaseAPIKeyStore without opening real DB or Redis."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:6543/d")
    with patch("shared.api_key_store.create_async_engine") as _e, patch(
        "shared.api_key_store.sessionmaker"
    ) as _s:
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
        def incr(self, key): pass
        def expire(self, key, sec): pass
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
        def incr(self, key): pass
        def expire(self, key, sec): pass
        async def execute(self): return [1, True]

    class _FakeRedis:
        def pipeline(self): return _FakePipeline()

    store._redis = _FakeRedis()

    info = await store.check_rate_limit(key_id="test", limit=60)
    assert info.reset_at.tzinfo is not None
    assert info.reset_at.tzinfo.utcoffset(info.reset_at) == timezone.utc.utcoffset(info.reset_at)
