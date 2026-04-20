"""Tests for Neo4j driver hot-reload and circuit-breaker wiring in
``supplier_graph_sync`` (issue #1410).

These tests cover the two defects called out in #1410:

* **Hot-reload.** The driver was built once at import time from env vars
  captured at that moment; a rotated ``NEO4J_PASSWORD`` was never picked up
  until the admin pod restarted.
* **Unbounded failure hammer.** Neo4j exceptions were silently swallowed
  inside a broad ``except``, so a down Neo4j was pounded with
  connection-refused errors from every admin request.

After the fix:

* Each call to a Neo4j-touching method goes through ``_get_driver``, which
  re-reads ``shared.secrets_manager.get_neo4j_credentials()`` and rebuilds
  the driver when any of (uri, user, password) changed.
* Driver calls participate in ``shared.circuit_breaker.neo4j_circuit``:
  failures are recorded on the breaker before being swallowed, and an open
  circuit short-circuits further calls instead of hammering Neo4j.

These tests exercise the new getter and breaker plumbing end-to-end with a
fake driver; there is no real Neo4j involved.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import supplier_graph_sync as sgs_module
from app.supplier_graph_sync import SupplierGraphSync
from shared.circuit_breaker import CircuitOpenError, neo4j_circuit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, record=None):
        self._record = record

    def single(self):
        return self._record


class _RecordingSession:
    def __init__(self, sink, *, record=None, raise_on_run=None):
        self._sink = sink
        self._record = record
        self._raise_on_run = raise_on_run

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, params):
        if self._raise_on_run is not None:
            raise self._raise_on_run
        self._sink.append((query, params))
        return _FakeResult(self._record)


class _RecordingDriver:
    """Fake driver that records ``session().run()`` calls and is closable."""

    def __init__(self, *, record=None, raise_on_run=None):
        self.calls: list[tuple[str, dict]] = []
        self.closed = False
        self._record = record
        self._raise_on_run = raise_on_run

    def session(self):
        return _RecordingSession(
            self.calls, record=self._record, raise_on_run=self._raise_on_run
        )

    def close(self):
        self.closed = True


class _FakeGraphDatabase:
    """Stand-in for neo4j.GraphDatabase.

    ``driver(uri, auth=...)`` returns a fresh ``_RecordingDriver`` each call,
    letting the test observe driver rebuilds.
    """

    def __init__(self):
        self.drivers: list[_RecordingDriver] = []
        self.calls: list[tuple[str, tuple[str, str]]] = []

    def driver(self, uri, auth):
        self.calls.append((uri, auth))
        d = _RecordingDriver()
        self.drivers.append(d)
        return d


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_neo4j_circuit():
    """Keep circuit state hermetic across tests."""
    neo4j_circuit.reset()
    yield
    neo4j_circuit.reset()


@pytest.fixture
def fake_neo4j(monkeypatch):
    """Patch ``GraphDatabase`` with a recording fake."""
    fake = _FakeGraphDatabase()
    monkeypatch.setattr(sgs_module, "GraphDatabase", fake)
    return fake


@pytest.fixture
def creds_source(monkeypatch):
    """Mutable credentials source routed through ``get_secrets_manager``.

    Returns a dict the test can mutate; each call into
    ``get_neo4j_credentials()`` returns the current contents.
    """
    creds = {"uri": "bolt://neo4j:7687", "username": "neo4j", "password": "v1"}

    class _FakeSecretsManager:
        def get_neo4j_credentials(self, environment=None):
            # Return a fresh dict each call so mutation of the test-owned
            # mapping is picked up but external mutation of the returned
            # copy is harmless.
            return dict(creds)

    monkeypatch.setattr(
        sgs_module,
        "get_secrets_manager",
        lambda: _FakeSecretsManager(),
    )
    return creds


# ---------------------------------------------------------------------------
# Hot-reload: driver is rebuilt when credentials change
# ---------------------------------------------------------------------------


def test_driver_is_built_lazily_on_first_use(fake_neo4j, creds_source):
    """Constructing an enabled sync does NOT immediately call GraphDatabase.driver."""
    sync = SupplierGraphSync(enabled=True, driver=None)

    assert fake_neo4j.calls == [], "driver should not be built at construction"

    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )

    # Exactly one driver built, using the current credentials.
    assert len(fake_neo4j.calls) == 1
    uri, auth = fake_neo4j.calls[0]
    assert uri == "bolt://neo4j:7687"
    assert auth == ("neo4j", "v1")


def test_driver_is_rebuilt_when_password_rotates(fake_neo4j, creds_source):
    """Core #1410 scenario: password rotation is picked up without restart."""
    sync = SupplierGraphSync(enabled=True, driver=None)

    # First call: driver built with v1.
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    assert len(fake_neo4j.drivers) == 1
    first_driver = fake_neo4j.drivers[0]
    assert first_driver.closed is False

    # Rotate the password — this simulates a live credential rotation.
    creds_source["password"] = "v2"

    # Next call: driver MUST be rebuilt with v2, old driver closed.
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-2",
        email="s2@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 13, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    assert len(fake_neo4j.drivers) == 2, "driver was not rebuilt after rotation"
    assert first_driver.closed is True, "stale driver was not closed"
    assert fake_neo4j.calls[1][1] == ("neo4j", "v2"), "new driver uses old password"


