"""QA correctness pass for services/graph routers, fsma and models.

Covers error handling and data integrity gaps that the tenant-scope
suites do not exercise:

- trace endpoints map corruption/invariant ValueErrors to JSON 500s
  instead of leaking unhandled exceptions,
- compliance score reads the tenant database like every other endpoint,
- label batch init rejects non-GLN packer ids at the boundary,
- lineage fallback lookup scopes the SUPERSEDES hop to the tenant,
- harmonize always releases its mapping engine driver,
- KDE completeness counts complete rows instead of deriving them from
  per-category maxima, averages confidence over non-null values only,
  and scopes lot linkage to the tenant.

Unfixed findings live at the bottom as xfail(strict=True).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.data_quality import analyze_kde_completeness
from services.graph.app.routers import (
    labels as labels_router,
    lineage_traversal as lineage_module,
    regulations as regulations_module,
)
from services.graph.app.routers.fsma import compliance as compliance_router, traceability as trace_module
from services.graph.app.routers.labels import (
    LabelBatchInitRequest,
    ProductInfo,
    TraceabilityInfo,
)

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _make_request(path: str = "/"):
    """Bare Starlette request that satisfies slowapi's type check."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "path": path,
        "query_string": b"",
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "app": MagicMock(state=MagicMock()),
    }
    return Request(scope)


