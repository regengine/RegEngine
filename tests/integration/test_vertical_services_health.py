"""
Unit tests for vertical services health check endpoints.

Tests health and readiness endpoints for:
- Aerospace service
- Construction service  
- Gaming service
- Manufacturing service
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch


def create_mock_db_session(should_fail=False):
    """Create a mock database session for testing."""
    mock_session = Mock()
    if should_fail:
        mock_session.execute.side_effect = Exception("Database connection failed")
    else:
        mock_session.execute.return_value = Mock()
    mock_session.close = Mock()
    return mock_session


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
    
    def test_ready_endpoint_with_db_connected(self, client):
        """Verify /ready endpoint returns 200 when DB is reachable."""
        # Mock the database session at the module level
        with patch("services.aerospace.app.db_session.SessionLocal") as mock_session_local:
            mock_db = create_mock_db_session(should_fail=False)
            mock_session_local.return_value = mock_db
            
            response = client.get("/ready")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["service"] == "aerospace"
            assert data["version"] == "1.0.0"
            assert data["database"] == "connected"
    
    def test_ready_endpoint_with_db_disconnected(self, client):
        """Verify /ready endpoint returns 503 when DB is unreachable."""
        # Mock the database session to fail
        with patch("services.aerospace.app.db_session.SessionLocal") as mock_session_local:
            mock_db = create_mock_db_session(should_fail=True)
            mock_session_local.return_value = mock_db
            
            response = client.get("/ready")
            
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["database"] == "disconnected"


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
    
    def test_ready_endpoint_with_db_connected(self, client):
        """Verify /ready endpoint returns 200 when DB is reachable."""
        with patch("services.construction.app.db_session.SessionLocal") as mock_session_local:
            mock_db = create_mock_db_session(should_fail=False)
            mock_session_local.return_value = mock_db
            
            response = client.get("/ready")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["database"] == "connected"


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
    
    def test_ready_endpoint_with_db_connected(self, client):
        """Verify /ready endpoint returns 200 when DB is reachable."""
        with patch("services.gaming.app.db_session.SessionLocal") as mock_session_local:
            mock_db = create_mock_db_session(should_fail=False)
            mock_session_local.return_value = mock_db
            
            response = client.get("/ready")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"


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
    
    def test_ready_endpoint_with_db_connected(self, client):
        """Verify /ready endpoint returns 200 when DB is reachable."""
        with patch("services.manufacturing.app.db_session.SessionLocal") as mock_session_local:
            mock_db = create_mock_db_session(should_fail=False)
            mock_session_local.return_value = mock_db
            
            response = client.get("/ready")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"


class TestHealthEndpointsNoAuth:
    """Verify health endpoints don't require authentication."""
    
    def test_aerospace_health_accessible_without_auth(self):
        """Aerospace health endpoint should be accessible without API keys."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "aerospace"))
        
        from app.main import app
        client = TestClient(app)
        response = client.get("/health")
        
        # Should succeed without authentication
        assert response.status_code == 200
    
    def test_construction_health_accessible_without_auth(self):
        """Construction health endpoint should be accessible without API keys."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "construction"))
        
        from app.main import app
        client = TestClient(app)
        response = client.get("/health")
        
        # Should succeed without authentication
        assert response.status_code == 200
    
    def test_gaming_health_accessible_without_auth(self):
        """Gaming health endpoint should be accessible without API keys."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "gaming"))
        
        from app.main import app
        client = TestClient(app)
        response = client.get("/health")
        
        # Should succeed without authentication
        assert response.status_code == 200
    
    def test_manufacturing_health_accessible_without_auth(self):
        """Manufacturing health endpoint should be accessible without API keys."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "manufacturing"))
        
        from app.main import app
        client = TestClient(app)
        response = client.get("/health")
        
        # Should succeed without authentication
        assert response.status_code == 200

