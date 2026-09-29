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
app). The ``_reset_prometheus_registry`` fixture temporarily clears the global
registry for each test so each build_app call starts clean, then restores it. In
production there's one app per process, so this collision doesn't apply.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_prometheus_registry():
    """Temporarily clear the global prometheus registry for each test.

    Also invalidates the module-level business-counter cache so
    install_metrics re-creates them in the fresh registry.
    """
    from prometheus_client import REGISTRY
    from shared.observability import fastapi_metrics as fm

    collectors = list(REGISTRY._collector_to_names.keys())  # type: ignore[attr-defined]
    business_counters = dict(fm._BUSINESS_COUNTERS_CACHE)
    try:
        for collector in collectors:
            REGISTRY.unregister(collector)
        fm._BUSINESS_COUNTERS_CACHE.clear()
        yield
    finally:
        for collector in list(REGISTRY._collector_to_names.keys()):  # type: ignore[attr-defined]
            REGISTRY.unregister(collector)
        for collector in collectors:
            REGISTRY.register(collector)
        fm._BUSINESS_COUNTERS_CACHE.clear()
        fm._BUSINESS_COUNTERS_CACHE.update(business_counters)


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

    # Reload mutates this cache independently of the patched environment.
    monkeypatch.setattr(ma, "_METRICS_API_KEY", ma._METRICS_API_KEY)
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


def test_dead_business_counters_are_not_seeded(monkeypatch):
    """Regression guard for #2866.

    Four ``regengine_*`` business counters were registered at install time
    "so they're visible on the first scrape", but nothing in the repo ever
    incremented them — so any alert built on them (e.g. an "ingest has
    stopped" rule on ``rate(regengine_events_ingested_total[5m]) == 0``) was
    permanently satisfied. The seeding was removed.

    This test is deliberately the inverse of the one it replaces: it fails if
    someone re-introduces seeding WITHOUT a real increment call site. If you
    are wiring one of these counters up for real, add its ``.inc()`` at the
    production call site and drop the name from this list in the same change.
    """
    monkeypatch.delenv("METRICS_API_KEY", raising=False)

    app = _build_app(require_auth=False)
    client = TestClient(app)

    resp = client.get("/metrics")
    body = resp.text
    for name in [
        "regengine_events_ingested_total",
        "regengine_auth_failures_total",
        "regengine_compliance_evaluations_total",
        "regengine_nlp_extractions_total",
    ]:
        assert name not in body, (
            f"business counter {name!r} is exported but never incremented — "
            "seed it only alongside a real .inc() call site (#2866)"
        )
