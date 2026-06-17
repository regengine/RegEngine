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
