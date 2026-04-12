"""Redis health monitoring with Sentry alerting.

Captures Redis connection failures as Sentry events so the team gets
alerted when the system degrades to in-memory fallbacks.

This module is intentionally lightweight — it wraps Sentry's capture_message
with deduplication so we don't flood Sentry on sustained Redis outages.
"""

from __future__ import annotations

import time
from typing import Optional

import structlog

logger = structlog.get_logger("shared.redis_health")

# Deduplication: only send one Sentry alert per component per cooldown window
_last_alert_times: dict[str, float] = {}
_ALERT_COOLDOWN_SECONDS = 300  # 5 minutes between alerts per component


def report_redis_fallback(
    component: str,
    error: str,
    extra: Optional[dict] = None,
) -> None:
    """Report a Redis fallback event to Sentry and structured logs.

    Args:
        component: Which subsystem fell back (e.g. "rate_limiter", "circuit_breaker",
                   "jwt_key_registry")
        error: The original error string
        extra: Additional context to attach to the Sentry event
    """
    now = time.monotonic()
    last_alert = _last_alert_times.get(component, 0)

    # Always log (structured logging handles its own dedup/sampling)
    logger.warning(
        "redis_fallback_active",
        component=component,
        error=error,
        **(extra or {}),
    )

    # Deduplicate Sentry alerts
    if now - last_alert < _ALERT_COOLDOWN_SECONDS:
        return

    _last_alert_times[component] = now

    try:
        import sentry_sdk

        sentry_sdk.capture_message(
            f"Redis unavailable — {component} fell back to in-memory mode",
            level="warning",
            extras={
                "component": component,
                "error": error,
                **(extra or {}),
            },
            tags={
                "subsystem": "redis_health",
                "component": component,
            },
        )
    except Exception:
        # If Sentry itself is down, just log
        logger.debug("sentry_capture_failed", component=component)
