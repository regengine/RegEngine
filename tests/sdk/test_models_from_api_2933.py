"""#2933: SDK model deserialisation — server payload -> populated dataclass.

``Record``, ``Facility`` and ``TimelineEvent`` used to define a hand-written
``__init__`` that filtered kwargs through ``hasattr``. ``@dataclass`` leaves an
``__init__`` already in ``cls.__dict__`` alone, so that filter won — and since
a field declared without a default is not a class attribute, ``hasattr`` was
False for every one of them and all were silently dropped.
``get_record(tlc).tlc`` raised ``AttributeError``, and so did ``repr(record)``.

Two halves are pinned here: the constructors are now the strict generated ones
(unknown keyword -> ``TypeError``), and ``from_api`` maps the server's key
names (``event_id``, ``traceability_lot_code``, ...) onto the SDK field names.

The payloads below are literal copies of the shapes the real endpoints emit:
``services/ingestion/app/canonical_router.py:139-158`` for records, the
``get_lot_timeline`` entries in ``services/graph/app/fsma/queries.py:111-126``
for the timeline, and the facility dicts in
``services/graph/app/fsma/tracer.py:187-193`` for facilities.
"""

from __future__ import annotations

import dataclasses

import httpx
import pytest

from regengine import RegEngineClient
from regengine.models import Facility, Record, TimelineEvent

# A row exactly as GET /api/v1/records returns it (canonical_router.py:140-157).
RECORDS_ROW = {
    "event_id": "3f1b1c8e-0000-4a00-9d00-000000000001",
    "event_type": "SHIPPING",
    "traceability_lot_code": "LOT-2026-001",
    "product_reference": "Romaine Lettuce, chopped",
    "quantity": 120.5,
    "unit_of_measure": "LB",
    "from_facility_reference": "0614141000012",
    "to_facility_reference": "0614141000029",
    "event_timestamp": "2026-04-12T16:00:00+00:00",
    "source_system": "epcis",
    "status": "active",
    "confidence_score": 1.0,
    "schema_version": "1.0",
    "created_at": "2026-04-12T16:05:00+00:00",
}

# A timeline entry exactly as GET /api/v1/fsma/traceability/timeline/{tlc}
# returns it (queries.py:111-126).
TIMELINE_ENTRY = {
    "event_id": "3f1b1c8e-0000-4a00-9d00-000000000002",
    "type": "RECEIVING",
    "event_date": "2026-04-13",
    "event_time": "08:30:00",
    "confidence": 0.98,
    "facility": {"name": "Metro Fresh Market", "gln": "0614141000029"},
}

# A facility exactly as a trace result carries it (tracer.py:187-193).
TRACE_FACILITY = {
    "gln": "0614141000012",
    "name": "Distribution Center Alpha",
    "address": "1 Distribution Way, Salinas CA",
    "facility_type": "distribution_center",
}


def make_client(handler) -> RegEngineClient:
    client = RegEngineClient(api_key="rge_test", retry_backoff_factor=0.0)
    client._session = httpx.Client(transport=httpx.MockTransport(handler))
    return client


class TestRecordFromApi:
    def test_every_documented_attribute_is_populated(self):
        record = Record.from_api(RECORDS_ROW)

        assert record.id == RECORDS_ROW["event_id"]
        assert record.tlc == "LOT-2026-001"
        assert record.cte_type == "SHIPPING"
        assert record.location == "0614141000012"
        assert record.quantity == 120.5
        assert record.quantity_uom == "LB"
        assert record.event_date == "2026-04-12T16:00:00+00:00"
        assert record.product_description == "Romaine Lettuce, chopped"
        assert record.created_at == "2026-04-12T16:05:00+00:00"

    def test_no_field_is_left_unset(self):
        """Pre-fix, only ``hash`` (the one field with a default) existed."""
        record = Record.from_api(RECORDS_ROW)
        for f in dataclasses.fields(Record):
            assert hasattr(record, f.name), f"{f.name} was dropped during deserialisation"

    def test_repr_does_not_raise(self):
        assert "LOT-2026-001" in repr(Record.from_api(RECORDS_ROW))

    def test_short_aliases_are_accepted(self):
        record = Record.from_api({"id": "E1", "tlc": "LOT-9", "cte_type": "COOLING", "sha256_hash": "abc"})
        assert (record.id, record.tlc, record.cte_type, record.hash) == ("E1", "LOT-9", "COOLING", "abc")

    def test_constructor_rejects_unrecognised_keys(self):
        """A required field can no longer end up unset: raw server keys raise."""
        with pytest.raises(TypeError, match="event_id"):
            Record(**RECORDS_ROW)

    def test_constructor_keeps_the_values_it_is_given(self):
        record = Record(
            id="E1",
            tlc="LOT-1",
            cte_type="SHIPPING",
            location="GLN1",
            quantity=5.0,
            quantity_uom="LB",
            event_date="2026-01-01",
            hash="abc",
        )
        assert (record.id, record.tlc, record.quantity, record.hash) == ("E1", "LOT-1", 5.0, "abc")


