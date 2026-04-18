"""
Tenant-scoping regression tests for services.graph.app.fsma.queries.

Covers issue #1250: `_tag_event_risk_flag` previously issued a Cypher
`MATCH (e:TraceEvent {event_id: $event_id})` with no tenant predicate.
Because the TraceEvent uniqueness constraint is composite
``(event_id, tenant_id)``, two tenants legitimately CAN share an
``event_id`` -- the old query would mutate whichever node the Neo4j
planner found first, silently corrupting a neighbor tenant's compliance
signal.

These tests lock in the fix:
  - The Cypher query includes ``tenant_id: $tenant_id`` in the MATCH.
  - The Python function requires ``tenant_id`` as a keyword-only kwarg
    and raises ValueError on empty/None.
  - When the tenant does not own a matching event, the function returns
    False (rather than silently succeeding on another tenant's row).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.graph.app.fsma.queries import _tag_event_risk_flag


@pytest.fixture
def mock_neo4j_session():
    session = MagicMock()
    session.run = AsyncMock()
    return session


@pytest.fixture
def mock_neo4j_client(mock_neo4j_session):
    client = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    client.session.return_value = ctx
    return client


@pytest.mark.asyncio
async def test_tag_event_risk_flag_requires_tenant_id(mock_neo4j_client):
    """Calling without tenant_id must raise -- fail-closed behavior."""
    with pytest.raises(TypeError):
        # missing tenant_id kwarg entirely (keyword-only arg)
        await _tag_event_risk_flag(
            mock_neo4j_client, "evt-001", "BROKEN_CHAIN"
        )  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_tag_event_risk_flag_rejects_empty_tenant_id(mock_neo4j_client):
    """Empty string / None tenant_id must raise rather than degrading to
    a cross-tenant MATCH."""
    with pytest.raises(ValueError):
        await _tag_event_risk_flag(
            mock_neo4j_client,
            "evt-001",
            "BROKEN_CHAIN",
            tenant_id="",
        )


@pytest.mark.asyncio
async def test_tag_event_risk_flag_query_includes_tenant_predicate(
    mock_neo4j_client, mock_neo4j_session
):
    """The Cypher MATCH must include both event_id AND tenant_id."""
    mock_result = MagicMock()
    mock_result.single = AsyncMock(return_value={"tagged_id": "evt-001"})
    mock_neo4j_session.run.return_value = mock_result

    success = await _tag_event_risk_flag(
        mock_neo4j_client,
        "evt-001",
        "BROKEN_CHAIN",
        tenant_id="11111111-1111-1111-1111-111111111111",
    )

    assert success is True
    call_args = mock_neo4j_session.run.call_args
    cypher = call_args[0][0]
    assert "tenant_id: $tenant_id" in cypher
    assert "event_id: $event_id" in cypher
    # tenant_id must be passed as a parameter
    kwargs = call_args[1]
    assert kwargs["tenant_id"] == "11111111-1111-1111-1111-111111111111"
    assert kwargs["event_id"] == "evt-001"


@pytest.mark.asyncio
async def test_tag_event_risk_flag_returns_false_when_wrong_tenant(
    mock_neo4j_client, mock_neo4j_session
):
    """If two tenants have colliding event_ids, a call from tenant B
    against an event_id that exists only in tenant A must return False
    (empty MATCH) rather than mutating tenant A's row.

    We simulate this by having the Neo4j session return None from
    ``result.single()`` -- as it would when the tenant_id predicate
    excludes the other tenant's node.
    """
    mock_result = MagicMock()
    mock_result.single = AsyncMock(return_value=None)  # no match
    mock_neo4j_session.run.return_value = mock_result

    success = await _tag_event_risk_flag(
        mock_neo4j_client,
        "evt-shared-id",
        "TIME_ARROW",
        tenant_id="22222222-2222-2222-2222-222222222222",
    )

    assert success is False


@pytest.mark.asyncio
async def test_tag_event_risk_flag_passes_tenant_id_into_run(
    mock_neo4j_client, mock_neo4j_session
):
    """Regression: ensure the tenant_id kwarg is threaded into
    session.run as a parameter binding (not interpolated as a string)."""
    mock_result = MagicMock()
    mock_result.single = AsyncMock(return_value={"tagged_id": "evt-99"})
    mock_neo4j_session.run.return_value = mock_result

    tenant = "33333333-3333-3333-3333-333333333333"
    await _tag_event_risk_flag(
        mock_neo4j_client,
        "evt-99",
        "BROKEN_CHAIN",
        tenant_id=tenant,
    )

    call_args = mock_neo4j_session.run.call_args
    # tenant_id is NOT baked into the Cypher text; it must be a parameter
    assert tenant not in call_args[0][0]
    assert call_args[1]["tenant_id"] == tenant
