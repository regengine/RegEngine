"""
Security tests for label generation endpoint.

Tests cover:
1. Mandatory X-Tenant-ID header enforcement
2. URL encoding in QR payload generation
3. Atomic serial number generation (no race conditions)
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

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
    """Test that tenant_id dependency is mandatory."""

    def test_missing_tenant_id_raises_error(self):
        """Test that missing tenant ID (no auth) results in error."""
        from fastapi import FastAPI
        from services.graph.app.routers.labels import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)

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

        # Make request without auth headers — should fail due to missing dependency
        with patch("services.graph.app.routers.labels.Neo4jClient"):
            response = client.post("/v1/labels/batch/init", json=request_body)

        # Should return 401, 403, or 422 (missing required auth dependency)
        assert response.status_code in [401, 403, 422]

    def test_empty_tenant_id_raises_error(self):
        """Test that empty X-Tenant-ID header is rejected."""
        from fastapi import FastAPI
        from services.graph.app.routers.labels import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)

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

        # Make request with empty X-Tenant-ID header — dependency should reject
        with patch("services.graph.app.routers.labels.Neo4jClient"):
            response = client.post(
                "/v1/labels/batch/init",
                json=request_body,
                headers={"X-Tenant-ID": ""},
            )

        # Should return 401, 403, or 422 for invalid/empty auth
        assert response.status_code in [401, 403, 422]


class TestAtomicSerialGeneration:
    """Test that serial number generation is atomic."""

    @pytest.mark.asyncio
    async def test_serial_generation_in_single_transaction(self):
        """Test that lot creation and serial reservation happen atomically."""
        # Mock Neo4j client with async session
        mock_neo4j = MagicMock()
        mock_session = AsyncMock()
        mock_result = AsyncMock()

        # Setup mock to return serial range
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {"start": 1, "end": 100}.get(key)
        mock_result.single = AsyncMock(return_value=mock_record)
        mock_session.run = AsyncMock(return_value=mock_result)

        # Setup async context manager for session
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_neo4j_class = MagicMock()
        mock_neo4j_class.return_value = mock_neo4j
        mock_neo4j.session = MagicMock(return_value=mock_session)
        mock_neo4j.close = AsyncMock()

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

        # Call endpoint using dependency overrides approach
        test_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        with patch("services.graph.app.routers.labels.Neo4jClient", mock_neo4j_class):
            mock_neo4j_class.get_tenant_database_name = MagicMock(return_value="test-db")
            response = await initialize_label_batch(
                request=request,
                tenant_id=test_tenant_id,
                api_key="test-key",
            )

        # Verify session.run() was called (atomic transaction)
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

    @pytest.mark.asyncio
    async def test_error_handling_in_transaction(self):
        """Test that database errors are properly handled."""
        # Mock Neo4j client that raises an error during session.run
        mock_neo4j = MagicMock()
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(side_effect=Exception("Database connection error"))

        # Setup async context manager
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_neo4j_class = MagicMock()
        mock_neo4j_class.return_value = mock_neo4j
        mock_neo4j.session = MagicMock(return_value=mock_session)
        mock_neo4j.close = AsyncMock()

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

        test_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        # Should raise HTTPException with 500 status
        with patch("services.graph.app.routers.labels.Neo4jClient", mock_neo4j_class):
            mock_neo4j_class.get_tenant_database_name = MagicMock(return_value="test-db")
            with pytest.raises(HTTPException) as exc_info:
                await initialize_label_batch(
                    request=request,
                    tenant_id=test_tenant_id,
                    api_key="test-key",
                )

        assert exc_info.value.status_code == 500
        assert "Database transaction failed" in exc_info.value.detail


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
