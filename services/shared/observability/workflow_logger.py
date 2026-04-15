"""
Structured workflow logging for production-critical paths.

Provides a context manager that automatically emits structured log entries
with all PRD-required fields at workflow boundaries:
    tenant_id, facility_id, correlation_id, workflow, outcome, duration_ms, error_category

Usage:
    from shared.observability.workflow_logger import workflow_span

    async def ingest_epcis_event(tenant_id: str, event: dict):
        with workflow_span("ingestion", tenant_id=tenant_id) as span:
            result = do_work(event)
            span.set_outcome("pass", record_count=len(result))
            return result

The context manager logs a structured entry on exit with timing and outcome.
On unhandled exceptions, it logs outcome="error" with the error_category.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Optional

import structlog

from shared.observability.correlation import get_correlation_id

logger = structlog.get_logger("workflow")


class WorkflowSpan:
    """Accumulates structured fields during a workflow span."""

    __slots__ = ("workflow", "tenant_id", "facility_id", "outcome",
                 "error_category", "extras", "_start")

    def __init__(self, workflow: str, tenant_id: str = "",
                 facility_id: str = ""):
        self.workflow = workflow
        self.tenant_id = tenant_id
        self.facility_id = facility_id
        self.outcome: str = "unknown"
        self.error_category: Optional[str] = None
        self.extras: dict[str, Any] = {}
        self._start = time.monotonic()

    def set_outcome(self, outcome: str, **extra: Any) -> None:
        """Set the workflow outcome and any extra structured fields."""
        self.outcome = outcome
        self.extras.update(extra)

    @property
    def duration_ms(self) -> float:
        return round((time.monotonic() - self._start) * 1000, 1)


@contextmanager
def workflow_span(
    workflow: str,
    *,
    tenant_id: str = "",
    facility_id: str = "",
):
    """Context manager that emits a structured log entry on exit.

    On normal exit: logs at INFO with outcome set via span.set_outcome().
    On exception: logs at ERROR with outcome="error" and error_category.
    """
    span = WorkflowSpan(workflow, tenant_id, facility_id)

    try:
        yield span
    except Exception as exc:
        span.outcome = "error"
        span.error_category = type(exc).__name__
        span.extras["error"] = str(exc)[:500]
        logger.error(
            f"{workflow}_failed",
            workflow=workflow,
            tenant_id=span.tenant_id,
            facility_id=span.facility_id,
            correlation_id=get_correlation_id() or "",
            outcome="error",
            error_category=span.error_category,
            duration_ms=span.duration_ms,
            **span.extras,
        )
        raise
    else:
        logger.info(
            f"{workflow}_complete",
            workflow=workflow,
            tenant_id=span.tenant_id,
            facility_id=span.facility_id,
            correlation_id=get_correlation_id() or "",
            outcome=span.outcome,
            duration_ms=span.duration_ms,
            **span.extras,
        )
