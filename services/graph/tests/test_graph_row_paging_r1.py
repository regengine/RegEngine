"""R1: chain_integrity / data_quality must not silently cap results at 2000 rows.

Rows are fully synthetic: every id is a fresh ``uuid4`` and business fields
are empty or ``None``. Where a sortable field needs a value, the row index is
used. The fake Neo4j session honours ``$page_skip`` / ``$page_size`` so the
tests exercise real paging.
"""

from __future__ import annotations

import sys
import uuid
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma import chain_integrity
from services.graph.app.fsma.chain_integrity import find_broken_chains, find_gaps
from services.graph.app.fsma.data_quality import find_orphaned_lots

TENANT = str(uuid.uuid4())
TOTAL_ROWS = 4501  # > 2 full pages of 2000, plus a partial page


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


def _assert_each_once(input_ids: list[str], output_ids: list[str]) -> None:
    counts = Counter(output_ids)
    assert set(counts) == set(input_ids)
    assert all(n == 1 for n in counts.values())


def _shipping_rows(n: int) -> list[dict]:
    return [
        {
            "event_id": str(uuid.uuid4()),
            "type": "SHIPPING",
            "event_date": i,  # sortable: row index
            "document_id": None,
            "lot_tlc": str(uuid.uuid4()),
            "product_description": "",
            "merkle_hash": None,
            "merkle_prev_hash": None,
            "expected_predecessors": [],
            "gaps": "",
        }
        for i in range(n)
    ]


def test_page_size_is_positive():
    assert chain_integrity._PAGE_SIZE > 0


@pytest.mark.asyncio
async def test_find_gaps_returns_more_than_2000_rows():
    rows = _shipping_rows(TOTAL_ROWS)
    session = _PagingSession(lambda q: rows)
    gaps = await find_gaps(_client(session), tenant_id=TENANT)
    assert len(gaps) == TOTAL_ROWS
    _assert_each_once([r["event_id"] for r in rows], [g["event_id"] for g in gaps])
    assert [c[1]["page_skip"] for c in session.calls] == [0, 2000, 4000]
    assert all(c[1]["page_size"] == 2000 for c in session.calls)
    assert all(c[1]["tenant_id"] == TENANT for c in session.calls)
    assert all("ORDER BY event_id" in c[0] for c in session.calls)


@pytest.mark.asyncio
async def test_find_gaps_drops_rows_repeated_across_pages():
    rows = _shipping_rows(TOTAL_ROWS)
    # Simulate a row shifting forward between pages: page 2 repeats the
    # last row of page 1.
    shifted = rows[:2000] + [rows[1999]] + rows[2000:]
    session = _PagingSession(lambda q: shifted)
    gaps = await find_gaps(_client(session), tenant_id=TENANT)
    _assert_each_once([r["event_id"] for r in rows], [g["event_id"] for g in gaps])


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
    _assert_each_once([r["lot_tlc"] for r in rows], [v["lot_tlc"] for v in violations])
    for q, _ in session.calls:
        assert "ORDER BY shipping.event_date, shipping.event_id, l.tlc" in q


def _orphan_rows(n: int) -> list[dict]:
    return [
        {
            "tlc": str(uuid.uuid4()),
            "product_description": "",
            "quantity": None,
            "unit_of_measure": "",
            "created_at": None,
            "last_event_type": "",
            "last_event_date": None,
        }
        for _ in range(n)
    ]


@pytest.mark.asyncio
async def test_find_orphaned_lots_returns_more_than_2000_rows():
    rows = _orphan_rows(TOTAL_ROWS)
    session = _PagingSession(lambda q: rows)
    orphans = await find_orphaned_lots(_client(session), tenant_id=TENANT)
    assert len(orphans) == TOTAL_ROWS
    _assert_each_once([r["tlc"] for r in rows], [o.tlc for o in orphans])
    assert len(session.calls) == 3
    assert "ORDER BY most_recent_event.event_date ASC, l.tlc ASC" in session.calls[0][0]


@pytest.mark.asyncio
async def test_find_orphaned_lots_drops_rows_repeated_across_pages():
    rows = _orphan_rows(TOTAL_ROWS)
    shifted = rows[:2000] + [rows[1999]] + rows[2000:]
    session = _PagingSession(lambda q: shifted)
    orphans = await find_orphaned_lots(_client(session), tenant_id=TENANT)
    _assert_each_once([r["tlc"] for r in rows], [o.tlc for o in orphans])


@pytest.mark.asyncio
async def test_exact_page_boundary_issues_one_empty_followup():
    rows = _shipping_rows(2000)
    session = _PagingSession(lambda q: rows)
    gaps = await find_gaps(_client(session), tenant_id=TENANT)
    assert len(gaps) == 2000
    _assert_each_once([r["event_id"] for r in rows], [g["event_id"] for g in gaps])
    assert [c[1]["page_skip"] for c in session.calls] == [0, 2000]
