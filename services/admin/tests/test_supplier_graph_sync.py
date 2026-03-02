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


class _FakeDriver:
    def __init__(self):
        self.calls = []

    def session(self):
        return _FakeSession(self.calls)


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
