"""
Integration tests for vertical services health check endpoints.

Tests health and readiness endpoints for:
- Aerospace service
- Construction service
- Gaming service
- Manufacturing service
"""

import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_service_app(service_root: Path):
    """Import the service's ``app`` object without disturbing other suites.

    The service directory is put first on ``sys.path`` and any cached
    ``app.*`` modules are set aside for the duration of the import, then
    both ``sys.path`` and ``sys.modules`` are restored to exactly what they
    were. Nothing the service import touches leaks into the shared module
    state, so test order cannot change the outcome. The returned app object
    stays usable because the caller keeps a reference to it.
    """
    original_path = sys.path.copy()
    original_modules = sys.modules.copy()
    sys.path.insert(0, str(service_root))
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    try:
        from app.main import app as service_app
    finally:
        sys.path = original_path
        sys.modules.clear()
        sys.modules.update(original_modules)
    return service_app


def _create_client(service_name: str) -> TestClient:
    service_root = _REPO_ROOT / "services" / service_name
    if not service_root.is_dir():
        pytest.skip(f"Optional vertical service '{service_name}' is not present in this checkout")

    return TestClient(_import_service_app(service_root))


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
        return _create_client("aerospace")

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
        return _create_client("construction")

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
        return _create_client("gaming")

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
        return _create_client("manufacturing")

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
        client = _create_client("aerospace")
        response = client.get("/health")

        # Should succeed without authentication
        assert response.status_code == 200

    def test_construction_health_accessible_without_auth(self):
        """Construction health endpoint should be accessible without API keys."""
        client = _create_client("construction")
        response = client.get("/health")

        # Should succeed without authentication
        assert response.status_code == 200

    def test_gaming_health_accessible_without_auth(self):
        """Gaming health endpoint should be accessible without API keys."""
        client = _create_client("gaming")
        response = client.get("/health")

        # Should succeed without authentication
        assert response.status_code == 200

    def test_manufacturing_health_accessible_without_auth(self):
        """Manufacturing health endpoint should be accessible without API keys."""
        client = _create_client("manufacturing")
        response = client.get("/health")

        # Should succeed without authentication
        assert response.status_code == 200


def _write_fake_service(service_root: Path) -> None:
    """Create a minimal on-disk service with an importable ``app.main``."""
    package_dir = service_root / "app"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("")
    (package_dir / "main.py").write_text("app = object()\n")


@pytest.mark.unit
class TestServiceImportIsolation:
    """The service import must not disturb ``app.*`` modules of other suites."""

    def test_import_preserves_preexisting_app_modules(self, tmp_path, monkeypatch):
        """Modules owned by other suites survive a service import."""
        sentinel_app = types.ModuleType("app")
        sentinel_child = types.ModuleType("app.shared")
        monkeypatch.setitem(sys.modules, "app", sentinel_app)
        monkeypatch.setitem(sys.modules, "app.shared", sentinel_child)

        service_root = tmp_path / "svc"
        _write_fake_service(service_root)

        loaded = _import_service_app(service_root)

        assert loaded is not None
        assert sys.modules["app"] is sentinel_app
        assert sys.modules["app.shared"] is sentinel_child

    def test_import_leaves_no_service_modules_behind(self, tmp_path):
        """Freshly imported service modules do not leak into shared state."""
        service_root = tmp_path / "svc"
        _write_fake_service(service_root)
        before = set(sys.modules)

        _import_service_app(service_root)

        assert set(sys.modules) == before
        assert "app.main" not in sys.modules
