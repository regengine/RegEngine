"""Auth-guarded scheduler diagnostic for the consolidated monolith.

The standalone scheduler entrypoint exposed an ``X-Metrics-Key``-gated
``/status`` surface (``services/scheduler/main.py:_handle_status``) returning
circuit-breaker state and per-source last-scrape results. That entrypoint
refuses to boot in production (the monolith runs the scheduler in-process via
``server.workers.embedded_scheduler``), so the diagnostic was lost. This
router restores it on ``GET /v1/scheduler/status``.

Multi-worker caveat: gunicorn runs ``WEB_CONCURRENCY`` workers and exactly one
holds the PostgreSQL advisory lock and drives the jobs. Only that leader has
live ``circuit_registry`` / ``last_results`` state in its process. A request
load-balanced to any other worker returns ``{"status": "standby"}``. Poll until
the leader answers, or rely on the Prometheus ``/metrics`` path for aggregate
job-failure visibility.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from shared.observability.metrics_auth import require_metrics_key

router = APIRouter(tags=["System"])


def _disabled_status() -> dict:
    return {"service": "scheduler", "status": "disabled"}


def _standby_status() -> dict:
    return {"service": "scheduler", "status": "standby"}


def _starting_status() -> dict:
    return {"service": "scheduler", "status": "starting"}


def _serialize_last_scrapes(service) -> dict:
    return {
        source_type.value: {
            "success": result.success,
            "count": result.items_found,
            "scraped_at": result.scraped_at.isoformat(),
            "error": result.error_message if not result.success else None,
            # #1140: surface soft-failure warnings (e.g.
            # parser_mismatch_suspected) even when success=True.
            "warnings": list(getattr(result, "warnings", []) or []),
        }
        for source_type, result in service.last_results.items()
    }


def _webhook_dlq_status(service) -> dict:
    """#2510: report whether the webhook dead-letter queue is durable.

    When ``WEBHOOK_URLS`` is set but ``WEBHOOK_OUTBOX_PATH`` is empty, failed
    deliveries of HIGH/CRITICAL alerts live only in process memory and are lost
    on the next restart. Surface that here so the footgun is visible without
    grepping startup logs.
    """
    # A live SchedulerService always carries .settings, but stay defensive: a
    # leader whose service object predates settings (or a future caller) must
    # not 500 the whole diagnostic route just to report the DLQ status.
    settings = getattr(service, "settings", None)
    if settings is None:
        return {
            "urls_configured": False,
            "persistence_enabled": False,
            "outbox_path": None,
            "at_risk": False,
        }
    urls_configured = bool(settings.webhook_url_list)
    persistent = bool(settings.webhook_outbox_path)
    # Live count of failed deliveries with no durable retry behind them.
    # A configured outbox path can still lose entries when the append
    # itself fails (disk error), so settings alone cannot prove safety.
    unpersisted = 0
    getter = getattr(getattr(service, "notifier", None), "unpersisted_dead_letter_count", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = None
        if isinstance(value, int):
            unpersisted = value
    return {
        "urls_configured": urls_configured,
        "persistence_enabled": persistent,
        "outbox_path": settings.webhook_outbox_path or None,
        "unpersisted_dead_letter_count": unpersisted,
        # Only a problem once webhooks are actually enabled, plus any
        # live unpersisted loss regardless of how the path is configured.
        "at_risk": (urls_configured and not persistent) or unpersisted > 0,
    }


def _running_status(service) -> dict:
    # Import the registry lazily so importing this module never drags in the
    # scheduler app package until a leader can report live diagnostics.
    from services.scheduler.app.circuit_breaker import circuit_registry

    return {
        "service": "scheduler",
        "status": "running",
        "circuit_breakers": circuit_registry.get_all_status(),
        "last_scrapes": _serialize_last_scrapes(service),
        "webhook_dlq": _webhook_dlq_status(service),
    }


def _scheduler_status_payload(runner) -> dict:
    if runner is None:
        # Scheduler disabled on this deploy (SCHEDULER_EMBEDDED=0 / non-prod).
        return _disabled_status()

    if not runner.is_leader:
        return _standby_status()

    service = runner.current_service
    if service is None:
        return _starting_status()

    return _running_status(service)


@router.get(
    "/v1/scheduler/status",
    include_in_schema=False,
    dependencies=[Depends(require_metrics_key)],
)
async def scheduler_status(request: Request) -> dict:
    """Return embedded-scheduler diagnostics (leader-only, X-Metrics-Key gated)."""
    runner = getattr(request.app.state, "embedded_scheduler", None)
    return _scheduler_status_payload(runner)
