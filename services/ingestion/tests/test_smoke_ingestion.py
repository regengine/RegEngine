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


from unittest.mock import patch


def test_health() -> None:
    try:
        from main import app
    except ModuleNotFoundError as exc:
        pytest.skip(
            f"ingestion smoke tests require optional dependency '{exc.name}'",
        )

    with patch("app.routes.AdminClient") as mock_admin_client:
        # Mock list_topics to return successfully
        mock_admin_client.return_value.list_topics.return_value = {}

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "regengine"
