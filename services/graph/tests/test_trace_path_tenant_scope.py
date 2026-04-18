"""Variable-length path tenant-scope tests (#1256).

`trace_forward`, `trace_backward`, and the lineage SUPERSEDES chain all
use variable-length Cypher paths. Without an `ALL(n IN nodes(path)
WHERE n.tenant_id = $tenant_id)` predicate, the traversal can cross
tenant boundaries via shared events, facilities, or fact chains and
leak another tenant's data.

These tests:
  1. Inspect the Cypher text to assert the ALL(...) predicate is present
     on every variable-length query.
  2. Exercise the post-query invariant check — if a mocked Neo4j session
     yields a cross-tenant node the tracer raises rather than returning.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.tracer import trace_backward, trace_forward
from services.graph.app.routers import lineage_traversal


TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def _make_mock_client(records):
    """Build a Neo4j client mock whose session.run() yields the given records."""
    mock_client = MagicMock()
    mock_session = AsyncMock()

    async def _aiter(self):  # pragma: no cover - async iterator protocol
        for r in records:
            yield r

    result = MagicMock()
    result.__aiter__ = _aiter
    mock_session.run = AsyncMock(return_value=result)

    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_client.session = MagicMock(return_value=mock_session)
    mock_client.close = AsyncMock()
    return mock_client, mock_session


# ── Cypher text inspection ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_forward_cypher_has_all_nodes_tenant_guard():
    """The variable-length forward trace must filter every node by tenant."""
    # Give the mock a single empty-record generator and capture the Cypher.
    mock_client, mock_session = _make_mock_client([])

    with patch(
        "services.graph.app.fsma.tracer.TimeArrowRule",
        MagicMock(),
    ):
        await trace_forward(mock_client, "TLC-TEST", max_depth=5, tenant_id=TENANT_A)

    # First call is the variable-length path query.
    variable_length_cypher = mock_session.run.call_args_list[0][0][0]
    # It must include the per-node guard.
    assert "ALL(" in variable_length_cypher, (
        "trace_forward variable-length query is missing ALL(n IN nodes(path) ...) "
        "tenant guard — this allows cross-tenant traversal"
    )
    assert "nodes(path)" in variable_length_cypher or "nodes(p)" in variable_length_cypher
    assert "n.tenant_id = $tenant_id" in variable_length_cypher


@pytest.mark.asyncio
async def test_trace_backward_cypher_has_all_nodes_tenant_guard():
    """Backward trace must also filter every node by tenant."""
    mock_client, mock_session = _make_mock_client([])
    await trace_backward(mock_client, "TLC-TEST", max_depth=5, tenant_id=TENANT_A)

    variable_length_cypher = mock_session.run.call_args_list[0][0][0]
    assert "ALL(" in variable_length_cypher
    assert "n.tenant_id = $tenant_id" in variable_length_cypher


def test_lineage_query_has_all_nodes_tenant_guard():
    """LINEAGE_QUERY (SUPERSEDES*0..50) must filter every node."""
    cypher = lineage_traversal.LINEAGE_QUERY
    assert "ALL(" in cypher
    assert "n.tenant_id = $tenant_id" in cypher


# ── Post-query invariant checks ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_forward_invariant_raises_on_cross_tenant_node():
    """If the mocked session yields a cross-tenant node, tracer must raise."""
    # Build a record whose props.tenant_id belongs to a *different* tenant.
    leaky_record = {
        "labels": ["Lot"],
        "props": {
            "tlc": "LOT-OTHER",
            "tenant_id": TENANT_B,  # wrong tenant
            "product_description": "leaked",
            "quantity": 10,
        },
        "hop_count": 2,
    }
    mock_client, _ = _make_mock_client([leaky_record])

    with pytest.raises(ValueError) as exc_info:
        await trace_forward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_A)
    assert "invariant violation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_trace_backward_invariant_raises_on_cross_tenant_node():
    leaky_record = {
        "labels": ["TraceEvent"],
        "props": {
            "event_id": "evt-leak",
            "tenant_id": TENANT_B,
            "type": "SHIPPING",
        },
        "hop_count": 1,
    }
    mock_client, _ = _make_mock_client([leaky_record])

    with pytest.raises(ValueError) as exc_info:
        await trace_backward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_A)
    assert "invariant violation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_trace_forward_passes_tenant_to_cypher():
    """Tenant id must be passed as a Cypher parameter (not string-interpolated)."""
    mock_client, mock_session = _make_mock_client([])
    await trace_forward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_A)

    kwargs = mock_session.run.call_args_list[0][1]
    assert kwargs.get("tenant_id") == TENANT_A
    assert kwargs.get("tlc") == "LOT-A"


@pytest.mark.asyncio
async def test_trace_backward_passes_tenant_to_cypher():
    mock_client, mock_session = _make_mock_client([])
    await trace_backward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_A)

    kwargs = mock_session.run.call_args_list[0][1]
    assert kwargs.get("tenant_id") == TENANT_A


@pytest.mark.asyncio
async def test_trace_forward_facility_fallback_has_three_way_tenant_guard():
    """The secondary facility query must filter Lot, Event, and Facility all by tenant."""
    mock_client, mock_session = _make_mock_client([])
    await trace_forward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_A)

    # Second call is the facility fallback.
    facility_cypher = mock_session.run.call_args_list[1][0][0]
    assert "l.tenant_id = $tenant_id" in facility_cypher
    assert "e.tenant_id = $tenant_id" in facility_cypher
    assert "f.tenant_id = $tenant_id" in facility_cypher


@pytest.mark.asyncio
async def test_trace_backward_facility_fallback_has_three_way_tenant_guard():
    mock_client, mock_session = _make_mock_client([])
    await trace_backward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_A)

    facility_cypher = mock_session.run.call_args_list[1][0][0]
    assert "l.tenant_id = $tenant_id" in facility_cypher
    assert "e.tenant_id = $tenant_id" in facility_cypher
    assert "f.tenant_id = $tenant_id" in facility_cypher


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
