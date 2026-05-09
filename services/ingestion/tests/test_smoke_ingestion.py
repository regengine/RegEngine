"""Smoke tests for the ingestion service."""

import sys
from pathlib import Path

# Add service directory to path for imports to work
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("opentelemetry")

from fastapi.testclient import TestClient


def test_health(monkeypatch) -> None:
    try:
        from main import app
    except ModuleNotFoundError as exc:
        pytest.skip(
            f"ingestion smoke tests require optional dependency '{exc.name}'",
        )

    # The /health endpoint moved to app/routes_health_metrics.py (PR #2200's
    # routes split, plus the routes_health_metrics extraction noted in
    # routes.py). It only contacts Kafka via shared.kafka_consumer_base.
    # kafka_health_check when KAFKA_BOOTSTRAP_SERVERS is set to a non-default
    # value, so we force it unset to keep the smoke test hermetic. The old
    # `app.routes.AdminClient` patch target was a leftover from the pre-split
    # kafka_utils import path and no longer exists in either module.
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "regengine"