class TestTimelineEventFromApi:
    def test_maps_type_date_and_nested_facility(self):
        event = TimelineEvent.from_api(TIMELINE_ENTRY)
        assert event.cte == "RECEIVING"
        assert event.date == "2026-04-13"
        assert event.location == "Metro Fresh Market"
        assert event.quantity is None

    def test_null_facility_leaves_location_empty(self):
        event = TimelineEvent.from_api({**TIMELINE_ENTRY, "facility": None})
        assert event.location == ""
        assert event.cte == "RECEIVING"

    def test_constructor_rejects_unrecognised_keys(self):
        with pytest.raises(TypeError, match="event_id"):
            TimelineEvent(**TIMELINE_ENTRY)


class TestFacilityFromApi:
    def test_maps_trace_facility_and_falls_back_to_gln_for_id(self):
        facility = Facility.from_api(TRACE_FACILITY)
        assert facility.gln == "0614141000012"
        assert facility.id == "0614141000012"
        assert facility.name == "Distribution Center Alpha"
        assert facility.address == "1 Distribution Way, Salinas CA"
        assert facility.facility_type == "distribution_center"
        assert "Distribution Center Alpha" in repr(facility)

    def test_constructor_rejects_unrecognised_keys(self):
        with pytest.raises(TypeError, match="nonsense"):
            Facility(id="F1", gln="G", name="N", nonsense=1)


class TestClientReadPathsReturnPopulatedModels:
    """The acceptance path: non-empty stubbed payloads, attribute values asserted."""

    def test_get_record_returns_a_populated_record(self):
        client = make_client(
            lambda request: httpx.Response(200, json={"tenant_id": "t1", "events": [RECORDS_ROW], "total": 1})
        )
        try:
            record = client.get_record("LOT-2026-001")
        finally:
            client._session.close()

        assert record.tlc == "LOT-2026-001"
        assert record.cte_type == "SHIPPING"
        assert record.location == "0614141000012"
        assert record.quantity == 120.5
        assert record.quantity_uom == "LB"
        assert record.event_date == "2026-04-12T16:00:00+00:00"
        assert record.id == RECORDS_ROW["event_id"]

    def test_query_records_returns_populated_records(self):
        second = {**RECORDS_ROW, "event_id": "evt-2", "traceability_lot_code": "LOT-2026-002"}
        client = make_client(
            lambda request: httpx.Response(200, json={"tenant_id": "t1", "events": [RECORDS_ROW, second], "total": 2})
        )
        try:
            records = client.query_records("2026-01-01", "2026-12-31")
        finally:
            client._session.close()

        assert [r.tlc for r in records] == ["LOT-2026-001", "LOT-2026-002"]
        assert [r.id for r in records] == [RECORDS_ROW["event_id"], "evt-2"]
        assert all(r.quantity == 120.5 for r in records)

    def test_get_timeline_returns_populated_events(self):
        first = {**TIMELINE_ENTRY, "type": "SHIPPING", "event_date": "2026-04-12"}
        client = make_client(
            lambda request: httpx.Response(200, json={"lot_id": "LOT-2026-001", "events": [first, TIMELINE_ENTRY]})
        )
        try:
            timeline = client.get_timeline("LOT-2026-001")
        finally:
            client._session.close()

        assert [e.cte for e in timeline] == ["SHIPPING", "RECEIVING"]
        assert [e.date for e in timeline] == ["2026-04-12", "2026-04-13"]
        assert all(e.location == "Metro Fresh Market" for e in timeline)
