"""Smoke tests for the ingestion service."""

import sys
from pathlib import Path

# Add service directory to path for imports to work
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from main import app


from unittest.mock import patch, MagicMock

@patch("app.routes.AdminClient")
def test_health(mock_admin_client) -> None:
    # Mock list_topics to return successfully
    mock_admin_client.return_value.list_topics.return_value = {}
    
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "kafka": "available"}
