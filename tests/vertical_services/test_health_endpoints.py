"""
Unit tests for vertical services health check endpoints.

Tests health and readiness endpoints for:
- Aerospace service
- Construction service  
- Gaming service
- Manufacturing service
"""

import os
import pytest
from fastapi.testclient import TestClient

# Set dummy database URLs before any imports to avoid connection attempts during tests
os.environ.setdefault('AEROSPACE_DATABASE_URL', 'sqlite:///./test_aerospace.db')
os.environ.setdefault('CONSTRUCTION_DATABASE_URL', 'sqlite:///./test_construction.db')
os.environ.setdefault('GAMING_DATABASE_URL', 'sqlite:///./test_gaming.db')
os.environ.setdefault('MANUFACTURING_DATABASE_URL', 'sqlite:///./test_manufacturing.db')


class TestAerospaceHealthEndpoints:
    """Tests for aerospace service health endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client for aerospace service."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "aerospace"))
        
        from app.main import app
        return TestClient(app)
    
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
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "construction"))
        
        from app.main import app
        return TestClient(app)
    
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
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "gaming"))
        
        from app.main import app
        return TestClient(app)
    
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
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "manufacturing"))
        
        from app.main import app
        return TestClient(app)
    
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
        import sys
        from pathlib import Path
        
        # Clear sys.path to avoid conflicts
        original_path = sys.path.copy()
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "aerospace"))
        
        try:
            from app.main import app
            client = TestClient(app)
            response = client.get("/health")
            
            # Should succeed without authentication
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
        finally:
            # Restore original path
            sys.path = original_path
