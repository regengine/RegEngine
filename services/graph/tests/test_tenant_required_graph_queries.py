"""Tenant-required regression tests for tenant-optional graph queries.

Covers the audit finding that three graph query paths ran without a
tenant: ``find_gaps``/``find_all_gaps`` in
``services/graph/app/fsma/chain_integrity.py`` (which used a
``$tenant_id IS NULL OR ...`` shim that exposed every tenant's events
to null-tenant callers), ``RegulationOverride.merge_cypher`` and
``OverlayRelationships.TENANT_HAS_OVERRIDE`` in
``services/graph/app/models/tenant_nodes.py`` (which merged/matched on
``override_id`` alone, so one tenant's override write could clobber or
link another tenant's override), and ``MappingEngine.map_requirement``
in ``services/graph/app/mapping_engine.py`` (which built tenant-optional
Cypher and persisted ``MAPPED_TO`` edges without a tenant anchor).

Tests mock the Neo4j client and assert on the Cypher strings, following
the inspection pattern in ``test_chain_integrity_tenant_scope.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.chain_integrity import find_all_gaps, find_gaps
from services.graph.app.models.tenant_nodes import (
    OverlayRelationships,
    RegulationOverride,
)

TENANT_A = "11111111-1111-1111-1111-111111111111"


def _flatten(q: str) -> str:
    """Strip Cypher `//` comments and collapse whitespace for substring match."""
    return " ".join(re.sub(r"//[^\n]*", "", q).split())


def _make_client_with_empty_results():
    """Return a client mock whose session.run() yields zero records."""
    client = MagicMock()
    session = AsyncMock()

    async def _empty_aiter(self):  # pragma: no cover - async iter protocol
        if False:
            yield None

    empty_result = MagicMock()
    empty_result.__aiter__ = _empty_aiter
    session.run = AsyncMock(return_value=empty_result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    client.session = MagicMock(return_value=session)
    return client, session


# ── find_gaps: reject empty tenants, scope Cypher ────────────────────────────


@pytest.mark.asyncio
async def test_find_gaps_none_tenant_raises():
    client, _ = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_gaps(client, tenant_id=None)


@pytest.mark.asyncio
async def test_find_gaps_empty_string_tenant_raises():
    client, _ = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_gaps(client, tenant_id="")


@pytest.mark.asyncio
async def test_find_gaps_query_scopes_events_and_binds_tenant():
    client, session = _make_client_with_empty_results()
    await find_gaps(client, tenant_id=TENANT_A)

    cypher = _flatten(session.run.call_args_list[0].args[0])
    assert "e.tenant_id = $tenant_id" in cypher, f"find_gaps must scope TraceEvent by tenant. Cypher:\n{cypher}"
    assert "$tenant_id IS NULL" not in cypher, "null-tenant shim must be removed"
    kwargs = session.run.call_args_list[0].kwargs
    assert kwargs.get("tenant_id") == TENANT_A


@pytest.mark.asyncio
async def test_find_all_gaps_empty_tenant_raises_before_query():
    client, session = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_all_gaps(client, tenant_id=None)
    session.run.assert_not_called()


# ── RegulationOverride: tenant in the MERGE key ──────────────────────────────


def test_regulation_override_merge_cypher_keys_on_tenant():
    cypher = _flatten(RegulationOverride.merge_cypher())
    assert "tenant_id: $tenant_id" in cypher, (
        f"MERGE key must include tenant_id so one tenant cannot clobber another's override. Cypher:\n{cypher}"
    )
    assert re.search(r"MERGE\s+\(r:RegulationOverride\s*\{[^}]*tenant_id", cypher), (
        f"tenant_id must be part of the MERGE pattern itself, not just a SET. Cypher:\n{cypher}"
    )


def test_tenant_has_override_match_scopes_override_by_tenant():
    cypher = _flatten(OverlayRelationships.TENANT_HAS_OVERRIDE)
    assert "RegulationOverride {override_id: $override_id, tenant_id: $tenant_id}" in cypher, (
        f"relationship MATCH must scope the override by tenant or it can link across tenants. Cypher:\n{cypher}"
    )


# ── MappingEngine.map_requirement: tenant required ──────────────────────────


def _make_mapping_engine():
    """Build a MappingEngine without opening a real Neo4j driver."""
    import services.graph.app.mapping_engine as mapping_engine_module

    engine = mapping_engine_module.MappingEngine.__new__(mapping_engine_module.MappingEngine)
    engine.driver = MagicMock()
    engine._groq_model = "test-model"
    engine.llm = MagicMock()
    return engine


@pytest.mark.asyncio
async def test_map_requirement_none_tenant_raises():
    engine = _make_mapping_engine()
    with pytest.raises(ValueError, match="tenant_id"):
        await engine.map_requirement("obligation-text", tenant_id=None)


@pytest.mark.asyncio
async def test_map_requirement_empty_string_tenant_raises():
    engine = _make_mapping_engine()
    with pytest.raises(ValueError, match="tenant_id"):
        await engine.map_requirement("obligation-text", tenant_id="")


@pytest.mark.asyncio
async def test_map_requirement_queries_scope_obligations_and_bind_tenant():
    """Both read queries must filter on o.tenant_id and bind $tenant_id;
    the persistence MERGE must anchor both endpoints by tenant."""
    engine = _make_mapping_engine()

    source_record = {"text": "source obligation", "regulation": "REG-A", "section_id": "s-1"}
    candidate_record = {"text": "candidate obligation", "regulation": "REG-B", "section_id": "s-2"}

    class _SourceResult:
        async def single(self):
            return source_record

    class _CandidateResult:
        def __aiter__(self):
            async def _gen():
                yield candidate_record

            return _gen()

    class _WriteResult:
        pass

    session = AsyncMock()
    session.run = AsyncMock(side_effect=[_SourceResult(), _CandidateResult(), _WriteResult()])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    engine.driver.session = MagicMock(return_value=session)

    response = MagicMock()
    response.content = "0:0.90"
    engine.llm.ainvoke = AsyncMock(return_value=response)

    mappings = await engine.map_requirement("source obligation", tenant_id=TENANT_A)

    assert len(mappings) == 1
    assert session.run.call_count == 3

    source_cypher = _flatten(session.run.call_args_list[0].args[0])
    assert "o.tenant_id = $tenant_id" in source_cypher, f"source query must scope Obligation. Cypher:\n{source_cypher}"
    # The joined Section is mixed shared-or-own catalog (the loader writes
    # sections with no tenant_id), so it carries null-or-own on the
    # property. The banned shape is the fail-open parameter shim, which
    # would expose every tenant's rows to a null-tenant caller.
    assert "$tenant_id IS NULL" not in source_cypher, f"fail-open shim in source query. Cypher:\n{source_cypher}"
    assert "(s.tenant_id IS NULL OR s.tenant_id = $tenant_id)" in source_cypher, (
        f"source query must scope Section. Cypher:\n{source_cypher}"
    )

    candidates_cypher = _flatten(session.run.call_args_list[1].args[0])
    assert "o.tenant_id = $tenant_id" in candidates_cypher, (
        f"candidate query must scope Obligation. Cypher:\n{candidates_cypher}"
    )
    assert "$tenant_id IS NULL" not in candidates_cypher, (
        f"fail-open shim in candidate query. Cypher:\n{candidates_cypher}"
    )
    assert "(s.tenant_id IS NULL OR s.tenant_id = $tenant_id)" in candidates_cypher, (
        f"candidate query must scope Section. Cypher:\n{candidates_cypher}"
    )

    persist_cypher = _flatten(session.run.call_args_list[2].args[0])
    assert persist_cypher.count("tenant_id: $tenant_id") >= 2, (
        f"persistence MATCH must anchor BOTH obligation endpoints by tenant. Cypher:\n{persist_cypher}"
    )

    for i, call in enumerate(session.run.call_args_list):
        kwargs = call.kwargs
        assert kwargs.get("tenant_id") == TENANT_A, f"query #{i} missing $tenant_id binding; kwargs={kwargs!r}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
