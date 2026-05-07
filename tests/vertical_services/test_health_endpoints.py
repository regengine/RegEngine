"""
Unit tests for vertical services health check endpoints.

Tests health and readiness endpoints for:
- Aerospace service
- Construction service  
- Gaming service
- Manufacturing service
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Set dummy database URLs before any imports to avoid connection attempts during tests
os.environ.setdefault('AEROSPACE_DATABASE_URL', 'sqlite:///./test_aerospace.db')
os.environ.setdefault('CONSTRUCTION_DATABASE_URL', 'sqlite:///./test_construction.db')
os.environ.setdefault('GAMING_DATABASE_URL', 'sqlite:///./test_gaming.db')
os.environ.setdefault('MANUFACTURING_DATABASE_URL', 'sqlite:///./test_manufacturing.db')

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _purge_service_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)


def _create_client(service_name: str) -> TestClient:
    service_root = _REPO_ROOT / "services" / service_name
    if not service_root.is_dir():
        pytest.skip(f"Optional vertical service '{service_name}' is not present in this checkout")

    original_path = sys.path.copy()
    sys.path.insert(0, str(service_root))
    _purge_service_modules()
    try:
        from app.main import app
    finally:
        sys.path = original_path

    return TestClient(app)


class TestAerospaceHealthEndpoints:
    """Tests for aerospace service health endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client for aerospace service."""
        return _create_client("aerospace")
    
    def test_health_endpoint_returns_200(self, client):
        """Verify /health endpoint returns 200 with correct structure."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "aerospace"
        assert data["version"] == "1.0.0"


class TestConstructionHealthEndpoints:
    """Tests for construction service health endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client for construction service."""
        return _create_client("construction")
    
    def test_health_endpoint_returns_200(self, client):
        """Verify /health endpoint returns 200 with correct structure."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "construction"
        assert data["version"] == "1.0.0"


class TestGamingHealthEndpoints:
    """Tests for gaming service health endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client for gaming service."""
        return _create_client("gaming")
    
    def test_health_endpoint_returns_200(self, client):
        """Verify /health endpoint returns 200 with correct structure."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "gaming"
        assert data["version"] == "1.0.0"


class TestManufacturingHealthEndpoints:
    """Tests for manufacturing service health endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client for manufacturing service."""
        return _create_client("manufacturing")
    
    def test_health_endpoint_returns_200(self, client):
        """Verify /health endpoint returns 200 with correct structure."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "manufacturing"
        assert data["version"] == "1.0.0"


class TestHealthEndpointsNoAuth:
    """Verify health endpoints don't require authentication."""
    
    def test_aerospace_health_accessible_without_auth(self):
        """Aerospace health endpoint should be accessible without API keys."""
        client = _create_client("aerospace")
        response = client.get("/health")

        # Should succeed without authentication
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
