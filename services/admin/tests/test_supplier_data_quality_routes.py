"""Supplier data quality routes: scoping and guards, no database.

A fake session answers the facility ownership lookups; the SQL fetchers are
stubbed so the tests check what the routes pass and return, not SQL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.supplier_data_quality import (
    DEFAULT_WINDOW_DAYS,
    EPCIS_TENANT_SCOPE_REASON,
    EPCIS_UNAVAILABLE_REASON,
    LATE_CTE_LABEL,
    LATE_CTE_NO_HOURS_REASON,
    MAX_WINDOW_DAYS,
    MIN_RECORDS,
)

TENANT = uuid4()
OTHER_TENANT = uuid4()
USER = uuid4()
OTHER_USER = uuid4()
OWN_FACILITY = uuid4()
FOREIGN_FACILITY = uuid4()
OTHER_TENANT_FACILITY = uuid4()

# Any positive whole number of hours; derived rather than picked.
AGREED_HOURS = MIN_RECORDS
NOW = datetime.now(timezone.utc)

# Shipping records with no KDEs on the owned facility, each received just past
# AGREED_HOURS after its event time, and one lot with no upstream link. Ids
# and lot codes are generated per run.
RECORD_ROWS = [
    {
        "record_id": str(uuid4()),
        "facility_id": str(OWN_FACILITY),
        "cte_type": "shipping",
        "kde_data": {},
        "event_time": NOW - timedelta(hours=AGREED_HOURS) - timedelta.resolution,
        "created_at": NOW,
        "lot_code": str(uuid4()),
    }
    for _ in range(MIN_RECORDS // 10)
]
LOT_ROWS = [
    {
        "lot_id": str(uuid4()),
        "lot_code": str(uuid4()),
        "facility_id": str(OWN_FACILITY),
        "cte_type": "shipping",
        "kde_data": {},
        "is_transformation_output": False,
    }
]


# Tenant wide EPCIS receipts: enough for a share, every other one rejected.
RECEIPTS = [uuid4() for _ in range(MIN_RECORDS)]
REJECTED_RECEIPTS = RECEIPTS[::2]


class FakeSession:
    def __init__(self, own_hours: int | None = None) -> None:
        self.commits = 0
        self.facilities = {
            OWN_FACILITY: SimpleNamespace(
                id=OWN_FACILITY, tenant_id=TENANT, supplier_user_id=USER, agreed_sending_hours=own_hours
            ),
            FOREIGN_FACILITY: SimpleNamespace(
                id=FOREIGN_FACILITY, tenant_id=TENANT, supplier_user_id=OTHER_USER, agreed_sending_hours=None
            ),
            OTHER_TENANT_FACILITY: SimpleNamespace(
                id=OTHER_TENANT_FACILITY, tenant_id=OTHER_TENANT, supplier_user_id=USER, agreed_sending_hours=None
            ),
        }

    def commit(self) -> None:
        self.commits += 1

    def get(self, _model, key):
        return self.facilities.get(key)

    def scalars(self, _stmt):
        # The route filters by tenant and user in SQL; the fake returns what that
        # filter yields for TENANT and USER.
        return SimpleNamespace(all=lambda: [OWN_FACILITY])


@pytest.fixture
def calls():
    return []


def _client(monkeypatch, calls, tenant=TENANT, session=None, receipt_counts=(len(REJECTED_RECEIPTS), len(RECEIPTS))):
    import app.supplier_compliance_routes as routes

    session = session if session is not None else FakeSession()

    def fake_receipt_counts(_db, tenant_id, since):
        calls.append(("receipts", tenant_id))
        return receipt_counts

    def fake_records(_db, tenant_id, user_id, facility_ids, since):
        calls.append(("records", tenant_id, user_id, list(facility_ids)))
        return [dict(row) for row in RECORD_ROWS]

    def fake_lots(_db, tenant_id, user_id, facility_ids, since):
        calls.append(("lots", tenant_id, user_id, list(facility_ids)))
        return [dict(row) for row in LOT_ROWS]

    def fake_hours(db, tenant_id, user_id, facility_ids):
        calls.append(("hours", tenant_id, user_id, list(facility_ids)))
        return {key: db.facilities[UUID(key)].agreed_sending_hours for key in facility_ids}

    monkeypatch.setattr(routes, "fetch_sending_hours", fake_hours)
    monkeypatch.setattr("shared.supplier_data_quality.fetch_sending_hours", fake_hours)
    monkeypatch.setattr(routes, "fetch_record_rows", fake_records)
    monkeypatch.setattr(routes, "fetch_lot_rows", fake_lots)
    monkeypatch.setattr("shared.supplier_data_quality.fetch_record_rows", fake_records)
    monkeypatch.setattr("shared.supplier_data_quality.fetch_lot_rows", fake_lots)
    monkeypatch.setattr("shared.supplier_data_quality.fetch_receipt_counts", fake_receipt_counts)
    monkeypatch.setattr(routes.TenantContext, "get_tenant_context", lambda _db: tenant)

    app = FastAPI()
    app.include_router(routes.router, prefix="/v1")
    app.dependency_overrides[routes.get_session] = lambda: session
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(id=USER)
    return TestClient(app)


def test_summary_returns_four_separate_metrics_for_owned_facilities(monkeypatch, calls):
    resp = _client(monkeypatch, calls).get("/v1/supplier/data-quality")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == DEFAULT_WINDOW_DAYS
    assert body["min_records"] == MIN_RECORDS
    assert body["late_cte_label"] == LATE_CTE_LABEL
    [supplier] = body["suppliers"]
    assert supplier["supplier_key"] == str(OWN_FACILITY)
    assert [m["key"] for m in supplier["metrics"]] == ["missing_kde", "unlinked_lot", "late_cte", "epcis_failed"]
    missing = supplier["metrics"][0]
    assert (missing["status"], missing["numerator"], missing["denominator"]) == (
        "not_enough_data",
        len(RECORD_ROWS),
        len(RECORD_ROWS),
    )
    assert supplier["agreed_sending_hours"] is None
    late = supplier["metrics"][2]
    assert (late["status"], late["numerator"], late["reason"]) == ("not_enough_data", None, LATE_CTE_NO_HOURS_REASON)
    epcis = supplier["metrics"][3]
    assert (epcis["status"], epcis["numerator"], epcis["denominator"], epcis["share"], epcis["reason"]) == (
        "ok",
        len(REJECTED_RECEIPTS),
        len(RECEIPTS),
        len(REJECTED_RECEIPTS) / len(RECEIPTS),
        EPCIS_TENANT_SCOPE_REASON,
    )
    scoped = [call for call in calls if call[0] != "receipts"]
    assert all(call[1:3] == (str(TENANT), str(USER)) for call in scoped)
    assert all(call[3] == [str(OWN_FACILITY)] for call in scoped)
    # Receipts carry no facility: one tenant scoped count, no user or facility filter.
    assert [call for call in calls if call[0] == "receipts"] == [("receipts", str(TENANT))]


def test_epcis_under_min_records_is_not_enough_data(monkeypatch, calls):
    receipts = RECEIPTS[: MIN_RECORDS - 1]
    rejected = receipts[::2]
    client = _client(monkeypatch, calls, receipt_counts=(len(rejected), len(receipts)))
    [supplier] = client.get("/v1/supplier/data-quality").json()["suppliers"]
    epcis = supplier["metrics"][3]
    assert (epcis["status"], epcis["numerator"], epcis["denominator"], epcis["share"]) == (
        "not_enough_data",
        len(rejected),
        len(receipts),
        None,
    )


def test_epcis_unreadable_receipts_is_unavailable(monkeypatch, calls):
    [supplier] = _client(monkeypatch, calls, receipt_counts=None).get("/v1/supplier/data-quality").json()["suppliers"]
    epcis = supplier["metrics"][3]
    assert (epcis["status"], epcis["reason"]) == ("unavailable", EPCIS_UNAVAILABLE_REASON)


@pytest.mark.parametrize("window", [0, MAX_WINDOW_DAYS + 1, -1])
def test_window_days_is_bounded(monkeypatch, calls, window):
    resp = _client(monkeypatch, calls).get(f"/v1/supplier/data-quality?window_days={window}")
    assert resp.status_code == 422
    assert calls == []


def test_summary_requires_tenant(monkeypatch, calls):
    assert _client(monkeypatch, calls, tenant=None).get("/v1/supplier/data-quality").status_code == 400


def test_drilldown_lists_missing_kde_records(monkeypatch, calls):
    resp = _client(monkeypatch, calls).get(
        f"/v1/supplier/data-quality/{OWN_FACILITY}/records?metric=missing_kde&limit=1"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["total"], body["limit"], body["offset"]) == (len(RECORD_ROWS), 1, 0)
    assert [item["record_id"] for item in body["items"]] == [RECORD_ROWS[0]["record_id"]]
    assert "product_description" in body["items"][0]["missing_kdes"]
    assert calls == [("records", str(TENANT), str(USER), [str(OWN_FACILITY)])]


def test_drilldown_offset_pages(monkeypatch, calls):
    resp = _client(monkeypatch, calls).get(
        f"/v1/supplier/data-quality/{OWN_FACILITY}/records?metric=missing_kde&limit=1&offset=1"
    )
    assert [item["record_id"] for item in resp.json()["items"]] == [RECORD_ROWS[1]["record_id"]]


def test_drilldown_lists_unlinked_lots(monkeypatch, calls):
    resp = _client(monkeypatch, calls).get(f"/v1/supplier/data-quality/{OWN_FACILITY}/records?metric=unlinked_lot")
    assert resp.status_code == 200
    assert [item["lot_code"] for item in resp.json()["items"]] == [LOT_ROWS[0]["lot_code"]]


@pytest.mark.parametrize("facility", [FOREIGN_FACILITY, OTHER_TENANT_FACILITY])
def test_drilldown_refuses_facility_not_owned_in_tenant(monkeypatch, calls, facility):
    resp = _client(monkeypatch, calls).get(f"/v1/supplier/data-quality/{facility}/records?metric=missing_kde")
    assert resp.status_code == 404
    assert calls == []


def test_summary_counts_late_records_against_agreed_hours(monkeypatch, calls):
    resp = _client(monkeypatch, calls, session=FakeSession(own_hours=AGREED_HOURS)).get("/v1/supplier/data-quality")
    [supplier] = resp.json()["suppliers"]
    assert supplier["agreed_sending_hours"] == AGREED_HOURS
    late = supplier["metrics"][2]
    # Fewer than MIN_RECORDS timed records: counts shown, no share.
    assert (late["status"], late["numerator"], late["denominator"], late["share"]) == (
        "not_enough_data",
        len(RECORD_ROWS),
        len(RECORD_ROWS),
        None,
    )
    assert [call for call in calls if call[0] == "hours"] == [("hours", str(TENANT), str(USER), [str(OWN_FACILITY)])]


def test_drilldown_lists_late_records(monkeypatch, calls):
    session = FakeSession(own_hours=AGREED_HOURS)
    resp = _client(monkeypatch, calls, session=session).get(
        f"/v1/supplier/data-quality/{OWN_FACILITY}/records?metric=late_cte"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == len(RECORD_ROWS)
    assert [item["record_id"] for item in body["items"]] == [row["record_id"] for row in RECORD_ROWS]
    assert all(item["received_at"] and item["event_time"] for item in body["items"])
    assert calls == [("records", str(TENANT), str(USER), [str(OWN_FACILITY)])]


def test_drilldown_late_cte_without_agreed_hours_is_refused(monkeypatch, calls):
    resp = _client(monkeypatch, calls).get(f"/v1/supplier/data-quality/{OWN_FACILITY}/records?metric=late_cte")
    assert resp.status_code == 409
    assert calls == []


@pytest.mark.parametrize("facility", [FOREIGN_FACILITY, OTHER_TENANT_FACILITY])
def test_drilldown_late_cte_refuses_facility_not_owned(monkeypatch, calls, facility):
    resp = _client(monkeypatch, calls).get(f"/v1/supplier/data-quality/{facility}/records?metric=late_cte")
    assert resp.status_code == 404
    assert calls == []


def test_drilldown_rejects_unavailable_metrics(monkeypatch, calls):
    for metric in ("epcis_failed", "anything"):
        resp = _client(monkeypatch, calls).get(f"/v1/supplier/data-quality/{OWN_FACILITY}/records?metric={metric}")
        assert resp.status_code == 422
    assert calls == []


def test_drilldown_rejects_bad_facility_id_and_limit(monkeypatch, calls):
    client = _client(monkeypatch, calls)
    assert client.get("/v1/supplier/data-quality/not-a-uuid/records?metric=missing_kde").status_code == 400
    assert (
        client.get(f"/v1/supplier/data-quality/{OWN_FACILITY}/records?metric=missing_kde&limit=201").status_code == 422
    )
    assert calls == []


# --- agreed sending hours ------------------------------------------------------


def _hours_url(facility) -> str:
    return f"/v1/supplier/facilities/{facility}/agreed-sending-hours"


def test_owner_sets_agreed_sending_hours(monkeypatch, calls):
    session = FakeSession()
    resp = _client(monkeypatch, calls, session=session).put(
        _hours_url(OWN_FACILITY), json={"agreed_sending_hours": AGREED_HOURS}
    )
    assert resp.status_code == 200
    assert resp.json() == {"facility_id": str(OWN_FACILITY), "agreed_sending_hours": AGREED_HOURS}
    assert session.facilities[OWN_FACILITY].agreed_sending_hours == AGREED_HOURS
    assert session.commits == len([resp])


def test_owner_clears_agreed_sending_hours_with_null(monkeypatch, calls):
    session = FakeSession(own_hours=AGREED_HOURS)
    resp = _client(monkeypatch, calls, session=session).put(
        _hours_url(OWN_FACILITY), json={"agreed_sending_hours": None}
    )
    assert resp.status_code == 200
    assert resp.json()["agreed_sending_hours"] is None
    assert session.facilities[OWN_FACILITY].agreed_sending_hours is None


@pytest.mark.parametrize("facility", [FOREIGN_FACILITY, OTHER_TENANT_FACILITY])
def test_agreed_sending_hours_refuses_facility_not_owned_in_tenant(monkeypatch, calls, facility):
    session = FakeSession()
    resp = _client(monkeypatch, calls, session=session).put(
        _hours_url(facility), json={"agreed_sending_hours": AGREED_HOURS}
    )
    assert resp.status_code == 404
    assert session.facilities[facility].agreed_sending_hours is None
    assert session.commits == 0


@pytest.mark.parametrize(
    "body",
    [
        {"agreed_sending_hours": 0},
        {"agreed_sending_hours": -AGREED_HOURS},
        {"agreed_sending_hours": str(AGREED_HOURS)},
        {"agreed_sending_hours": AGREED_HOURS + 0.5},
        {"agreed_sending_hours": float(AGREED_HOURS)},
        {"agreed_sending_hours": True},
        # One past the Postgres integer maximum.
        {"agreed_sending_hours": 2**31},
        {},
    ],
)
def test_agreed_sending_hours_must_be_positive_int_or_null(monkeypatch, calls, body):
    session = FakeSession()
    resp = _client(monkeypatch, calls, session=session).put(_hours_url(OWN_FACILITY), json=body)
    assert resp.status_code == 422
    assert session.facilities[OWN_FACILITY].agreed_sending_hours is None
    assert session.commits == 0


def test_agreed_sending_hours_rejects_bad_id_and_missing_tenant(monkeypatch, calls):
    body = {"agreed_sending_hours": AGREED_HOURS}
    assert _client(monkeypatch, calls).put(_hours_url("not-a-uuid"), json=body).status_code == 400
    assert _client(monkeypatch, calls, tenant=None).put(_hours_url(OWN_FACILITY), json=body).status_code == 400
