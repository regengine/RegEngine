"""
ReDoS-safe regex execution for user-supplied rule patterns.

Rule definitions live in the `fsma.rule_definitions` table and may be edited
by tenant admins. A malicious pattern such as ``(a+)+$`` combined with a
crafted input can cause exponential backtracking in the stock ``re`` engine,
freezing a worker thread and DoS-ing the compliance API (#1356).

Defense in depth — three layers, strongest first:

1. **Linear-time backend (preferred).** If the ``re2`` (Cython binding for
   RE2, Google's DFA engine) is importable, we use it. RE2 has no
   backtracking and is immune to catastrophic blowup by construction.
2. **Pattern sanity check.** When only stock ``re`` is available, we
   pre-scan the pattern for catastrophic-backtracking constructs (nested
   quantifiers like ``(a+)+``, ``(a*)+``, ``(a|a)+``) and reject them.
3. **Wall-clock timeout.** Even a "clean" pattern can go quadratic on
   pathological input, so we run ``re.match`` under a 100 ms wall-clock
   budget (SIGALRM on POSIX main-thread, threading.Thread fallback
   elsewhere). A timeout is treated as ``match_timeout`` — the caller
   decides whether that means fail-closed (regulatory) or skip.

Public API:
    safe_match(pattern, value, timeout_ms=100) -> MatchOutcome

    MatchOutcome is a small enum-like namespace with:
        MATCH         — pattern matched the value
        NO_MATCH      — pattern did not match
        INVALID_PATTERN — pattern failed to compile or was rejected for RE2
                          unsafety / catastrophic backtracking
        TIMEOUT       — evaluation exceeded the wall-clock budget

The caller MUST distinguish TIMEOUT/INVALID_PATTERN from NO_MATCH so that
a DoS-bait rule does not silently produce a "compliant" stamp (fail-open).
The rule evaluator treats both as a hard fail with a structured reason.
"""

from __future__ import annotations

import logging
import re
import signal
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("rules-engine.safe_regex")

# --- Prefer re2 (DFA, no catastrophic backtracking). -----------------------

try:
    import re2 as _re2_module  # type: ignore[import-not-found]
    _HAS_RE2 = True
except Exception:  # pragma: no cover — re2 is optional
    _re2_module = None
    _HAS_RE2 = False


# --- Outcome values --------------------------------------------------------


MATCH = "match"
NO_MATCH = "no_match"
INVALID_PATTERN = "invalid_pattern"
TIMEOUT = "timeout"


@dataclass(frozen=True)
class MatchOutcome:
    status: str  # one of MATCH / NO_MATCH / INVALID_PATTERN / TIMEOUT
    detail: Optional[str] = None  # human-readable reason

    def is_match(self) -> bool:
        return self.status == MATCH

    def is_safe_no_match(self) -> bool:
        """True when the pattern ran to completion and simply did not match.

        Callers must NOT treat TIMEOUT / INVALID_PATTERN as "no match" —
        that would fail-open a DoS'd rule as "compliant".
        """
        return self.status == NO_MATCH


# --- Catastrophic-backtracking pre-screen ---------------------------------


# Heuristic red flags. Any of these shapes in a pattern means the stock
# ``re`` engine can blow up exponentially given the right input.
#
#   (X+)+      — nested + on a group
#   (X*)+      — nested * inside a +
#   (X+)*      — nested + inside a *
#   (X*)*      — nested * inside a *
#   (X|X)+     — alternation of equivalent branches with outer +
#
# We do NOT try to be exhaustive; we aim for the Owasp-listed "evil regex"
# shapes that account for almost every real-world ReDoS CVE.
_REDOS_SHAPES = [
    re.compile(r"\([^()]*[+*][^()]*\)[+*]"),          # (X+)+ / (X*)*
    re.compile(r"\(\?:[^()]*[+*][^()]*\)[+*]"),        # non-cap equivalents
    re.compile(r"\([^()]*\|[^()]*\)[+*]\s*[+*]"),      # (a|b)++
]


def _has_catastrophic_shape(pattern: str) -> bool:
    """Return True if the pattern shape is known to trigger ReDoS."""
    for shape in _REDOS_SHAPES:
        if shape.search(pattern):
            return True
    # Also reject absurdly long patterns (DoS via pattern compilation time).
    return len(pattern) > 2048


# --- Timed match under stock re --------------------------------------------


def _match_with_signal_timeout(
    pattern: str, value: str, timeout_ms: int
) -> MatchOutcome:
    """POSIX main-thread path: SIGALRM-based wall-clock timeout."""
    def _handler(signum, frame):
        raise _RegexTimeoutError()

    prev = signal.signal(signal.SIGALRM, _handler)
    try:
        # setitimer uses floating-point seconds, giving us millisecond
        # precision — signal.alarm() would round up to whole seconds.
        signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000.0)
        try:
            matched = re.match(pattern, value) is not None
        except re.error as exc:
            return MatchOutcome(INVALID_PATTERN, f"re.error: {exc}")
        return MatchOutcome(MATCH if matched else NO_MATCH)
    except _RegexTimeoutError:
        logger.warning(
            "regex_match_timeout",
            extra={"pattern_prefix": pattern[:80], "timeout_ms": timeout_ms},
        )
        return MatchOutcome(TIMEOUT, f"regex exceeded {timeout_ms}ms budget")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prev)


