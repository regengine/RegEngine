"""Rules engine enforcement policy.

Translates an ``EvaluationSummary`` into a reject/accept decision based on
the ``RULES_ENGINE_ENFORCE`` environment variable. Keeps policy in one
place so call sites only have to know ``should_reject()`` — the policy
can tighten over time without touching the ingestion hot path.

The flag exists so the rules engine can be switched from "log-and-accept"
to "reject-on-violation" behind a single env var, with a one-line
rollback if an alpha tenant hits a false positive:

    # Railway / shell
    RULES_ENGINE_ENFORCE=off       # current prod default; engine runs but
                                   # never rejects (exception-queue only)
    RULES_ENGINE_ENFORCE=cte_only  # reject when any critical_failures is
                                   # set; warnings/info still pass through
    RULES_ENGINE_ENFORCE=all       # reject on any ``compliant is False``

In every mode a no-verdict summary (``summary.compliant is None``) is
NEVER a reject. Blocking an event on non-evaluation would silently break
ingestion for tenants without seeded rules and for non-FTL products —
the engine treats those as an explicit "no verdict" signal, not as
compliance failure. See ``types.EvaluationSummary.compliant`` docstring
(#1346, #1347).
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from .types import EvaluationSummary


class EnforcementMode:
    OFF = "off"
    CTE_ONLY = "cte_only"
    ALL = "all"


_VALID_MODES = frozenset({EnforcementMode.OFF, EnforcementMode.CTE_ONLY, EnforcementMode.ALL})


def current_mode() -> str:
    """Read ``RULES_ENGINE_ENFORCE`` at call time.

    Intentionally not cached — reading per-call costs ~microseconds and
    lets operators flip the flag (via Railway env update + redeploy) and
    have the change take effect on the next request without restart
    coordination. Unknown values fall back to ``off`` — fail-safe for
    typos or misconfigured environments.
    """
    raw = os.getenv("RULES_ENGINE_ENFORCE", EnforcementMode.OFF).strip().lower()
    if raw not in _VALID_MODES:
        return EnforcementMode.OFF
    return raw


def should_reject(summary: EvaluationSummary) -> Tuple[bool, Optional[str]]:
    """Return ``(reject, reason)`` for a rules evaluation.

    ``reject``: True means the caller should reject the event (typically
    with HTTP 422 + savepoint rollback). False means accept.

    ``reason``: a short human-readable string suitable for the HTTP
    response body when rejecting. ``None`` when not rejecting.
    """
    mode = current_mode()
    if mode == EnforcementMode.OFF:
        return False, None
    # No-verdict (compliant is None) is never a reject in any mode —
    # "we didn't evaluate" is not the same as "the event violates a rule".
    if summary.compliant is None:
        return False, None
    if mode == EnforcementMode.CTE_ONLY:
        if summary.critical_failures:
            return True, _first_failure_reason(summary)
        return False, None
    if mode == EnforcementMode.ALL:
        if summary.compliant is False:
            return True, _first_failure_reason(summary)
        return False, None
    return False, None


def _first_failure_reason(summary: EvaluationSummary) -> str:
    for result in summary.critical_failures or summary.results:
        if result.result in ("fail", "error"):
            rule_id = result.rule_id or "unknown_rule"
            why = result.why_failed or "failed"
            return f"{rule_id}: {why}"
    return "rule_violation"
