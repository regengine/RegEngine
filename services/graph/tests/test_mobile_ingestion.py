"""
Tests for Mobile Field Capture CTE Ingestion Endpoint.
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add local path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client for persistence tests."""
    with patch("services.graph.app.routers.fsma.traceability.Neo4jClient") as mock:
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_instance.session.return_value.__aenter__.return_value.run = AsyncMock()
        mock.return_value = mock_instance
        mock.get_tenant_database_name.return_value = "test-db"
        yield mock_instance

@pytest.fixture
def mock_validation():
    """Mock identifier validation utilities."""
    with patch("services.graph.app.routers.fsma.traceability.validate_tlc") as mock_tlc, \
         patch("services.graph.app.routers.fsma.traceability.validate_gln") as mock_gln, \
         patch("services.graph.app.routers.fsma.traceability.validate_gtin") as mock_gtin:
        
        mock_tlc.return_value = MagicMock(is_valid=True)
        mock_gln.return_value = MagicMock(is_valid=True)
        mock_gtin.return_value = MagicMock(is_valid=True)
        yield mock_tlc, mock_gln, mock_gtin

# =============================================================================
# TESTS
# =============================================================================

def test_log_traceability_event_success(mock_neo4j_client, mock_validation):
    """Verify that a valid mobile event is successfully validated and persisted."""
    from services.graph.app.routers.fsma.traceability import router
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)

    # Mock dependencies
    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": "test-tenant"}
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

    client = TestClient(app)
    
    payload = {
        "event_type": "RECEIVING",
        "event_date": "2026-02-22",
        "tlc": "TLC-2024-001",
        "location_identifier": "0614141000036",
        "product_description": "Green Spinach 10oz",
        "gtin": "10614141000019"
    }
    
    response = client.post("/event", json=payload)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
    data = response.json()
    assert data["status"] == "success"
    assert "event_id" in data
    assert data["tlc"] == "TLC-2024-001"
    
    # Check that persistence was triggered correctly
    mock_run = mock_neo4j_client.session.return_value.__aenter__.return_value.run
    assert mock_run.call_count == 5 # TraceEvent, Lot, Facility, and 2 Relationships

def test_log_traceability_event_invalid_tlc(mock_neo4j_client, mock_validation):
    """Verify that identity validation failures are handled with 400 Bad Request."""
    mock_tlc, _, _ = mock_validation
    mock_tlc.return_value = MagicMock(is_valid=False, errors=[MagicMock(message="Format violation: TLC must be alphanumeric")])

    from services.graph.app.routers.fsma.traceability import router
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)

    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": "test-tenant"}
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

    client = TestClient(app)
    
    payload = {
        "event_type": "RECEIVING",
        "event_date": "2026-02-22",
        "tlc": "!!!INVALID!!!",
        "location_identifier": "0614141000036"
    }
    
    response = client.post("/event", json=payload)

    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.json()}"
    assert "Invalid TLC" in response.json()["detail"]
    assert "Format violation" in response.json()["detail"]
    
    # Verify no persistence occurred
    mock_neo4j_client.session.return_value.__aenter__.return_value.run.assert_not_called()
