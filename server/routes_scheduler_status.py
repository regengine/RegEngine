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


@router.get(
    "/v1/scheduler/status",
    include_in_schema=False,
    dependencies=[Depends(require_metrics_key)],
)
async def scheduler_status(request: Request) -> dict:
    """Return embedded-scheduler diagnostics (leader-only, X-Metrics-Key gated)."""
    runner = getattr(request.app.state, "embedded_scheduler", None)
    if runner is None:
        # Scheduler disabled on this deploy (SCHEDULER_EMBEDDED=0 / non-prod).
        return {"service": "scheduler", "status": "disabled"}

    if not runner.is_leader:
        return {"service": "scheduler", "status": "standby"}

    # Import the registry lazily so importing this module never drags in the
    # scheduler app package on workers that never reach the leader branch.
    from services.scheduler.app.circuit_breaker import circuit_registry

    service = runner.current_service
    return {
        "service": "scheduler",
        "status": "running",
        "circuit_breakers": circuit_registry.get_all_status(),
        "last_scrapes": {
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
        },
    }
