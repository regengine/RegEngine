"""Operational exports preserve tenant facts and refuse incomplete reads."""

import csv
import io
import traceback
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app import epcis_export
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from shared.tenant_context import TenantContext
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

TENANT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(epcis_export.router)
    app.dependency_overrides[epcis_export.require_tenant_context] = lambda: TenantContext(TENANT, "test", "test-key")
    with TestClient(app) as client:
        yield client


@pytest.fixture
def event():
    return {
        "event_type": "shipping",
        "traceability_lot_code": "LOT-A",
        "product_description": "Tomatoes",
        "quantity": 5,
        "unit_of_measure": "case",
        "event_timestamp": datetime(2026, 9, 28, 12, tzinfo=timezone.utc),
        "location_gln": "1234567890123",
        "location_name": "Origin",
        "sha256_hash": "a" * 64,
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "OBSERVE",
        "epcis_biz_step": "urn:epcglobal:cbv:bizstep:shipping",
        "ship_from": "Origin",
        "ship_from_gln": "1234567890123",
        "ship_to": "Destination",
        "ship_to_gln": "1234567890124",
        "carrier": "Carrier",
        "temperature_c": 0,
    }


def test_csv_preserves_multiline_punctuation_zero_and_neutralizes_every_text_column(client, monkeypatch, event):
    event.update(
        traceability_lot_code="=1+1",
        product_description='Tomatoes, fresh\nGrade "A"',
        unit_of_measure="+case",
        ship_from_gln="@origin",
        ship_to_gln="-destination",
        carrier='Carrier, "A"',
        sha256_hash="=untrusted",
        quantity=0,
    )
    monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *args: [event])

    response = client.post("/api/v1/export/fda", json={"tenant_id": TENANT})

    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["Product_Description"] == 'Tomatoes, fresh\nGrade "A"'
    assert rows[0]["Carrier"] == 'Carrier, "A"'
    assert rows[0]["Temperature_C"] == "0"
    assert rows[0]["Quantity"] == "0"
    assert rows[0]["Traceability_Lot_Code"] == "'=1+1"
    assert rows[0]["Unit_of_Measure"] == "'+case"
    assert rows[0]["Ship_From_GLN"] == "'@origin"
    assert rows[0]["Ship_To_GLN"] == "'-destination"
    assert rows[0]["SHA256_Hash"] == "'=untrusted"


def test_epcis_offset_matches_the_persisted_event_timestamp(client, monkeypatch, event):
    event["event_timestamp"] = datetime(2026, 9, 28, 0, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *args: [event])

    response = client.post("/api/v1/export/epcis", json={"tenant_id": TENANT})

    exported = response.json()["epcisBody"]["eventList"][0]
    assert exported["eventTime"] == "2026-09-28T00:30:00+05:30"
    assert exported["eventTimeZoneOffset"] == "+05:30"


def test_fda_timestamp_labelled_utc_is_converted_to_utc(client, monkeypatch, event):
    event["event_timestamp"] = datetime(2026, 9, 28, 0, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *args: [event])

    response = client.post("/api/v1/export/fda", json={"tenant_id": TENANT})

    row = next(csv.DictReader(io.StringIO(response.text)))
    assert row["Event_Date"] == "2026-09-27"
    assert row["Event_Time"] == "19:00:00Z"


@pytest.mark.parametrize("endpoint", ["epcis", "fda"])
def test_database_error_never_becomes_sample_export(client, monkeypatch, endpoint):
    def fail(*args):
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: SimpleNamespace(execute=fail, close=lambda: None))
    response = client.post(f"/api/v1/export/{endpoint}", json={"tenant_id": TENANT})
    assert response.status_code == 503
    assert "private diagnostic" not in response.text
    assert "TOM-0226" not in response.text


def test_unavailable_database_refuses_export(monkeypatch):
    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: None)
    with pytest.raises(HTTPException) as caught:
        epcis_export._query_tenant_events(TENANT, None, None, None)
    assert caught.value.status_code == 503


