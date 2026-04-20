"""Coverage sweep for ``app.supplier_graph_sync`` to take the module from 91% to 100%.

The existing tests under ``tests/test_supplier_graph_sync.py`` and
``tests/test_supplier_graph_sync_tenant_scoping.py`` exercise the happy paths
for every public writer, but leave four narrow branches uncovered. This module
fills them in so the coverage gate can be tightened without regressing on any
production behavior.

Covered branches:

* ``_to_utc_iso`` naive-datetime branch (line 140) — when a caller passes a
  ``datetime`` without ``tzinfo`` we stamp it as UTC rather than reinterpret it
  via ``astimezone``. Existing tests only pass tz-aware datetimes.
* ``SupplierGraphSync.from_env`` success branch (lines 162-164) — when
  ``NEO4J_URI`` and ``NEO4J_PASSWORD`` are both set, ``GraphDatabase.driver``
  is invoked and a connected ``SupplierGraphSync`` is returned.
* ``_query_required_ctes`` disabled-driver short-circuit (line 191) — the
  public ``get_required_ctes_for_facility`` must return ``None`` without
  touching Neo4j when the sync is disabled.
* ``_query_required_ctes`` empty-record branch (line 208) — when the Neo4j
  query returns no record, we return an empty-categories payload rather than
  ``None`` so callers can distinguish "facility exists but has no FTL mapping"
  from "sync disabled".

Tracks GitHub issue #1342.
"""

from datetime import datetime, timezone

from app import supplier_graph_sync as module
from app.supplier_graph_sync import SupplierGraphSync, _to_utc_iso


class _FakeResult:
    def __init__(self, record=None):
        self._record = record

    def single(self):
        return self._record


class _FakeSession:
    def __init__(self, record=None):
        self._record = record

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, params):
        return _FakeResult(self._record)


class _FakeDriver:
    def __init__(self, record=None):
        self._record = record

    def session(self):
        return _FakeSession(self._record)


def test_to_utc_iso_stamps_utc_on_naive_datetime():
    """Covers line 140: naive datetimes are treated as UTC, not reinterpreted."""
    naive = datetime(2026, 4, 20, 15, 30, 0)
    assert naive.tzinfo is None

    result = _to_utc_iso(naive)

    # 15:30 naive -> 15:30+00:00 (no timezone shift); existing tests only pass
    # tz-aware values which hit the else-branch on line 142.
    assert result == "2026-04-20T15:30:00+00:00"


def test_to_utc_iso_converts_non_utc_aware_datetime():
    """Regression companion: the else-branch converts non-UTC tz-aware datetimes."""
    from datetime import timedelta

    aware_non_utc = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone(timedelta(hours=5)))

    result = _to_utc_iso(aware_non_utc)

    # 10:00+05:00 -> 05:00+00:00
    assert result == "2026-04-20T05:00:00+00:00"


def test_from_env_returns_connected_instance_when_env_complete(monkeypatch):
    """Covers lines 162-164: the try-block constructs a real driver and returns enabled=True."""
    monkeypatch.setenv("NEO4J_URI", "bolt://fake-host:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "s3cret")
    monkeypatch.setenv("NEO4J_USER", "neo4j")

    captured: dict = {}
    sentinel_driver = object()

    class _FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            captured["uri"] = uri
            captured["auth"] = auth
            return sentinel_driver

    monkeypatch.setattr(module, "GraphDatabase", _FakeGraphDatabase)

    sync = SupplierGraphSync.from_env()

    assert sync.enabled is True
    assert sync._driver is sentinel_driver
    assert captured["uri"] == "bolt://fake-host:7687"
    assert captured["auth"] == ("neo4j", "s3cret")


def test_from_env_falls_back_to_neo4j_url_when_uri_unset(monkeypatch):
    """Companion for the env-reading fallback used alongside the success branch."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("NEO4J_URL", "bolt://alt-host:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "s3cret")

    captured: dict = {}

    class _FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            captured["uri"] = uri
            return object()

    monkeypatch.setattr(module, "GraphDatabase", _FakeGraphDatabase)

    sync = SupplierGraphSync.from_env()

    assert sync.enabled is True
    assert captured["uri"] == "bolt://alt-host:7687"


def test_get_required_ctes_for_facility_returns_none_when_disabled():
    """Covers line 191: disabled/no-driver short-circuits before touching Neo4j."""
    sync = SupplierGraphSync(enabled=False, driver=None)

    result = sync.get_required_ctes_for_facility("facility-1", "tenant-1")

    assert result is None


def test_get_required_ctes_for_facility_returns_none_when_driver_missing():
    """Defense-in-depth: enabled=True but driver=None must still return None."""
    sync = SupplierGraphSync(enabled=True, driver=None)

    result = sync.get_required_ctes_for_facility("facility-1", "tenant-1")

    assert result is None


def test_get_required_ctes_for_facility_returns_empty_payload_when_no_record():
    """Covers line 208: a ``None`` record yields an empty-categories payload."""
    sync = SupplierGraphSync(enabled=True, driver=_FakeDriver(record=None))

    result = sync.get_required_ctes_for_facility("facility-missing", "tenant-1")

    assert result == {
        "source": "neo4j",
        "categories": [],
        "required_ctes": [],
    }


# Tracks GitHub issue #1342.
