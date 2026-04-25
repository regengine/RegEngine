"""Regression tests for #1082 — /login user-enumeration timing oracle.

Before the fix, ``POST /auth/login`` short-circuited ``verify_password``
when the submitted email did not exist in the ``users`` table, because
the handler tested ``if not user or not verify_password(...)`` and ``or``
stops on the first truthy fail. Argon2 verify is ~80-200 ms and is
trivial to measure — an attacker who wants to know whether
``alice@acme.com`` is a RegEngine customer just times a few /login
requests and looks for the latency gap.

The fix introduces :func:`services.admin.app.auth_utils.verify_login`
which always runs one argon2 verify, even when ``user`` is None, by
verifying the submitted password against a module-level dummy hash.
This test pins:

    1. ``verify_login`` returns False for both unknown-user and
       wrong-password inputs, True for the correct password.
    2. The wall-clock cost of ``verify_login`` for the unknown-user
       branch is within ~50 ms of the wrong-password branch across
       20 iterations (p50 delta). 50 ms is loose enough for CI
       jitter; on a warm argon2 context the delta should be < 5 ms.
    3. Unknown-user path calls ``pwd_context.verify`` exactly once —
       it must not skip the work.
    4. The login route calls ``verify_login`` and records failed
       attempts in BOTH branches so subsequent-request side-effects
       don't become a secondary oracle.
"""
from __future__ import annotations

import statistics
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────
# Unit: verify_login behaviour
# ─────────────────────────────────────────────────────────────────────


def test_verify_login_returns_false_for_unknown_user():
    from services.admin.app.auth_utils import verify_login

    assert verify_login("any-password", None) is False


def test_verify_login_returns_false_for_wrong_password():
    from services.admin.app.auth_utils import verify_login, get_password_hash

    user = SimpleNamespace(password_hash=get_password_hash("correct-horse-battery-staple"))
    assert verify_login("wrong-password", user) is False


def test_verify_login_returns_true_for_correct_password():
    from services.admin.app.auth_utils import verify_login, get_password_hash

    user = SimpleNamespace(password_hash=get_password_hash("correct-horse-battery-staple"))
    assert verify_login("correct-horse-battery-staple", user) is True


def test_verify_login_calls_argon2_on_unknown_user(monkeypatch):
    """The core fix: unknown-user branch must call ``pwd_context.verify``
    exactly once so the wall-time matches the wrong-password branch.
    If someone refactors this to short-circuit again, this test fails.
    """
    import services.admin.app.auth_utils as auth_utils

    verify_calls: list = []
    real_verify = auth_utils.pwd_context.verify

    def _spy_verify(plain, hashed):
        verify_calls.append((plain, hashed))
        return real_verify(plain, hashed)

    monkeypatch.setattr(auth_utils.pwd_context, "verify", _spy_verify)

    result = auth_utils.verify_login("any-password", None)
    assert result is False
    assert len(verify_calls) == 1, (
        "verify_login(None) must call pwd_context.verify exactly once "
        "against the dummy hash — otherwise the timing oracle is back."
    )
    # The dummy hash is what got verified, not the user's (non-existent) hash.
    assert verify_calls[0][1] == auth_utils._DUMMY_ARGON2_HASH


def test_verify_login_defensive_user_without_password_hash():
    """A user row with no password_hash still pays the argon2 cost so
    that edge case isn't its own oracle."""
    from services.admin.app.auth_utils import verify_login

    user = SimpleNamespace(password_hash=None)
    assert verify_login("x", user) is False


# ─────────────────────────────────────────────────────────────────────
# Timing: unknown-user vs wrong-password latency
# ─────────────────────────────────────────────────────────────────────


# Tolerance chosen from the issue's guidance:
#   * "loose enough for CI jitter"  — 50 ms
#   * "real fix gets it to <5 ms"    — aspirational; we don't pin that
#     here because shared CI runners can spike well past 5 ms.
_TIMING_TOLERANCE_SECONDS = 0.050


