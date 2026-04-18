"""Tests for Prometheus /metrics exposition (#1325).

Covers:
* install_metrics mounts /metrics and it responds with Prometheus format.
* Auth guard — requests without X-Metrics-Key get 403.
* HTTP counters increment after traffic hits the app.
* install_metrics is idempotent (safe to call twice).
* metrics_path=None instruments without exposing an endpoint.

NOTE on test isolation: prometheus_client maintains a *global* registry —
if test A registers ``http_requests_total`` with labels bound to app A,
test B's app will increment the same counter but may not surface its
route template (the instrumentator's middleware captures the route per
app). The ``_reset_prometheus_registry`` fixture wipes the global
registry before each test so each build_app call starts clean. In
production there's one app per process, so this collision doesn't apply.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_prometheus_registry():
    """Clear the global prometheus registry between tests.

    Also invalidates the module-level business-counter cache so
    install_metrics re-creates them in the fresh registry.
    """
    from prometheus_client import REGISTRY

    # Unregister everything we can — skip built-in platform collectors
    collectors = list(REGISTRY._collector_to_names.keys())  # type: ignore[attr-defined]
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass

    # Wipe the business-counter cache so install_metrics re-seeds into
    # the now-clean registry.
    from shared.observability import fastapi_metrics as fm

    fm._BUSINESS_COUNTERS_CACHE.clear()

    yield


def _build_app(require_auth: bool = True, metrics_path: str | object = "/metrics") -> FastAPI:
    """Build a minimal FastAPI app with the shared metrics installer."""
    from shared.observability.fastapi_metrics import install_metrics

    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict:
        return {"ok": True}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("boom")

    kwargs = {"require_auth": require_auth}
    if metrics_path is not None or metrics_path is None:
        kwargs["metrics_path"] = metrics_path

    install_metrics(app, service_name="test-service", **kwargs)
    return app


# ---------------------------------------------------------------------------
# Exposition + auth
# ---------------------------------------------------------------------------


def test_metrics_endpoint_requires_auth_by_default(monkeypatch):
    monkeypatch.setenv("METRICS_API_KEY", "secret-scrape-key")
    # Reload the module-level key cache in metrics_auth
    import importlib

    import shared.observability.metrics_auth as ma

    importlib.reload(ma)

    app = _build_app(require_auth=True)
    client = TestClient(app)

    # No header — 403
    resp = client.get("/metrics")
    assert resp.status_code == 403

    # Wrong key — 403
    resp = client.get("/metrics", headers={"X-Metrics-Key": "wrong"})
    assert resp.status_code == 403

    # Correct key — 200 + Prometheus format
    resp = client.get("/metrics", headers={"X-Metrics-Key": "secret-scrape-key"})
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    # Default RED metrics should be present as soon as the endpoint is live.
    assert "http_request" in resp.text or "python_info" in resp.text


def test_metrics_endpoint_without_auth_in_tests(monkeypatch):
    """require_auth=False for unit tests — no header needed."""
    monkeypatch.delenv("METRICS_API_KEY", raising=False)

    app = _build_app(require_auth=False)
    client = TestClient(app)

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_http_counters_increment_after_traffic(monkeypatch):
    """Hit /hello a few times and confirm the counter shows up."""
    monkeypatch.delenv("METRICS_API_KEY", raising=False)

    app = _build_app(require_auth=False)
    client = TestClient(app)

    for _ in range(3):
        assert client.get("/hello").status_code == 200

    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text

    # prometheus_fastapi_instrumentator's default counter name is
    # http_requests_total. Accept either form since the library version
    # may change the prefix; the key assertion is "traffic is visible".
    assert any(token in body for token in ["http_requests_total", "http_request_duration_seconds"])
    # And the route template should appear as a label (not a literal path).
    assert "/hello" in body


def test_install_metrics_is_idempotent(monkeypatch):
    """Calling install_metrics twice on the same app must not raise."""
    monkeypatch.delenv("METRICS_API_KEY", raising=False)

    from shared.observability.fastapi_metrics import install_metrics

    app = FastAPI()
    install_metrics(app, service_name="test-service", require_auth=False)
    # Second call is a no-op
    install_metrics(app, service_name="test-service", require_auth=False)

    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_path_none_skips_endpoint(monkeypatch):
    """Scheduler-style: instrument the app but don't expose a second endpoint."""
    monkeypatch.delenv("METRICS_API_KEY", raising=False)

    from shared.observability.fastapi_metrics import install_metrics

    app = FastAPI()

    @app.get("/")
    def root() -> dict:
        return {"ok": True}

    install_metrics(app, service_name="scheduler-like", metrics_path=None)

    client = TestClient(app)
    # /metrics should not exist
    resp = client.get("/metrics")
    assert resp.status_code == 404
    # But the instrumentator is still measuring the other route
    assert client.get("/").status_code == 200


def test_business_counters_registered(monkeypatch):
    """The install_metrics helper seeds the regengine_* business counters."""
    monkeypatch.delenv("METRICS_API_KEY", raising=False)

    app = _build_app(require_auth=False)
    client = TestClient(app)

    resp = client.get("/metrics")
    body = resp.text
    # We don't require them to have non-zero values; we just want them
    # visible on the first scrape (they should be 0 until traffic flows).
    for name in [
        "regengine_events_ingested_total",
        "regengine_auth_failures_total",
        "regengine_compliance_evaluations_total",
        "regengine_nlp_extractions_total",
    ]:
        assert name in body, f"expected business counter {name!r} in /metrics output"
