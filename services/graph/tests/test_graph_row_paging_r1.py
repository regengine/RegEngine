"""R1: chain_integrity / data_quality must not silently cap results at 2000 rows.

Rows are fully synthetic: every id is a fresh ``uuid4`` and business fields
are empty or ``None``. Where a sortable field needs a value, the row index is
used. The fake Neo4j session honours ``$after_key`` / ``$page_size`` so the
tests exercise real keyset paging.
"""

from __future__ import annotations

import re
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
    """Fake session: routes by query text and serves keyset pages.

    The page key columns are read from the generated Cypher; each page holds
    the rows whose key is strictly after ``$after_key``, sorted by key.
    ``on_page(n, rows)`` runs after page ``n`` is served, so a test can
    delete rows between pages. ``dup_in_page(n, page)`` may return a changed
    page ``n`` (for example one row served twice) before it is sent.
    """

    def __init__(self, rows_for, on_page=None, dup_in_page=None):
        self._rows_for = rows_for
        self._on_page = on_page
        self._dup_in_page = dup_in_page
        self.calls: list[tuple[str, dict]] = []

    async def run(self, query, **params):
        self.calls.append((query, params))
        assert "LIMIT 2000" not in query
        assert "SKIP" not in query
        assert "LIMIT $page_size" in query
        assert "CALL {" not in query
        assert "// @page" not in query
        exprs = re.findall(r"coalesce\(toString\((\w+\.\w+)\), ''\)", query)
        assert exprs, query
        rows = self._rows_for(query)
        # The cursor filter runs on anchor properties (``l.tlc``); map each to
        # the returned column (``tlc``, or ``lot_tlc`` for chain rows).
        cols = []
        for expr in exprs:
            col = expr.split(".")[1]
            if rows and col not in rows[0]:
                col = f"lot_{col}"
            cols.append(col)

        def key(r):
            return ["" if r[c] is None else str(r[c]) for c in cols]

        after = params["after_key"]
        page = sorted((r for r in rows if after is None or key(r) > after), key=key)
        page = [{**r, "_page_key": key(r)} for r in page[: params["page_size"]]]
        if self._dup_in_page:
            page = self._dup_in_page(len(self.calls), page)
        if self._on_page:
            self._on_page(len(self.calls), rows)
        return _Result(page)

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
            "event_date": f"{i:05d}",  # sortable: row index
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
    assert len(session.calls) == 3
    assert session.calls[0][1]["after_key"] is None
    assert all(c[1]["page_size"] == 2000 for c in session.calls)
    assert all(c[1]["tenant_id"] == TENANT for c in session.calls)


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
    # Reported in event-date order (the row index here).
    assert [v["event_date"] for v in violations] == [f"{i:05d}" for i in range(TOTAL_ROWS)]


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
    assert [o.tlc for o in orphans] == sorted(r["tlc"] for r in rows)


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
    assert len(session.calls) == 2


def _delete_after_first_page(victims):
    def on_page(n, rows):
        if n == 1:
            for v in victims:
                rows.remove(v)

    return on_page


@pytest.mark.asyncio
async def test_find_gaps_deletion_between_pages_skips_nothing():
    rows = _shipping_rows(TOTAL_ROWS)
    ordered = sorted(rows, key=lambda r: r["event_id"])
    # One already-read row and one unread row vanish after page 1. With
    # offset paging the next page would start one row late and skip a row.
    read, unread = ordered[10], ordered[3000]
    session = _PagingSession(lambda q: rows, on_page=_delete_after_first_page([read, unread]))
    expected = [r["event_id"] for r in rows if r is not unread]
    gaps = await find_gaps(_client(session), tenant_id=TENANT)
    _assert_each_once(expected, [g["event_id"] for g in gaps])


@pytest.mark.asyncio
async def test_find_broken_chains_deletion_between_pages_skips_nothing():
    rows = _shipping_rows(TOTAL_ROWS)
    ordered = sorted(rows, key=lambda r: (r["event_id"], r["lot_tlc"]))
    read = ordered[0]

    def rows_for(q):
        if "NOT EXISTS" in q and "merkle_prev_hash" not in q and "origin_date" not in q:
            return rows
        return []

    unread = ordered[2500]
    session = _PagingSession(rows_for, on_page=_delete_after_first_page([read, unread]))
    expected = [r["event_id"] for r in rows if r is not unread]
    violations = await find_broken_chains(_client(session), tenant_id=TENANT)
    _assert_each_once(expected, [v["event_id"] for v in violations])


@pytest.mark.asyncio
async def test_find_orphaned_lots_deletion_between_pages_skips_nothing():
    rows = _orphan_rows(TOTAL_ROWS)
    ordered = sorted(rows, key=lambda r: r["tlc"])
    read, unread = ordered[5], ordered[4400]
    session = _PagingSession(lambda q: rows, on_page=_delete_after_first_page([read, unread]))
    expected = [r["tlc"] for r in rows if r is not unread]
    orphans = await find_orphaned_lots(_client(session), tenant_id=TENANT)
    _assert_each_once(expected, [o.tlc for o in orphans])


