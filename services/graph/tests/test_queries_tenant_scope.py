"""Tenant-scope regression tests for ``services/graph/app/fsma/queries.py``.

Context (#1261): the tracer SHIPPED_TO / SHIPPED queries got a three-way
tenant guard via #1256, but the sibling queries in ``queries.py`` —
``get_lot_timeline`` and ``query_events_by_range`` — had the same
partial-scoping pattern and were missed by the audit. This file pins the
fix:

  • ``get_lot_timeline`` must require ``tenant_id`` on Lot, TraceEvent,
    AND the optional Facility.
  • ``query_events_by_range`` must require ``tenant_id`` on TraceEvent,
    AND the optional joined Lot AND optional joined Facility.

Both functions must also drop rows and raise ``ValueError`` if a post-
query invariant check detects a cross-tenant node (belt-and-suspenders
against future Cypher edits or planner fallbacks).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.queries import (
    get_lot_timeline,
    query_events_by_range,
)

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _make_mock_client(records):
    """Neo4j client whose session.run() yields the given records."""
    mock_client = MagicMock()
    mock_session = AsyncMock()

    async def _aiter(self):  # pragma: no cover - async-iterator protocol
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


# ─────────────────────────────────────────────────────────────────────
# Cypher text pinning — predicates must exist on every joined node
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lot_timeline_cypher_scopes_lot_event_and_facility():
    """Timeline query must predicate tenant_id on l, e, and f."""
    mock_client, mock_session = _make_mock_client([])
    await get_lot_timeline(mock_client, tlc="LOT-A", tenant_id=TENANT_A)

    cypher = mock_session.run.call_args[0][0]
    assert "l.tenant_id = $tenant_id" in cypher, "get_lot_timeline must scope the Lot by tenant"
    assert "e.tenant_id = $tenant_id" in cypher, (
        "get_lot_timeline must scope the TraceEvent by tenant — without "
        "this predicate, a lot that UNDERWENT an event in another tenant "
        "leaks that event into the timeline (#1261)"
    )
    assert "f.tenant_id = $tenant_id" in cypher, (
        "get_lot_timeline must scope the optional Facility by tenant — "
        "otherwise OCCURRED_AT can cross into another tenant's location"
    )


@pytest.mark.asyncio
async def test_query_events_by_range_cypher_scopes_event_lot_and_facility():
    """FDA date-range query must predicate tenant_id on e, l, and f."""
    mock_client, mock_session = _make_mock_client([])
    await query_events_by_range(
        mock_client,
        start_date="2026-01-01",
        end_date="2026-12-31",
        tenant_id=TENANT_A,
    )

    cypher = mock_session.run.call_args[0][0]
    assert "e.tenant_id = $tenant_id" in cypher
    assert "l.tenant_id = $tenant_id" in cypher, (
        "query_events_by_range must scope the joined Lot by tenant — the "
        "FDA Sortable Spreadsheet export was leaking cross-tenant "
        "product_description and quantity without this predicate (#1261)"
    )
    assert "f.tenant_id = $tenant_id" in cypher, "query_events_by_range must scope the joined Facility by tenant"
    # EPCIS export RETURN contract (#3680): Digital Link + shipping endpoints
    assert "l.gtin as gtin" in cypher
    assert "input_lot.tlc as input_tlc" in cypher
    assert "input_lot.gtin as input_gtin" in cypher
    assert "ship_from_f.gln as ship_from_gln" in cypher
    assert "ship_to_f.gln as ship_to_gln" in cypher


# ─────────────────────────────────────────────────────────────────────
# Parameter-binding — $tenant_id must be passed, never interpolated
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lot_timeline_passes_tenant_parameter():
    mock_client, mock_session = _make_mock_client([])
    await get_lot_timeline(mock_client, tlc="LOT-A", tenant_id=TENANT_A)

    kwargs = mock_session.run.call_args[1]
    assert kwargs["tenant_id"] == TENANT_A
    assert kwargs["tlc"] == "LOT-A"


@pytest.mark.asyncio
async def test_query_events_by_range_passes_tenant_parameter():
    mock_client, mock_session = _make_mock_client([])
    await query_events_by_range(
        mock_client,
        start_date="2026-01-01",
        end_date="2026-12-31",
        tenant_id=TENANT_A,
    )

    kwargs = mock_session.run.call_args[1]
    assert kwargs["tenant_id"] == TENANT_A


# ─────────────────────────────────────────────────────────────────────
# Post-query invariant — raise if a cross-tenant record slips through
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lot_timeline_raises_on_cross_tenant_event():
    """If Cypher ever returns a cross-tenant TraceEvent, the helper raises."""
    leaky_record = {
        "event_id": "evt-leak",
        "type": "SHIPPING",
        "event_date": "2026-04-01",
        "event_time": None,
        "confidence": 1.0,
        "event_tenant": TENANT_B,  # WRONG tenant
        "facility_name": None,
        "facility_gln": None,
        "facility_tenant": None,
    }
    mock_client, _ = _make_mock_client([leaky_record])

    with pytest.raises(ValueError) as exc_info:
        await get_lot_timeline(mock_client, tlc="LOT-A", tenant_id=TENANT_A)
    assert "invariant violation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_lot_timeline_raises_on_cross_tenant_facility():
    """Event is in-tenant but the facility is cross-tenant — must raise."""
    leaky_record = {
        "event_id": "evt-1",
        "type": "RECEIVING",
        "event_date": "2026-04-01",
        "event_time": None,
        "confidence": 0.9,
        "event_tenant": TENANT_A,  # correct
        "facility_name": "Other Tenant's Facility",
        "facility_gln": "0000000000000",
        "facility_tenant": TENANT_B,  # WRONG
    }
    mock_client, _ = _make_mock_client([leaky_record])

    with pytest.raises(ValueError) as exc_info:
        await get_lot_timeline(mock_client, tlc="LOT-A", tenant_id=TENANT_A)
    assert "facility invariant violation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_query_events_by_range_raises_on_cross_tenant_lot():
    leaky_record = {
        "event_id": "evt-1",
        "type": "SHIPPING",
        "event_date": "2026-04-01",
        "event_time": None,
        "risk_flag": None,
        "tlc": "LOT-OTHER",
        "gtin": "09506000134352",
        "product_description": "LEAKED PRODUCT",
        "quantity": 100,
        "uom": "KG",
        "lot_tenant": TENANT_B,  # WRONG
        "input_tlc": None,
        "input_gtin": None,
        "ship_from_gln": None,
        "ship_to_gln": None,
        "facility_name": None,
        "facility_gln": None,
        "facility_address": None,
        "facility_tenant": None,
    }
    mock_client, _ = _make_mock_client([leaky_record])

    with pytest.raises(ValueError) as exc_info:
        await query_events_by_range(
            mock_client,
            start_date="2026-01-01",
            end_date="2026-12-31",
            tenant_id=TENANT_A,
        )
    assert "lot invariant violation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_query_events_by_range_raises_on_cross_tenant_facility():
    leaky_record = {
        "event_id": "evt-1",
        "type": "SHIPPING",
        "event_date": "2026-04-01",
        "event_time": None,
        "risk_flag": None,
        "tlc": "LOT-A",
        "gtin": "09506000134352",
        "product_description": "OK PRODUCT",
        "quantity": 50,
        "uom": "KG",
        "lot_tenant": TENANT_A,  # correct
        "input_tlc": None,
        "input_gtin": None,
        "ship_from_gln": "0614141000005",
        "ship_to_gln": "0614141123452",
        "facility_name": "Other Tenant's Depot",
        "facility_gln": "9999999999999",
        "facility_address": "Somewhere Else",
        "facility_tenant": TENANT_B,  # WRONG
    }
    mock_client, _ = _make_mock_client([leaky_record])

    with pytest.raises(ValueError) as exc_info:
        await query_events_by_range(
            mock_client,
            start_date="2026-01-01",
            end_date="2026-12-31",
            tenant_id=TENANT_A,
        )
    assert "facility invariant violation" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────
# Happy path — correct-tenant records pass through unchanged
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lot_timeline_returns_in_tenant_records():
    good_record = {
        "event_id": "evt-a",
        "type": "RECEIVING",
        "event_date": "2026-04-01",
        "event_time": "12:00",
        "confidence": 0.95,
        "event_tenant": TENANT_A,
        "facility_name": "Tenant A Depot",
        "facility_gln": "1234567890123",
        "facility_tenant": TENANT_A,
    }
    mock_client, _ = _make_mock_client([good_record])

    out = await get_lot_timeline(mock_client, tlc="LOT-A", tenant_id=TENANT_A)

    assert len(out) == 1
    assert out[0]["event_id"] == "evt-a"
    assert out[0]["facility"]["name"] == "Tenant A Depot"


@pytest.mark.asyncio
async def test_query_events_by_range_returns_in_tenant_records():
    good_record = {
        "event_id": "evt-a",
        "type": "SHIPPING",
        "event_date": "2026-04-01",
        "event_time": None,
        "risk_flag": None,
        "tlc": "LOT-A",
        "gtin": "09506000134352",
        "product_description": "Lettuce",
        "quantity": 100,
        "uom": "KG",
        "lot_tenant": TENANT_A,
        "input_tlc": None,
        "input_gtin": None,
        "ship_from_gln": "0614141000005",
        "ship_to_gln": "0614141123452",
        "facility_name": "Tenant A Farm",
        "facility_gln": "1234567890123",
        "facility_address": "101 Farm Rd",
        "facility_tenant": TENANT_A,
    }
    mock_client, _ = _make_mock_client([good_record])

    out = await query_events_by_range(
        mock_client,
        start_date="2026-01-01",
        end_date="2026-12-31",
        tenant_id=TENANT_A,
    )

    assert len(out) == 1
    assert out[0]["product_description"] == "Lettuce"
    assert out[0]["location_description"] == "Tenant A Farm"
    assert out[0]["gtin"] == "09506000134352"
    assert out[0]["input_tlc"] == ""
    assert out[0]["input_gtin"] == ""
    assert out[0]["ship_from_gln"] == "0614141000005"
    assert out[0]["ship_to_gln"] == "0614141123452"


# ─────────────────────────────────────────────────────────────────────
# Null / empty tenant — fail closed (#2540)
# ─────────────────────────────────────────────────────────────────────
# Previously tenant_id=None was an "admin-scope" path that returned every
# tenant's rows via the `$tenant_id IS NULL OR ...` Cypher shim. On the
# default Community Neo4j (one shared DB) that is a cross-tenant leak the
# moment any caller forgets to pass a tenant. Both helpers now fail closed.


@pytest.mark.asyncio
async def test_get_lot_timeline_none_tenant_raises():
    """#2540: tenant_id=None must raise rather than returning all tenants."""
    mock_client, _ = _make_mock_client([])
    with pytest.raises(ValueError, match="tenant_id"):
        await get_lot_timeline(mock_client, tlc="LOT-A", tenant_id=None)


