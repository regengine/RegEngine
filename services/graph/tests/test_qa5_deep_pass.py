"""Deep-QA regression tests for services/graph (fleet qa5).

Four real defects, each pinned so a future refactor fails fast:

1. ``find_gaps`` null-tenant leak: the sibling ``find_broken_chains``
   fails closed on an empty tenant (#1301) but ``find_gaps`` kept the
   ``$tenant_id IS NULL OR ...`` shim, so a caller that forgets the
   tenant reads every tenant's gap events.
2. Compliance-score fanout: ``GET /fsma/compliance/score`` counts
   ``count(DISTINCT c)`` controls over ``count(DISTINCT o)`` obligations
   for "obligation_coverage" (documented as "% of obligations that have
   >=1 mapped control") and ``sum(CASE ...)`` over fanned-out join rows
   for fresh evidence against ``count(DISTINCT e)`` items. One evidence
   proving two controls already pushes freshness past 100%.
3. Regulations mappings leak: ``GET /regulations/mappings`` scopes the
   Obligation nodes but not the joined Section nodes, so a cross-tenant
   Section linked to our obligation leaks its regulation name; the
   ``/regulations/list`` section count has the same hole.
4. Lineage fallback leak: ``LINEAGE_BY_TLC_QUERY`` resolves
   ``superseded_by`` through an unscoped ``prev`` node, leaking a
   cross-tenant TLC into our fact history.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _empty_aiter_result():
    """An async-iterable result yielding zero records."""

    async def _gen():
        if False:
            yield None

    result = MagicMock()
    result.__aiter__ = lambda self: _gen()  # noqa: E731
    return result


def _client_ctx_with_session(mock_session):
    client = AsyncMock()
    session_ctx = AsyncMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    client.session = MagicMock(return_value=session_ctx)
    client_ctx = AsyncMock()
    client_ctx.__aenter__ = AsyncMock(return_value=client)
    client_ctx.__aexit__ = AsyncMock(return_value=False)
    return client_ctx


# ── 1. find_gaps must fail closed on an empty tenant ─────────────────────────


@pytest.mark.asyncio
async def test_find_gaps_rejects_none_tenant():
    """Null tenant must raise, not read every tenant's gap events."""
    from services.graph.app.fsma.chain_integrity import find_gaps

    client = MagicMock()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_gaps(client, None)


@pytest.mark.asyncio
async def test_find_gaps_rejects_empty_tenant():
    from services.graph.app.fsma.chain_integrity import find_gaps

    client = MagicMock()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_gaps(client, "")


@pytest.mark.asyncio
async def test_find_gaps_query_has_no_null_tenant_shim():
    """The `$tenant_id IS NULL OR` escape hatch must be gone."""
    from services.graph.app.fsma.chain_integrity import find_gaps

    client = MagicMock()
    session = AsyncMock()
    session.run = AsyncMock(return_value=_empty_aiter_result())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    client.session = MagicMock(return_value=session)

    await find_gaps(client, str(TENANT_A))

    cypher = session.run.call_args.args[0]
    assert "$tenant_id IS NULL" not in cypher
    assert "e.tenant_id = $tenant_id" in cypher


# ── 2. Compliance-score fanout ───────────────────────────────────────────────


def _score_mocks(row_data):
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value=row_data)
    mock_session.run = AsyncMock(return_value=mock_result)
    return mock_session, _client_ctx_with_session(mock_session)


def _score_request():
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


@pytest.mark.asyncio
async def test_score_cypher_counts_covered_obligations_distinctly():
    """Coverage must count obligations with a control, not mapped controls.

    Old math: ``count(DISTINCT c) / count(DISTINCT o)``: three
    obligations with two controls each scores 200% "coverage".
    """
    from services.graph.app.routers.fsma import compliance as compliance_router

    mock_session, ctx = _score_mocks(
        {
            "total_obligations": 0,
            "controls_mapped": 0,
            "evidence_items": 0,
            "avg_effectiveness": None,
            "fresh_evidence": 0,
            "covered_obligations": 0,
        }
    )
    with patch.object(compliance_router, "Neo4jClient", MagicMock(return_value=ctx)):
        await compliance_router.get_compliance_score(
            request=_score_request(), tenant_id=TENANT_A, api_key={"user_id": "t"}
        )
    cypher = mock_session.run.call_args.args[0]
    assert "covered_obligations" in cypher, f"score query must aggregate covered obligations distinctly:\n{cypher}"


