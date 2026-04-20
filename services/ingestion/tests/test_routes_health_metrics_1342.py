"""Unit tests for ``app.routes_health_metrics`` — issue #1342.

Covers the extracted health-check route that replaced the hand-rolled
``/metrics`` endpoint after #1325 silenced production scraping.

Branches pinned:
  - Kafka unconfigured (empty or local dev value) → "healthy" + "not_configured"
  - Kafka configured + available → "healthy" + "available"
  - Kafka configured + unavailable → "degraded" + non-available status,
    and the warning log fires with the kafka error message
  - The local-dev sentinels ``redpanda:9092`` and ``localhost:9092`` are
    treated as *unconfigured* (we don't want monitoring to scream
    "degraded" in a laptop dev loop)
  - Router exposes a single GET /health route with the "health-metrics" tag

Stubs ``shared.kafka_consumer_base`` and ``app.config.get_settings`` so
the test doesn't require a real Kafka cluster or full Pydantic settings
boot.  Re-installs stubs in an autouse fixture to survive the root
conftest's ``app.*`` eviction sweep.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


# ---------------------------------------------------------------------------
# Stub shared.kafka_consumer_base — only kafka_health_check is consumed.
# ---------------------------------------------------------------------------

_kafka_health_calls: list[dict[str, Any]] = []
_kafka_health_result: dict[str, Any] = {"status": "available", "error": None}


def _fake_kafka_health_check(*, bootstrap_servers: str, timeout: float) -> dict[str, Any]:
    _kafka_health_calls.append(
        {"bootstrap_servers": bootstrap_servers, "timeout": timeout}
    )
    return dict(_kafka_health_result)


# ``shared`` is a real top-level package on sys.path; we only need to
# override ``shared.kafka_consumer_base``. Import the package first so
# the submodule attribute binding lines up, then slot in the stub.
import shared as _shared_pkg  # noqa: E402

_kafka_mod = ModuleType("shared.kafka_consumer_base")
_kafka_mod.kafka_health_check = _fake_kafka_health_check
_kafka_mod.__file__ = str(service_dir / "shared_kafka_consumer_base.py")
sys.modules["shared.kafka_consumer_base"] = _kafka_mod
_shared_pkg.kafka_consumer_base = _kafka_mod  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Stub app.config.get_settings — the real one boots Pydantic settings
# from env, which is more than we need. Return a SimpleNamespace with
# the one attribute the route consumes.
# ---------------------------------------------------------------------------

_fake_settings = SimpleNamespace(kafka_bootstrap_servers="kafka.prod:9092")


def _fake_get_settings():
    return _fake_settings


_config_stub = ModuleType("app.config")
_config_stub.get_settings = _fake_get_settings
_config_stub.__file__ = str(service_dir / "app" / "config.py")
sys.modules["app.config"] = _config_stub

import app as _app_pkg  # noqa: E402
_app_pkg.config = _config_stub


from app import routes_health_metrics as rhm  # noqa: E402
from app.routes_health_metrics import health, router  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Re-install stubs evicted by the root conftest + reset mutable state."""
    sys.modules["shared.kafka_consumer_base"] = _kafka_mod
    sys.modules["app.config"] = _config_stub

    # Re-pin into the route module in case a reload swapped it.
    monkeypatch.setattr(rhm, "kafka_health_check", _fake_kafka_health_check,
                        raising=False)
    monkeypatch.setattr(rhm, "get_settings", _fake_get_settings, raising=False)

    _kafka_health_calls.clear()
    # Reset to default "available"; individual tests override as needed.
    _kafka_health_result.clear()
    _kafka_health_result.update({"status": "available", "error": None})

    # Clear env var between tests so we don't leak state.
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    yield


# ---------------------------------------------------------------------------
# /health — Kafka unconfigured / dev sentinels
# ---------------------------------------------------------------------------