def test_driver_is_reused_when_credentials_unchanged(fake_neo4j, creds_source):
    """Second call with identical creds must reuse the driver, not rebuild."""
    sync = SupplierGraphSync(enabled=True, driver=None)

    for i in range(3):
        sync.record_invite_created(
            tenant_id="tenant-A",
            invite_id=f"invite-{i}",
            email="s@example.com",
            role_id="role-1",
            expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
            created_by="user-1",
        )

    # One driver built, three writes against it.
    assert len(fake_neo4j.drivers) == 1
    assert len(fake_neo4j.drivers[0].calls) == 3


def test_driver_rebuilds_when_uri_changes(fake_neo4j, creds_source):
    """URI rotation (e.g. failover to a replica) must also rebuild."""
    sync = SupplierGraphSync(enabled=True, driver=None)
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    creds_source["uri"] = "bolt://neo4j-failover:7687"

    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-2",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 13, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    assert len(fake_neo4j.drivers) == 2
    assert fake_neo4j.calls[1][0] == "bolt://neo4j-failover:7687"


def test_pinned_driver_is_never_rebuilt(fake_neo4j, creds_source):
    """A driver passed explicitly to the constructor must not be rebuilt.

    Tests (and callers with a pre-built driver) rely on this — otherwise
    the injected fake would be swapped for a credentials-built
    ``GraphDatabase.driver`` on first use.
    """
    injected = _RecordingDriver()
    sync = SupplierGraphSync(enabled=True, driver=injected)

    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    creds_source["password"] = "v2"
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-2",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 13, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )

    assert fake_neo4j.calls == []  # GraphDatabase.driver never called
    assert len(injected.calls) == 2  # both writes landed on injected driver


def test_current_driver_accessor_returns_hot_reloaded_driver(fake_neo4j, creds_source):
    """``current_driver()`` is the public hot-reloaded accessor used by
    ``scripts/drain_graph_outbox.py`` — it must return the current driver
    and trigger a rebuild on rotation."""
    sync = SupplierGraphSync(enabled=True, driver=None)

    d1 = sync.current_driver()
    assert d1 is fake_neo4j.drivers[0]

    creds_source["password"] = "rotated"
    d2 = sync.current_driver()

    assert d2 is fake_neo4j.drivers[1]
    assert d2 is not d1
    assert d1.closed is True


def test_current_driver_returns_none_when_disabled(fake_neo4j):
    sync = SupplierGraphSync(enabled=False)
    assert sync.current_driver() is None


# ---------------------------------------------------------------------------
# Circuit breaker: Neo4j failures trip the shared neo4j_circuit
# ---------------------------------------------------------------------------


class _AlwaysFailingDriver:
    def __init__(self):
        self.session_calls = 0

    def session(self):
        self.session_calls += 1
        raise ConnectionError("neo4j unreachable")

    def close(self):
        pass


def test_breaker_opens_after_threshold_failures_and_short_circuits():
    """After ``neo4j_circuit.failure_threshold`` failures the breaker opens
    and subsequent calls must short-circuit — i.e. not attempt a new
    ``driver.session()`` at all — so a down Neo4j isn't hammered.
    """
    driver = _AlwaysFailingDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)

    threshold = neo4j_circuit.failure_threshold
    for i in range(threshold):
        sync.record_invite_created(
            tenant_id="tenant-A",
            invite_id=f"invite-{i}",
            email="s@example.com",
            role_id="role-1",
            expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
            created_by="user-1",
        )
    # All ``threshold`` attempts landed on the driver (the breaker opens on
    # the ``threshold``-th failure, not before).
    assert driver.session_calls == threshold
    assert neo4j_circuit.state.value == "OPEN"

    # Next calls should short-circuit: no new driver.session() invocations.
    for i in range(3):
        sync.record_invite_created(
            tenant_id="tenant-A",
            invite_id=f"invite-after-open-{i}",
            email="s@example.com",
            role_id="role-1",
            expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
            created_by="user-1",
        )
    assert driver.session_calls == threshold, (
        "breaker did not short-circuit: admin is still hammering a down Neo4j"
    )


def test_breaker_short_circuits_reads_too():
    """Read path (``get_required_ctes_for_facility``) must also honor the
    circuit breaker — otherwise a down Neo4j still gets hammered by reads."""
    driver = _AlwaysFailingDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)

    threshold = neo4j_circuit.failure_threshold
    for _ in range(threshold):
        result = sync.get_required_ctes_for_facility("facility-1", "tenant-A")
        assert result is None, "failing reads must return None (best-effort)"

    assert neo4j_circuit.state.value == "OPEN"
    before = driver.session_calls

    for _ in range(3):
        assert sync.get_required_ctes_for_facility("facility-1", "tenant-A") is None
    assert driver.session_calls == before, "read path ignored open circuit"


