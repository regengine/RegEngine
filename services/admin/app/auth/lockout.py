"""Email-scoped login throttling + account lockout helpers.

Extracted from ``auth_routes.py`` (Phase 1 — first auth/ sub-split) so
that the rate-limit / lockout / progressive-delay logic can be
unit-tested without pulling in the whole FastAPI router surface. Every
function here is pure I/O against a ``RedisSessionStore`` plus an
``email`` string — no route decorators, no request lifecycle, no DI.

Behavioral guarantees this module enforces (tracked by #972, #1070, #1082, #1404):

- **Per-email rate limit (#1404):** after ``_EMAIL_ATTEMPT_LIMIT``
  failures in ``_EMAIL_ATTEMPT_WINDOW``, raise 401 (indistinguishable
  from wrong-password) with a brief artificial delay. Previously raised
  429 which leaked account-existence to attackers.
- **Cumulative lockout (#972):** after ``_LOCKOUT_THRESHOLD`` failures,
  the account is hard-locked for ``_LOCKOUT_DURATION`` seconds and
  returns 423 with a ``Retry-After`` header. This is a harder stop than
  the progressive delay.
- **Progressive delay (#1070):** the cool-down window is persisted as a
  Redis TTL, NOT enforced via ``asyncio.sleep`` on the failing worker.
  The sleep-based version could be defeated by running parallel
  connections; the TTL-based version applies to every connection that
  targets the same email.

``auth_routes.py`` re-exports every name defined here so the
``from services.admin.app.auth_routes import _progressive_delay_seconds``
imports used by existing tests continue to work unchanged.
"""
from __future__ import annotations

import asyncio
import inspect

import structlog
from fastapi import HTTPException, status

from ..session_store import RedisSessionStore
from shared.pii import mask_email

logger = structlog.get_logger("auth.lockout")


# ── Per-email login-attempt tracking (credential stuffing prevention) ──
_EMAIL_ATTEMPT_LIMIT = 5
_EMAIL_ATTEMPT_WINDOW = 900  # 15 minutes


def _email_attempt_key(email: str) -> str:
    return f"login_attempts:{email}"


async def _maybe_await(result):
    """Accept either a direct value or an awaitable from injected collaborators."""
    if inspect.isawaitable(result):
        return await result
    return result


async def _check_email_rate_limit(session_store: RedisSessionStore, email: str) -> None:
    """Raise 401 if this email has exceeded the failed login attempt limit.

    #1404 — previously raised 429 with a Retry-After header, which let an
    attacker probe whether a given email address has an active account: after 5
    attempts against victim@company.com the 429 response leaks "this email
    exists." We now return 401 (indistinguishable from a wrong-password response)
    with a short artificial delay to slow the attacker without advertising the
    hit. The per-email counter is still maintained internally so the throttle
    remains effective; we just don't advertise it via a distinct status code or
    Retry-After header.
    """
    client = await session_store._get_client()
    count_str = await client.get(_email_attempt_key(email))
    if count_str and int(count_str) >= _EMAIL_ATTEMPT_LIMIT:
        await asyncio.sleep(0.1)  # brief artificial delay; does NOT expose the limit
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _record_failed_login_attempt(session_store: RedisSessionStore, email: str) -> None:
    client = await session_store._get_client()
    key = _email_attempt_key(email)
    async with client.pipeline(transaction=False) as pipe:
        pipe.incr(key)
        pipe.expire(key, _EMAIL_ATTEMPT_WINDOW)
        await pipe.execute()


async def _clear_email_rate_limit(session_store: RedisSessionStore, email: str) -> None:
    client = await session_store._get_client()
    await client.delete(_email_attempt_key(email))


# ── Account lockout (cumulative, cross-IP) — NIST AC-7 / OWASP A07 (#972) ──
_LOCKOUT_THRESHOLD = 10
_LOCKOUT_DURATION = 86400  # 24 hours
_PROGRESSIVE_DELAY_START = 3  # start delays after 3rd cumulative failure
# #1070 — raise the cap so the exponential stays meaningful past ~8
# failures. At the old cap of 30s a patient attacker could drive
# ~2,880 attempts/day against a single account before lockout. With
# this cap the effective rate drops by an order of magnitude well
# before the 10-attempt threshold.
_PROGRESSIVE_DELAY_CAP_SECONDS = 300


