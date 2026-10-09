"""LLM failures in harmonization must not be reported as completed with zero mappings.

Regression test for the audit finding: ``MappingEngine.map_requirement``
caught every LLM exception and returned ``[]``, and the
``POST /harmonize/{obligation_id}`` endpoint then returned
``{"status": "completed", "mappings_found": 0}``. Callers could not tell
an LLM outage from a genuine "no similar requirements" result.

The contract after the fix:
- LLM invocation failure propagates out of ``map_requirement`` (the
  router converts it to 503 "Harmonization engine unavailable").
- A missing LLM client raises instead of returning ``[]``.
- Genuine empty results (unknown source, no candidates, LLM says NONE)
  still return ``[]`` and the endpoint still reports them as completed.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import services.graph.app.mapping_engine as mapping_engine_module
from services.graph.app.routers import regulations as regulations_router

TENANT = "11111111-1111-1111-1111-111111111111"


def _make_engine(*, llm=None, runs=None):
    engine = mapping_engine_module.MappingEngine.__new__(mapping_engine_module.MappingEngine)
    engine.driver = MagicMock()
    engine._groq_model = "test-model"
    engine.llm = llm
    if runs is not None:
        session = AsyncMock()
        session.run = AsyncMock(side_effect=runs)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        engine.driver.session = MagicMock(return_value=session)
    return engine


class _SourceResult:
    def __init__(self, row):
        self._row = row

    async def single(self):
        return self._row


class _CandidateResult:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        async def _gen():
            for row in self._rows:
                yield row

        return _gen()


def _reads(source, candidates):
    return [_SourceResult(source), _CandidateResult(candidates)]


SOURCE = {"text": "source obligation", "regulation": "REG-A", "section_id": "s-1"}
CANDIDATE = {"text": "candidate obligation", "regulation": "REG-B", "section_id": "s-2"}


@pytest.mark.asyncio
async def test_map_requirement_llm_failure_raises_instead_of_empty():
    """An LLM exception must propagate, not become a silent empty result."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=ConnectionError("llm down"))
    engine = _make_engine(llm=llm, runs=_reads(SOURCE, [CANDIDATE]))
    with pytest.raises(ConnectionError, match="llm down"):
        await engine.map_requirement("source obligation", tenant_id=TENANT)


@pytest.mark.asyncio
async def test_map_requirement_without_llm_client_raises():
    """No configured LLM client must raise, not report completed with zero."""
    engine = _make_engine(llm=None)
    with pytest.raises(RuntimeError, match="not configured"):
        await engine.map_requirement("source obligation", tenant_id=TENANT)


@pytest.mark.asyncio
async def test_map_requirement_genuine_none_result_still_returns_empty():
    """The LLM answering NONE is a real completed result and stays []."""
    llm = MagicMock()
    response = MagicMock()
    response.content = "NONE"
    llm.ainvoke = AsyncMock(return_value=response)
    engine = _make_engine(llm=llm, runs=_reads(SOURCE, [CANDIDATE]))
    assert await engine.map_requirement("source obligation", tenant_id=TENANT) == []


@pytest.mark.asyncio
async def test_map_requirement_unknown_source_still_returns_empty():
    """A missing source obligation is a real completed result and stays []."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()
    engine = _make_engine(llm=llm, runs=[_SourceResult(None)])
    assert await engine.map_requirement("unknown obligation", tenant_id=TENANT) == []
    llm.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_harmonize_reports_503_when_llm_fails():
    """The endpoint must not report status completed when the LLM failed."""
    fake_engine = MagicMock()
    fake_engine.map_requirement = AsyncMock(side_effect=ConnectionError("llm down"))
    fake_engine.close = AsyncMock()

    with patch.object(mapping_engine_module, "MappingEngine", return_value=fake_engine):
        with pytest.raises(HTTPException) as exc_info:
            await regulations_router.harmonize_requirement(
                "source obligation",
                api_key=MagicMock(),
                tenant_id=uuid.UUID(TENANT),
            )
    assert exc_info.value.status_code == 503
    fake_engine.close.assert_awaited()


@pytest.mark.asyncio
async def test_harmonize_still_reports_completed_for_genuine_empty():
    """A genuine zero-mapping result still returns status completed."""
    fake_engine = MagicMock()
    fake_engine.map_requirement = AsyncMock(return_value=[])
    fake_engine.close = AsyncMock()

    with patch.object(mapping_engine_module, "MappingEngine", return_value=fake_engine):
        resp = await regulations_router.harmonize_requirement(
            "source obligation",
            api_key=MagicMock(),
            tenant_id=uuid.UUID(TENANT),
        )
    assert resp["status"] == "completed"
    assert resp["mappings_found"] == 0
    assert resp["mappings"] == []
    fake_engine.close.assert_awaited()
