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

# Unrecognized RULES_ENGINE_ENFORCE values already reported this process —
# log once per distinct bad value, not once per request.
_reported_invalid_modes: set[str] = set()


def _safe_counter(name: str, description: str, labelnames: list[str]):
    """Return an existing Prometheus Counter when this module is re-imported."""
    from prometheus_client import REGISTRY, Counter

    try:
        return Counter(name, description, labelnames)
    except ValueError:
        collector = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if collector is None and name.endswith("_total"):
            collector = REGISTRY._names_to_collectors.get(name[:-6])  # type: ignore[attr-defined]
        if collector is not None:
            return collector
        return Counter(name, description, labelnames, registry=None)


# #2710 (enforcement-GA decision): the no-verdict accept contract stays —
# blocking on non-evaluation would break unseeded tenants and non-FTL
# products (#1346/#1347) — but under an enforcement mode it must be LOUD:
# with RULES_ENGINE_ENFORCE=all, a tenant with an empty or unreadable rule
# set has every event accepted, and this counter is the alarm for that.
rules_no_verdict_accepted_total = _safe_counter(
    "rules_no_verdict_accepted_total",
    "Events accepted with NO rule verdict while an enforcement mode was active",
    ["mode", "tenant_id"],
)

# Tenants already warned about this process — warn once per (tenant, mode),
# not once per event (the counter carries the volume).
_no_verdict_warned: set[tuple[str, str]] = set()


def _record_no_verdict_accept(mode: str) -> None:
    """Metric + once-per-tenant warning for an enforcement-mode no-verdict accept."""
    tenant = "unknown"
    try:
        from shared.tenant_context import get_rls_tenant_id

        tenant = str(get_rls_tenant_id() or "unknown")
    except Exception:
        pass
    try:
        rules_no_verdict_accepted_total.labels(mode=mode, tenant_id=tenant).inc()
    except Exception:  # pragma: no cover — metrics must never affect the decision
        pass
    key = (tenant, mode)
    if key not in _no_verdict_warned:
        _no_verdict_warned.add(key)
        import logging  # noqa: PLC0415

        logging.getLogger(__name__).warning(
            "rules_no_verdict_accepted mode=%s tenant_id=%s — event accepted without any rule "
            "verdict while enforcement is active; empty/unreadable rule sets are invisible to "
            "enforcement (#1346/#1347, revisit #2710)",
            mode,
            tenant,
        )


def current_mode() -> str:
    """Read ``RULES_ENGINE_ENFORCE`` at call time.

    Intentionally not cached — reading per-call costs ~microseconds and
    lets operators flip the flag (via Railway env update + redeploy) and
    have the change take effect on the next request without restart
    coordination.

    Unset or empty means ``off`` (the prod default). A PRESENT but
    unrecognized value (e.g. ``true``, ``on``, ``cte-only``) fails CLOSED
    to ``all`` with an error log: an operator who set the variable
    intended enforcement, and silently reverting to ``off`` on a typo
    disables the compliance gate while everyone believes it is on (the
    #2662 failure shape).
    """
    raw = os.getenv("RULES_ENGINE_ENFORCE", EnforcementMode.OFF).strip().lower()
    if not raw:
        return EnforcementMode.OFF
    if raw not in _VALID_MODES:
        if raw not in _reported_invalid_modes:
            _reported_invalid_modes.add(raw)
            import logging  # noqa: PLC0415

            logging.getLogger(__name__).error(
                "rules_enforce_invalid_value value=%r valid=%s — failing closed to 'all'",
                raw,
                sorted(_VALID_MODES),
            )
        return EnforcementMode.ALL
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
    # "we didn't evaluate" is not the same as "the event violates a rule"
    # (#1346/#1347). Decision recorded in #2710: the accept contract stays,
    # but under an active enforcement mode the accept is now counted
    # per-tenant and warned once — the alarm for an empty/unreadable rule
    # set silently bypassing enforcement.
    if summary.compliant is None:
        _record_no_verdict_accept(mode)
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
