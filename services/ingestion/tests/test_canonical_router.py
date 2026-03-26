"""Tests for canonical records router endpoints."""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.authz import IngestionPrincipal, get_ingestion_principal
from app.canonical_router import _get_db_session, router as canonical_router

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENANT_ID = "00000000-0000-0000-0000-000000000111"
OTHER_TENANT_ID = "00000000-0000-0000-0000-000000000222"
EVENT_ID = "evt-abc-001"
RUN_ID = "run-abc-001"
NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Fake DB helpers
# ---------------------------------------------------------------------------


class _Row(tuple):
    """Tuple subclass that behaves like a SQLAlchemy row."""
    pass


class _Result:
    """Mimics the object returned by session.execute()."""

    def __init__(self, *, row: Any = None, rows: Optional[List[Any]] = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


def _make_event_row(
    event_id: str = EVENT_ID,
    event_type: str = "shipping",
    tlc: str = "TLC-2026-001",
    product_ref: str = "PROD-001",
    quantity: float = 100.0,
    uom: str = "cases",
    from_facility: str = "FAC-A",
    to_facility: str = "FAC-B",
    ts: datetime = NOW,
    source_system: str = "webhook",
    status: str = "active",
    confidence: float = 0.98,
    schema_version: str = "1.0",
    created_at: datetime = NOW,
) -> _Row:
    return _Row((
        event_id, event_type, tlc, product_ref, quantity, uom,
        from_facility, to_facility, ts, source_system, status,
        confidence, schema_version, created_at,
    ))


def _make_run_row(
    run_id: str = RUN_ID,
    source_system: str = "webhook",
    file_name: str = "upload.csv",
    record_count: int = 50,
    accepted: int = 48,
    rejected: int = 2,
    status: str = "completed",
    mapper_version: str = "2.1",
    initiated_by: str = "api",
    started_at: datetime = NOW,
    completed_at: datetime = NOW,
) -> _Row:
    return _Row((
        run_id, source_system, file_name, record_count,
        accepted, rejected, status, mapper_version,
        initiated_by, started_at, completed_at,
    ))


def _make_run_detail_row(
    run_id: str = RUN_ID,
    source_system: str = "webhook",
    file_name: str = "upload.csv",
    file_hash: str = "abc123",
    file_size: int = 4096,
    record_count: int = 50,
    accepted: int = 48,
    rejected: int = 2,
    status: str = "completed",
    mapper_version: str = "2.1",
    schema_version: str = "1.0",
    initiated_by: str = "api",
    started_at: datetime = NOW,
    completed_at: datetime = NOW,
    errors: str = "[]",
) -> _Row:
    return _Row((
        run_id, source_system, file_name, file_hash, file_size,
        record_count, accepted, rejected, status, mapper_version,
        schema_version, initiated_by, started_at, completed_at, errors,
    ))


def _make_eval_row(
    result: str = "fail",
    why_failed: str = "Missing TLC",
    title: str = "TLC Required",
    severity: str = "critical",
    citation: str = "21 CFR 1.1315",
    remediation: str = "Add traceability lot code",
    category: str = "data_quality",
) -> _Row:
    return _Row((result, why_failed, title, severity, citation, remediation, category))


def _make_exception_row(
    case_id: str = "case-001",
    severity: str = "high",
    status: str = "open",
    remediation: str = "Review record",
    owner: str = "user-1",
    due_date: datetime = NOW,
) -> _Row:
    return _Row((case_id, severity, status, remediation, owner, due_date))


class _FakeSession:
    """Programmable fake database session.

    Accepts an ordered list of _Result objects. Each call to execute()
    pops the next result from the list.
    """

    def __init__(self, results: Optional[List[_Result]] = None):
        self._results = list(results or [])
        self._call_index = 0

    def execute(self, *_args, **_kwargs):
        if self._call_index < len(self._results):
            r = self._results[self._call_index]
            self._call_index += 1
            return r
        return _Result()

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fake CanonicalEventStore for get_record endpoint
# ---------------------------------------------------------------------------


class _FakeEventStore:
    def __init__(self, session, dual_write=False):
        self._session = session
        # Store events keyed by (tenant, event_id)
        self._events: Dict[tuple, dict] = {}

    def get_event(self, tenant_id: str, event_id: str) -> Optional[dict]:
        return self._events.get((tenant_id, event_id))


# Global reference so tests can inject data
_fake_store_instance: Optional[_FakeEventStore] = None


def _fake_event_store_factory(session, dual_write=False):
    global _fake_store_instance
    _fake_store_instance = _FakeEventStore(session, dual_write)
    return _fake_store_instance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app_and_client(
    principal: IngestionPrincipal,
    db_session: _FakeSession,
) -> TestClient:
    app = FastAPI()
    app.include_router(canonical_router)

    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    app.dependency_overrides[_get_db_session] = lambda: db_session

    return TestClient(app)


@pytest.fixture()
def principal() -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        tenant_id=TENANT_ID,
        auth_mode="test",
    )


