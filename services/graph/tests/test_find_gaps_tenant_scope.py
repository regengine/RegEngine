"""Tenant-scope regression tests for ``chain_integrity.find_gaps``.

``find_gaps`` was the last FSMA query in the graph service still carrying
the ``$tenant_id IS NULL OR ...`` shim that every sibling already dropped
(#2540 fail-closed contract, #1301 for ``find_broken_chains`` in this same
file). With the shim, a null-tenant call returned every tenant's gap
events, and the ``missing_lot`` check matched Lots from any tenant, so a
cross-tenant UNDERWENT edge suppressed a genuine gap (false negative in a
compliance report).

Tests mock the Neo4j client and assert on the Cypher string the function
sends, plus the fail-closed behavior. Same inspection pattern as
``test_chain_integrity_tenant_scope.py``.
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

TENANT_A = "11111111-1111-1111-1111-111111111111"


def _flatten(q: str) -> str:
    """Strip Cypher `//` comments and collapse whitespace for substring match."""
    return " ".join(re.sub(r"//[^\n]*", "", q).split())


def _make_client_with_empty_results():
    """Return a client mock whose session.run() yields zero records.

    We only need to capture the Cypher: the function short-circuits on
    empty results so no post-processing code runs.
    """
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


def _make_client_with_records(records):
    """Return a client mock whose session.run() yields the given record dicts."""
    client = MagicMock()
    session = AsyncMock()

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def __aiter__(self):
            async def _gen():
                for row in self._rows:
                    yield row

            return _gen()

    session.run = AsyncMock(return_value=_Result(records))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    client.session = MagicMock(return_value=session)
    return client, session


# ── Cypher inspection ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_gaps_has_no_null_tenant_shim():
    """The ``$tenant_id IS NULL OR`` shim must be gone: a null tenant must
    never silently match every tenant's TraceEvents."""
    client, session = _make_client_with_empty_results()
    await find_gaps(client, tenant_id=TENANT_A)

    cypher = _flatten(session.run.call_args_list[0].args[0])
    assert "$tenant_id IS NULL" not in cypher, "null-tenant shim must be removed: caller must pass tenant_id"
    assert "e.tenant_id = $tenant_id" in cypher


@pytest.mark.asyncio
async def test_find_gaps_scopes_lot_in_missing_lot_subquery():
    """The ``missing_lot`` NOT EXISTS sub-query must scope the Lot to the
    caller tenant. Unscoped, a cross-tenant UNDERWENT edge satisfies the
    existence check and suppresses a genuine missing_lot gap (compliance
    false negative)."""
    client, session = _make_client_with_empty_results()
    await find_gaps(client, tenant_id=TENANT_A)

    cypher = _flatten(session.run.call_args_list[0].args[0])
    assert "l.tenant_id = $tenant_id" in cypher, f"missing_lot sub-query must scope the Lot node. Cypher:\n{cypher}"


@pytest.mark.asyncio
async def test_find_gaps_binds_tenant_id_parameter():
    """session.run() must bind $tenant_id, or the scoped predicates are
    silently inert (match nothing)."""
    client, session = _make_client_with_empty_results()
    await find_gaps(client, tenant_id=TENANT_A)

    assert session.run.call_count == 1
    kwargs = session.run.call_args_list[0].kwargs
    assert kwargs.get("tenant_id") == TENANT_A, f"missing $tenant_id binding; kwargs={kwargs!r}"


# ── Fail-fast on null-tenant callers ───────────────────────────────────────


@pytest.mark.asyncio
async def test_none_tenant_id_raises():
    """A null tenant previously returned every tenant's gap events. Callers
    that pass None must now get a loud error."""
    client, _ = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_gaps(client, tenant_id=None)


@pytest.mark.asyncio
async def test_empty_string_tenant_id_raises():
    """Empty string counts as absent: same failure mode as None."""
    client, _ = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_gaps(client, tenant_id="")


@pytest.mark.asyncio
async def test_find_all_gaps_none_tenant_raises():
    """``find_all_gaps`` delegates to ``find_gaps`` + ``find_broken_chains``.
    A null tenant must fail closed, not half-leak (gaps for everyone) and
    half-raise."""
    client, _ = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_all_gaps(client, tenant_id=None)


# ── Behavior ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_gaps_parses_gap_strings():
    """Sanity: a record's comma-joined gap string becomes a list, and the
    violation_type is set, so the endpoint summary counts stay correct."""
    client, _ = _make_client_with_records(
        [
            {
                "event_id": "evt-1",
                "type": "SHIPPING",
                "event_date": "2026-01-02",
                "document_id": "doc-9",
                "gaps": "missing_date,missing_lot",
            }
        ]
    )
    gaps = await find_gaps(client, tenant_id=TENANT_A)

    assert len(gaps) == 1
    assert gaps[0]["event_id"] == "evt-1"
    assert gaps[0]["gaps"] == ["missing_date", "missing_lot"]
    assert gaps[0]["violation_type"] == "missing_kde"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
