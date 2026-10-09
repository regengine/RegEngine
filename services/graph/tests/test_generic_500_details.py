"""Error responses must not forward internal exception text to API callers.

The traceability linker endpoints and the metrics dashboard used to echo
``str(e)`` (driver messages, query fragments, credentials in URIs) into
500 response bodies. They now return a generic message while the full
error still goes to server-side logs.
"""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

_AUTH_HEADERS = {"X-RegEngine-API-Key": os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")}

# Sentinel that looks like the internal text we must never return.
_SENTINEL = "SENTINEL bolt://admin:s3cret@internal-neo4j:7687 MATCH (n) FAILURE"

_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _build_app():
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id

    from services.graph.app.routers.fsma import metrics_router, trace_router

    app = FastAPI()
    app.include_router(trace_router)
    app.include_router(metrics_router)
    app.dependency_overrides[require_api_key] = lambda: {
        "tenant_id": "test-tenant",
        "key_id": "test-key",
    }
    app.dependency_overrides[get_current_tenant_id] = lambda: _TENANT
    return app


def _linker_cls_raising(method_name):
    """TraceabilityLinker double whose linker call raises with sentinel text."""
    cls = MagicMock()
    instance = MagicMock()
    instance.close = AsyncMock()
    getattr(instance, method_name).side_effect = ValueError(_SENTINEL)
    cls.return_value = instance
    return cls


def test_regulations_endpoint_returns_generic_500():
    with patch(
        "services.graph.app.routers.fsma.traceability.TraceabilityLinker",
        new=_linker_cls_raising("get_governing_regulations"),
    ):
        response = TestClient(_build_app()).get(
            "/traceability/regulations",
            params={"lot_tlc": "LOT-1"},
            headers=_AUTH_HEADERS,
        )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert _SENTINEL not in response.text


def test_impacted_lots_endpoint_returns_generic_500():
    with patch(
        "services.graph.app.routers.fsma.traceability.TraceabilityLinker",
        new=_linker_cls_raising("get_impacted_lots"),
    ):
        response = TestClient(_build_app()).get(
            "/traceability/impacted-lots",
            params={"obligation_id": "OBL-1"},
            headers=_AUTH_HEADERS,
        )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert _SENTINEL not in response.text


def test_link_obligation_endpoint_returns_generic_500():
    with patch(
        "services.graph.app.routers.fsma.traceability.TraceabilityLinker",
        new=_linker_cls_raising("link_obligation_to_traceability"),
    ):
        response = TestClient(_build_app()).post(
            "/traceability/link/OBL-1",
            headers=_AUTH_HEADERS,
        )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert _SENTINEL not in response.text


def test_mobile_event_endpoint_returns_generic_500():
    with (
        patch("services.graph.app.routers.fsma.traceability.validate_tlc") as mock_tlc,
        patch("services.graph.app.routers.fsma.traceability.validate_gln") as mock_gln,
        patch("services.graph.app.routers.fsma.traceability.validate_gtin") as mock_gtin,
        patch("services.graph.app.routers.fsma.traceability.Neo4jClient") as mock_client_cls,
    ):
        mock_tlc.return_value = MagicMock(is_valid=True)
        mock_gln.return_value = MagicMock(is_valid=True)
        mock_gtin.return_value = MagicMock(is_valid=True)
        instance = MagicMock()
        instance.close = AsyncMock()
        instance.session.return_value.__aenter__.return_value.run = AsyncMock(side_effect=ConnectionError(_SENTINEL))
        mock_client_cls.return_value = instance
        mock_client_cls.get_tenant_database_name.return_value = "test-db"
        response = TestClient(_build_app()).post(
            "/event",
            json={
                "event_type": "RECEIVING",
                "event_date": "2026-04-12",
                "tlc": "LOT-2026-04-A1",
                "location_identifier": "0614141000012",
                "responsible_party_contact": "Jane Doe",
            },
            headers=_AUTH_HEADERS,
        )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert _SENTINEL not in response.text


def test_dashboard_returns_generic_error():
    with (
        patch("services.graph.app.routers.fsma.metrics.Neo4jClient") as mock_client_cls,
        patch(
            "services.graph.app.routers.fsma.metrics.find_gaps",
            new=AsyncMock(side_effect=Exception(_SENTINEL)),
        ),
    ):
        mock_client_cls.get_tenant_database_name.return_value = "test-db"
        response = TestClient(_build_app()).get("/dashboard", headers=_AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["error"] == "Internal server error"
    assert _SENTINEL not in response.text
