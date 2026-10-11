"""Follow-up regression tests for PR #3227 audit findings.

Covers the fixes applied after the re-review round:
1. ``/dashboard`` and ``/harmonize`` reconcile the middleware tenant with
   the authenticated API-key tenant (fail closed with 409 on mismatch).
2. ``MappingEngine`` routes reads and writes through the tenant database
   when one is configured (Enterprise per-tenant databases).
3. ``RegulationOverride.merge_cypher`` no longer copies ``tenant_id`` from
   ``$properties`` on MATCH, so a caller cannot retag a node.
4. Whitespace-only ``tenant_id`` is rejected like ``None``/``""``.

Each test fails on the pre-fix code and passes with the fix.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.chain_integrity import (
    find_all_gaps,
    find_broken_chains,
    find_gaps,
)
from services.graph.app.models.tenant_nodes import RegulationOverride

TENANT_A = "11111111-1111-1111-1111-111111111111"


def _make_client_with_empty_results():
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


def _make_mapping_engine(database=None):
    import services.graph.app.mapping_engine as mapping_engine_module

    engine = mapping_engine_module.MappingEngine.__new__(mapping_engine_module.MappingEngine)
    engine.driver = MagicMock()
    engine._groq_model = "test-model"
    engine.llm = MagicMock()
    if database is not None:
        engine._database = database
    return engine


# -- whitespace-only tenant guards -------------------------------------------


@pytest.mark.asyncio
async def test_find_gaps_whitespace_tenant_raises():
    client, session = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_gaps(client, tenant_id="   ")
    session.run.assert_not_called()


@pytest.mark.asyncio
async def test_find_broken_chains_whitespace_tenant_raises():
    client, session = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_broken_chains(client, tenant_id=" \t ")
    session.run.assert_not_called()


@pytest.mark.asyncio
async def test_find_all_gaps_whitespace_tenant_raises():
    client, session = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_all_gaps(client, tenant_id="  ")
    session.run.assert_not_called()


@pytest.mark.asyncio
async def test_map_requirement_whitespace_tenant_raises():
    engine = _make_mapping_engine()
    with pytest.raises(ValueError, match="tenant_id"):
        await engine.map_requirement("obligation-text", tenant_id="  ")
    engine.driver.session.assert_not_called()


# -- override MERGE must not retag tenant ------------------------------------


def _flatten(q: str) -> str:
    return " ".join(re.sub(r"//[^\n]*", "", q).split())


def test_override_merge_on_match_does_not_set_tenant():
    cypher = _flatten(RegulationOverride.merge_cypher())
    on_match = cypher.split("ON MATCH SET", 1)[1]
    assert "tenant_id" not in on_match, f"ON MATCH must not assign tenant_id. Cypher:\n{cypher}"
    assert "override_id" not in on_match, f"ON MATCH must not assign override_id. Cypher:\n{cypher}"
    assert "r.rule_id" in on_match and "r.parameter" in on_match and "r.value" in on_match, (
        f"ON MATCH must still update the mutable rule fields. Cypher:\n{cypher}"
    )


# -- engine tenant-database routing -------------------------------------------


def test_engine_session_uses_configured_database():
    engine = _make_mapping_engine(database="reg_tenant_abc")
    engine._open_session()
    engine.driver.session.assert_called_once_with(database="reg_tenant_abc")


def test_engine_session_defaults_to_home_database():
    engine = _make_mapping_engine()
    engine._open_session()
    engine.driver.session.assert_called_once_with()


@pytest.mark.asyncio
async def test_map_requirement_runs_on_tenant_database():
    engine = _make_mapping_engine(database="reg_tenant_abc")

    source_record = {"text": "source obligation", "regulation": "REG-A", "section_id": "s-1"}

    class _SourceResult:
        async def single(self):
            return source_record

    class _CandidateResult:
        def __aiter__(self):
            async def _gen():
                yield {"text": "candidate", "regulation": "REG-B", "section_id": "s-2"}
                # pragma: no cover - generator body runs on iteration
            return _gen()

    session = AsyncMock()
    session.run = AsyncMock(side_effect=[_SourceResult(), _CandidateResult(), MagicMock()])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    engine.driver.session = MagicMock(return_value=session)

    response = MagicMock()
    response.content = "0:0.90"
    engine.llm.ainvoke = AsyncMock(return_value=response)

    mappings = await engine.map_requirement("source obligation", tenant_id=TENANT_A)
    assert len(mappings) == 1

    assert engine.driver.session.call_count == 2
    for call in engine.driver.session.call_args_list:
        assert call.kwargs.get("database") == "reg_tenant_abc"


# -- route-level reconcile pins ------------------------------------------------


def test_dashboard_reconciles_api_key_tenant():
    from services.graph.app.routers.fsma.metrics import fsma_dashboard

    source = inspect.getsource(fsma_dashboard)
    assert "reconcile_tenant_scope(api_key, tenant_id" in source, (
        "dashboard must reconcile the middleware tenant with the API-key tenant"
    )
    # Reconcile must run before the try block so a 409 mismatch is not
    # swallowed into the degraded-status response.
    assert source.index("reconcile_tenant_scope") < source.index("try:")


def test_harmonize_reconciles_api_key_tenant():
    from services.graph.app.routers.regulations import harmonize_requirement

    source = inspect.getsource(harmonize_requirement)
    assert "reconcile_tenant_scope(api_key, tenant_id" in source, (
        "harmonize must reconcile the middleware tenant with the API-key tenant"
    )
    assert "scoped_tenant_id" in source
