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

    # The /health endpoint lives in app/routes_health_metrics.py and contacts
    # no external service (the Kafka probe was retired in WI-05).
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "regengine"
