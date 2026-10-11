"""QA deep-pass: scheduler status diagnostic units.

Exercises server/routes_scheduler_status.py payload builders directly with
fake runners/services, plus the HTTP wiring on a scratch FastAPI app (auth
dependency declared, metrics-key gating via dependency override). Fast and
deterministic, no network, no scheduler import at module load.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routes_scheduler_status import (
    _scheduler_status_payload,
    _serialize_last_scrapes,
    _webhook_dlq_status,
    router,
)


class _FakeSource:
    def __init__(self, value):
        self.value = value


def _results(**kwargs):
    return SimpleNamespace(last_results={_FakeSource(k): v for k, v in kwargs.items()})


def _scrape(*, success=True, count=3, error=None, warnings=()):
    return SimpleNamespace(
        success=success,
        items_found=count,
        scraped_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        error_message=error,
        warnings=list(warnings),
    )


def test_disabled_when_no_runner():
    assert _scheduler_status_payload(None) == {"service": "scheduler", "status": "disabled"}


def test_standby_when_not_leader():
    runner = SimpleNamespace(is_leader=False, current_service=object())
    assert _scheduler_status_payload(runner) == {"service": "scheduler", "status": "standby"}


def test_starting_when_leader_has_no_service():
    runner = SimpleNamespace(is_leader=True, current_service=None)
    assert _scheduler_status_payload(runner) == {"service": "scheduler", "status": "starting"}


def test_serialize_last_scrapes_reports_error_only_on_failure():
    scraped = _scrape(success=False, count=0, error="timeout")
    body = _serialize_last_scrapes(_results(src=scraped))
    assert body["src"]["error"] == "timeout"
    assert body["src"]["scraped_at"] == "2026-01-02T03:04:00+00:00"


def test_serialize_last_scrapes_hides_error_on_success_and_keeps_warnings():
    scraped = _scrape(success=True, error="stale", warnings=["parser_mismatch_suspected"])
    body = _serialize_last_scrapes(_results(src=scraped))
    assert body["src"]["error"] is None
    assert body["src"]["warnings"] == ["parser_mismatch_suspected"]


def test_webhook_dlq_without_settings_is_not_at_risk():
    body = _webhook_dlq_status(SimpleNamespace())
    assert body == {
        "urls_configured": False,
        "persistence_enabled": False,
        "outbox_path": None,
        "at_risk": False,
    }


def test_webhook_dlq_flags_memory_only_delivery():
    settings = SimpleNamespace(webhook_url_list=["https://hooks.example/x"], webhook_outbox_path="")
    body = _webhook_dlq_status(SimpleNamespace(settings=settings))
    assert body["urls_configured"] is True
    assert body["persistence_enabled"] is False
    assert body["at_risk"] is True


def test_webhook_dlq_quiet_when_persistent():
    settings = SimpleNamespace(webhook_url_list=["https://hooks.example/x"], webhook_outbox_path="/data/outbox")
    body = _webhook_dlq_status(SimpleNamespace(settings=settings))
    assert body["at_risk"] is False
    assert body["outbox_path"] == "/data/outbox"


def _wired_client(runner):
    app = FastAPI()
    app.state.embedded_scheduler = runner
    app.include_router(router)
    app.dependency_overrides = {}
    from shared.observability.metrics_auth import require_metrics_key

    app.dependency_overrides[require_metrics_key] = lambda: True
    return TestClient(app)


def test_route_is_hidden_from_schema():
    assert any(r.path == "/v1/scheduler/status" for r in router.routes)
    app = FastAPI()
    app.include_router(router)
    assert app.openapi()["paths"] == {}


def test_wired_disabled_status():
    resp = _wired_client(None).get("/v1/scheduler/status")
    assert resp.status_code == 200
    assert resp.json() == {"service": "scheduler", "status": "disabled"}