@pytest.mark.timeout(60)
def test_verify_login_timing_parity_unknown_vs_wrong_password():
    """p50 latency of the unknown-email branch must be within ~50 ms
    of the wrong-password branch. If the short-circuit ever returns,
    the unknown branch is essentially free (~microseconds) while the
    wrong-password branch still eats ~80-200 ms of argon2, and this
    assertion fails loudly."""
    from services.admin.app.auth_utils import verify_login, get_password_hash

    password = "correct-horse-battery-staple"
    user = SimpleNamespace(password_hash=get_password_hash(password))

    # One warm-up pass per branch — first argon2 call on a fresh
    # process pays extra setup cost that would skew p50.
    verify_login("wrong", user)
    verify_login("wrong", None)

    iters = 20
    wrong_password_times: list[float] = []
    unknown_user_times: list[float] = []

    # Alternate the branches so any monotonic CPU warmup/cooldown
    # affects both equally.
    for _ in range(iters):
        t0 = time.perf_counter()
        verify_login("wrong-password", user)
        wrong_password_times.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        verify_login("wrong-password", None)
        unknown_user_times.append(time.perf_counter() - t0)

    p50_wrong = statistics.median(wrong_password_times)
    p50_unknown = statistics.median(unknown_user_times)
    delta = abs(p50_unknown - p50_wrong)

    assert delta < _TIMING_TOLERANCE_SECONDS, (
        f"Timing oracle regression: p50 unknown-email={p50_unknown*1000:.1f}ms "
        f"vs p50 wrong-password={p50_wrong*1000:.1f}ms, "
        f"delta={delta*1000:.1f}ms exceeds {_TIMING_TOLERANCE_SECONDS*1000:.0f}ms tolerance. "
        f"If the delta is small but negative (unknown > wrong), that is fine — "
        f"only an attacker-useful gap (unknown much shorter than wrong) breaks the test."
    )


# ─────────────────────────────────────────────────────────────────────
# Integration: login route calls verify_login and records both branches
# ─────────────────────────────────────────────────────────────────────


def test_login_route_uses_verify_login_symbol():
    """Guard-rail: if someone reverts the login handler to
    ``verify_password(payload.password, user.password_hash)`` the
    short-circuit on ``not user`` comes back. Assert the imported
    symbol is present in the source so that regression is caught at
    collect time."""
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "app" / "auth_routes.py"
    text = src.read_text()
    assert "verify_login" in text, (
        "auth_routes.py must import and use verify_login() for the "
        "/login check (see #1082). The old verify_password call "
        "short-circuits when user is None and leaks existence via "
        "response timing."
    )
    # And the import itself must come from auth_utils.
    assert "from .auth_utils import" in text
    assert "verify_login" in text.split("from .auth_utils import", 1)[1].split("\n", 1)[0]


def test_login_route_records_failed_attempt_for_both_branches():
    """Both the unknown-email and wrong-password branches must call
    ``_record_failed_login_attempt`` and ``_record_lockout_attempt``.
    Otherwise the progressive-delay / lockout counters advance only
    on one branch and become a secondary oracle via Retry-After
    headers."""
    from pathlib import Path

    # login handler lives in auth/login_router.py after the Phase 1 split
    src = Path(__file__).resolve().parent.parent / "app" / "auth" / "login_router.py"
    text = src.read_text()

    # The handler should have a SINGLE fail block that runs both
    # record calls unconditionally after verify_login() returns False.
    # This is a source-level smoke test — detailed behaviour is
    # covered by the unit tests above.
    login_fn = _extract_function(text, "async def login(")
    assert "_record_failed_login_attempt(session_store, normalized_login_email)" in login_fn, (
        "/login must call _record_failed_login_attempt on the failure path (#1082)."
    )
    assert "_record_lockout_attempt(session_store, normalized_login_email)" in login_fn, (
        "/login must call _record_lockout_attempt on the failure path (#1082)."
    )


def _extract_function(src: str, signature_prefix: str) -> str:
    """Return the source text of the function whose signature starts
    with ``signature_prefix`` (first match). Stops at the next
    top-level ``@router.`` decorator or ``def``/``async def`` at the
    same indentation."""
    lines = src.splitlines(keepends=True)
    out: list[str] = []
    capturing = False
    for line in lines:
        if not capturing and signature_prefix in line:
            capturing = True
            out.append(line)
            continue
        if capturing:
            # Stop when we hit a new top-level route decorator or
            # another top-level def. The login function ends before
            # the next ``@router.post(...)`` block.
            stripped = line.lstrip()
            if line.startswith("@router.") or line.startswith("def ") or line.startswith("async def ") or (line.startswith("class ") and "(" in line):
                break
            out.append(line)
    return "".join(out)
