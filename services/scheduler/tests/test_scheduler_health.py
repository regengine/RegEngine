"""Regression test: scheduler /health must reflect leadership and scrape state.

The standalone scheduler entrypoint (`services/scheduler/main.py`) always
answered `{"status":"healthy"}` with HTTP 200, even when the scheduler was
dead (shut down while leader) or every scrape was failing. These tests drive
`HealthHandler._handle_health` with stub services covering standby, healthy
leader, degraded, and dead states.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import main as scheduler_main
from app.models import ScrapeResult, SourceType


def _scrape_result(*, success: bool, source: SourceType = SourceType.FDA_RECALL) -> ScrapeResult:
    return ScrapeResult(
        source_type=source,
        success=success,
        items_found=3 if success else 0,
        error_message=None if success else "connection refused",
        scraped_at=datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def _service(*, is_leader: bool, running: bool, results: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        scheduler=SimpleNamespace(running=running),
        distributed_context=SimpleNamespace(_is_leader=is_leader),
        last_results=dict(results or {}),
    )


def _get_health(service) -> tuple[int, dict]:
    """Invoke the handler without a socket; return (http status, parsed body)."""
    handler = scheduler_main.HealthHandler.__new__(scheduler_main.HealthHandler)
    handler.scheduler_service = service
    captured: dict = {}
    body = io.BytesIO()

    handler.send_response = lambda code: captured.setdefault("status", code)  # noqa: E731
    handler.send_header = lambda *args: None  # noqa: E731
    handler.end_headers = lambda: None  # noqa: E731
    handler.wfile = body

    handler._handle_health()
    return captured["status"], json.loads(body.getvalue().decode())


class TestSchedulerHealth:
    def test_standby_reports_leadership_not_healthy(self):
        status, payload = _get_health(_service(is_leader=False, running=False))

        assert status == 200
        assert payload["service"] == "scheduler"
        assert payload["is_leader"] is False
        assert payload["status"] != "healthy"

    def test_healthy_leader_reports_success_state(self):
        service = _service(
            is_leader=True,
            running=True,
            results={SourceType.FDA_RECALL: _scrape_result(success=True)},
        )
        status, payload = _get_health(service)

        assert status == 200
        assert payload["status"] == "healthy"
        assert payload["is_leader"] is True
        assert payload["scheduler_running"] is True
        assert payload["last_success_at"] is not None

    def test_partially_failing_leader_is_degraded(self):
        service = _service(
            is_leader=True,
            running=True,
            results={
                SourceType.FDA_RECALL: _scrape_result(success=True),
                SourceType.FDA_WARNING_LETTER: _scrape_result(success=False, source=SourceType.FDA_WARNING_LETTER),
            },
        )
        status, payload = _get_health(service)

        assert status == 200
        assert payload["status"] == "degraded"

    def test_all_scrapes_failing_is_unhealthy(self):
        service = _service(
            is_leader=True,
            running=True,
            results={SourceType.FDA_RECALL: _scrape_result(success=False)},
        )
        status, payload = _get_health(service)

        assert status == 503
        assert payload["status"] == "unhealthy"

    def test_dead_leader_scheduler_stopped_is_unhealthy(self):
        service = _service(
            is_leader=True,
            running=False,
            results={SourceType.FDA_RECALL: _scrape_result(success=True)},
        )
        status, payload = _get_health(service)

        assert status == 503
        assert payload["status"] == "unhealthy"

    def test_starting_service_is_not_healthy(self):
        status, payload = _get_health(None)

        assert status == 200
        assert payload["status"] != "healthy"
        assert payload["is_leader"] is False
