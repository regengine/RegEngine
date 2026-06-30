"""Lock the monolith ↔ service observability/throttle parity fixes.

The production monolith (``server.main``) is the only deployed container,
but it was assembled without several cross-cutting capabilities that every
legacy per-service entrypoint installed. These tests pin the remediations so
the drift cannot silently reopen:

* Prometheus ``/metrics`` is mounted and auth-guarded (#1325).
* ``TenantRateLimitMiddleware`` default floor is 100 rpm (matches the
  consolidated services + documented prod default), not 200.
* The boot-time object-storage probe is wired into the lifespan (#2348).
* The ``X-FSMA-204-Traceability`` response header is stamped on every
  response (admin-route parity).
* The embedded-scheduler ``/v1/scheduler/status`` diagnostic is restored,
  auth-guarded and leader-only (#1255).
"""

from __future__ import annotations

import importlib
import inspect

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def server_main():
    return importlib.import_module("server.main")


# ---------------------------------------------------------------------------
# #1325 — Prometheus /metrics is mounted and auth-guarded
# ---------------------------------------------------------------------------


def test_metrics_route_is_mounted(server_main):
    paths = {getattr(r, "path", None) for r in server_main.app.router.routes}
    assert "/metrics" in paths, "monolith must expose /metrics (install_metrics not wired)"


def test_metrics_requires_auth(server_main):
    """Without a valid X-Metrics-Key the endpoint is forbidden — Prometheus
    series must never be publicly scrapeable."""
    client = TestClient(server_main.app)
    assert client.get("/metrics").status_code == 403
    assert client.get("/metrics", headers={"X-Metrics-Key": "wrong"}).status_code == 403


