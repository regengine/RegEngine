"""Regression tests for #1070 — progressive login-lockout delay.

Before the fix, ``_record_lockout_attempt`` enforced the progressive
delay with ``await asyncio.sleep(delay)``. That throttles the serial
code path of the failing worker but does NOT throttle the attacker:
spawning 10 concurrent TCP connections to the same endpoint lets an
attacker run ~10× the intended throughput, because each worker's
sleep blocks only its own request.

The fix persists the cool-down as a Redis TTL and rejects with 429
Retry-After on every subsequent attempt to the same email until the
TTL elapses — serial or parallel. These tests pin:

    1. ``_progressive_delay_seconds(count)`` returns the expected
       exponential table, clamped to the new cap.
    2. ``_record_lockout_attempt`` writes SETEX on the delay key and
       does NOT sleep.
    3. ``_check_account_lockout`` raises 429 with Retry-After while
       the TTL is live, and 423 once the threshold is reached.
    4. A successful login clears both the counter AND the delay key,
       so a legitimate user who eventually types their password
       right doesn't keep seeing 429 through the remaining window.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status


# ─────────────────────────────────────────────────────────────────────
# Progressive-delay table
# ─────────────────────────────────────────────────────────────────────


def test_progressive_delay_zero_below_start_threshold():
    """First two failures impose no delay — the 3rd starts the ramp."""
    from services.admin.app.auth_routes import _progressive_delay_seconds

    assert _progressive_delay_seconds(0) == 0
    assert _progressive_delay_seconds(1) == 0
    assert _progressive_delay_seconds(2) == 0


def test_progressive_delay_exponential_ramp():
    """3rd failure → 1s, 4th → 2s, 5th → 4s, and so on (2^(n-3))."""
    from services.admin.app.auth_routes import _progressive_delay_seconds

    assert _progressive_delay_seconds(3) == 1
    assert _progressive_delay_seconds(4) == 2
    assert _progressive_delay_seconds(5) == 4
    assert _progressive_delay_seconds(6) == 8
    assert _progressive_delay_seconds(7) == 16


def test_progressive_delay_cap_is_five_minutes():
    """High counts saturate at the cap — 300s, not the old 30s.

    The whole point of #1070: after ~8 failures the old cap made the
    endpoint feel throttled while allowing ~2 req/min indefinitely.
    The new cap makes the attacker wait minutes between attempts,
    dropping the effective brute-force rate by an order of magnitude
    before the 10-attempt hard lockout fires."""
    from services.admin.app.auth_routes import (
        _progressive_delay_seconds,
        _PROGRESSIVE_DELAY_CAP_SECONDS,
    )

    assert _PROGRESSIVE_DELAY_CAP_SECONDS == 300
    # At count=11, 2^8 = 256 (still under cap)
    assert _progressive_delay_seconds(11) == 256
    # At count=12, 2^9 = 512 (capped)
    assert _progressive_delay_seconds(12) == 300
    # Anything large saturates.
    assert _progressive_delay_seconds(100) == 300


# ─────────────────────────────────────────────────────────────────────
# _record_lockout_attempt — writes TTL, does not sleep
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_lockout_attempt_does_not_sleep(monkeypatch):
    """The core bypass bug: asyncio.sleep only blocked the failing
    worker, not concurrent attackers. Removing the sleep is the
    necessary (and sufficient) change for parallel-connection attacks
    to stop working."""
    import services.admin.app.auth_routes as auth_routes

    sleep_calls: list = []

    async def _fail_on_sleep(*args, **kwargs):
        sleep_calls.append((args, kwargs))
        raise AssertionError(
            "_record_lockout_attempt must not call asyncio.sleep — "
            "the sleep was bypassable by concurrent connections (#1070)"
        )

    monkeypatch.setattr(auth_routes.asyncio, "sleep", _fail_on_sleep)

    # Redis pipeline returns [new_count, expire_ok]. Use count=5 so
    # the progressive delay is non-zero and we prove setex is called.
    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[5, 1])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)

    client = MagicMock()
    client.pipeline = MagicMock(return_value=pipe)
    client.setex = AsyncMock(return_value=True)

    session_store = MagicMock()
    session_store._get_client = AsyncMock(return_value=client)

    count = await auth_routes._record_lockout_attempt(session_store, "a@b.c")
    assert count == 5
    # Delay at count=5 is 2^(5-3) = 4 seconds → SETEX fires with TTL=4.
    client.setex.assert_awaited_once_with(
        auth_routes._lockout_delay_key("a@b.c"), 4, "1"
    )
    assert sleep_calls == []  # the assertion-raising sleep never fired


@pytest.mark.asyncio
async def test_record_lockout_attempt_below_threshold_skips_setex(monkeypatch):
    """First two failures must not arm the delay — users typo
    passwords and we don't want to greet them with 429 after two
    tries."""
    import services.admin.app.auth_routes as auth_routes

    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, 1])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)

    client = MagicMock()
    client.pipeline = MagicMock(return_value=pipe)
    client.setex = AsyncMock()

    session_store = MagicMock()
    session_store._get_client = AsyncMock(return_value=client)

    count = await auth_routes._record_lockout_attempt(session_store, "a@b.c")
    assert count == 1
    client.setex.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# _check_account_lockout — 429 during cool-down, 423 after threshold
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_account_lockout_raises_429_during_cool_down():
    """Core #1070 assertion: once the delay key has live TTL,
    subsequent attempts are rejected with 429 / Retry-After —
    whether from the same connection or a parallel one."""
    import services.admin.app.auth_routes as auth_routes

    client = MagicMock()
    client.get = AsyncMock(return_value=None)  # below lockout threshold
    client.ttl = AsyncMock(return_value=42)  # 42 seconds left

    session_store = MagicMock()
    session_store._get_client = AsyncMock(return_value=client)

    with pytest.raises(HTTPException) as exc:
        await auth_routes._check_account_lockout(session_store, "a@b.c")
    assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert exc.value.headers["Retry-After"] == "42"


@pytest.mark.asyncio
async def test_check_account_lockout_ignores_expired_delay_key():
    """A delay key with TTL ≤ 0 (already elapsed or missing) must
    NOT raise. The whole point of moving to TTL is that it expires
    itself — no bookkeeping needed to release users."""
    import services.admin.app.auth_routes as auth_routes

    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.ttl = AsyncMock(return_value=-2)  # key missing
    session_store = MagicMock()
    session_store._get_client = AsyncMock(return_value=client)

    # Must not raise — delay window has elapsed.
    await auth_routes._check_account_lockout(session_store, "a@b.c")


@pytest.mark.asyncio
async def test_check_account_lockout_prefers_423_over_429():
    """Threshold reached → 423 (24h lockout), regardless of whether
    the short delay is also live. Attackers who've crossed the hard
    limit must see the unambiguous response code, not a 429 that
    suggests waiting a few seconds."""
    import services.admin.app.auth_routes as auth_routes

    client = MagicMock()
    client.get = AsyncMock(return_value=str(auth_routes._LOCKOUT_THRESHOLD))
    client.ttl = AsyncMock(return_value=120)  # delay key also live

    session_store = MagicMock()
    session_store._get_client = AsyncMock(return_value=client)

    with pytest.raises(HTTPException) as exc:
        await auth_routes._check_account_lockout(session_store, "a@b.c")
    assert exc.value.status_code == status.HTTP_423_LOCKED


# ─────────────────────────────────────────────────────────────────────
# _clear_lockout — legitimate user on successful login
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_lockout_deletes_both_keys():
    """If a user typos twice, then logs in correctly, they must not
    continue seeing 429 for the remainder of the cool-down."""
    import services.admin.app.auth_routes as auth_routes

    client = MagicMock()
    client.delete = AsyncMock()
    session_store = MagicMock()
    session_store._get_client = AsyncMock(return_value=client)

    await auth_routes._clear_lockout(session_store, "a@b.c")

    client.delete.assert_awaited_once_with(
        auth_routes._lockout_key("a@b.c"),
        auth_routes._lockout_delay_key("a@b.c"),
    )