def test_breaker_records_failure_but_caller_never_sees_exception():
    """Regression against silent swallow: the breaker MUST see the failure,
    but the caller MUST NOT — best-effort contract is preserved."""
    driver = _AlwaysFailingDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)

    # One failure — does not raise, breaker still closed (threshold=5 by default).
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    metrics = neo4j_circuit.get_metrics()
    assert metrics["failure_count"] == 1
    assert metrics["state"] == "CLOSED"


# ---------------------------------------------------------------------------
# Happy paths remain green
# ---------------------------------------------------------------------------


def test_happy_path_write_with_breaker_wired(fake_neo4j, creds_source):
    """Successful writes record success on the breaker and leave it CLOSED."""
    sync = SupplierGraphSync(enabled=True, driver=None)

    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )

    driver = fake_neo4j.drivers[0]
    assert len(driver.calls) == 1
    assert neo4j_circuit.state.value == "CLOSED"


def test_happy_path_read_with_breaker_wired():
    """Successful reads return the flattened CTE payload."""
    record = {
        "categories": [
            {"id": "2", "name": "Vegetables", "ctes": ["harvesting", "shipping"]},
        ]
    }
    # Pinned driver variant — avoids credentials stubbing.
    class _QueryDriver:
        def session(self_inner):  # noqa: N805
            return _RecordingSession([], record=record)

        def close(self_inner):  # noqa: N805
            pass

    sync = SupplierGraphSync(enabled=True, driver=_QueryDriver())
    result = sync.get_required_ctes_for_facility("facility-1", "tenant-A")

    assert result is not None
    assert result["source"] == "neo4j"
    assert result["required_ctes"] == ["harvesting", "shipping"]
    assert neo4j_circuit.state.value == "CLOSED"


def test_bulk_upload_style_fire_and_forget_still_succeeds(fake_neo4j, creds_source):
    """``bulk_upload/transaction_manager.py`` wraps each call in its own
    ``try/except`` for fire-and-forget semantics. Validate that path by
    calling a sequence of writes through the module-level instance with
    the breaker CLOSED — every call must succeed and none may raise.
    """
    sync = SupplierGraphSync(enabled=True, driver=None)

    for i in range(4):
        # Each record_* call is exactly what bulk_upload invokes.
        sync.record_facility_ftl_scoping(
            tenant_id="tenant-A",
            facility_id=f"facility-{i}",
            facility_name="Packhouse",
            supplier_user_id="user-1",
            supplier_email="s@example.com",
            street="1 Main",
            city="Salinas",
            state="CA",
            postal_code="93901",
            fda_registration_number="12345678901",
            roles=["Grower"],
            categories=[
                {"id": "2", "name": "Vegetables", "ctes": ["harvesting"]},
            ],
        )

    assert neo4j_circuit.state.value == "CLOSED"
    assert len(fake_neo4j.drivers[0].calls) == 4


def test_bulk_upload_style_caller_broad_catch_is_preserved(fake_neo4j, creds_source):
    """When the inner driver fails, ``_run`` must return normally (not
    raise) so ``bulk_upload``'s ``try/except`` around a sync call still
    lands on the warning path. The raw exception must still reach the
    breaker first (asserted via failure_count).
    """
    class _FailingDriver:
        def __init__(self):
            self.closed = False

        def session(self_inner):  # noqa: N805
            raise ConnectionError("boom")

        def close(self_inner):  # noqa: N805
            self_inner.closed = True

    sync = SupplierGraphSync(enabled=True, driver=_FailingDriver())

    # Must not raise — fire-and-forget contract.
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )

    # But the breaker saw the failure.
    assert neo4j_circuit.get_metrics()["failure_count"] == 1


# ---------------------------------------------------------------------------
# Defensive: credentials disappearing mid-flight does not crash
# ---------------------------------------------------------------------------


def test_credentials_go_missing_mid_flight_noops(fake_neo4j, creds_source):
    """If the password is unset after the first call, subsequent calls
    must no-op rather than crash. The old driver is closed."""
    sync = SupplierGraphSync(enabled=True, driver=None)
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    first_driver = fake_neo4j.drivers[0]

    creds_source["password"] = ""  # rotation blanked the secret

    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-2",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 13, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )

    # No new driver built; old driver closed.
    assert len(fake_neo4j.drivers) == 1
    assert first_driver.closed is True


# ---------------------------------------------------------------------------
# Circuit-open directly on a public call does not bubble
# ---------------------------------------------------------------------------


def test_circuit_already_open_does_not_raise_from_public_api():
    """If another caller already tripped the breaker, ``record_*`` must
    still return cleanly (not raise CircuitOpenError)."""
    # Trip the breaker manually.
    for _ in range(neo4j_circuit.failure_threshold):
        neo4j_circuit._record_failure(RuntimeError("seed failure"))
    assert neo4j_circuit.state.value == "OPEN"

    driver = _RecordingDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)

    # Must not raise.
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    assert len(driver.calls) == 0  # short-circuited, no session attempt


def test_circuit_open_error_is_subclass_sentinel_assert():
    """Smoke: CircuitOpenError is importable and is an Exception subclass."""
    assert issubclass(CircuitOpenError, Exception)
