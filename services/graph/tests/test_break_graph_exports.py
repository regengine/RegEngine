"""Adversarial checks for graph export paths, empty traces, and hierarchies.

These tests target three failures:

* A download name that still walks out of a directory after percent-decoding.
* A trace that counts the same lot once per path, and a non-numeric quantity
  that aborts the FDA export.
* A leaf jurisdiction code whose country is never linked, and a parent chain
  that points back at itself.
"""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from _fsma_graph_double import FakeGraph, FakeNeo4jClient  # noqa: E402

import services.graph.app.hierarchy_builder as hierarchy_builder  # noqa: E402
from services.graph.app.exporters.recall_contacts_csv import (  # noqa: E402
    build_recall_contacts_rows,
)
from services.graph.app.exporters.safe_text import (  # noqa: E402
    header_filename,
    rfc5987_filename,
)
from services.graph.app.exporters.trace_csv import (  # noqa: E402
    TRACE_CSV_HEADER,
    build_trace_csv_rows,
)
from services.graph.app.fsma.tracer import trace_forward  # noqa: E402
from services.graph.app.fsma.types import TraceResult  # noqa: E402
from services.graph.app.hierarchy_builder import (  # noqa: E402
    InvalidJurisdictionCodeError,
    build_jurisdiction_hierarchy,
)
from services.graph.app.models.fsma_nodes import FSMARelationships  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"
_COL = {name: idx for idx, name in enumerate(TRACE_CSV_HEADER)}

LOT_A = {"tlc": "LOT-A", "product_description": "Romaine", "quantity": 40, "unit_of_measure": "CASE"}
LOT_B = {"tlc": "LOT-B", "product_description": "Spinach", "quantity": 18, "unit_of_measure": "CASE"}
EVT_1 = {"event_id": "evt-1", "type": "SHIPPING", "event_date": "2026-03-01", "confidence": 0.9}
FAC_DC = {"gln": "0614141000029", "name": "Regional DC", "address": "9 Dock St", "facility_type": "DISTRIBUTOR"}


def _cell(row, column):
    return row[_COL[column]]


def _resolved_download(root: Path, encoded_name: str) -> Path:
    """Where a single percent-decode of the download name would land."""
    return (root / urllib.parse.unquote(encoded_name)).resolve()


def _assert_stays_in_directory(encoded_name: str) -> None:
    # macOS resolves /tmp to /private/tmp. Compare resolved paths so a
    # name that stayed inside the folder is not reported as an escape.
    root = Path("/tmp/regengine-export-root").resolve()
    landing = _resolved_download(root, encoded_name)
    landing.relative_to(root)
    assert "/" not in encoded_name
    assert "\\" not in encoded_name
    assert ".." not in Path(urllib.parse.unquote(encoded_name)).parts


# ---------------------------------------------------------------------------
# Export filename: path traversal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "attack",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "foo/../../etc/passwd",
        "reports/../../../tmp/secret.csv",
        "..%2F..%2Fetc%2Fpasswd",
        "%2e%2e/%2e%2e/etc/passwd",
        "%252e%252e%252fetc%252fpasswd",
    ],
)
def test_header_filename_cannot_escape_after_decode(attack):
    _assert_stays_in_directory(header_filename(attack))


@pytest.mark.parametrize(
    "attack",
    [
        "../../etc/passwd",
        "foo/../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "%252e%252e%252fetc%252fpasswd",
    ],
)
def test_rfc5987_filename_cannot_escape_after_decode(attack):
    _assert_stays_in_directory(rfc5987_filename(attack))


def test_header_filename_keeps_a_plain_name():
    assert header_filename("fsma_trace_forward_LOT-1.csv") == "fsma_trace_forward_LOT-1.csv"


# ---------------------------------------------------------------------------
# Exporters: malformed rows must not abort the file
# ---------------------------------------------------------------------------


