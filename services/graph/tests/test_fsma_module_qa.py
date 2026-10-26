"""Deep QA tests for ``services/graph/app/fsma/``.

Each test below pins a real bug found during the QA pass: it fails on the
old code and passes on the fixed code. Bug classes:

* Tenant boundary: ``find_gaps`` kept the ``$tenant_id IS NULL OR ...``
  fail-open shim long after every sibling helper was hardened, and its
  missing-lot ``EXISTS`` check (like the KDE one) let a cross-tenant Lot
  satisfy linkage. ``find_all_gaps`` ran the gaps query before the
  broken-chains tenant check could raise.
* Wrong data: ``find_orphaned_lots`` reported every lot as exactly
  ``days_stagnant`` days old (naive minus aware datetime raises TypeError,
  swallowed by the parse fallback); the trace facility merge compared raw
  node props against projected dicts so it could never match and appended
  duplicates; the paradox query paired ``min(date)`` with an unordered
  ``head(collect(id))``; the crypto-gap query had no row cap.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.chain_integrity import (  # noqa: E402
    find_all_gaps,
    find_broken_chains,
    find_gaps,
)
from services.graph.app.fsma.data_quality import (  # noqa: E402
    analyze_kde_completeness,
    find_orphaned_lots,
)
from services.graph.app.fsma.tracer import (  # noqa: E402
    trace_backward,
    trace_forward,
)

TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _flatten(query: str) -> str:
    """Strip Cypher ``//`` comments and collapse whitespace."""
    return " ".join(re.sub(r"//[^\n]*", "", query).split())


class _Aiter:
    """Minimal async-iterable result yielding the given records."""

    def __init__(self, records):
        self._records = list(records)

    def __aiter__(self):
        async def _gen():
            for record in self._records:
                yield record

        return _gen()


def _make_client(*results):
    """Client mock whose ``session.run`` returns ``results`` in call order."""
    client = MagicMock()
    session = AsyncMock()
    session.run = AsyncMock(side_effect=list(results))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    client.session = MagicMock(return_value=session)
    return client, session


def _empty_client():
    """Client mock returning empty results for every query."""
    client = MagicMock()
    session = AsyncMock()

    async def _run(*args, **kwargs):
        session._last_call = (args, kwargs)
        return _Aiter([])

    session.run = AsyncMock(side_effect=_run)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    client.session = MagicMock(return_value=session)
    return client, session


# ============================================================================
# find_gaps: fail closed on null/empty tenant
# ============================================================================


class TestFindGapsTenantBoundary:
    @pytest.mark.asyncio
    async def test_none_tenant_raises(self):
        client, session = _empty_client()
        with pytest.raises(ValueError, match="tenant_id"):
            await find_gaps(client, tenant_id=None)

    @pytest.mark.asyncio
    async def test_empty_tenant_raises(self):
        client, session = _empty_client()
        with pytest.raises(ValueError, match="tenant_id"):
            await find_gaps(client, tenant_id="")

    @pytest.mark.asyncio
    async def test_none_tenant_runs_no_query(self):
        """Fail fast: a null tenant must never reach Neo4j."""
        client, session = _empty_client()
        with pytest.raises(ValueError):
            await find_gaps(client, tenant_id=None)
        assert session.run.call_count == 0

    @pytest.mark.asyncio
    async def test_no_fail_open_shim_in_cypher(self):
        client, session = _empty_client()
        await find_gaps(client, tenant_id=TENANT)
        cypher = _flatten(session.run.call_args[0][0])
        assert "$tenant_id IS NULL" not in cypher
        assert "e.tenant_id = $tenant_id" in cypher

    @pytest.mark.asyncio
    async def test_missing_lot_check_scopes_lot_to_tenant(self):
        """A cross-tenant UNDERWENT edge must not satisfy the linkage check."""
        client, session = _empty_client()
        await find_gaps(client, tenant_id=TENANT)
        cypher = _flatten(session.run.call_args[0][0])
        assert "NOT EXISTS" in cypher
        assert cypher.count("tenant_id = $tenant_id") >= 2, (
            f"both the event and the Lot inside NOT EXISTS must be tenant-scoped. Cypher:\n{cypher}"
        )


# ============================================================================
# find_all_gaps: fail fast before any query
# ============================================================================


