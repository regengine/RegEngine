"""Prometheus metrics for the webhook ingest path (#1245, F-5) plus the
replay-rejection / HMAC-skip recorders that emit them.

Code moved verbatim from the original ``webhook_router_v2.py``. The
mutable rate-limit gate ``_last_hmac_skip_warn_at`` and the counter
objects live on the package namespace (``_pkg``) so tests that reset or
patch ``app.webhook_router_v2.<attr>`` keep working exactly as before.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

_pkg = sys.modules[__package__]


# ── Prometheus metric (#1245) ──────────────────────────────────────────────
# The replay-window check itself blocks the stale/future-replay vector; the
# metric makes it observable in prod. Without a counter, an SRE can't tell
# whether rejections are a steady-state partner-clock-skew issue, a surge
# from one bad integration, or an active replay attack.
try:  # pragma: no cover - metrics are best-effort; never break ingest on registry error
    from prometheus_client import REGISTRY, Counter

    def _matches_registered_name(collector_name: str, requested: str) -> bool:
        """Prometheus strips ``_total`` from Counter names internally, so
        a Counter requested as ``foo_total`` ends up with ``_name='foo'``.
        Compare both forms so the fallback-lookup works regardless of
        which suffix is present in either string."""
        if not collector_name:
            return False
        a = collector_name[:-6] if collector_name.endswith("_total") else collector_name
        b = requested[:-6] if requested.endswith("_total") else requested
        return a == b

    def _get_or_create_counter(name, documentation, labelnames):
        try:
            return Counter(name, documentation, labelnames)
        except ValueError:
            # Already registered (common during pytest re-imports or
            # multi-path imports).
            for collector in list(REGISTRY._collector_to_names):
                if _matches_registered_name(
                    getattr(collector, "_name", None), name
                ):
                    return collector
            raise

    WEBHOOK_REPLAY_REJECTED = _get_or_create_counter(
        "webhook_replay_rejected_total",
        "Webhook ingest events rejected by the replay-window check (#1245)",
        ["reason", "age_bucket"],
    )
    # F-5: also register the HMAC-skip counter while the helper is in scope.
    WEBHOOK_HMAC_SKIPPED = _get_or_create_counter(
        "webhook_hmac_verification_skipped_total",
        "Webhook ingest requests where HMAC verification was skipped because "
        "WEBHOOK_HMAC_SECRET is unset (F-5, fail-open visibility).",
        ["reason"],
    )
    _WEBHOOK_METRICS_ENABLED = True
except Exception as _wh_metrics_exc:  # pragma: no cover
    _pkg.logger.debug("webhook_replay_metric_init_failed: %s", _wh_metrics_exc)
    WEBHOOK_REPLAY_REJECTED = None
    WEBHOOK_HMAC_SKIPPED = None
    _WEBHOOK_METRICS_ENABLED = False


def _record_hmac_skip() -> None:
    """F-5: increment HMAC-skip metric + emit rate-limited WARN.

    Rate-limited to one log line per minute to avoid flooding ingest logs in a
    busy partner integration. The metric counter is incremented on every skip
    so SREs still get accurate counts.

    The ``_last_hmac_skip_warn_at`` gate lives on the package module (the
    original module's ``global``) so tests can reset it via
    ``webhook_router_v2._last_hmac_skip_warn_at = 0.0``.
    """
    if _pkg.WEBHOOK_HMAC_SKIPPED is not None:
        try:
            _pkg.WEBHOOK_HMAC_SKIPPED.labels(reason="secret_unset").inc()
        except Exception:  # pragma: no cover
            pass
    now = time.monotonic()
    if now - _pkg._last_hmac_skip_warn_at >= _pkg._HMAC_SKIP_WARN_INTERVAL_SECS:
        _pkg._last_hmac_skip_warn_at = now
        _pkg.logger.warning(
            "webhook_hmac_verification_skipped",
            reason="WEBHOOK_HMAC_SECRET unset; webhook signatures NOT verified",
            mitigation="Set WEBHOOK_HMAC_SECRET in environment to enforce signing",
        )


def _classify_replay_rejection(timestamp: str) -> tuple[str, str]:
    """Return ``(reason, age_bucket)`` for metric labelling.

    ``reason`` is one of ``"stale"`` / ``"future"`` / ``"unparseable"``.
    ``age_bucket`` is a coarse, bounded-cardinality bucket of how far
    off the event timestamp is from now. Using buckets rather than raw
    offsets keeps Prometheus label cardinality finite regardless of
    hostile input.

    Both are string literals from a closed set — nothing user-supplied
    reaches the label values.
    """
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return ("unparseable", "na")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = dt - now

    if delta.total_seconds() > 0:
        hours = delta.total_seconds() / 3600
        # Future bucket: how far in the future
        if hours <= 48:
            return ("future", "lt_48h")
        if hours <= 24 * 30:
            return ("future", "lt_30d")
        return ("future", "gte_30d")

    # Stale path
    days = (-delta).total_seconds() / 86400
    if days <= 180:
        return ("stale", "lt_180d")
    if days <= 365:
        return ("stale", "lt_1y")
    return ("stale", "gte_1y")


def _record_replay_rejection(timestamp: str) -> None:
    """Best-effort metric emission on replay-window rejection. Never
    raises — a metric-registry blip must not fail the ingest path."""
    if not _pkg._WEBHOOK_METRICS_ENABLED or _pkg.WEBHOOK_REPLAY_REJECTED is None:
        return
    try:
        reason, age_bucket = _pkg._classify_replay_rejection(timestamp)
        _pkg.WEBHOOK_REPLAY_REJECTED.labels(
            reason=reason, age_bucket=age_bucket
        ).inc()
    except Exception:  # pragma: no cover
        pass
