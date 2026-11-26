"""Data-free GLN regressions for graph CSV exports."""

import csv
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from shared.fsma_validation import calculate_gs1_check_digit, gln_for_export

from services.graph.app.exporters import recall_contacts_csv, trace_csv
from services.graph.app.routers.fsma import compliance


def shapes():
    base = "0" * 12
    return [None, "", " ", "x", "0", "x" * 13, base + str(calculate_gs1_check_digit(base))]


@pytest.mark.parametrize("raw", shapes())
def test_trace_facility_gln(raw):
    assert trace_csv._row({}, {}, {"gln": raw})[8] == gln_for_export(raw)


@pytest.mark.parametrize("raw", shapes())
def test_recall_facility_gln(raw):
    assert recall_contacts_csv._row({"gln": raw}, {}, {})[1] == gln_for_export(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", shapes())
async def test_fda_sortable_gln(monkeypatch, raw):
    monkeypatch.setattr(compliance, "reconcile_tenant_scope", lambda *a, **k: "x")
    monkeypatch.setattr(compliance.uuid, "UUID", lambda value: value)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(compliance, "Neo4jClient", MagicMock(return_value=client))
    monkeypatch.setattr(compliance, "_load_range_export_events", AsyncMock(return_value=[{"location_gln": raw}]))
    request = SimpleNamespace(url=SimpleNamespace(path="x"))
    response = await compliance.export_fda_request_sheet.__wrapped__(
        request, start_date="", end_date="", tlc=None, tenant_id=None, api_key=None
    )
    body = b"".join([chunk async for chunk in response.body_iterator]).decode("utf-8-sig")
    assert list(csv.reader(io.StringIO(body)))[1][6] == gln_for_export(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", shapes())
@pytest.mark.parametrize("direction", ["forward", "backward"])
async def test_trace_api_gln(monkeypatch, raw, direction):
    from services.graph.app.fsma.types import TraceResult
    from services.graph.app.routers.fsma import traceability

    result = TraceResult("x", direction, [{"gln": raw}], [], [], None, 0, 0)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(traceability, "Neo4jClient", MagicMock(return_value=client))
    monkeypatch.setattr(traceability, f"trace_{direction}", AsyncMock(return_value=result))
    monkeypatch.setattr(traceability, "record_trace_query", MagicMock())
    monkeypatch.setattr(traceability, "get_audit_log", lambda: SimpleNamespace(alog=AsyncMock()))
    endpoint = getattr(traceability, f"trace_{direction}_endpoint").__wrapped__
    response = await endpoint(SimpleNamespace(), tlc="x", max_depth=1, tenant_id=None, api_key=None)
    assert response["facilities"][0]["gln"] == gln_for_export(raw)
    assert result.facilities[0]["gln"] == raw


@pytest.mark.parametrize("raw", shapes())
def test_recall_result_gln(raw):
    from services.graph.app.fsma_recall.models import AffectedFacility, RecallResult

    facility = AffectedFacility(raw, "", "", [], None)
    result = RecallResult("x", True, affected_facilities=[facility])
    assert result.to_dict()["affected_facilities"][0]["gln"] == gln_for_export(raw)
    assert facility.gln == raw


@pytest.mark.parametrize("raw", shapes())
def test_recall_target_gln(raw):
    from datetime import datetime, timezone

    from services.graph.app.fsma_recall.models import RecallDrill, RecallSeverity, RecallType

    drill = RecallDrill(
        "x",
        "x",
        datetime.now(timezone.utc),
        next(iter(RecallType)),
        next(iter(RecallSeverity)),
        target_facility_gln=raw,
    )
    assert drill.to_dict()["target_facility_gln"] == gln_for_export(raw)