@pytest.mark.parametrize("endpoint", ["epcis", "fda"])
@pytest.mark.parametrize("field", ["date_from", "date_to"])
@pytest.mark.parametrize("value", ["private-invalid-date", "2026-02-30", "", "2026-09-28T25:00:00"])
def test_malformed_date_is_rejected_before_database_access(client, monkeypatch, endpoint, field, value):
    database_calls = []

    def database():
        database_calls.append("acquire")
        return None

    monkeypatch.setattr(epcis_export, "get_db_safe", database)
    response = client.post(f"/api/v1/export/{endpoint}", json={"tenant_id": TENANT, field: value})

    assert response.status_code == 400
    assert database_calls == []
    assert "private-invalid-date" not in response.text


def test_end_date_without_representable_next_day_is_rejected_before_database_access(client, monkeypatch):
    database_calls = []
    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: database_calls.append("acquire"))

    response = client.post("/api/v1/export/fda", json={"tenant_id": TENANT, "date_to": "9999-12-31"})

    assert response.status_code == 400
    assert database_calls == []


@pytest.mark.parametrize(
    "date_from,date_to,expected_start,expected_end",
    [
        ("2026-09-28", "2026-09-28", "2026-09-28T00:00:00+00:00", "2026-09-29T00:00:00+00:00"),
        ("2026-09-28T12:30:00", "2026-09-28T14:30:00", "2026-09-28T12:30:00+00:00", "2026-09-28T14:30:00+00:00"),
        (
            "2026-09-28 12:30:00.123456",
            "2026-09-28 14:30:00.123456",
            "2026-09-28T12:30:00.123456+00:00",
            "2026-09-28T14:30:00.123456+00:00",
        ),
        (
            "2026-09-28T12:30:00+05:30",
            "2026-09-28T14:30:00+05:30",
            "2026-09-28T12:30:00+05:30",
            "2026-09-28T14:30:00+05:30",
        ),
        ("2026-09-28T12:30:00Z", "2026-09-28T14:30:00Z", "2026-09-28T12:30:00+00:00", "2026-09-28T14:30:00Z"),
    ],
)
def test_valid_date_and_datetime_filters_preserve_query_bounds(
    monkeypatch, date_from, date_to, expected_start, expected_end
):
    bound_parameters = []

    def execute(statement, params):
        bound_parameters.append(params)
        return SimpleNamespace(fetchall=lambda: [])

    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: SimpleNamespace(execute=execute, close=lambda: None))

    assert epcis_export._query_tenant_events(TENANT, None, date_from, date_to) == []
    assert bound_parameters == [{"tenant_id": TENANT, "date_from": expected_start, "date_to": expected_end}]


def test_query_error_has_no_private_exception_chain(monkeypatch, caplog):
    def fail(*args):
        raise RuntimeError("synthetic-private-db-diagnostic")

    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: SimpleNamespace(execute=fail, close=lambda: None))
    with pytest.raises(HTTPException) as caught:
        epcis_export._query_tenant_events(TENANT, None, None, None)

    assert caught.value.status_code == 503
    assert "synthetic-private" not in "".join(traceback.format_exception(caught.value))
    assert "synthetic-private" not in caplog.text


@pytest.mark.parametrize("outcome", ["query_error", "overflow", "success"])
def test_cleanup_error_never_masks_query_outcome_or_exposes_diagnostics(monkeypatch, caplog, event, outcome):
    def execute(*args):
        if outcome == "query_error":
            raise RuntimeError("synthetic-private-db-diagnostic")
        rows = [SimpleNamespace(_mapping=event)] * (5001 if outcome == "overflow" else 1)
        return SimpleNamespace(fetchall=lambda: rows)

    def close():
        raise RuntimeError("synthetic-private-close-diagnostic")

    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: SimpleNamespace(execute=execute, close=close))
    if outcome == "success":
        assert epcis_export._query_tenant_events(TENANT, None, None, None) == [event]
    else:
        with pytest.raises(HTTPException) as caught:
            epcis_export._query_tenant_events(TENANT, None, None, None)
        assert caught.value.status_code == (503 if outcome == "query_error" else 413)
        assert "synthetic-private" not in "".join(traceback.format_exception(caught.value))
    assert "synthetic-private" not in caplog.text


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS fsma")
        connection.exec_driver_sql("""CREATE TABLE fsma.cte_events (
            id INTEGER PRIMARY KEY, tenant_id TEXT, validation_status TEXT,
            event_type TEXT, traceability_lot_code TEXT, product_description TEXT,
            quantity REAL, unit_of_measure TEXT, event_timestamp TEXT,
            location_gln TEXT, location_name TEXT, sha256_hash TEXT,
            epcis_event_type TEXT, epcis_action TEXT, epcis_biz_step TEXT)""")
        connection.exec_driver_sql("CREATE TABLE fsma.cte_kdes (cte_event_id INTEGER, kde_key TEXT, kde_value TEXT)")
    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: Session(engine))
    yield engine
    engine.dispose()


