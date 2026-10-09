"""Bounded-expansion regression tests (audit medium).

``get_compliance_gaps`` used to load every provision for a jurisdiction
with an unbounded ``RETURN prov`` and filter in Python, and the tracer
variable-length queries relied only on a trailing ``LIMIT 5000`` that
trims final rows after path expansion already exploded. These tests
assert the server-side guards: SKIP/LIMIT paging on the jurisdiction
load and a path cap before UNWIND on every trace path query.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app import overlay_resolver as overlay_resolver_module
from services.graph.app.fsma.tracer import (
    MAX_TRACE_PATHS,
    trace_backward,
    trace_forward,
)
from services.graph.app.overlay_resolver import (
    DEFAULT_GAP_PAGE_SIZE,
    MAX_GAP_PAGE_SIZE,
    OverlayResolver,
)

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_STR = "11111111-1111-1111-1111-111111111111"


def _make_trace_client():
    """Neo4j client mock yielding zero records (Cypher inspection only)."""
    mock_client = MagicMock()
    mock_session = AsyncMock()

    async def _aiter(self):
        return
        yield  # pragma: no cover - empty generator

    result = MagicMock()
    result.__aiter__ = _aiter
    mock_session.run = AsyncMock(return_value=result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_client.session = MagicMock(return_value=mock_session)
    mock_client.close = AsyncMock()
    return mock_client, mock_session


class _SingleResult:
    def __init__(self, records):
        self._records = list(records)

    async def single(self):
        return self._records[0] if self._records else None

    def __aiter__(self):
        async def _gen():
            for r in self._records:
                yield r

        return _gen()


def _install_gaps_mocks():
    """Route OverlayResolver Neo4jClient builds to scripted mocks."""
    tenant_session = AsyncMock()
    tenant_session.run = AsyncMock(return_value=_SingleResult([{"mapped_hashes": []}]))
    tenant_session.__aenter__ = AsyncMock(return_value=tenant_session)
    tenant_session.__aexit__ = AsyncMock(return_value=False)
    tenant_client = MagicMock()
    tenant_client.session = MagicMock(return_value=tenant_session)
    tenant_client.close = AsyncMock()

    global_session = AsyncMock()
    global_session.run = AsyncMock(return_value=_SingleResult([]))
    global_session.__aenter__ = AsyncMock(return_value=global_session)
    global_session.__aexit__ = AsyncMock(return_value=False)
    global_client = MagicMock()
    global_client.session = MagicMock(return_value=global_session)
    global_client.close = AsyncMock()

    def _factory(database=None, **kwargs):
        if database and database.startswith("reg_tenant_"):
            return tenant_client
        return global_client

    return _factory, global_session


async def _run_gaps(**kwargs):
    factory, global_session = _install_gaps_mocks()
    with patch.object(overlay_resolver_module, "Neo4jClient") as mock_cls:
        mock_cls.side_effect = factory
        mock_cls.get_global_database_name = MagicMock(return_value="neo4j")
        mock_cls.get_tenant_database_name = MagicMock(return_value=f"reg_tenant_{TENANT_A}")
        resolver = OverlayResolver(tenant_id=TENANT_A)
        result = await resolver.get_compliance_gaps(
            product_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            jurisdiction="US",
            **kwargs,
        )
    assert global_session.run.call_count == 1
    cypher = global_session.run.call_args.args[0]
    params = global_session.run.call_args.args[1]
    return result, cypher, params


@pytest.mark.asyncio
async def test_gaps_jurisdiction_load_is_paged_server_side():
    """The jurisdiction provision load must page with SKIP/LIMIT."""
    result, cypher, params = await _run_gaps()
    flat = " ".join(cypher.split())
    assert "SKIP $offset LIMIT $limit" in flat
    assert params["limit"] == DEFAULT_GAP_PAGE_SIZE
    assert params["offset"] == 0
    assert result["limit"] == DEFAULT_GAP_PAGE_SIZE
    assert result["offset"] == 0


@pytest.mark.asyncio
async def test_gaps_limit_is_clamped_to_ceiling():
    """An outsized limit must clamp to MAX_GAP_PAGE_SIZE, never unbounded."""
    _, _, params = await _run_gaps(limit=10**9)
    assert params["limit"] == MAX_GAP_PAGE_SIZE


@pytest.mark.asyncio
async def test_gaps_rejects_nonpositive_limit_and_negative_offset():
    _, _, params = await _run_gaps(limit=0, offset=-5)
    assert params["limit"] >= 1
    assert params["offset"] == 0


@pytest.mark.asyncio
async def test_trace_forward_caps_path_expansion_before_unwind():
    """Forward path queries must cap paths before UNWIND, both variants."""
    mock_client, mock_session = _make_trace_client()
    await trace_forward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_STR)
    assert mock_session.run.call_args_list[0][1].get("path_cap") == MAX_TRACE_PATHS
    cypher = mock_session.run.call_args_list[0][0][0]
    assert "LIMIT $path_cap" in cypher
    assert cypher.index("LIMIT $path_cap") < cypher.index("UNWIND")

    mock_client, mock_session = _make_trace_client()
    await trace_forward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_STR, enforce_time_arrow=False)
    cypher = mock_session.run.call_args_list[0][0][0]
    assert "LIMIT $path_cap" in cypher
    assert cypher.index("LIMIT $path_cap") < cypher.index("UNWIND")
    assert mock_session.run.call_args_list[0][1].get("path_cap") == MAX_TRACE_PATHS


@pytest.mark.asyncio
async def test_trace_backward_caps_path_expansion_before_unwind():
    """Backward path query must cap paths before UNWIND."""
    mock_client, mock_session = _make_trace_client()
    await trace_backward(mock_client, "LOT-A", max_depth=5, tenant_id=TENANT_STR)
    cypher = mock_session.run.call_args_list[0][0][0]
    assert "LIMIT $path_cap" in cypher
    assert cypher.index("LIMIT $path_cap") < cypher.index("UNWIND")
    assert mock_session.run.call_args_list[0][1].get("path_cap") == MAX_TRACE_PATHS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