def _trace_result(**overrides) -> TraceResult:
    base = dict(
        lot_id="LOT-A",
        direction="forward",
        facilities=[FAC_DC],
        events=[EVT_1],
        lots=[LOT_A, LOT_B],
        total_quantity=58.0,
        query_time_ms=1.0,
        hop_count=2,
        trace_rows=None,
    )
    base.update(overrides)
    return TraceResult(**base)


def test_malformed_lot_does_not_abort_trace_csv():
    result = _trace_result(lots=["not-a-lot", LOT_A])
    rows = build_trace_csv_rows(result, "LOT-A")
    assert rows
    assert any(_cell(row, "Traceability Lot Code (TLC)") == "LOT-A" for row in rows)


def test_malformed_association_does_not_abort_trace_csv():
    rows = build_trace_csv_rows(_trace_result(trace_rows=["not-a-row"]), "LOT-A")
    assert len(rows) == 1


def test_malformed_association_does_not_abort_recall_contacts():
    result = _trace_result(
        trace_rows=[
            "not-a-row",
            {"lot": LOT_A, "event": {"type": "RECEIVING", "event_date": "2026-03-06"}, "facility": FAC_DC},
        ]
    )
    rows = build_recall_contacts_rows(result)
    assert rows
    assert any("2026-03-06" in row for row in rows)


def test_empty_trace_csv_returns_no_rows():
    """An empty graph produces a header-only file and does not raise."""
    rows = build_trace_csv_rows(
        _trace_result(facilities=[], events=[], lots=[], total_quantity=None, hop_count=0),
        "LOT-A",
    )
    assert rows == []


def test_empty_recall_list_returns_no_rows():
    rows = build_recall_contacts_rows(
        _trace_result(facilities=[], events=[], lots=[], trace_rows=[], total_quantity=None, hop_count=0)
    )
    assert rows == []


# ---------------------------------------------------------------------------
# Trace quantity: multi-path inflation and malformed quantities
# ---------------------------------------------------------------------------


def _linear_chain() -> FakeGraph:
    g = FakeGraph()
    g.add_node("LOT-A", ["Lot"], tlc="LOT-A", tenant_id=TENANT, product_description="Romaine", quantity=40)
    g.add_node("LOT-B", ["Lot"], tlc="LOT-B", tenant_id=TENANT, product_description="Case", quantity=40)
    g.add_node("evt-1", ["TraceEvent"], event_id="evt-1", tenant_id=TENANT, type="HARVESTING", event_date="2026-03-01")
    g.add_node("evt-2", ["TraceEvent"], event_id="evt-2", tenant_id=TENANT, type="SHIPPING", event_date="2026-03-04")
    g.apply_writer(FSMARelationships.LOT_UNDERWENT_EVENT, tlc="LOT-A", event_id="evt-1", tenant_id=TENANT)
    g.apply_writer(FSMARelationships.EVENT_PRODUCED_LOT, event_id="evt-1", tlc="LOT-B", tenant_id=TENANT)
    g.apply_writer(FSMARelationships.LOT_UNDERWENT_EVENT, tlc="LOT-B", event_id="evt-2", tenant_id=TENANT)
    return g


def _one_hop(quantity) -> FakeGraph:
    g = FakeGraph()
    g.add_node("LOT-A", ["Lot"], tlc="LOT-A", tenant_id=TENANT, quantity=quantity, product_description="Romaine")
    g.add_node("evt-1", ["TraceEvent"], event_id="evt-1", tenant_id=TENANT, type="SHIPPING", event_date="2026-03-01")
    g.apply_writer(FSMARelationships.LOT_UNDERWENT_EVENT, tlc="LOT-A", event_id="evt-1", tenant_id=TENANT)
    return g