def _seed(database, rows):
    with database.begin() as connection:
        connection.execute(
            text("""INSERT INTO fsma.cte_events
            (id, tenant_id, validation_status, traceability_lot_code, event_timestamp)
            VALUES (:id, :tenant, :status, :lot, :timestamp)"""),
            rows,
        )


def test_query_excludes_rejected_and_foreign_tenant_but_keeps_warning(database):
    _seed(
        database,
        [
            {"id": 1, "tenant": TENANT, "status": "valid", "lot": "valid", "timestamp": "2026-09-28T12:00:00+00:00"},
            {
                "id": 2,
                "tenant": TENANT,
                "status": "warning",
                "lot": "warning",
                "timestamp": "2026-09-28T12:00:00+00:00",
            },
            {
                "id": 3,
                "tenant": TENANT,
                "status": "rejected",
                "lot": "rejected",
                "timestamp": "2026-09-28T12:00:00+00:00",
            },
            {
                "id": 4,
                "tenant": "foreign",
                "status": "valid",
                "lot": "foreign",
                "timestamp": "2026-09-28T12:00:00+00:00",
            },
        ],
    )
    rows = epcis_export._query_tenant_events(TENANT, None, None, None)
    assert {row["traceability_lot_code"] for row in rows} == {"valid", "warning"}


def test_date_to_includes_the_requested_calendar_day(database):
    _seed(
        database,
        [
            {"id": 1, "tenant": TENANT, "status": "valid", "lot": "included", "timestamp": "2026-09-28T23:59:59+00:00"},
            {"id": 2, "tenant": TENANT, "status": "valid", "lot": "excluded", "timestamp": "2026-09-29T00:00:00+00:00"},
        ],
    )
    rows = epcis_export._query_tenant_events(TENANT, None, "2026-09-28", "2026-09-28")
    assert [row["traceability_lot_code"] for row in rows] == ["included"]


def test_naive_datetime_date_to_keeps_the_exact_instant_exclusive(database):
    _seed(
        database,
        [
            {
                "id": 1,
                "tenant": TENANT,
                "status": "valid",
                "lot": "included",
                "timestamp": "2026-09-28T14:29:59.999999+00:00",
            },
            {"id": 2, "tenant": TENANT, "status": "valid", "lot": "at-bound", "timestamp": "2026-09-28T14:30:00+00:00"},
            {
                "id": 3,
                "tenant": TENANT,
                "status": "valid",
                "lot": "after-bound",
                "timestamp": "2026-09-28T14:30:01+00:00",
            },
        ],
    )

    rows = epcis_export._query_tenant_events(TENANT, None, None, "2026-09-28T14:30:00")

    assert [row["traceability_lot_code"] for row in rows] == ["included"]


@pytest.mark.parametrize("count", [5000, 5001])
def test_row_limit_delivers_complete_results_or_refuses(database, count):
    _seed(
        database,
        [
            {"id": index, "tenant": TENANT, "status": "valid", "lot": "LOT-A", "timestamp": "2026-09-28T12:00:00+00:00"}
            for index in range(count)
        ],
    )
    if count == 5000:
        assert len(epcis_export._query_tenant_events(TENANT, None, None, None)) == 5000
        return
    with pytest.raises(HTTPException) as caught:
        epcis_export._query_tenant_events(TENANT, None, None, None)
    assert caught.value.status_code == 413
