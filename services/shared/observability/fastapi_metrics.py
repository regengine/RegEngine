"""Prometheus RED metrics exposition for FastAPI services.

Single source of truth for ``/metrics`` across every RegEngine FastAPI app.
Mounts ``prometheus_fastapi_instrumentator`` with a **cardinality-safe** label
set (method + status class + route template only — never tenant_id, user_id,
or raw path) so scraping Prometheus stays bounded no matter how many tenants
we onboard.

The endpoint is guarded by a shared API key header (``X-Metrics-Key``) that
matches ``METRICS_API_KEY`` in the environment. This matches the existing
``shared.observability.metrics_auth.require_metrics_key`` pattern used by
hand-rolled ``/metrics`` handlers (graph, admin legacy, scheduler).

Usage (FastAPI):
    from shared.observability.fastapi_metrics import install_metrics

    install_metrics(app, service_name="ingestion-service")

Called once, *before* ``app.include_router(...)`` so instrumentation picks up
every route. Safe to call multiple times (idempotent).
"""

from __future__ import annotations

import os
from typing import Optional

import structlog
from fastapi import FastAPI

logger = structlog.get_logger("observability.metrics")

# Track whether install_metrics has run on a given FastAPI instance so we
# don't double-mount the instrumentator (which would raise at scrape time).
_INSTALLED_FLAG = "_regengine_metrics_installed"

# Business counters documented in #1325. Exposed at module level so both
# route handlers and background jobs can increment without a second import.
# Declared lazily on first import so tests that reload modules don't hit
# "already registered" errors from the global prometheus registry.
_BUSINESS_COUNTERS_CACHE: dict[str, object] = {}


def _get_business_counter(name: str, description: str) -> Optional[object]:
    """Return a Counter, reusing the one already in the default registry."""
    if name in _BUSINESS_COUNTERS_CACHE:
        return _BUSINESS_COUNTERS_CACHE[name]
    try:
        from prometheus_client import REGISTRY, Counter

        try:
            counter = Counter(name, description)
        except ValueError:
            # Already registered (test re-imports, hot-reload).
            counter = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if counter is not None:
            _BUSINESS_COUNTERS_CACHE[name] = counter
        return counter
    except ImportError:
        logger.warning("prometheus_client_not_installed")
        return None


def install_metrics(
    app: FastAPI,
    service_name: str,
    *,
    metrics_path: Optional[str] = "/metrics",
    require_auth: bool = True,
) -> None:
    """Mount Prometheus RED metrics on ``metrics_path``.

    Args:
        app: The FastAPI app to instrument.
        service_name: Appears as the ``service`` label on every metric.
        metrics_path: HTTP path to expose metrics on. Default ``/metrics``.
            Pass ``None`` to instrument the app without exposing an
            endpoint (useful when the service has its own handler that
            calls ``prometheus_client.generate_latest`` directly, e.g.
            the scheduler's combined handler).
        require_auth: When True (default), wrap the endpoint with the
            ``X-Metrics-Key`` guard so Prometheus scrapers must be trusted.
            Set False only in tests.

    Behaviour:
        - Adds default RED metrics: ``http_requests_total``,
          ``http_request_duration_seconds``, ``http_request_size_bytes``,
          ``http_response_size_bytes``.
        - Labels are the route **template** (``/users/{user_id}``), the HTTP
          method, and status code class — no raw paths, no tenant IDs.
        - Seeds the module-level business counters (``regengine_events_ingested_total``
          etc.) into the registry so they're visible on the first scrape even
          before any event flows through.
    """
    if getattr(app.state, _INSTALLED_FLAG, False):
        # Idempotent — safe to call twice during hot-reload.
        return

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        logger.warning(
            "prometheus_fastapi_instrumentator_not_installed",
            service=service_name,
            note="Skipping /metrics — add prometheus-fastapi-instrumentator to requirements.",
        )
        return

    # Service label is applied via prometheus_client's global default — use an
    # env var that every Prometheus scrape can pick up via relabel_config.
    os.environ.setdefault("REGENGINE_SERVICE_NAME", service_name)

    instrumentator = Instrumentator(
        should_group_status_codes=True,    # 2xx/3xx/4xx/5xx — not per-status
        should_ignore_untemplated=True,    # drop raw paths, keep templates
        should_group_untemplated=True,
        should_instrument_requests_inprogress=False,
        excluded_handlers=["/metrics", "/health", "/ready"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="http_requests_inprogress",
        inprogress_labels=False,
    )

    # Add the default RED metrics. The library chooses cardinality-safe labels
    # (handler template, method, status class) by default.
    instrumentator.instrument(app)

    # Expose the endpoint. When require_auth, wrap in a dependency via Starlette
    # route decoration — the library's expose() accepts a Response callable.
    if metrics_path is not None:
        if require_auth:
            _expose_with_auth(app, instrumentator, metrics_path)
        else:
            instrumentator.expose(
                app,
                endpoint=metrics_path,
                include_in_schema=False,
                should_gzip=False,
            )

    # Seed business counters so they're visible on the first scrape.
    _get_business_counter(
        "regengine_events_ingested_total",
        "Total canonical events ingested across all sources.",
    )
    _get_business_counter(
        "regengine_auth_failures_total",
        "Total authentication failures (bad password / invalid API key / expired JWT).",
    )
    _get_business_counter(
        "regengine_compliance_evaluations_total",
        "Total FSMA compliance rule evaluations executed.",
    )
    _get_business_counter(
        "regengine_nlp_extractions_total",
        "Total NLP extraction events published to downstream topics.",
    )

    setattr(app.state, _INSTALLED_FLAG, True)
    logger.info(
        "metrics_endpoint_installed",
        service=service_name,
        path=metrics_path,
        auth=require_auth,
    )


def _expose_with_auth(
    app: FastAPI,
    instrumentator: "Instrumentator",  # type: ignore[name-defined]  # noqa: F821
    metrics_path: str,
) -> None:
    """Attach the instrumentator output to an auth-guarded route."""
    from fastapi import Depends, Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    from shared.observability.metrics_auth import require_metrics_key

    @app.get(
        metrics_path,
        include_in_schema=False,
        dependencies=[Depends(require_metrics_key)],
    )
    def metrics() -> Response:  # noqa: D401 — FastAPI endpoint
        """Prometheus exposition (guarded by X-Metrics-Key)."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


__all__ = ["install_metrics"]