def test_metrics_returns_exposition_with_valid_key(server_main, monkeypatch):
    """With the configured key the endpoint returns Prometheus exposition
    including the seeded ``regengine_*`` business counters."""
    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "test-metrics-key")

    client = TestClient(server_main.app)
    # Fire one instrumented request so RED series are populated too.
    client.get("/health")

    resp = client.get("/metrics", headers={"X-Metrics-Key": "test-metrics-key"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    # Seeded at install time, so deterministically present on first scrape.
    assert "regengine_events_ingested_total" in resp.text


# ---------------------------------------------------------------------------
# Tenant rate-limit floor is 100 rpm (not 200)
# ---------------------------------------------------------------------------


def test_tenant_rate_limit_default_is_100_rpm(server_main):
    entry = next(m for m in server_main.app.user_middleware if m.cls.__name__ == "TenantRateLimitMiddleware")
    assert entry.kwargs.get("default_rpm") == 100, (
        "monolith default_rpm must match the consolidated services' 100 rpm floor"
    )


# ---------------------------------------------------------------------------
# #2348 — boot-time object-storage probe wired into the lifespan
# ---------------------------------------------------------------------------


def test_lifespan_probes_object_storage_config(server_main):
    """Source-level check (mirrors test_server_import_smoke's lifespan-wiring
    pattern) so we don't need a live DB to enter the full lifespan."""
    src = inspect.getsource(server_main.lifespan)
    assert "is_object_storage_configured" in src
    assert "object_storage_disabled" in src
    # Must use the fully-qualified import path in the monolith, not the
    # service-relative ``app.s3_utils`` the standalone entrypoint uses.
    assert "services.ingestion.app.s3_utils" in src


# ---------------------------------------------------------------------------
# X-FSMA-204-Traceability response header parity
# ---------------------------------------------------------------------------


def test_fsma_traceability_header_on_responses(server_main):
    client = TestClient(server_main.app)
    resp = client.get("/health")
    assert resp.headers.get("X-FSMA-204-Traceability") == "true"


# ---------------------------------------------------------------------------
# #1255 — embedded-scheduler /status diagnostic (leader-only, auth-guarded)
# ---------------------------------------------------------------------------


class _FakeScrape:
    def __init__(self, *, success, items_found, scraped_at, error_message=None, warnings=None):
        self.success = success
        self.items_found = items_found
        self.scraped_at = scraped_at
        self.error_message = error_message
        self.warnings = warnings or []


class _FakeSource:
    def __init__(self, value):
        self.value = value


class _FakeService:
    def __init__(self, last_results):
        self.last_results = last_results


class _FakeRunner:
    def __init__(self, *, is_leader, current_service=None):
        self.is_leader = is_leader
        self.current_service = current_service


def test_scheduler_status_requires_auth(server_main):
    client = TestClient(server_main.app)
    assert client.get("/v1/scheduler/status").status_code == 403


def test_scheduler_status_rejects_wrong_metrics_key(server_main, monkeypatch):
    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "k")

    resp = TestClient(server_main.app).get("/v1/scheduler/status", headers={"X-Metrics-Key": "wrong"})
    assert resp.status_code == 403


def test_scheduler_status_disabled_when_no_runner(server_main, monkeypatch):
    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "k")
    # No runner on app.state (lifespan not entered) → disabled.
    monkeypatch.setattr(server_main.app.state, "embedded_scheduler", None, raising=False)

    resp = TestClient(server_main.app).get("/v1/scheduler/status", headers={"X-Metrics-Key": "k"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


def test_scheduler_status_standby_when_not_leader(server_main, monkeypatch):
    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "k")
    monkeypatch.setattr(server_main.app.state, "embedded_scheduler", _FakeRunner(is_leader=False), raising=False)

    resp = TestClient(server_main.app).get("/v1/scheduler/status", headers={"X-Metrics-Key": "k"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "standby"


def test_scheduler_status_starting_when_leader_has_no_service(server_main, monkeypatch):
    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "k")
    monkeypatch.setattr(
        server_main.app.state,
        "embedded_scheduler",
        _FakeRunner(is_leader=True, current_service=None),
        raising=False,
    )

    resp = TestClient(server_main.app).get("/v1/scheduler/status", headers={"X-Metrics-Key": "k"})
    assert resp.status_code == 200
    assert resp.json() == {"service": "scheduler", "status": "starting"}


def test_scheduler_status_leader_returns_circuit_and_scrape_state(server_main, monkeypatch):
    from datetime import datetime, timezone

    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "k")

    scraped = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    service = _FakeService(
        {
            _FakeSource("fda_recalls"): _FakeScrape(
                success=True, items_found=7, scraped_at=scraped, warnings=["parser_mismatch_suspected"]
            ),
            _FakeSource("import_alerts"): _FakeScrape(
                success=False, items_found=0, scraped_at=scraped, error_message="timeout"
            ),
        }
    )
    monkeypatch.setattr(
        server_main.app.state,
        "embedded_scheduler",
        _FakeRunner(is_leader=True, current_service=service),
        raising=False,
    )

    # The route imports circuit_registry lazily from this module at call time.
    import services.scheduler.app.circuit_breaker as cb

    class _FakeRegistry:
        def get_all_status(self):
            return {"fda_recalls": {"state": "closed"}}

    monkeypatch.setattr(cb, "circuit_registry", _FakeRegistry())

    resp = TestClient(server_main.app).get("/v1/scheduler/status", headers={"X-Metrics-Key": "k"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["circuit_breakers"] == {"fda_recalls": {"state": "closed"}}
    assert body["last_scrapes"]["fda_recalls"] == {
        "success": True,
        "count": 7,
        "scraped_at": scraped.isoformat(),
        "error": None,
        "warnings": ["parser_mismatch_suspected"],
    }
    assert body["last_scrapes"]["import_alerts"]["error"] == "timeout"
    # #2510: a service without settings must not 500 the diagnostic — the DLQ
    # block is reported defensively.
    assert body["webhook_dlq"]["at_risk"] is False


# ---------------------------------------------------------------------------
# #2517 — /api/v1/features is auth-gated and hidden from the schema
# ---------------------------------------------------------------------------


def test_features_requires_auth(server_main):
    """An unauthenticated caller must not learn the router topology. Without a
    valid X-Metrics-Key the endpoint is forbidden (mirrors /v1/scheduler/status)."""
    client = TestClient(server_main.app)
    assert client.get("/api/v1/features").status_code == 403


def test_features_rejects_wrong_metrics_key(server_main, monkeypatch):
    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "k")
    resp = TestClient(server_main.app).get("/api/v1/features", headers={"X-Metrics-Key": "wrong"})
    assert resp.status_code == 403


def test_features_returns_topology_with_valid_key(server_main, monkeypatch):
    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "k")
    resp = TestClient(server_main.app).get("/api/v1/features", headers={"X-Metrics-Key": "k"})
    assert resp.status_code == 200
    body = resp.json()
    # Full topology payload is only available to the authenticated caller.
    assert set(body) == {"enabled", "disabled", "auto_disabled", "experimental_enabled"}


def test_features_hidden_from_openapi_schema(server_main):
    """The route must not be advertised in the generated (non-prod) schema."""
    schema = server_main.app.openapi()
    assert "/api/v1/features" not in schema.get("paths", {})


def test_scheduler_status_reports_webhook_dlq_at_risk(server_main, monkeypatch):
    """#2510: when WEBHOOK_URLS is set but no durable outbox path is configured,
    /v1/scheduler/status surfaces webhook_dlq.at_risk=true so the in-memory-only
    footgun is visible without grepping startup logs."""
    import shared.observability.metrics_auth as metrics_auth

    monkeypatch.setattr(metrics_auth, "_METRICS_API_KEY", "k")

    class _Settings:
        webhook_url_list = ["https://hook.example.com/alerts"]
        webhook_outbox_path = ""

    service = _FakeService({})
    service.settings = _Settings()
    monkeypatch.setattr(
        server_main.app.state,
        "embedded_scheduler",
        _FakeRunner(is_leader=True, current_service=service),
        raising=False,
    )

    import services.scheduler.app.circuit_breaker as cb

    class _FakeRegistry:
        def get_all_status(self):
            return {}

    monkeypatch.setattr(cb, "circuit_registry", _FakeRegistry())

    resp = TestClient(server_main.app).get("/v1/scheduler/status", headers={"X-Metrics-Key": "k"})
    assert resp.status_code == 200
    dlq = resp.json()["webhook_dlq"]
    assert dlq["urls_configured"] is True
    assert dlq["persistence_enabled"] is False
    assert dlq["at_risk"] is True