@pytest.mark.asyncio
async def test_multi_path_trace_counts_each_lot_once():
    """The same lot sits on every prefix of a chain. Quantity must not multiply."""
    result = await trace_forward(FakeNeo4jClient(_linear_chain()), "LOT-A", max_depth=10, tenant_id=TENANT)

    assert len(result.lots) == 2
    assert len(result.events) == 2
    assert result.total_quantity == 80


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", ["=1+1", "40", "not-a-number"])
async def test_non_numeric_quantity_does_not_abort_the_trace(quantity):
    result = await trace_forward(FakeNeo4jClient(_one_hop(quantity)), "LOT-A", max_depth=4, tenant_id=TENANT)
    assert result.lots
    if quantity == "40":
        assert result.total_quantity == 40
    elif quantity == "=1+1":
        assert result.total_quantity is None
        assert result.lots[0]["quantity"] == "=1+1"
    else:
        assert result.total_quantity is None


def _result_of(records_for_query):
    mock_client = MagicMock()
    mock_session = AsyncMock()

    async def _run(query, **_params):
        records = records_for_query(query)
        result = MagicMock()

        async def _aiter(_self):
            for record in records:
                yield record

        result.__aiter__ = _aiter
        return result

    mock_session.run = AsyncMock(side_effect=_run)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_client.session = MagicMock(return_value=mock_session)
    return mock_client


@pytest.mark.asyncio
async def test_same_facility_is_not_listed_twice_when_the_follow_up_query_repeats_it():
    facility = {
        "gln": "0614141000005",
        "name": "Packhouse",
        "address": "1 Way",
        "facility_type": "PACKER",
        "tenant_id": TENANT,
    }

    def records_for_query(query):
        if "MATCH path" in query:
            return [{"labels": ["Facility"], "props": dict(facility), "hop_count": 1}]
        if "properties(f)" in query or "facility" in query:
            # Full property bag, same GLN. The old membership test compared
            # this dict to the slim dict already stored and always missed.
            return [{"facility": dict(facility, extra="full-bag")}]
        return []

    result = await trace_forward(_result_of(records_for_query), "LOT-A", max_depth=4, tenant_id=TENANT)
    assert len(result.facilities) == 1
    assert result.facilities[0]["gln"] == facility["gln"]


@pytest.mark.asyncio
async def test_null_node_properties_do_not_abort_an_empty_trace():
    def records_for_query(query):
        if "MATCH path" in query:
            return [
                "not-a-record",
                {"labels": ["Lot"], "props": None, "hop_count": 1},
            ]
        return []

    result = await trace_forward(_result_of(records_for_query), "LOT-MISSING", max_depth=2, tenant_id=TENANT)
    assert result.total_quantity is None


# ---------------------------------------------------------------------------
# Jurisdiction hierarchy: missing ancestors and a cyclic parent chain
# ---------------------------------------------------------------------------


def _session_driver():
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = None
    return driver, session


def _contains_edges(session):
    edges = []
    for call in session.run.call_args_list:
        cypher = call.args[0] if call.args else ""
        if "CONTAINS" not in cypher:
            continue
        edges.append((call.kwargs.get("parent"), call.kwargs.get("child")))
    return edges


def test_leaf_jurisdiction_is_linked_up_to_its_country():
    driver, session = _session_driver()
    build_jurisdiction_hierarchy(driver, ["US-CA-SF"])
    edges = _contains_edges(session)
    assert ("US-CA", "US-CA-SF") in edges
    assert ("US", "US-CA") in edges

    # The edges that were written must not loop.
    children = {}
    for parent, child in edges:
        children.setdefault(parent, set()).add(child)
    for start in list(children):
        stack = [start]
        seen = set()
        while stack:
            node = stack.pop()
            assert node not in seen, edges
            seen.add(node)
            stack.extend(children.get(node, ()))


def test_cyclic_parent_chain_is_rejected_before_any_write(monkeypatch):
    def cyclic(code):
        if code == "AAAA":
            return "BBBB"
        if code == "BBBB":
            return "AAAA"
        return None

    monkeypatch.setattr(hierarchy_builder, "parent_code_for", cyclic)
    driver, session = _session_driver()
    with pytest.raises(InvalidJurisdictionCodeError):
        build_jurisdiction_hierarchy(driver, ["AAAA"])
    assert session.run.call_count == 0
