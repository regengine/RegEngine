from datetime import datetime, timezone

from app.supplier_graph_sync import SupplierGraphSync


class _FakeSession:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, params):
        self._sink.append((query, params))
        return _FakeResult()


class _FakeResult:
    def __init__(self, record=None):
        self._record = record

    def single(self):
        return self._record


class _FakeDriver:
    def __init__(self):
        self.calls = []

    def session(self):
        return _FakeSession(self.calls)


class _FakeQuerySession:
    def __init__(self, record):
        self._record = record

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, params):
        return _FakeResult(self._record)


class _FakeQueryDriver:
    def __init__(self, record):
        self._record = record

    def session(self):
        return _FakeQuerySession(self._record)


def test_from_env_disabled_when_required_neo4j_env_missing(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_URL", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    sync = SupplierGraphSync.from_env()
    assert sync.enabled is False


def test_record_invite_created_writes_expected_query_payload():
    driver = _FakeDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)

    sync.record_invite_created(
        tenant_id="tenant-1",
        invite_id="invite-1",
        email="supplier@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )

    assert len(driver.calls) == 1
    query, params = driver.calls[0]
    assert "PendingSupplierInvite" in query
    assert params["operation"] == "invite_created"
    assert params["tenant_id"] == "tenant-1"
    assert params["invite_id"] == "invite-1"


def test_record_invite_accepted_writes_expected_query_payload():
    driver = _FakeDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)

    sync.record_invite_accepted(
        tenant_id="tenant-1",
        invite_id="invite-1",
        user_id="user-1",
        email="supplier@example.com",
        role_id="role-1",
        accepted_at=datetime(2026, 3, 2, 13, 0, tzinfo=timezone.utc),
    )

    assert len(driver.calls) == 1
    query, params = driver.calls[0]
    assert "SupplierContact" in query
    assert params["operation"] == "invite_accepted"
    assert params["user_id"] == "user-1"


def test_noop_when_sync_disabled():
    sync = SupplierGraphSync(enabled=False, driver=None)

    sync.record_invite_created(
        tenant_id="tenant-1",
        invite_id="invite-1",
        email="supplier@example.com",
        role_id="role-1",
        expires_at=datetime.now(timezone.utc),
        created_by="user-1",
    )

    sync.record_invite_accepted(
        tenant_id="tenant-1",
        invite_id="invite-1",
        user_id="user-1",
        email="supplier@example.com",
        role_id="role-1",
        accepted_at=datetime.now(timezone.utc),
    )


def test_record_facility_ftl_scoping_writes_expected_payload():
    driver = _FakeDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)

    sync.record_facility_ftl_scoping(
        tenant_id="tenant-1",
        facility_id="facility-1",
        facility_name="Salinas Packhouse",
        supplier_user_id="user-1",
        supplier_email="supplier@example.com",
        street="1200 Abbott St",
        city="Salinas",
        state="CA",
        postal_code="93901",
        fda_registration_number="12345678901",
        roles=["Grower", "Packer"],
        categories=[
            {"id": "2", "name": "Vegetables (leafy greens)", "ctes": ["harvesting", "shipping"]},
        ],
    )

    assert len(driver.calls) == 1
    query, params = driver.calls[0]
    assert "SupplierFacility" in query
    assert params["operation"] == "facility_ftl_scoping"
    assert params["facility_id"] == "facility-1"
    assert params["categories"][0]["id"] == "2"


def test_get_required_ctes_for_facility_flattens_distinct_values():
    record = {
        "categories": [
            {"id": "2", "name": "Vegetables", "ctes": ["harvesting", "shipping"]},
            {"id": "5", "name": "Fresh herbs", "ctes": ["shipping", "receiving"]},
        ]
    }
    sync = SupplierGraphSync(enabled=True, driver=_FakeQueryDriver(record))

    result = sync.get_required_ctes_for_facility("facility-1", "tenant-1")

    assert result is not None
    assert result["source"] == "neo4j"
    assert len(result["categories"]) == 2
    assert result["required_ctes"] == ["harvesting", "shipping", "receiving"]


def test_record_cte_event_writes_expected_payload():
    driver = _FakeDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)

    sync.record_cte_event(
        tenant_id="tenant-1",
        facility_id="facility-1",
        facility_name="Salinas Packhouse",
        cte_event_id="event-1",
        cte_type="shipping",
        event_time="2026-03-02T12:00:00+00:00",
        tlc_code="TLC-2026-SAL-0001",
        product_description="Baby Spinach",
        lot_status="active",
        kde_data={"quantity": 120, "unit_of_measure": "cases"},
        payload_sha256="payload-hash",
        merkle_prev_hash="prev-hash",
        merkle_hash="merkle-hash",
        sequence_number=2,
        obligation_ids=["21cfr_subpart_s_123", "21cfr_subpart_s_456"],
    )

    assert len(driver.calls) == 1
    query, params = driver.calls[0]
    assert "CTEEvent" in query
    assert params["operation"] == "cte_event_recorded"
    assert params["cte_event_id"] == "event-1"
    assert params["merkle_hash"] == "merkle-hash"
    assert params["obligation_ids"] == ["21cfr_subpart_s_123", "21cfr_subpart_s_456"]
