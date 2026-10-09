"""Uniform tenant reconciliation on the three recall/compliance exports.

Audit finding: ``export_epcis``, ``export_trace_csv`` and
``export_recall_contacts`` in
``services/graph/app/routers/fsma/compliance.py`` scoped Neo4j from the
middleware tenant only and never compared it with the authenticated
API-key tenant, while the sibling FDA/gap exports already fail closed
with 409 E_TENANT_MISMATCH on divergence (#2511).

These tests pin the uniform fix: on middleware/API-key divergence each
of the three exports returns 409 and never touches Neo4j.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from shared.auth import APIKey, require_api_key  # noqa: E402
from shared.middleware import get_current_tenant_id  # noqa: E402

TENANT_KEY = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_MIDDLEWARE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _api_key(tenant_id):
    return APIKey(
        key_id="test-key",
        key_hash="",
        name="test",
        tenant_id=tenant_id,
        created_at=datetime.now(timezone.utc),
    )


def _build_app():
    from services.graph.app.routers.fsma import compliance_router

    app = FastAPI()
    app.include_router(compliance_router, prefix="/v1/fsma/compliance")
    app.dependency_overrides[require_api_key] = lambda: _api_key(TENANT_KEY)
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID(TENANT_MIDDLEWARE)
    return app


DIVERGENT_EXPORT_URLS = [
    "/v1/fsma/compliance/export/epcis?start_date=2026-01-01&end_date=2026-12-31",
    "/v1/fsma/compliance/export/trace/LOT123?direction=forward",
    "/v1/fsma/compliance/export/recall-contacts/LOT123",
]


@pytest.mark.parametrize("url", DIVERGENT_EXPORT_URLS)
def test_exports_409_and_no_neo4j_read_on_divergence(url):
    app = _build_app()
    client = TestClient(app, raise_server_exceptions=False)

    with (
        patch("services.graph.app.routers.fsma.compliance.Neo4jClient") as mock_client_cls,
        patch(
            "services.graph.app.fsma_utils.query_events_by_range",
            new_callable=AsyncMock,
        ) as mock_query_range,
        patch(
            "services.graph.app.routers.fsma.compliance.trace_forward",
            new_callable=AsyncMock,
        ) as mock_forward,
        patch(
            "services.graph.app.routers.fsma.compliance.trace_backward",
            new_callable=AsyncMock,
        ) as mock_backward,
    ):
        resp = client.get(url)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "E_TENANT_MISMATCH"
    mock_client_cls.assert_not_called()
    mock_query_range.assert_not_called()
    mock_forward.assert_not_called()
    mock_backward.assert_not_called()


def test_epcis_uses_reconciled_tenant_on_agreement():
    """On agreement the EPCIS export queries with the authenticated tenant."""
    from services.graph.app.routers.fsma import compliance_router

    app = FastAPI()
    app.include_router(compliance_router, prefix="/v1/fsma/compliance")
    app.dependency_overrides[require_api_key] = lambda: _api_key(TENANT_KEY)
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID(TENANT_KEY)
    client = TestClient(app, raise_server_exceptions=False)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "services.graph.app.routers.fsma.compliance.Neo4jClient",
            return_value=mock_client,
        ) as mock_client_cls,
        patch(
            "services.graph.app.fsma_utils.query_events_by_range",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_query_range,
    ):
        resp = client.get(DIVERGENT_EXPORT_URLS[0])

    assert resp.status_code == 200, resp.text
    mock_client_cls.assert_called_once()
    mock_query_range.assert_called_once()
    _args, _kwargs = mock_query_range.call_args
    assert _args[3] == TENANT_KEY
