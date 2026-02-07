"""
Tests for FSMA 204 API Routes.
"""

# Mock shared.auth before importing routes
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))


@pytest.fixture
def mock_auth():
    """Mock API key authentication."""
    with patch("shared.auth.require_api_key") as mock:
        mock.return_value = {"tenant_id": "test-tenant", "key_id": "test-key"}
        yield mock


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client."""
    with patch("services.graph.app.neo4j_utils.Neo4jClient") as mock:
        mock_instance = MagicMock()
        mock_instance.session.return_value.__enter__ = MagicMock()
        mock_instance.session.return_value.__exit__ = MagicMock()
        mock.return_value = mock_instance
        mock.get_global_database_name.return_value = "test-db"
        yield mock_instance


@pytest.fixture
def mock_trace_forward():
    """Mock trace_forward function."""
    with patch("services.graph.app.fsma_utils.trace_forward") as mock:
        from services.graph.app.fsma_utils import TraceResult

        mock.return_value = TraceResult(
            lot_id="LOT-2024-001",
            direction="forward",
            facilities=[
                {
                    "gln": "1234567890123",
                    "name": "Fresh Foods Distribution",
                    "address": "123 Warehouse St",
                    "facility_type": "DISTRIBUTOR",
                }
            ],
            events=[
                {
                    "event_id": "evt-001",
                    "type": "SHIPPING",
                    "event_date": "2024-01-15",
                    "confidence": 0.95,
                }
            ],
            lots=[
                {
                    "tlc": "LOT-2024-002",
                    "product_description": "Romaine Lettuce 12ct",
                    "quantity": 50,
                    "unit_of_measure": "cases",
                }
            ],
            total_quantity=50.0,
            query_time_ms=12.5,
            hop_count=2,
            # Physics Engine additions
            time_violations=None,
            risk_flags=None,
        )
        yield mock


@pytest.fixture
def mock_trace_backward():
    """Mock trace_backward function."""
    with patch("services.graph.app.fsma_utils.trace_backward") as mock:
        from services.graph.app.fsma_utils import TraceResult

        mock.return_value = TraceResult(
            lot_id="LOT-2024-002",
            direction="backward",
            facilities=[
                {
                    "gln": "9876543210123",
                    "name": "Organic Farms Inc",
                    "address": "456 Farm Rd",
                    "facility_type": "GROWER",
                }
            ],
            events=[
                {
                    "event_id": "evt-002",
                    "type": "RECEIVING",
                    "event_date": "2024-01-10",
                    "confidence": 0.92,
                }
            ],
            lots=[
                {
                    "tlc": "LOT-2024-001",
                    "product_description": "Raw Lettuce",
                    "quantity": 100,
                    "unit_of_measure": "lbs",
                }
            ],
            total_quantity=100.0,
            query_time_ms=8.3,
            hop_count=1,
            # Physics Engine additions
            time_violations=None,
            risk_flags=None,
        )
        yield mock


@pytest.fixture
def mock_find_gaps():
    """Mock find_gaps function."""
    with patch("services.graph.app.fsma_utils.find_gaps") as mock:
        mock.return_value = [
            {
                "event_id": "evt-003",
                "type": "TRANSFORMATION",
                "event_date": None,
                "document_id": "doc-001",
                "gaps": ["missing_date"],
            }
        ]
        yield mock


@pytest.fixture
def mock_get_lot_timeline():
    """Mock get_lot_timeline function."""
    with patch("services.graph.app.fsma_utils.get_lot_timeline") as mock:
        mock.return_value = [
            {
                "event_id": "evt-001",
                "type": "RECEIVING",
                "event_date": "2024-01-10",
                "event_time": "08:00:00",
                "confidence": 0.95,
                "facility": {"name": "Warehouse A", "gln": "1111111111111"},
            },
            {
                "event_id": "evt-002",
                "type": "TRANSFORMATION",
                "event_date": "2024-01-11",
                "event_time": "14:30:00",
                "confidence": 0.88,
                "facility": {"name": "Processing Plant", "gln": "2222222222222"},
            },
            {
                "event_id": "evt-003",
                "type": "SHIPPING",
                "event_date": "2024-01-12",
                "event_time": "16:00:00",
                "confidence": 0.92,
                "facility": {"name": "Warehouse A", "gln": "1111111111111"},
            },
        ]
        yield mock


class TestTraceForwardEndpoint:
    """Tests for /v1/fsma/trace/forward/{tlc}"""

    def test_trace_forward_success(
        self, mock_auth, mock_neo4j_client, mock_trace_forward
    ):
        """Test successful forward trace."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/forward/LOT-2024-001",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["lot_id"] == "LOT-2024-001"
        assert data["direction"] == "forward"
        assert len(data["facilities"]) == 1
        assert data["facilities"][0]["gln"] == "1234567890123"
        assert data["hop_count"] == 2

    def test_trace_forward_with_max_depth(
        self, mock_auth, mock_neo4j_client, mock_trace_forward
    ):
        """Test forward trace with custom max_depth."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/forward/LOT-2024-001?max_depth=5",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        mock_trace_forward.assert_called_once()


class TestTraceBackwardEndpoint:
    """Tests for /v1/fsma/trace/backward/{tlc}"""

    def test_trace_backward_success(
        self, mock_auth, mock_neo4j_client, mock_trace_backward
    ):
        """Test successful backward trace."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/backward/LOT-2024-002",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["lot_id"] == "LOT-2024-002"
        assert data["direction"] == "backward"
        assert len(data["source_lots"]) == 1