def _lockout_key(email: str) -> str:
    return f"login_lockout:{email}"


def _lockout_delay_key(email: str) -> str:
    """Redis key whose TTL encodes the cool-down window for the email.

    #1070: the old implementation enforced the progressive delay via
    ``await asyncio.sleep(delay)`` inside ``_record_lockout_attempt``,
    which holds the server worker open but does NOT throttle the
    attacker — they can run N concurrent connections to defeat the
    serial sleep. Persisting the deadline in Redis and gating the
    endpoint on it makes the cool-down stateful across all
    connections: every parallel attempt sees the same TTL and is
    rejected with 429 / Retry-After until it elapses.
    """
    return f"login_lockout_delay:{email}"


def _progressive_delay_seconds(count: int) -> int:
    """Return the cool-down seconds a failing request should impose.

    Returns 0 when we're below ``_PROGRESSIVE_DELAY_START`` (no
    throttle yet). Otherwise exponential backoff, capped. Split out
    of ``_record_lockout_attempt`` so tests can pin the table
    directly — easier to reason about than observing via
    ``asyncio.sleep`` timings.
    """
    if count < _PROGRESSIVE_DELAY_START:
        return 0
    return min(2 ** (count - _PROGRESSIVE_DELAY_START), _PROGRESSIVE_DELAY_CAP_SECONDS)


async def _check_account_lockout(session_store: RedisSessionStore, email: str) -> None:
    """Raise 423 if account is locked; raise 429 if still in cool-down.

    Order matters: the 24-hour lockout is a harder stop than the
    per-email progressive delay, and we want an attacker who crosses
    the threshold to get the unambiguous 423 response rather than a
    cycle of 429 Retry-After responses that could mislead them into
    waiting for the short delay window to elapse.
    """
    client = await session_store._get_client()

    # Hard lockout (threshold reached).
    count_str = await client.get(_lockout_key(email))
    if count_str and int(count_str) >= _LOCKOUT_THRESHOLD:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to repeated failed login attempts. Contact support or wait 24 hours.",
            headers={"Retry-After": str(_LOCKOUT_DURATION)},
        )

    # Progressive-delay cool-down — stateful across concurrent
    # connections so parallel attempts cannot bypass it (#1070).
    delay_ttl = await client.ttl(_lockout_delay_key(email))
    if delay_ttl and delay_ttl > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait before trying again.",
            headers={"Retry-After": str(delay_ttl)},
        )


async def _record_lockout_attempt(session_store: RedisSessionStore, email: str) -> int:
    """Increment the cumulative failure counter and arm the
    progressive cool-down. Returns the new count.

    #1070: the cool-down is now persisted as a Redis TTL rather than
    enforced via ``asyncio.sleep`` on the failing worker. That swap
    makes the delay apply to every connection that targets the same
    email — serial or parallel — instead of only the one that tripped
    it. The next call to ``_check_account_lockout`` observes the TTL
    and raises 429 / Retry-After without any further DB work.
    """
    client = await session_store._get_client()
    key = _lockout_key(email)
    async with client.pipeline(transaction=False) as pipe:
        pipe.incr(key)
        pipe.expire(key, _LOCKOUT_DURATION)
        results = await pipe.execute()
    count = results[0]

    # Arm the progressive delay via TTL — concurrent connections all
    # see it, no asyncio.sleep to bypass by spawning more sockets.
    delay = _progressive_delay_seconds(count)
    if delay > 0:
        await client.setex(_lockout_delay_key(email), delay, "1")

    if count == _LOCKOUT_THRESHOLD:
        logger.warning("account_locked", email=mask_email(email), cumulative_failures=count)

    return count


async def _clear_lockout(session_store: RedisSessionStore, email: str) -> None:
    client = await session_store._get_client()
    # Clear both the counter and the cool-down so a legitimate user
    # who succeeds after a run of failures does not keep seeing 429
    # for the remainder of the delay window.
    await client.delete(_lockout_key(email), _lockout_delay_key(email))
