"""The FSMA dashboard degraded path must not leak internal error text.

Driver failures can carry connection strings, query text, and topology
details. The endpoint already logs the full error server-side; the caller
gets only the generic degraded shape (matching the sibling
``/metrics/quality`` endpoint's generic 500).
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.routers.fsma import metrics as dashboard_metrics


async def test_dashboard_degraded_hides_internal_error_text(monkeypatch):
    secret_message = "connection refused: bolt://neo4j:SUPERSECRET@graph.internal:7687"

    class _FailingClient:
        @staticmethod
        def get_tenant_database_name(tenant_id):
            return "neo4j"

        def __init__(self, *args, **kwargs):
            raise RuntimeError(secret_message)

    monkeypatch.setattr(dashboard_metrics, "Neo4jClient", _FailingClient)

    # #3316 reconciles the middleware tenant with the API-key tenant before
    # any read, so the key must carry the same tenant to reach the driver.
    tenant_id = uuid.uuid4()
    request = MagicMock()
    request.url.path = "/dashboard"
    result = await dashboard_metrics.fsma_dashboard(
        request=request,
        tenant_id=tenant_id,
        api_key=MagicMock(tenant_id=str(tenant_id)),
    )

    assert result["status"] == "degraded"
    assert result["error"] == "Internal server error"
    assert "SUPERSECRET" not in str(result)
    assert "bolt://" not in str(result)