def _repeat_row_in_first_page(n, page):
    # Serve row 4 a second time, inside page 1, before the cursor moves on.
    if n == 1:
        return page[:5] + [dict(page[4])] + page[5:]
    return page


@pytest.mark.asyncio
async def test_find_gaps_drops_row_repeated_within_one_page():
    rows = _shipping_rows(TOTAL_ROWS)
    session = _PagingSession(lambda q: rows, dup_in_page=_repeat_row_in_first_page)
    gaps = await find_gaps(_client(session), tenant_id=TENANT)
    _assert_each_once([r["event_id"] for r in rows], [g["event_id"] for g in gaps])


@pytest.mark.asyncio
async def test_find_broken_chains_drops_row_repeated_within_one_page():
    rows = _shipping_rows(TOTAL_ROWS)

    def rows_for(q):
        if "NOT EXISTS" in q and "merkle_prev_hash" not in q and "origin_date" not in q:
            return rows
        return []

    session = _PagingSession(rows_for, dup_in_page=_repeat_row_in_first_page)
    violations = await find_broken_chains(_client(session), tenant_id=TENANT)
    _assert_each_once([r["event_id"] for r in rows], [v["event_id"] for v in violations])


@pytest.mark.asyncio
async def test_find_orphaned_lots_drops_row_repeated_within_one_page():
    rows = _orphan_rows(TOTAL_ROWS)
    session = _PagingSession(lambda q: rows, dup_in_page=_repeat_row_in_first_page)
    orphans = await find_orphaned_lots(_client(session), tenant_id=TENANT)
    _assert_each_once([r["tlc"] for r in rows], [o.tlc for o in orphans])


@pytest.mark.asyncio
async def test_non_hit_anchor_rows_advance_cursor_but_are_not_reported():
    rows = _orphan_rows(TOTAL_ROWS)
    for i, r in enumerate(rows):
        r["_hit"] = i % 2 == 0
    session = _PagingSession(lambda q: rows)
    orphans = await find_orphaned_lots(_client(session), tenant_id=TENANT)
    _assert_each_once([r["tlc"] for r in rows if r["_hit"]], [o.tlc for o in orphans])
    assert len(session.calls) == 3


@pytest.mark.asyncio
async def test_page_filter_and_limit_sit_inside_the_match():
    session = _PagingSession(lambda q: [])
    await find_broken_chains(_client(session), tenant_id=TENANT)
    await find_gaps(_client(session), tenant_id=TENANT)
    for query, _ in session.calls:
        assert "CALL {" not in query
        # The cursor filter and LIMIT come before the final RETURN.
        assert query.index("LIMIT $page_size") < query.rindex("RETURN")
        assert query.index("$after_key") < query.rindex("RETURN")


def _hit_expr(query: str) -> str:
    """The RETURN expression aliased ``_hit``, whitespace collapsed."""
    ret = query[query.rindex("RETURN") :]
    return " ".join(ret[: ret.index("AS _hit")].split())


@pytest.mark.asyncio
async def test_hit_flags_coalesce_cypher_null_to_false():
    session = _PagingSession(lambda q: [])
    await find_broken_chains(_client(session), tenant_id=TENANT)
    await find_orphaned_lots(_client(session), tenant_id=TENANT)
    hits = [_hit_expr(q) for q, _ in session.calls if "AS _hit" in q]
    assert len(hits) == 3  # temporal paradox, crypto gap, orphan
    assert all(h.split("_page_key,", 1)[1].strip().startswith("coalesce(") for h in hits)
    assert all(h.endswith(", false)") for h in hits)


@pytest.mark.asyncio
async def test_null_merkle_hash_hit_is_not_a_crypto_gap():
    # Null merkle_hash on shipping and origin: the comparison is null in
    # Cypher, so the row must not be reported.
    rows = _shipping_rows(5)
    for r in rows:
        r["_hit"] = None

    def rows_for(q):
        return rows if "merkle_prev_hash" in q else []

    session = _PagingSession(rows_for)
    violations = await find_broken_chains(_client(session), tenant_id=TENANT)
    assert violations == []


@pytest.mark.asyncio
async def test_uncomparable_dates_hit_is_not_an_orphan():
    # last_event_date empty vs a cutoff date: the comparison is null.
    rows = _orphan_rows(5)
    for r in rows:
        r["last_event_date"] = ""
        r["_hit"] = None
    session = _PagingSession(lambda q: rows)
    orphans = await find_orphaned_lots(_client(session), tenant_id=TENANT)
    assert orphans == []


@pytest.mark.asyncio
async def test_page_clause_orders_and_limits_in_its_own_with():
    # openCypher: WITH <items> [ORDER BY] [SKIP] [LIMIT] [WHERE]. A WHERE
    # before ORDER BY is not valid, so filter and order use separate WITHs.
    session = _PagingSession(lambda q: [])
    await find_gaps(_client(session), tenant_id=TENANT)
    for query, _ in session.calls:
        lines = [ln.strip() for ln in query.splitlines()]
        w = next(i for i, ln in enumerate(lines) if ln.startswith("WHERE $after_key IS NULL"))
        assert lines[w + 1].startswith("WITH ")
        assert lines[w + 2].startswith("ORDER BY _page_key[0]")
        assert lines[w + 3] == "LIMIT $page_size"