class TestHealthKafkaUnconfigured:
    def test_empty_env_returns_healthy_and_not_configured(self, monkeypatch):
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "")
        result = health()
        assert result == {
            "status": "healthy",
            "service": "ingestion-service",
            "kafka": "not_configured",
        }
        # kafka_health_check must not be called when unconfigured.
        assert _kafka_health_calls == []

    def test_missing_env_returns_healthy_and_not_configured(self):
        # KAFKA_BOOTSTRAP_SERVERS not set at all.
        result = health()
        assert result["status"] == "healthy"
        assert result["kafka"] == "not_configured"
        assert _kafka_health_calls == []

    def test_redpanda_dev_sentinel_treated_as_unconfigured(self, monkeypatch):
        # Dev-loop sentinels must NOT cause a "degraded" status —
        # that would make laptop dev screen explode with alerts.
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
        result = health()
        assert result["status"] == "healthy"
        assert result["kafka"] == "not_configured"
        assert _kafka_health_calls == []

    def test_localhost_dev_sentinel_treated_as_unconfigured(self, monkeypatch):
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        result = health()
        assert result["status"] == "healthy"
        assert result["kafka"] == "not_configured"
        assert _kafka_health_calls == []


# ---------------------------------------------------------------------------
# /health — Kafka configured, reachable
# ---------------------------------------------------------------------------


class TestHealthKafkaAvailable:
    def test_prod_kafka_available_returns_healthy(self, monkeypatch):
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.prod:9092")
        _kafka_health_result.update({"status": "available", "error": None})

        result = health()
        assert result == {
            "status": "healthy",
            "service": "ingestion-service",
            "kafka": "available",
        }

    def test_forwards_configured_bootstrap_servers_and_timeout(self, monkeypatch):
        # Critical contract: the health check must use the configured
        # Kafka servers, not whatever happens to be in os.environ —
        # the settings object is the source of truth.
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.prod:9092")
        health()
        assert len(_kafka_health_calls) == 1
        call = _kafka_health_calls[0]
        assert call["bootstrap_servers"] == "kafka.prod:9092"
        # Timeout is a hard 3.0s — slow-starting kafkas shouldn't block
        # the LB health probe.
        assert call["timeout"] == 3.0


# ---------------------------------------------------------------------------
# /health — Kafka configured, unreachable
# ---------------------------------------------------------------------------


class TestHealthKafkaUnavailable:
    def test_unavailable_downgrades_to_degraded(self, monkeypatch):
        # Degraded (not failed) is the right status — #1325 commentary:
        # the LB should keep routing traffic even when Kafka is sick,
        # because the ingest API has degraded-mode fallbacks.
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.prod:9092")
        _kafka_health_result.update({"status": "unavailable", "error": "timeout"})

        result = health()
        assert result == {
            "status": "degraded",
            "service": "ingestion-service",
            "kafka": "unavailable",
        }

    def test_unknown_status_also_degrades(self, monkeypatch):
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.prod:9092")
        _kafka_health_result.update({"status": "unknown"})

        result = health()
        assert result["status"] == "degraded"
        assert result["kafka"] == "unknown"

    def test_logs_warning_with_kafka_error(self, monkeypatch, caplog):
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.prod:9092")
        _kafka_health_result.update(
            {"status": "unavailable", "error": "broker connection refused"}
        )

        with caplog.at_level(logging.WARNING, logger=rhm.logger.name):
            health()

        # Find our specific warning line.
        matching = [
            rec for rec in caplog.records
            if "ingestion_health_kafka_unavailable" in rec.getMessage()
        ]
        assert matching, (
            f"Expected kafka warning, got records: "
            f"{[r.getMessage() for r in caplog.records]}"
        )
        assert "broker connection refused" in matching[0].getMessage()

    def test_unavailable_missing_error_logs_unknown(self, monkeypatch, caplog):
        # The .get("error", "unknown") fallback protects against kafka
        # health checks that set status=unavailable but forgot to
        # attach an error — the log must still fire with "unknown"
        # rather than crash with KeyError.
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.prod:9092")
        _kafka_health_result.clear()
        _kafka_health_result["status"] = "unavailable"
        # note: no "error" key

        with caplog.at_level(logging.WARNING, logger=rhm.logger.name):
            result = health()

        assert result["status"] == "degraded"
        matching = [
            rec for rec in caplog.records
            if "ingestion_health_kafka_unavailable" in rec.getMessage()
        ]
        assert matching
        assert "unknown" in matching[0].getMessage()


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_router_exposes_single_health_route(self):
        paths = {r.path for r in router.routes}
        assert "/health" in paths

    def test_health_route_is_get_only(self):
        health_routes = [r for r in router.routes if r.path == "/health"]
        assert len(health_routes) == 1
        assert health_routes[0].methods == {"GET"}

    def test_router_uses_health_metrics_tag(self):
        # Tagging lets the OpenAPI spec group endpoints; drift here
        # breaks any docs bot that filters by tag.
        assert router.tags == ["health-metrics"]
