"""Smoke tests for the admin service."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient
from services.admin.main import app


def test_health(monkeypatch: pytest.MonkeyPatch):
    """Test health endpoint."""
    for env_var in [
        "DATABASE_URL",
        "ADMIN_DATABASE_URL",
        "NEO4J_URI",
        "NEO4J_URL",
        "REDIS_URL",
    ]:
        monkeypatch.delenv(env_var, raising=False)

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
