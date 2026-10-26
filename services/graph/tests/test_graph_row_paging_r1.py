"""R1: chain_integrity / data_quality must not silently cap results at 2000 rows.

Business field values (TLC, product description, quantity, unit, harvest date,
reference document) are taken verbatim from the checked-in ingestion fixture
``services/ingestion/tests/fixtures/01_harvesting.csv``. The only generated
value per row is an opaque synthetic test identifier (``r1-synthetic-NNNNN``)
used to make rows distinct; it is not business data. The fake Neo4j session
honours ``$page_skip`` / ``$page_size`` so the tests exercise real paging.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma import chain_integrity
from services.graph.app.fsma.chain_integrity import find_broken_chains, find_gaps
from services.graph.app.fsma.data_quality import find_orphaned_lots

TENANT = "11111111-1111-1111-1111-111111111111"
TOTAL_ROWS = 4501  # > 2 full pages of 2000, plus a partial page
FIXTURE = Path(__file__).resolve().parents[2] / "ingestion" / "tests" / "fixtures" / "01_harvesting.csv"


def _fixture_rows() -> list[dict]:
    with FIXTURE.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "fixture must not be empty"
    return rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for r in self._rows:
            yield r


class _PagingSession:
    """Fake session: routes by query text, slices rows by SKIP/LIMIT params."""

    def __init__(self, rows_for):
        self._rows_for = rows_for
        self.calls: list[tuple[str, dict]] = []

    async def run(self, query, **params):
        self.calls.append((query, params))
        assert "LIMIT 2000" not in query
        assert "SKIP $page_skip LIMIT $page_size" in query
        rows = self._rows_for(query)
        skip, size = params["page_skip"], params["page_size"]
        return _Result(rows[skip : skip + size])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _client(session):
    client = MagicMock()
    client.session = MagicMock(return_value=session)
    return client


def _shipping_rows(n: int) -> list[dict]:
    fx = _fixture_rows()
    out = []
    for i in range(n):
        src = fx[i % len(fx)]
        out.append(
            {
                "event_id": f"r1-synthetic-{i:05d}",
                "type": "SHIPPING",
                "event_date": src["harvest_date"],
                "document_id": src["reference_document"],
                "lot_tlc": src["traceability_lot_code"],
                "product_description": src["product_description"],
                "merkle_hash": None,
                "merkle_prev_hash": None,
                "expected_predecessors": [],
                "gaps": "missing_lot",
            }
        )
    return out


def test_page_size_is_positive():
    assert chain_integrity._PAGE_SIZE > 0


@pytest.mark.asyncio
async def test_find_gaps_returns_more_than_2000_rows():
    rows = _shipping_rows(TOTAL_ROWS)
    session = _PagingSession(lambda q: rows)
    gaps = await find_gaps(_client(session), tenant_id=TENANT)
    assert len(gaps) == TOTAL_ROWS
    assert len({g["event_id"] for g in gaps}) == TOTAL_ROWS
    assert [c[1]["page_skip"] for c in session.calls] == [0, 2000, 4000]
    assert all(c[1]["page_size"] == 2000 for c in session.calls)
    assert all("ORDER BY event_id" in c[0] for c in session.calls)


@pytest.mark.asyncio
async def test_find_broken_chains_returns_more_than_2000_rows():
    rows = _shipping_rows(TOTAL_ROWS)

    def rows_for(q):
        # missing_origin query only; temporal_paradox and crypto_gap empty.
        if "NOT EXISTS" in q and "merkle_prev_hash" not in q and "origin_date" not in q:
            return rows
        return []

    session = _PagingSession(rows_for)
    violations = await find_broken_chains(_client(session), tenant_id=TENANT)
    assert len(violations) == TOTAL_ROWS
    assert {v["lot_tlc"] for v in violations} == {r["traceability_lot_code"] for r in _fixture_rows()}
    for q, _ in session.calls:
        assert "ORDER BY shipping.event_date, shipping.event_id, l.tlc" in q


@pytest.mark.asyncio
async def test_find_orphaned_lots_returns_more_than_2000_rows():
    fx = _fixture_rows()
    rows = []
    for i in range(TOTAL_ROWS):
        src = fx[i % len(fx)]
        rows.append(
            {
                "tlc": src["traceability_lot_code"],
                "product_description": src["product_description"],
                "quantity": float(src["quantity"]),
                "unit_of_measure": src["unit_of_measure"],
                "created_at": src["harvest_date"],
                "last_event_type": "RECEIVING",
                "last_event_date": src["harvest_date"],
            }
        )
    session = _PagingSession(lambda q: rows)
    orphans = await find_orphaned_lots(_client(session), tenant_id=TENANT)
    assert len(orphans) == TOTAL_ROWS
    assert len(session.calls) == 3
    assert "ORDER BY most_recent_event.event_date ASC, l.tlc ASC" in session.calls[0][0]


@pytest.mark.asyncio
async def test_exact_page_boundary_issues_one_empty_followup():
    rows = _shipping_rows(2000)
    session = _PagingSession(lambda q: rows)
    gaps = await find_gaps(_client(session), tenant_id=TENANT)
    assert len(gaps) == 2000
    assert [c[1]["page_skip"] for c in session.calls] == [0, 2000]