class TestFindAllGapsFailFast:
    @pytest.mark.asyncio
    async def test_none_tenant_raises_without_querying(self):
        client, session = _empty_client()
        with pytest.raises(ValueError, match="tenant_id"):
            await find_all_gaps(client, tenant_id=None)
        assert session.run.call_count == 0, (
            "old code ran the gaps query cross-tenant before the broken-chains tenant check raised"
        )

    @pytest.mark.asyncio
    async def test_empty_tenant_raises_without_querying(self):
        client, session = _empty_client()
        with pytest.raises(ValueError, match="tenant_id"):
            await find_all_gaps(client, tenant_id="")
        assert session.run.call_count == 0


# ============================================================================
# find_orphaned_lots: stagnant_days reflects the real elapsed time
# ============================================================================


def _orphan_client(last_event_date):
    record = {
        "tlc": "ORPHAN-001",
        "product_description": "Test Product",
        "quantity": 100.0,
        "unit_of_measure": "cases",
        "created_at": "2020-01-01",
        "last_event_type": "RECEIVING",
        "last_event_date": last_event_date,
    }
    return _make_client(_Aiter([record]))[0]


class TestOrphanStagnantDays:
    @pytest.mark.asyncio
    async def test_old_event_reports_real_age(self):
        """A lot idle since 2020-01-01 is far older than the 30-day default."""
        client = _orphan_client("2020-01-01")
        (orphan,) = await find_orphaned_lots(client, tenant_id=TENANT, days_stagnant=30)
        expected = (datetime.now(timezone.utc) - datetime(2020, 1, 1, tzinfo=timezone.utc)).days
        assert orphan.stagnant_days == expected
        assert orphan.stagnant_days > 30

    @pytest.mark.asyncio
    async def test_recent_event_reports_small_age(self):
        five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
        client = _orphan_client(five_days_ago)
        (orphan,) = await find_orphaned_lots(client, tenant_id=TENANT, days_stagnant=30)
        assert orphan.stagnant_days == 5

    @pytest.mark.asyncio
    async def test_unparseable_date_falls_back_to_threshold(self):
        client = _orphan_client("not-a-date")
        (orphan,) = await find_orphaned_lots(client, tenant_id=TENANT, days_stagnant=30)
        assert orphan.stagnant_days == 30

    @pytest.mark.asyncio
    async def test_missing_date_falls_back_to_threshold(self):
        client = _orphan_client(None)
        (orphan,) = await find_orphaned_lots(client, tenant_id=TENANT, days_stagnant=45)
        assert orphan.stagnant_days == 45


# ============================================================================
# analyze_kde_completeness: missing-lot check scopes the Lot to the tenant
# ============================================================================


class TestKdeMissingLotTenantScope:
    @pytest.mark.asyncio
    async def test_exists_check_scopes_lot(self):
        client, session = _empty_client()
        await analyze_kde_completeness(client, tenant_id=TENANT)
        cypher = _flatten(session.run.call_args[0][0])
        assert "NOT EXISTS" in cypher
        assert cypher.count("tenant_id = $tenant_id") >= 2, (
            f"both the event and the Lot inside NOT EXISTS must be tenant-scoped. Cypher:\n{cypher}"
        )


# ============================================================================
# find_broken_chains: crypto cap + paradox origin ordering
# ============================================================================


class TestBrokenChainsQueries:
    @pytest.mark.asyncio
    async def test_broken_chain_queries_are_paged_not_capped(self):
        """R1: each broken-chain query fetches bounded pages, never a silent 2000-row cap."""
        client, session = _empty_client()
        await find_broken_chains(client, tenant_id=TENANT)
        assert session.run.call_count == 3
        for i, call in enumerate(session.run.call_args_list):
            cypher = _flatten(call.args[0])
            assert "LIMIT 2000" not in cypher, f"query {i} still has a fixed row cap"
            assert "SKIP $page_skip LIMIT $page_size" in cypher, f"query {i} is not paged"
            assert call.kwargs["page_size"] > 0

    @pytest.mark.asyncio
    async def test_paradox_query_sorts_origins_before_collect(self):
        """head(collect(id)) must correspond to min(date), not an arbitrary row."""
        client, session = _empty_client()
        await find_broken_chains(client, tenant_id=TENANT)
        cypher = _flatten(session.run.call_args_list[1].args[0])
        order_pos = cypher.find("ORDER BY origin.event_date")
        collect_pos = cypher.find("collect(origin.event_id)")
        assert order_pos != -1, f"origins must be sorted before aggregating. Cypher:\n{cypher}"
        assert order_pos < collect_pos, "sort must precede the collect, not follow it"


