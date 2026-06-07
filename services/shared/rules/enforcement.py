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


# Manifest of the routes / persistence paths that respect the enforcement
# mode by calling ``should_reject()`` on their evaluation summary. Adding
# a new CTE-writing path is a deliberate decision — if the path should
# block on rule violations under enforcement, wire ``should_reject()``
# AND add the path here. The drift test in
# ``services/shared/tests/test_rules_enforcement_manifest.py`` asserts
# this list matches the actual call sites so a new ``should_reject()``
# call without a manifest entry (or vice versa) fails CI.
#
# Per the project limitations note: rule failures are NOT universally
# blocking. Enforcement is per-route opt-in by design — the manifest
# documents the current contract so reviewers can see at a glance which
# ingestion paths actually enforce.
ENFORCEMENT_AWARE_CALL_SITES: tuple[str, ...] = (
    "services/ingestion/app/webhook_compat.py",
    "services/ingestion/app/epcis/persistence.py",
    "services/ingestion/app/webhook_router_v2/rules_eval.py",
)


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


def handle_preeval_exception(err: BaseException, *, where: str) -> None:
    """Decide how a pre-eval crash is surfaced to the caller.

    Compliance-defensibility behavior:

    * ``RULES_ENGINE_ENFORCE=off`` → warn + return. The caller treats
      pre-eval as no-verdict and proceeds (current default-prod
      behavior — engine is "log-and-accept" so a transient bug must
      not block ingestion).

    * ``RULES_ENGINE_ENFORCE=cte_only`` / ``all`` → emit a Sentry
      ``error`` event with the exception attached, then raise
      ``HTTPException(500, RULES_ENGINE_EVAL_FAILED)``. Silently
      accepting an event because the rule engine crashed defeats the
      product's purpose under enforcement; we'd rather take a 5xx
      and have ops triage than emit a compliance-pass we cannot
      actually defend.

    Single funnel for all three pre-eval call sites (EPCIS,
    webhook_router_v2, webhook_compat) so the policy stays in one
    place and stays auditable.

    Imports HTTPException lazily so this module stays usable from
    contexts (CLI, jobs, tests) where FastAPI may not be installed.
    """
    import logging  # noqa: PLC0415

    logger = logging.getLogger(__name__)
    mode = current_mode()
    if mode == EnforcementMode.OFF:
        logger.warning(
            "rules_preeval_skipped where=%s error=%s",
            where,
            str(err),
        )
        return

    # cte_only / all — fail loud.
    logger.error(
        "rules_preeval_failed where=%s mode=%s error=%s",
        where,
        mode,
        str(err),
    )
    try:
        import sentry_sdk  # noqa: PLC0415

        sentry_sdk.capture_exception(err)
        sentry_sdk.capture_message(
            "rules_preeval_failed",
            level="error",
            extras={"where": where, "mode": mode, "error": str(err)},
            tags={
                "subsystem": "rules_engine",
                "component": "preeval",
                "enforcement_mode": mode,
            },
        )
    except Exception:  # noqa: BLE001
        logger.debug("sentry_capture_failed component=preeval")

    from fastapi import HTTPException  # noqa: PLC0415

    raise HTTPException(
        status_code=500,
        detail={
            "error": "RULES_ENGINE_EVAL_FAILED",
            "message": (
                "Rules engine pre-evaluation failed under enforcement mode. Refusing to silently accept the event."
            ),
            "where": where,
        },
    ) from err


def _first_failure_reason(summary: EvaluationSummary) -> str:
    for result in summary.critical_failures or summary.results:
        if result.result in ("fail", "error"):
            rule_id = result.rule_id or "unknown_rule"
            why = result.why_failed or "failed"
            return f"{rule_id}: {why}"
    return "rule_violation"
