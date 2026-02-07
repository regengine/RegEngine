"""
Security tests for label generation endpoint.

Tests cover:
1. Mandatory X-Tenant-ID header enforcement
2. URL encoding in QR payload generation
3. Atomic serial number generation (no race conditions)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.graph.app.routers.labels import (
    LabelBatchInitRequest,
    PackagingLevel,
    ProductInfo,
    TraceabilityInfo,
    UnitOfMeasure,
    generate_qr_payload,
    initialize_label_batch,
)


class TestURLEncoding:
    """Test URL encoding in QR payload generation."""

    def test_generate_qr_payload_encodes_special_characters(self):
        """Test that special characters in lot number are properly URL encoded."""
        gtin = "00000012345678"
        lot = "LOT-2024/001"  # Contains forward slash
        serial = "1234567890"

        payload = generate_qr_payload(gtin, lot, serial)

        # Forward slash should be encoded as %2F
        assert "LOT-2024%2F001" in payload
        assert "LOT-2024/001" not in payload

    def test_generate_qr_payload_encodes_spaces(self):
        """Test that spaces in lot number are properly URL encoded."""
        gtin = "00000012345678"
        lot = "LOT 2024 001"  # Contains spaces
        serial = "1234567890"

        payload = generate_qr_payload(gtin, lot, serial)

        # Spaces should be encoded as %20
        assert "LOT%202024%20001" in payload
        assert " " not in payload.split("/21/")[0]  # Check before serial

    def test_generate_qr_payload_encodes_special_chars(self):
        """Test that various special characters are properly URL encoded."""
        gtin = "00000012345678"
        lot = "LOT&TEST?ID#123"  # Contains &, ?, #
        serial = "1234567890"

        payload = generate_qr_payload(gtin, lot, serial)

        # Special characters should be encoded
        assert "%26" in payload or "LOT&TEST?ID#123" not in payload
        assert "?" not in payload.split("/21/")[0]
        assert "#" not in payload.split("/21/")[0]

    def test_generate_qr_payload_preserves_structure(self):
        """Test that the GS1 Digital Link structure is preserved."""
        gtin = "00000012345678"
        lot = "SIMPLE-LOT"
        serial = "1234567890"
        domain = "https://trace.example.com"

        payload = generate_qr_payload(gtin, lot, serial, domain)

        # Check structure
        assert payload.startswith(f"{domain}/01/")
        assert f"/01/{gtin}/10/" in payload
        assert payload.endswith(f"/21/{serial}")


class TestTenantIDMandatory:
    """Test that X-Tenant-ID header is mandatory."""

    def test_missing_tenant_id_raises_error(self):
        """Test that missing X-Tenant-ID header is rejected."""
        from fastapi import FastAPI

        from services.graph.app.routers.labels import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Prepare valid request body
        request_body = {
            "packer_gln": "0614141000001",
            "product": {
                "gtin": "00000012345678",
                "description": "Test Product",
                "expected_units": 1,
            },
            "traceability": {"lot_number": "LOT-TEST-001", "pack_date": "2024-01-01"},
            "quantity": 10,
            "unit_of_measure": "EA",
            "packaging_level": "item",
        }

        # Make request without X-Tenant-ID header
        with patch("services.graph.app.routers.labels.Neo4jClient"):
            response = client.post("/v1/labels/batch/init", json=request_body)

        # Should return 422 Unprocessable Entity for missing required header
        assert response.status_code == 422

    def test_empty_tenant_id_raises_error(self):
        """Test that empty X-Tenant-ID header is rejected."""
        from fastapi import FastAPI

        from services.graph.app.routers.labels import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        request_body = {
            "packer_gln": "0614141000001",
            "product": {
                "gtin": "00000012345678",
                "description": "Test Product",
                "expected_units": 1,
            },
            "traceability": {"lot_number": "LOT-TEST-001", "pack_date": "2024-01-01"},
            "quantity": 10,
            "unit_of_measure": "EA",
            "packaging_level": "item",
        }

        # Make request with empty X-Tenant-ID header
        with patch("services.graph.app.routers.labels.Neo4jClient"):
            response = client.post(
                "/v1/labels/batch/init", json=request_body, headers={"X-Tenant-ID": ""}
            )

        # Should return 422 for empty string
        assert response.status_code == 422


class TestAtomicSerialGeneration:
    """Test that serial number generation is atomic."""

    def test_serial_generation_in_single_transaction(self):
        """Test that lot creation and serial reservation happen atomically."""
        # Create mock Neo4j client
        mock_neo4j = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()

        # Setup mock to return serial range
        mock_result.single.return_value = {"start": 1, "end": 100}
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = lambda self: mock_session
        mock_session.__exit__ = lambda *args: None
        mock_neo4j.driver.session.return_value = mock_session

        # Create request
        request = LabelBatchInitRequest(
            packer_gln="0614141000001",
            product=ProductInfo(
                gtin="00000012345678", description="Test Product", expected_units=1
            ),
            traceability=TraceabilityInfo(
                lot_number="LOT-TEST-001", pack_date="2024-01-01"
            ),
            quantity=100,
            unit_of_measure=UnitOfMeasure.EA,
            packaging_level=PackagingLevel.ITEM,
        )

        # Call endpoint
        response = initialize_label_batch(
            request=request, x_tenant_id="test-tenant-123", neo4j=mock_neo4j
        )

        # Verify single session.run() call was made (atomic transaction)
        assert mock_session.run.call_count == 1

        # Verify the Cypher query includes atomic serial increment
        cypher_call = mock_session.run.call_args
        cypher_query = cypher_call[0][0]

        # Should have WITH clause for atomic operation
        assert "WITH l, coalesce(l.next_serial, 1) AS start" in cypher_query
        assert "SET l.next_serial = start + $quantity" in cypher_query

        # Verify response has correct serial range
        assert response.reserved_range["start"] == 1
        assert response.reserved_range["end"] == 100


class TestHealthEndpoint:
    """Tests for Label Inception health endpoint."""

    def test_health_endpoint_returns_status(self):
        """Health endpoint should return service status information."""
        from fastapi import FastAPI

        from services.graph.app.routers.labels import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/v1/labels/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "label-inception"
        assert data["version"]


class TestErrorHandling:
    """Tests for error handling in label batch initialization."""

    def test_error_handling_in_transaction(self):
        """Test that database errors are properly handled."""
        # Create mock Neo4j client that raises an error
        mock_neo4j = MagicMock()
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Database connection error")
        mock_session.__enter__ = lambda self: mock_session
        mock_session.__exit__ = lambda *args: None
        mock_neo4j.driver.session.return_value = mock_session

        request = LabelBatchInitRequest(
            packer_gln="0614141000001",
            product=ProductInfo(
                gtin="00000012345678", description="Test Product", expected_units=1
            ),
            traceability=TraceabilityInfo(
                lot_number="LOT-TEST-001", pack_date="2024-01-01"
            ),
            quantity=10,
            unit_of_measure=UnitOfMeasure.EA,
            packaging_level=PackagingLevel.ITEM,
        )

        # Should raise HTTPException with 500 status
        with pytest.raises(HTTPException) as exc_info:
            initialize_label_batch(
                request=request, x_tenant_id="test-tenant-123", neo4j=mock_neo4j
            )

        assert exc_info.value.status_code == 500
        assert "Database transaction failed" in exc_info.value.detail


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