@pytest.mark.asyncio
async def test_get_lot_timeline_empty_tenant_raises():
    """#2540: empty-string tenant_id is treated as absent — same failure."""
    mock_client, _ = _make_mock_client([])
    with pytest.raises(ValueError, match="tenant_id"):
        await get_lot_timeline(mock_client, tlc="LOT-A", tenant_id="")


@pytest.mark.asyncio
async def test_query_events_by_range_none_tenant_raises():
    """#2540: the FDA-export query must fail closed on a null tenant."""
    mock_client, _ = _make_mock_client([])
    with pytest.raises(ValueError, match="tenant_id"):
        await query_events_by_range(
            mock_client,
            start_date="2026-01-01",
            end_date="2026-12-31",
            tenant_id=None,
        )


@pytest.mark.asyncio
async def test_query_events_by_range_empty_tenant_raises():
    """#2540: empty-string tenant_id is treated as absent — same failure."""
    mock_client, _ = _make_mock_client([])
    with pytest.raises(ValueError, match="tenant_id"):
        await query_events_by_range(
            mock_client,
            start_date="2026-01-01",
            end_date="2026-12-31",
            tenant_id="",
        )


@pytest.mark.asyncio
async def test_no_query_contains_is_null_or_shim():
    """#2540: the `$tenant_id IS NULL OR` fail-open idiom must be gone from
    both helpers' Cypher."""
    mock_client, mock_session = _make_mock_client([])
    await get_lot_timeline(mock_client, tlc="LOT-A", tenant_id=TENANT_A)
    timeline_cypher = mock_session.run.call_args[0][0]
    assert "$tenant_id IS NULL OR" not in timeline_cypher

    mock_client, mock_session = _make_mock_client([])
    await query_events_by_range(
        mock_client,
        start_date="2026-01-01",
        end_date="2026-12-31",
        tenant_id=TENANT_A,
    )
    range_cypher = mock_session.run.call_args[0][0]
    assert "$tenant_id IS NULL OR" not in range_cypher


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