class _AsyncIterator:
    """Minimal async iterator over canned Neo4j records."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


def _client_ctx_with_session(mock_session):
    """Mock Neo4jClient class whose instance is an async context manager."""
    mock_client = MagicMock()
    mock_client.session = MagicMock(
        return_value=_ctx_manager_r(mock_session),
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_cls = MagicMock(return_value=mock_client)
    # Use the real naming function: it is pure string formatting, and the
    # tenant-database test asserts on its exact output.
    from services.graph.app.neo4j_utils import Neo4jClient

    mock_cls.get_tenant_database_name = Neo4jClient.get_tenant_database_name
    return mock_cls, mock_client


def _ctx_manager_r(value):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=value)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _record(mapping):
    rec = MagicMock()
    rec.__getitem__ = lambda self, key: mapping.get(key)
    return rec


# ============================================================================
# Trace endpoints: ValueError (tenant invariant) must become a JSON 500
# ============================================================================


async def _call_trace_forward(value_error: Exception):
    mock_session = AsyncMock()
    mock_cls, _ = _client_ctx_with_session(mock_session)
    with (
        patch.object(trace_module, "Neo4jClient", mock_cls),
        patch.object(trace_module, "trace_forward", AsyncMock(side_effect=value_error)),
        patch.object(trace_module, "record_trace_query", MagicMock()),
    ):
        return await trace_module.trace_forward_endpoint(
            request=_make_request("/trace/forward/LOT-1"),
            tlc="LOT-1",
            max_depth=10,
            enforce_time_arrow=True,
            tenant_id=TENANT_A,
            api_key={"key_id": "k"},
        )


async def test_trace_forward_maps_value_error_to_500():
    """A tenant-invariant ValueError must not escape as an unhandled error."""
    with pytest.raises(HTTPException) as exc_info:
        await _call_trace_forward(ValueError("trace_forward tenant invariant violation"))
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"


async def test_trace_backward_maps_value_error_to_500():
    mock_session = AsyncMock()
    mock_cls, _ = _client_ctx_with_session(mock_session)
    with (
        patch.object(trace_module, "Neo4jClient", mock_cls),
        patch.object(trace_module, "trace_backward", AsyncMock(side_effect=ValueError("cross-tenant row"))),
        patch.object(trace_module, "record_trace_query", MagicMock()),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await trace_module.trace_backward_endpoint(
                request=_make_request("/trace/backward/LOT-1"),
                tlc="LOT-1",
                max_depth=10,
                tenant_id=TENANT_A,
                api_key={"key_id": "k"},
            )
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"


async def test_lot_timeline_maps_value_error_to_500():
    mock_session = AsyncMock()
    mock_cls, _ = _client_ctx_with_session(mock_session)
    with (
        patch.object(trace_module, "Neo4jClient", mock_cls),
        patch.object(trace_module, "get_lot_timeline", AsyncMock(side_effect=ValueError("cross-tenant event"))),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await trace_module.lot_timeline_endpoint(
                request=_make_request("/timeline/LOT-1"),
                tlc="LOT-1",
                tenant_id=TENANT_A,
                api_key={"key_id": "k"},
            )
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"


async def test_search_events_maps_value_error_to_500():
    mock_session = AsyncMock()
    mock_cls, _ = _client_ctx_with_session(mock_session)
    with (
        patch.object(trace_module, "Neo4jClient", mock_cls),
        patch.object(trace_module, "query_events_by_range", AsyncMock(side_effect=ValueError("cross-tenant lot"))),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await trace_module.search_traceability_events(
                request=_make_request("/search/events"),
                # Pass every Query param explicitly: on a direct call the
                # Query() objects would otherwise arrive as the values.
                start_date=None,
                end_date=None,
                product_contains=None,
                facility_contains=None,
                cte_type=None,
                limit=100,
                starting_after=None,
                tenant_id=TENANT_A,
                api_key={"key_id": "k"},
            )
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"


async def test_mobile_event_maps_session_value_error_to_500():
    """A corrupt-graph ValueError mid-write must become a 500, not a crash."""
    from services.graph.app.routers.fsma.traceability import TraceabilityEventRequest

    payload = TraceabilityEventRequest(
        event_type="RECEIVING",
        event_date="2026-04-12",
        tlc="LOT-2026-04-A1",
        location_identifier="0614141000012",
        responsible_party_contact="Jane Doe, 555-0100",
        quantity=500,
        uom="cases",
    )
    failing_session_ctx = MagicMock()
    failing_session_ctx.__aenter__ = AsyncMock(side_effect=ValueError("tenant invariant"))
    failing_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.session = MagicMock(return_value=failing_session_ctx)
    mock_cls = MagicMock(return_value=mock_client)
    mock_cls.get_tenant_database_name = MagicMock(return_value="test-db")
    with patch.object(trace_module, "Neo4jClient", mock_cls):
        with pytest.raises(HTTPException) as exc_info:
            await trace_module.log_traceability_event(
                request=_make_request("/event"),
                payload=payload,
                tenant_id=TENANT_A,
                api_key={"key_id": "k"},
            )
    assert exc_info.value.status_code == 500


# ============================================================================
# Compliance score must read the tenant database
# ============================================================================


async def test_compliance_score_uses_tenant_database():
    """The score query must run against the per-tenant database.

    Every other endpoint in the module passes database=db_name; the score
    endpoint used the default, which is a different database on Enterprise.
    """
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(
        return_value=_record(
            {
                "total_obligations": 0,
                "controls_mapped": 0,
                "evidence_items": 0,
                "avg_effectiveness": None,
                "fresh_evidence": 0,
            }
        )
    )
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_cls, _ = _client_ctx_with_session(mock_session)
    with patch.object(compliance_router, "Neo4jClient", mock_cls):
        await compliance_router.get_compliance_score(
            request=_make_request("/fsma/compliance/score"),
            tenant_id=TENANT_A,
            api_key={"key_id": "k"},
        )
    mock_cls.assert_called_once_with(database=f"reg_tenant_{TENANT_A}")


# ============================================================================
# Label batch init rejects non-GLN packer ids at the boundary
# ============================================================================


def _label_request(packer_gln: str) -> LabelBatchInitRequest:
    return LabelBatchInitRequest(
        packer_gln=packer_gln,
        product=ProductInfo(gtin="00000012345678", description="Test Product", expected_units=1),
        traceability=TraceabilityInfo(lot_number="LOT-TEST-001", pack_date="2024-01-01"),
        quantity=10,
    )


def test_label_batch_rejects_non_numeric_packer_gln():
    """Non-numeric GLNs used to reach generate_sscc and die with a plain 500."""
    with pytest.raises(ValidationError):
        _label_request("NOT-A-GLN!!")


def test_label_batch_rejects_wrong_length_packer_gln():
    with pytest.raises(ValidationError):
        _label_request("12345")


def test_label_batch_accepts_13_digit_packer_gln():
    req = _label_request("0614141000012")
    assert req.packer_gln == "0614141000012"


# ============================================================================
# Lineage fallback lookup scopes the SUPERSEDES hop to the tenant
# ============================================================================


async def test_lineage_fallback_scopes_prev_to_tenant():
    """The fallback query must not disclose another tenant's TLC.

    Drives the chain query to empty so the TLC fallback runs, then
    inspects the Cypher actually sent for the prev tenant guard.
    """
    row = _record(
        {
            "tlc": "LOT-X",
            "version": 2,
            "record_hash": "h2",
            "prev_hash": "h1",
            "created_at": "2026-01-01",
            "superseded_at": None,
            "source_document": "doc-1",
            "fact_type": "receiving",
            "is_current": True,
            "superseded_by": None,
            "all_props": {"tenant_id": str(TENANT_A), "custom": "x"},
        }
    )
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[_AsyncIterator([]), _AsyncIterator([row])])
    mock_cls, _ = _client_ctx_with_session(mock_session)
    mock_audit = MagicMock()
    mock_audit.alog = AsyncMock()
    with (
        patch.object(lineage_module, "Neo4jClient", mock_cls),
        patch.object(lineage_module, "get_audit_log", MagicMock(return_value=mock_audit)),
    ):
        resp = await lineage_module.get_fact_lineage(
            request=_make_request("/lineage/LOT-X/history"),
            tlc="LOT-X",
            tenant_id=TENANT_A,
            api_key={"key_id": "k"},
        )
    assert resp.total_versions == 1
    fallback_query = mock_session.run.call_args_list[1][0][0]
    assert "prev.tenant_id = $tenant_id" in fallback_query


# ============================================================================
# Harmonize always releases the mapping engine driver
# ============================================================================


def _harmonize_api_key():
    """Principal whose tenant matches TENANT_A.

    harmonize reconciles the middleware tenant with the API-key tenant
    before building the engine (#3316), so the key must carry TENANT_A.
    """
    return MagicMock(key_id="k", tenant_id=str(TENANT_A))


async def test_harmonize_closes_engine_on_mapping_failure():
    """A failed mapping must still close the engine (driver leak)."""
    engine = AsyncMock()
    engine.map_requirement = AsyncMock(side_effect=RuntimeError("llm down"))
    engine.close = AsyncMock()
    with patch("services.graph.app.mapping_engine.MappingEngine", MagicMock(return_value=engine)):
        with pytest.raises(HTTPException) as exc_info:
            await regulations_module.harmonize_requirement(
                request=_make_request("/regulations/harmonize/OB-1"),
                obligation_id="OB-1",
                api_key=_harmonize_api_key(),
                tenant_id=TENANT_A,
            )
    assert exc_info.value.status_code == 503
    engine.close.assert_awaited_once()


async def test_harmonize_maps_constructor_failure_to_503():
    """A constructor failure must become a 503, not an unhandled error."""
    with patch("services.graph.app.mapping_engine.MappingEngine", MagicMock(side_effect=RuntimeError("no uri"))):
        with pytest.raises(HTTPException) as exc_info:
            await regulations_module.harmonize_requirement(
                request=_make_request("/regulations/harmonize/OB-1"),
                obligation_id="OB-1",
                api_key=_harmonize_api_key(),
                tenant_id=TENANT_A,
            )
    assert exc_info.value.status_code == 503


# ============================================================================
# KDE completeness: exact counts, null-safe average, tenant-scoped linkage
# ============================================================================


def _kde_client(rows):
    mock_client = MagicMock()
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=_AsyncIterator([_record(r) for r in rows]))
    mock_client.session = MagicMock(return_value=_ctx_manager_r(mock_session))
    return mock_client, mock_session


async def test_kde_completeness_counts_complete_rows_exactly():
    """Disjoint gap categories must not inflate the completeness rate.

    10 events where 5 miss dates and 5 *other* events miss lots have zero
    complete events. The old max() formula reported 5 of 10 complete.
    """
    mock_client, _ = _kde_client(
        [
            {
                "event_type": "SHIPPING",
                "total": 10,
                "missing_date": 5,
                "missing_lot": 5,
                "low_confidence": 0,
                "avg_confidence": 0.9,
                "complete_count": 0,
            }
        ]
    )
    report = await analyze_kde_completeness(mock_client, tenant_id=str(TENANT_A))
    assert report.total_events == 10
    assert report.overall_completeness_rate == 0.0


async def test_kde_query_averages_confidence_without_zero_fill():
    """Events with no confidence value must not drag the average to 0."""
    mock_client, mock_session = _kde_client([])
    await analyze_kde_completeness(mock_client, tenant_id=str(TENANT_A))
    query = mock_session.run.call_args[0][0]
    assert "avg(e.confidence)" in query


async def test_kde_query_scopes_lot_linkage_to_tenant():
    """An edge to another tenant's Lot must not mark the event as linked."""
    mock_client, mock_session = _kde_client([])
    await analyze_kde_completeness(mock_client, tenant_id=str(TENANT_A))
    query = mock_session.run.call_args[0][0]
    assert "l.tenant_id = $tenant_id" in query


# ============================================================================
# Unfixed findings (real bugs, intentionally not fixed here)
# ============================================================================


@pytest.mark.xfail(strict=True, reason="BUG labels/generate_sscc: 19-digit output is not a valid 18-digit GS1 SSCC")
def test_sscc_output_is_18_digits():
    """GS1 SSCCs are 18 digits; generate_sscc emits extension + 12 + 5 + check = 19."""
    sscc = labels_router.generate_sscc("0614141000012", 1)
    assert len(sscc) == 18


@pytest.mark.xfail(strict=True, reason="BUG labels/generate_sscc: serial truncated to 5 digits, repeats after 99999")
def test_sscc_serials_do_not_wrap():
    """Serial 100001 must not reuse serial 1's SSCC on the same GLN."""
    gln = "0614141000012"
    assert labels_router.generate_sscc(gln, 1) != labels_router.generate_sscc(gln, 100001)


@pytest.mark.xfail(
    strict=True,
    reason="BUG regulations/loader contract: regulation_loader writes global Regulation nodes with no tenant_id, so tenant-scoped list endpoints return nothing",
)
async def test_global_regulations_visible_to_tenants():
    """Reference regulations seeded without a tenant (the loader's shape)
    should still be listed. Neo4j `=` matching never matches a node that
    lacks the property, so the tenant predicate filters every loader row.
    """
    seeded = [{"name": "FSMA 204", "tenant_id": None}]

    def _emulate_neo4j_equality(query, **params):
        # Faithful on one point: `r.tenant_id = $tenant_id` matches no
        # node that lacks tenant_id, exactly as Neo4j evaluates it.
        if "r.tenant_id = $tenant_id" in query:
            wanted = params.get("tenant_id")
            rows = [n for n in seeded if n.get("tenant_id") == wanted]
        else:
            rows = list(seeded)
        return _AsyncIterator([_record(r) for r in rows])

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=_emulate_neo4j_equality)
    mock_cls, _ = _client_ctx_with_session(mock_session)
    with patch.object(regulations_module, "Neo4jClient", mock_cls):
        resp = await regulations_module.list_regulations(
            jurisdiction=None,
            skip=0,
            limit=50,
            api_key={"key_id": "k"},
            tenant_id=TENANT_A,
        )
    assert len(resp) > 0
