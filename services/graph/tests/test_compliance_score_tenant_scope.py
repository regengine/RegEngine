"""Tenant-scope regression tests for `GET /fsma/compliance/score` (#1273).

Prior to the fix the Cypher query anchored on
`MATCH (o:Obligation {tenant_id: $tenant_id})` but the two
`OPTIONAL MATCH` clauses for `Control` and `Evidence` had no tenant
filter. Any cross-tenant `REQUIRES` or `PROVEN_BY` edge — created by an
ingestion bug, a mistakenly shared global control, or an explicit
mapping — would pull tenant B's controls and evidence into tenant A's
compliance score. That's both wrong numbers AND an info-disclosure
leak (controls_mapped / evidence_items reflect another tenant's data).

These tests inspect the Cypher string the endpoint sends to Neo4j so a
future refactor that re-loosens the predicates fails fast in CI.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.routers.fsma import compliance as compliance_router


TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _make_mock_neo4j_client(row_data):
    """Construct a Neo4jClient mock whose session.run().single() returns row_data.

    The route uses two nested `async with` blocks:
        async with Neo4jClient() as client:
            async with client.session() as session:
                result = await session.run(query, tenant_id=...)
                row = await result.single()
    """
    mock_client = AsyncMock()
    mock_session = AsyncMock()

    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value=row_data)
    mock_session.run = AsyncMock(return_value=mock_result)

    # `async with client.session()` — session() returns an async ctx manager.
    session_ctx = AsyncMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_client.session = MagicMock(return_value=session_ctx)

    # `async with Neo4jClient() as client` — Neo4jClient() returns an async
    # ctx manager whose __aenter__ yields the client itself.
    client_ctx = AsyncMock()
    client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    client_ctx.__aexit__ = AsyncMock(return_value=False)

    return client_ctx, mock_client, mock_session


def _make_request():
    """Build a minimal Starlette Request that satisfies slowapi's type check.

    The endpoint is wrapped by `@limiter.limit(...)` which inspects
    `kwargs["request"]` and rejects MagicMock. A bare scope dict is
    enough — we don't actually exercise rate limiting.
    """
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "path": "/fsma/compliance/score",
        "query_string": b"",
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "app": MagicMock(state=MagicMock()),
    }
    return Request(scope)


async def _call_endpoint(mock_client_ctx):
    """Invoke `get_compliance_score` directly with patched Neo4jClient."""
    request = _make_request()
    api_key = {"user_id": "test-user"}

    with patch.object(
        compliance_router,
        "Neo4jClient",
        MagicMock(return_value=mock_client_ctx),
    ):
        return await compliance_router.get_compliance_score(
            request=request,
            tenant_id=TENANT_A,
            api_key=api_key,
        )


@pytest.mark.asyncio
async def test_cypher_filters_control_by_tenant():
    """OPTIONAL MATCH on Control must include `c.tenant_id = $tenant_id`.

    Without this filter, a Control belonging to tenant B reached through
    a cross-tenant REQUIRES edge counts toward tenant A's score (#1273).
    """
    client_ctx, _, mock_session = _make_mock_neo4j_client(
        # Empty-row response triggers the "no data" demo path, which is
        # fine — we only care about the Cypher actually sent.
        row_data={
            "total_obligations": 0,
            "controls_mapped": 0,
            "evidence_items": 0,
            "avg_effectiveness": None,
            "fresh_evidence": 0,
        },
    )

    await _call_endpoint(client_ctx)

    cypher = mock_session.run.call_args.args[0]
    # Must filter Control nodes — the bug was the absence of any
    # `c.tenant_id` predicate following the OPTIONAL MATCH on Control.
    assert "c.tenant_id = $tenant_id" in cypher, (
        "#1273: OPTIONAL MATCH on Control must include `WHERE c.tenant_id "
        "= $tenant_id` so cross-tenant REQUIRES edges don't leak tenant B's "
        f"controls into tenant A's score. Cypher was:\n{cypher}"
    )


@pytest.mark.asyncio
async def test_cypher_filters_evidence_by_tenant():
    """OPTIONAL MATCH on Evidence must include `e.tenant_id = $tenant_id`."""
    client_ctx, _, mock_session = _make_mock_neo4j_client(
        row_data={
            "total_obligations": 0,
            "controls_mapped": 0,
            "evidence_items": 0,
            "avg_effectiveness": None,
            "fresh_evidence": 0,
        },
    )

    await _call_endpoint(client_ctx)

    cypher = mock_session.run.call_args.args[0]
    assert "e.tenant_id = $tenant_id" in cypher, (
        "#1273: OPTIONAL MATCH on Evidence must include `WHERE e.tenant_id "
        "= $tenant_id`. Otherwise cross-tenant PROVEN_BY edges leak "
        f"tenant B's evidence freshness into tenant A's score. Cypher was:\n{cypher}"
    )


@pytest.mark.asyncio
async def test_cypher_anchor_still_scoped_to_tenant():
    """Anchor `(o:Obligation {tenant_id: $tenant_id})` must remain scoped.

    Defense in depth: this assertion was the original guard before the
    OPTIONAL MATCH clauses were added. Locks it in alongside the new
    Control/Evidence filters so a future refactor that drops the inline
    map syntax in favour of a separate WHERE doesn't lose tenancy.
    """
    client_ctx, _, mock_session = _make_mock_neo4j_client(
        row_data={
            "total_obligations": 0,
            "controls_mapped": 0,
            "evidence_items": 0,
            "avg_effectiveness": None,
            "fresh_evidence": 0,
        },
    )

    await _call_endpoint(client_ctx)

    cypher = mock_session.run.call_args.args[0]
    assert "Obligation" in cypher
    # Either inline map syntax or a follow-up WHERE is acceptable.
    has_inline_filter = "Obligation {tenant_id: $tenant_id}" in cypher
    has_where_filter = "o.tenant_id = $tenant_id" in cypher
    assert has_inline_filter or has_where_filter, (
        "Obligation anchor must be tenant-scoped (inline map or WHERE). "
        f"Cypher was:\n{cypher}"
    )


@pytest.mark.asyncio
async def test_endpoint_passes_caller_tenant_id_as_param():
    """The `$tenant_id` Cypher parameter must be the caller's tenant.

    The fix is structural (predicates added) but it's only meaningful if
    the same tenant_id is bound on every reference — the route already
    binds once via `tenant_id=str(tenant_id)`. Asserts the binding so a
    future refactor that splits parameters doesn't accidentally pass
    different ids per predicate.
    """
    client_ctx, _, mock_session = _make_mock_neo4j_client(
        row_data={
            "total_obligations": 0,
            "controls_mapped": 0,
            "evidence_items": 0,
            "avg_effectiveness": None,
            "fresh_evidence": 0,
        },
    )

    await _call_endpoint(client_ctx)

    kwargs = mock_session.run.call_args.kwargs
    assert kwargs.get("tenant_id") == str(TENANT_A), (
        "endpoint must bind $tenant_id to the caller's tenant; "
        f"actual kwargs: {kwargs!r}"
    )