@pytest.mark.asyncio
async def test_score_cypher_counts_fresh_evidence_distinctly():
    """Fresh evidence must be distinct evidence nodes, not join rows."""
    from services.graph.app.routers.fsma import compliance as compliance_router

    mock_session, ctx = _score_mocks(
        {
            "total_obligations": 0,
            "controls_mapped": 0,
            "evidence_items": 0,
            "avg_effectiveness": None,
            "fresh_evidence": 0,
            "covered_obligations": 0,
        }
    )
    with patch.object(compliance_router, "Neo4jClient", MagicMock(return_value=ctx)):
        await compliance_router.get_compliance_score(
            request=_score_request(), tenant_id=TENANT_A, api_key={"user_id": "t"}
        )
    cypher = mock_session.run.call_args.args[0]
    assert "SUM(CASE" not in cypher.upper().replace(" ", ""), (
        "row-fanout SUM over join rows double-counts evidence shared by "
        f"several controls; count distinct nodes instead:\n{cypher}"
    )


@pytest.mark.asyncio
async def test_score_dimensions_never_exceed_100():
    """Fanout-shaped aggregates must still yield percentages within 0-100."""
    from services.graph.app.routers.fsma import compliance as compliance_router

    _, ctx = _score_mocks(
        {
            "total_obligations": 4,
            "controls_mapped": 6,
            "evidence_items": 2,
            "avg_effectiveness": 0.8,
            "fresh_evidence": 1,
            "covered_obligations": 2,
        }
    )
    with patch.object(compliance_router, "Neo4jClient", MagicMock(return_value=ctx)):
        result = await compliance_router.get_compliance_score(
            request=_score_request(), tenant_id=TENANT_A, api_key={"user_id": "t"}
        )
    assert result.obligation_coverage == 50.0
    assert result.evidence_freshness == 50.0
    assert 0 <= (result.overall_score or 0) <= 100


# ── 3. Regulations router section scoping ────────────────────────────────────


@pytest.mark.asyncio
async def test_mappings_query_scopes_both_section_nodes():
    """``s1``/``s2`` Section joins must carry the tenant predicate."""
    from services.graph.app.routers import regulations as regulations_router

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=_empty_aiter_result())
    ctx = _client_ctx_with_session(mock_session)
    with patch.object(regulations_router, "Neo4jClient", MagicMock(return_value=ctx)):
        await regulations_router.get_requirement_mappings(
            obligation_id=None, regulation=None, skip=0, limit=50, api_key={}, tenant_id=TENANT_A
        )
    cypher = mock_session.run.call_args.args[0]
    assert "s1.tenant_id = $tenant_id" in cypher, f"mappings query must scope s1:\n{cypher}"
    assert "s2.tenant_id = $tenant_id" in cypher, f"mappings query must scope s2:\n{cypher}"


@pytest.mark.asyncio
async def test_list_regulations_section_count_is_tenant_scoped():
    """``section_count`` must not count cross-tenant sections."""
    from services.graph.app.routers import regulations as regulations_router

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=_empty_aiter_result())
    ctx = _client_ctx_with_session(mock_session)
    with patch.object(regulations_router, "Neo4jClient", MagicMock(return_value=ctx)):
        await regulations_router.list_regulations(
            jurisdiction=None, skip=0, limit=50, api_key={}, tenant_id=TENANT_A
        )
    cypher = mock_session.run.call_args.args[0]
    assert "s.tenant_id = $tenant_id" in cypher, f"section_count join must be tenant-scoped:\n{cypher}"


# ── 4. Lineage fallback prev-node scoping ────────────────────────────────────


def test_lineage_fallback_query_scopes_prev_node():
    """``superseded_by`` must resolve through a tenant-scoped ``prev``."""
    from services.graph.app.routers.lineage_traversal import LINEAGE_BY_TLC_QUERY

    # The tenant predicate must belong to the OPTIONAL MATCH itself, inline
    # or as its own WHERE (the #3360 shape main already carried when this
    # landed), so a non-matching prev stays NULL instead of dropping rows.
    flat = " ".join(LINEAGE_BY_TLC_QUERY.split())
    inline = "OPTIONAL MATCH (f)-[:SUPERSEDES]->(prev:RegulatoryFact {tenant_id: $tenant_id})" in flat
    optional_where = re.search(
        r"OPTIONAL MATCH \(f\)-\[:SUPERSEDES\]->\(prev:RegulatoryFact\) "
        r"WHERE (prev IS NULL OR )?prev\.tenant_id = \$tenant_id RETURN ",
        flat,
    )
    assert inline or optional_where, (
        "unscoped prev leaks a cross-tenant TLC into superseded_by; "
        "scope it on the OPTIONAL MATCH so non-matches stay NULL instead of dropping rows"
    )