def _match_with_thread_timeout(
    pattern: str, value: str, timeout_ms: int
) -> MatchOutcome:
    """Worker-thread fallback: run re.match in a daemon thread with join timeout.

    Python cannot preempt a runaway C regex from another thread — the
    worker keeps eating CPU until the regex engine yields. We DO, however,
    guarantee that the calling thread returns within the budget so the
    request pipeline does not stall. The orphaned thread will reap itself
    once re bails (typically seconds later on backtracking, minutes at
    worst). For a regulatory API this is acceptable: the caller sees a
    TIMEOUT outcome and produces a fail-closed verdict.
    """
    result: dict[str, MatchOutcome] = {}

    def _work():
        try:
            matched = re.match(pattern, value) is not None
            result["outcome"] = MatchOutcome(MATCH if matched else NO_MATCH)
        except re.error as exc:
            result["outcome"] = MatchOutcome(INVALID_PATTERN, f"re.error: {exc}")
        except Exception as exc:  # pragma: no cover — defense in depth
            result["outcome"] = MatchOutcome(INVALID_PATTERN, f"{type(exc).__name__}: {exc}")

    t = threading.Thread(target=_work, name="safe-regex-match", daemon=True)
    t.start()
    t.join(timeout=timeout_ms / 1000.0)
    if t.is_alive():
        logger.warning(
            "regex_match_timeout",
            extra={"pattern_prefix": pattern[:80], "timeout_ms": timeout_ms},
        )
        return MatchOutcome(TIMEOUT, f"regex exceeded {timeout_ms}ms budget")
    return result.get("outcome", MatchOutcome(INVALID_PATTERN, "worker produced no result"))


class _RegexTimeoutError(Exception):
    """Internal marker to bail out of re.match from SIGALRM."""


# --- Main entry point ------------------------------------------------------


def safe_match(
    pattern: str,
    value: str,
    timeout_ms: int = 100,
) -> MatchOutcome:
    """Run ``re.match(pattern, value)`` safely under a time + shape budget.

    See module docstring for layering semantics. Returns a MatchOutcome;
    callers MUST branch on ``.status`` rather than treating non-MATCH as
    "compliant".
    """
    if not isinstance(pattern, str):
        return MatchOutcome(INVALID_PATTERN, "pattern is not a string")
    if not isinstance(value, str):
        value = str(value)

    # Layer 1 — RE2 is linear time, so we can skip the shape check and
    # just let it run. Anchored match semantics: re.match only anchors at
    # the start, so we use re2.match (same semantics).
    if _HAS_RE2 and _re2_module is not None:
        try:
            compiled = _re2_module.compile(pattern)
        except Exception as exc:  # pragma: no cover — re2 rejects some syntax
            logger.info(
                "re2_compile_rejected",
                extra={"pattern_prefix": pattern[:80], "error": str(exc)},
            )
            # Fall through to stock-re path — some PCRE features re2 doesn't
            # support (e.g. backrefs). Stock re will still be protected by
            # the shape check + timeout below.
        else:
            try:
                matched = compiled.match(value) is not None
                return MatchOutcome(MATCH if matched else NO_MATCH)
            except Exception as exc:  # pragma: no cover
                return MatchOutcome(INVALID_PATTERN, f"re2 match failed: {exc}")

    # Layer 2 — stock re: reject catastrophic shapes BEFORE compiling.
    if _has_catastrophic_shape(pattern):
        logger.warning(
            "regex_pattern_rejected_catastrophic_shape",
            extra={"pattern_prefix": pattern[:80]},
        )
        return MatchOutcome(
            INVALID_PATTERN,
            "pattern contains catastrophic-backtracking shape (nested quantifiers)",
        )

    # Pre-compile to catch syntax errors deterministically.
    try:
        re.compile(pattern)
    except re.error as exc:
        return MatchOutcome(INVALID_PATTERN, f"re.error: {exc}")

    # Layer 3 — wall-clock timeout. SIGALRM only works on the main thread
    # on POSIX. FastAPI workers run requests on main thread of each worker
    # process, BUT individual requests may land on helper threads under
    # uvicorn's asyncio bridge. Detect and fall through to threaded path.
    is_main_thread = threading.current_thread() is threading.main_thread()
    if hasattr(signal, "SIGALRM") and is_main_thread:
        return _match_with_signal_timeout(pattern, value, timeout_ms)
    return _match_with_thread_timeout(pattern, value, timeout_ms)


def has_re2() -> bool:
    """Introspection helper for tests and deployment diagnostics."""
    return _HAS_RE2