@pytest.fixture()
def list_session() -> _FakeSession:
    """Session pre-loaded for list_records: count then rows."""
    return _FakeSession([
        _Result(row=(3,)),  # COUNT(*)
        _Result(rows=[
            _make_event_row(event_id="evt-1"),
            _make_event_row(event_id="evt-2"),
            _make_event_row(event_id="evt-3"),
        ]),
    ])


@pytest.fixture()
def client(principal: IngestionPrincipal, list_session: _FakeSession) -> TestClient:
    return _make_app_and_client(principal, list_session)


# ---------------------------------------------------------------------------
# list_records  (GET /api/v1/records)
# ---------------------------------------------------------------------------


class TestListRecords:
    def test_returns_events_with_total(self, client: TestClient) -> None:
        resp = client.get("/api/v1/records", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == TENANT_ID
        assert body["total"] == 3
        assert len(body["events"]) == 3
        assert body["events"][0]["event_id"] == "evt-1"

    def test_event_shape(self, client: TestClient) -> None:
        resp = client.get("/api/v1/records", params={"tenant_id": TENANT_ID})
        evt = resp.json()["events"][0]
        expected_keys = {
            "event_id", "event_type", "traceability_lot_code",
            "product_reference", "quantity", "unit_of_measure",
            "from_facility_reference", "to_facility_reference",
            "event_timestamp", "source_system", "status",
            "confidence_score", "schema_version", "created_at",
        }
        assert set(evt.keys()) == expected_keys

    def test_pagination_params_accepted(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(row=(100,)),
            _Result(rows=[_make_event_row(event_id="evt-50")]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get(
            "/api/v1/records",
            params={"tenant_id": TENANT_ID, "limit": 1, "offset": 49},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 100
        assert len(body["events"]) == 1

    def test_filter_by_event_type(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(row=(1,)),
            _Result(rows=[_make_event_row(event_type="receiving")]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get(
            "/api/v1/records",
            params={"tenant_id": TENANT_ID, "event_type": "receiving"},
        )
        assert resp.status_code == 200
        assert resp.json()["events"][0]["event_type"] == "receiving"

    def test_filter_by_tlc(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(row=(1,)),
            _Result(rows=[_make_event_row(tlc="TLC-SPECIAL")]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get(
            "/api/v1/records",
            params={"tenant_id": TENANT_ID, "tlc": "TLC-SPECIAL"},
        )
        assert resp.status_code == 200
        assert resp.json()["events"][0]["traceability_lot_code"] == "TLC-SPECIAL"

    def test_empty_result(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(row=(0,)),
            _Result(rows=[]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get("/api/v1/records", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["events"] == []

    def test_db_unavailable_returns_503(self, principal: IngestionPrincipal) -> None:
        app = FastAPI()
        app.include_router(canonical_router)
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
        app.dependency_overrides[_get_db_session] = lambda: None

        c = TestClient(app)
        resp = c.get("/api/v1/records", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 503
        assert "Database unavailable" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# get_record  (GET /api/v1/records/{event_id})
# ---------------------------------------------------------------------------


class TestGetRecord:
    def test_returns_record_with_evaluations_and_exceptions(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        eval_rows = [_make_eval_row()]
        exc_rows = [_make_exception_row()]

        # Session: first call for eval query, second for exception query
        session = _FakeSession([
            _Result(rows=eval_rows),
            _Result(rows=exc_rows),
        ])

        # Patch CanonicalEventStore
        fake_event = {
            "event_id": EVENT_ID,
            "event_type": "shipping",
            "tenant_id": TENANT_ID,
        }

        import app.canonical_router as cr_module

        class _PatchedStore:
            def __init__(self, sess, dual_write=False):
                pass
            def get_event(self, tid, eid):
                if tid == TENANT_ID and eid == EVENT_ID:
                    return dict(fake_event)
                return None

        # We need to patch the import inside the function
        fake_persistence = types.ModuleType("shared.canonical_persistence")
        fake_persistence.CanonicalEventStore = _PatchedStore
        monkeypatch.setitem(sys.modules, "shared.canonical_persistence", fake_persistence)

        c = _make_app_and_client(principal, session)
        resp = c.get(f"/api/v1/records/{EVENT_ID}", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_id"] == EVENT_ID
        assert len(body["rule_evaluations"]) == 1
        assert body["rule_evaluations"][0]["result"] == "fail"
        assert body["rule_evaluations"][0]["severity"] == "critical"
        assert len(body["exception_cases"]) == 1
        assert body["exception_cases"][0]["case_id"] == "case-001"

    def test_record_not_found_returns_404(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = _FakeSession([])

        import app.canonical_router as cr_module

        class _EmptyStore:
            def __init__(self, sess, dual_write=False):
                pass
            def get_event(self, tid, eid):
                return None

        fake_persistence = types.ModuleType("shared.canonical_persistence")
        fake_persistence.CanonicalEventStore = _EmptyStore
        monkeypatch.setitem(sys.modules, "shared.canonical_persistence", fake_persistence)

        c = _make_app_and_client(principal, session)
        resp = c.get(f"/api/v1/records/nonexistent-id", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_db_unavailable_returns_503(self, principal: IngestionPrincipal) -> None:
        app = FastAPI()
        app.include_router(canonical_router)
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
        app.dependency_overrides[_get_db_session] = lambda: None

        c = TestClient(app)
        resp = c.get(f"/api/v1/records/{EVENT_ID}", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# get_record_history  (GET /api/v1/records/{event_id}/history)
# ---------------------------------------------------------------------------


class TestGetRecordHistory:
    def test_empty_amendment_chain(self, principal: IngestionPrincipal) -> None:
        # Walk backward returns None (no supersedes), walk forward returns None
        session = _FakeSession([
            _Result(row=_Row((EVENT_ID, None, "shipping", "active", NOW, None))),
            _Result(row=None),  # no forward link
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get(f"/api/v1/records/{EVENT_ID}/history", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_id"] == EVENT_ID
        assert body["amendment_chain"] == []

    def test_amendment_chain_with_predecessor(self, principal: IngestionPrincipal) -> None:
        # Walk backward: first iteration finds a link, second iteration has no further link
        # Walk forward: no successor
        session = _FakeSession([
            # backward step 1: event has supersedes_event_id
            _Result(row=_Row((EVENT_ID, "evt-old", "shipping", "active", NOW, None))),
            # backward step 2: predecessor has no further link
            _Result(row=_Row(("evt-old", None, "shipping", "superseded", NOW, None))),
            # forward step 1: no successor
            _Result(row=None),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get(f"/api/v1/records/{EVENT_ID}/history", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        chain = resp.json()["amendment_chain"]
        assert len(chain) == 1
        assert chain[0]["event_id"] == "evt-old"
        assert chain[0]["superseded_by"] == EVENT_ID

    def test_db_unavailable_returns_503(self, principal: IngestionPrincipal) -> None:
        app = FastAPI()
        app.include_router(canonical_router)
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
        app.dependency_overrides[_get_db_session] = lambda: None

        c = TestClient(app)
        resp = c.get(f"/api/v1/records/{EVENT_ID}/history", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# list_ingestion_runs  (GET /api/v1/records/ingestion-runs)
# ---------------------------------------------------------------------------


class TestListIngestionRuns:
    def test_returns_runs(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(rows=[_make_run_row(), _make_run_row(run_id="run-002")]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get("/api/v1/records/ingestion-runs", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == TENANT_ID
        assert body["total"] == 2
        assert len(body["runs"]) == 2

    def test_run_shape(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(rows=[_make_run_row()]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get("/api/v1/records/ingestion-runs", params={"tenant_id": TENANT_ID})
        run = resp.json()["runs"][0]
        expected_keys = {
            "id", "source_system", "source_file_name", "record_count",
            "accepted_count", "rejected_count", "status", "mapper_version",
            "initiated_by", "started_at", "completed_at",
        }
        assert set(run.keys()) == expected_keys

    def test_filter_by_status(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(rows=[_make_run_row(status="failed")]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get(
            "/api/v1/records/ingestion-runs",
            params={"tenant_id": TENANT_ID, "status": "failed"},
        )
        assert resp.status_code == 200
        assert resp.json()["runs"][0]["status"] == "failed"

    def test_empty_runs(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([_Result(rows=[])])
        c = _make_app_and_client(principal, session)
        resp = c.get("/api/v1/records/ingestion-runs", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        assert resp.json()["runs"] == []
        assert resp.json()["total"] == 0

    def test_db_unavailable_returns_503(self, principal: IngestionPrincipal) -> None:
        app = FastAPI()
        app.include_router(canonical_router)
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
        app.dependency_overrides[_get_db_session] = lambda: None

        c = TestClient(app)
        resp = c.get("/api/v1/records/ingestion-runs", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# get_ingestion_run  (GET /api/v1/records/ingestion-runs/{run_id})
# ---------------------------------------------------------------------------


class TestGetIngestionRun:
    def test_returns_run_detail(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(row=_make_run_detail_row()),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get(
            f"/api/v1/records/ingestion-runs/{RUN_ID}",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == RUN_ID
        assert body["record_count"] == 50
        assert body["accepted_count"] == 48
        assert body["rejected_count"] == 2
        assert body["errors"] == []

    def test_run_detail_with_errors_list(self, principal: IngestionPrincipal) -> None:
        errors = [{"row": 5, "message": "bad TLC"}]
        session = _FakeSession([
            _Result(row=_make_run_detail_row(errors=json.dumps(errors))),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get(
            f"/api/v1/records/ingestion-runs/{RUN_ID}",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        assert resp.json()["errors"] == errors

    def test_run_not_found_returns_404(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([_Result(row=None)])
        c = _make_app_and_client(principal, session)
        resp = c.get(
            "/api/v1/records/ingestion-runs/nonexistent",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_db_unavailable_returns_503(self, principal: IngestionPrincipal) -> None:
        app = FastAPI()
        app.include_router(canonical_router)
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
        app.dependency_overrides[_get_db_session] = lambda: None

        c = TestClient(app)
        resp = c.get(
            f"/api/v1/records/ingestion-runs/{RUN_ID}",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Auth: missing API key  →  401 (or 403 depending on config)
# ---------------------------------------------------------------------------


class TestAuth:
    def test_no_auth_returns_401_in_production_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When API_KEY is configured, requests without a key get 401."""
        monkeypatch.setenv("REGENGINE_ENV", "production")
        monkeypatch.setenv("API_KEY", "secret-master-key")

        # Force config cache to clear
        from app.config import get_settings
        get_settings.cache_clear()

        app = FastAPI()
        app.include_router(canonical_router)
        # Do NOT override get_ingestion_principal — let real auth run.
        session = _FakeSession([])
        app.dependency_overrides[_get_db_session] = lambda: session

        c = TestClient(app)
        resp = c.get("/api/v1/records", params={"tenant_id": TENANT_ID})
        # Should be 401 (no API key header)
        assert resp.status_code in (401, 403)

        # Clean up
        get_settings.cache_clear()

    def test_insufficient_scope_returns_403(self) -> None:
        limited_principal = IngestionPrincipal(
            key_id="limited-key",
            scopes=["fda.export"],  # does not include records.read
            tenant_id=TENANT_ID,
            auth_mode="test",
        )
        session = _FakeSession([
            _Result(row=(0,)),
            _Result(rows=[]),
        ])
        c = _make_app_and_client(limited_principal, session)
        resp = c.get("/api/v1/records", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 403
        assert "records.read" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    def test_tenant_mismatch_returns_403(self) -> None:
        """Principal bound to TENANT_ID cannot query OTHER_TENANT_ID."""
        principal = IngestionPrincipal(
            key_id="scoped-key",
            scopes=["records.read"],
            tenant_id=TENANT_ID,
            auth_mode="test",
        )
        session = _FakeSession([
            _Result(row=(0,)),
            _Result(rows=[]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get("/api/v1/records", params={"tenant_id": OTHER_TENANT_ID})
        assert resp.status_code == 403
        assert "tenant" in resp.json()["detail"].lower()

    def test_wildcard_scope_allows_cross_tenant(self) -> None:
        """Principal with wildcard scope can query any tenant."""
        principal = IngestionPrincipal(
            key_id="admin-key",
            scopes=["*"],
            tenant_id=TENANT_ID,
            auth_mode="test",
        )
        session = _FakeSession([
            _Result(row=(0,)),
            _Result(rows=[]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get("/api/v1/records", params={"tenant_id": OTHER_TENANT_ID})
        assert resp.status_code == 200

    def test_principal_tenant_used_when_no_query_param(self) -> None:
        """When tenant_id query param is omitted, principal.tenant_id is used."""
        principal = IngestionPrincipal(
            key_id="scoped-key",
            scopes=["records.read"],
            tenant_id=TENANT_ID,
            auth_mode="test",
        )
        session = _FakeSession([
            _Result(row=(1,)),
            _Result(rows=[_make_event_row()]),
        ])
        c = _make_app_and_client(principal, session)
        # No tenant_id in params — should use principal's tenant_id
        resp = c.get("/api/v1/records")
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == TENANT_ID

    def test_missing_tenant_context_returns_400(self) -> None:
        """No tenant_id in query and no tenant_id on principal -> 400."""
        principal = IngestionPrincipal(
            key_id="no-tenant-key",
            scopes=["*"],
            tenant_id=None,
            auth_mode="test",
        )
        session = _FakeSession([
            _Result(row=(0,)),
            _Result(rows=[]),
        ])
        c = _make_app_and_client(principal, session)
        resp = c.get("/api/v1/records")
        assert resp.status_code == 400
        assert "tenant" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Evaluations endpoint (GET /api/v1/records/{event_id}/evaluations)
# ---------------------------------------------------------------------------
# Note: The router defines /{event_id}/history but not a standalone
# /{event_id}/evaluations. Evaluations are embedded in get_record.
# We verify that via the get_record tests above.
