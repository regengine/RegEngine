"""Supplier data quality routes: scoping and guards, no database.

A fake session answers the facility ownership lookups; the SQL fetchers are
stubbed so the tests check what the routes pass and return, not SQL.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

TENANT = uuid4()
OTHER_TENANT = uuid4()
USER = uuid4()
OTHER_USER = uuid4()
OWN_FACILITY = uuid4()
FOREIGN_FACILITY = uuid4()
OTHER_TENANT_FACILITY = uuid4()

# Two shipping records with no KDEs on the owned facility, and one lot with no
# upstream link. Ids and lot codes are generated per run.
RECORD_ROWS = [
    {
        "record_id": str(uuid4()),
        "facility_id": str(OWN_FACILITY),
        "cte_type": "shipping",
        "kde_data": {},
        "event_time": None,
        "created_at": None,
        "lot_code": str(uuid4()),
    }
    for _ in range(2)
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


class FakeSession:
    def __init__(self) -> None:
        self.facilities = {
            OWN_FACILITY: SimpleNamespace(id=OWN_FACILITY, tenant_id=TENANT, supplier_user_id=USER),
            FOREIGN_FACILITY: SimpleNamespace(id=FOREIGN_FACILITY, tenant_id=TENANT, supplier_user_id=OTHER_USER),
            OTHER_TENANT_FACILITY: SimpleNamespace(
                id=OTHER_TENANT_FACILITY, tenant_id=OTHER_TENANT, supplier_user_id=USER
            ),
        }

    def get(self, _model, key):
        return self.facilities.get(key)

    def scalars(self, _stmt):
        # The route filters by tenant and user in SQL; the fake returns what that
        # filter yields for TENANT and USER.
        return SimpleNamespace(all=lambda: [OWN_FACILITY])


@pytest.fixture
def calls():
    return []


def _client(monkeypatch, calls, tenant=TENANT):
    import app.supplier_compliance_routes as routes

    def fake_records(_db, tenant_id, user_id, facility_ids, since):
        calls.append(("records", tenant_id, user_id, list(facility_ids)))
        return [dict(row) for row in RECORD_ROWS]

    def fake_lots(_db, tenant_id, user_id, facility_ids, since):
        calls.append(("lots", tenant_id, user_id, list(facility_ids)))
        return [dict(row) for row in LOT_ROWS]

    monkeypatch.setattr(routes, "fetch_record_rows", fake_records)
    monkeypatch.setattr(routes, "fetch_lot_rows", fake_lots)
    monkeypatch.setattr("shared.supplier_data_quality.fetch_record_rows", fake_records)
    monkeypatch.setattr("shared.supplier_data_quality.fetch_lot_rows", fake_lots)
    monkeypatch.setattr(routes.TenantContext, "get_tenant_context", lambda _db: tenant)

    app = FastAPI()
    app.include_router(routes.router, prefix="/v1")
    session = FakeSession()
    app.dependency_overrides[routes.get_session] = lambda: session
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(id=USER)
    return TestClient(app)


def test_summary_returns_four_separate_metrics_for_owned_facilities(monkeypatch, calls):
    resp = _client(monkeypatch, calls).get("/v1/supplier/data-quality")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 30
    assert body["min_records"] == 20
    assert body["late_cte_label"] == (
        "Our measure, based on the agreed sending time with this supplier; not a regulatory requirement"
    )
    [supplier] = body["suppliers"]
    assert supplier["supplier_key"] == str(OWN_FACILITY)
    assert [m["key"] for m in supplier["metrics"]] == ["missing_kde", "unlinked_lot", "late_cte", "epcis_failed"]
    missing = supplier["metrics"][0]
    assert (missing["status"], missing["numerator"], missing["denominator"]) == (
        "not_enough_data",
        len(RECORD_ROWS),
        len(RECORD_ROWS),
    )
    assert supplier["metrics"][2]["status"] == "unavailable"
    assert supplier["metrics"][3]["status"] == "unavailable"
    assert all(call[1:3] == (str(TENANT), str(USER)) for call in calls)
    assert all(call[3] == [str(OWN_FACILITY)] for call in calls)


@pytest.mark.parametrize("window", [0, 366, -1])
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


def test_drilldown_rejects_unavailable_metrics(monkeypatch, calls):
    for metric in ("late_cte", "epcis_failed", "anything"):
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