# ============================================================================
# tracer: facility merge must not duplicate a GLN already present
# ============================================================================


def _trace_client(traversal_records, facility_props):
    facility_records = [{"facility": facility_props}] if facility_props else []
    return _make_client(
        _Aiter(traversal_records),
        _Aiter(facility_records),
        _Aiter([]),  # trace-rows enrichment
    )[0]


class TestTraceFacilityDedup:
    @pytest.mark.asyncio
    async def test_forward_no_duplicate_when_both_paths_return_same_gln(self):
        traversal = [
            {
                "labels": ["Facility"],
                "props": {
                    "gln": "GLN-1",
                    "name": "Plant",
                    "address": "1 Main St",
                    "facility_type": "MFG",
                    "tenant_id": TENANT,
                },
                "hop_count": 1,
            }
        ]
        # Raw node props carry extra keys (tenant_id, ...) the old
        # membership test compared against projected dicts and never matched.
        facility = {
            "gln": "GLN-1",
            "name": "Plant",
            "address": "1 Main St",
            "facility_type": "MFG",
            "tenant_id": TENANT,
            "created_at": "2024-01-01",
        }
        result = await trace_forward(_trace_client(traversal, facility), "LOT-1", tenant_id=TENANT)
        glns = [f["gln"] for f in result.facilities]
        assert glns == ["GLN-1"], f"expected one facility, got: {result.facilities!r}"

    @pytest.mark.asyncio
    async def test_backward_no_duplicate_when_both_paths_return_same_gln(self):
        traversal = [
            {
                "labels": ["Facility"],
                "props": {
                    "gln": "GLN-9",
                    "name": "Depot",
                    "address": "9 Dock Rd",
                    "facility_type": "DIST",
                    "tenant_id": TENANT,
                },
                "hop_count": 1,
            }
        ]
        facility = {
            "gln": "GLN-9",
            "name": "Depot",
            "address": "9 Dock Rd",
            "facility_type": "DIST",
            "tenant_id": TENANT,
            "created_at": "2024-01-01",
        }
        result = await trace_backward(_trace_client(traversal, facility), "LOT-9", tenant_id=TENANT)
        glns = [f["gln"] for f in result.facilities]
        assert glns == ["GLN-9"], f"expected one facility, got: {result.facilities!r}"

    @pytest.mark.asyncio
    async def test_forward_same_gln_less_facility_not_duplicated(self):
        """GLN-less facilities dedup on the projected shape, not by None GLN."""
        traversal = [
            {
                "labels": ["Facility"],
                "props": {
                    "gln": None,
                    "name": "No-GLN Plant",
                    "address": "2 Mill Ln",
                    "facility_type": "MFG",
                    "tenant_id": TENANT,
                },
                "hop_count": 1,
            }
        ]
        facility = {
            "gln": None,
            "name": "No-GLN Plant",
            "address": "2 Mill Ln",
            "facility_type": "MFG",
            "tenant_id": TENANT,
        }
        result = await trace_forward(_trace_client(traversal, facility), "LOT-2", tenant_id=TENANT)
        assert len(result.facilities) == 1, f"expected one facility, got: {result.facilities!r}"

    @pytest.mark.asyncio
    async def test_forward_distinct_gln_less_facilities_both_kept(self):
        """Two different facilities without GLNs must not collapse into one."""
        traversal = [
            {
                "labels": ["Facility"],
                "props": {
                    "gln": None,
                    "name": "Plant A",
                    "address": "1 Mill Ln",
                    "facility_type": "MFG",
                    "tenant_id": TENANT,
                },
                "hop_count": 1,
            }
        ]
        facility = {
            "gln": None,
            "name": "Plant B",
            "address": "2 Mill Ln",
            "facility_type": "MFG",
            "tenant_id": TENANT,
        }
        result = await trace_forward(_trace_client(traversal, facility), "LOT-3", tenant_id=TENANT)
        names = sorted(f["name"] for f in result.facilities)
        assert names == ["Plant A", "Plant B"], f"got: {result.facilities!r}"