class TestTimelineEndpoint:
    """Tests for /v1/fsma/timeline/{tlc}"""

    def test_timeline_success(
        self, mock_auth, mock_neo4j_client, mock_get_lot_timeline
    ):
        """Test lot timeline retrieval."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get(
            "/v1/fsma/timeline/LOT-2024-001",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["lot_id"] == "LOT-2024-001"
        assert len(data["events"]) == 3
        # Events should be in chronological order
        dates = [e["event_date"] for e in data["events"]]
        assert dates == sorted(dates)


class TestExportEndpoints:
    """Tests for CSV export endpoints."""

    def test_export_trace_csv(self, mock_auth, mock_neo4j_client, mock_trace_forward):
        """Test trace CSV export."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get(
            "/v1/fsma/export/trace/LOT-2024-001?direction=forward",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert (
            "fsma_trace_forward_LOT-2024-001" in response.headers["content-disposition"]
        )

        # Verify CSV content
        content = response.content.decode("utf-8")
        lines = content.strip().split("\n")
        assert len(lines) >= 1  # At least header
        assert "Traceability Lot Code" in lines[0]

    def test_export_recall_contacts(
        self, mock_auth, mock_neo4j_client, mock_trace_forward
    ):
        """Test recall contacts CSV export."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get(
            "/v1/fsma/export/recall-contacts/LOT-2024-001",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "recall_contacts" in response.headers["content-disposition"]

        content = response.content.decode("utf-8")
        assert "Facility Name" in content
        assert "Global Location Number" in content


class TestGapAnalysisEndpoints:
    """Tests for gap analysis endpoints."""

    def test_get_gaps(self, mock_auth, mock_neo4j_client, mock_find_gaps):
        """Test gap analysis retrieval."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get(
            "/v1/fsma/gaps",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_gaps"] == 1
        assert data["summary"]["missing_date"] == 1

    def test_export_gaps_csv(self, mock_auth, mock_neo4j_client, mock_find_gaps):
        """Test gaps CSV export."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get(
            "/v1/fsma/export/gaps",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"

        content = response.content.decode("utf-8")
        assert "Event ID" in content
        assert "Missing Fields" in content


class TestHealthEndpoint:
    """Tests for FSMA health endpoint."""

    def test_health(self):
        """Test FSMA health endpoint (no auth required)."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/v1/fsma/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["module"] == "fsma-204"
