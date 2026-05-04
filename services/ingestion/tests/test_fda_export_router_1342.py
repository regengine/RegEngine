"""Coverage tests for ``app/fda_export/router.py`` — issue #1342.

The existing ``test_fda_export_router.py`` covers the happy-path ZIP/CSV
flow, ``verify_export``, and the forbidden-scope branch. This file
exercises the remaining 156 lines of ``fda_export/router.py``:

* ``_authorize_pii_access`` permission-denied path (lines 178-204).
* ``_enforce_kde_coverage_gate`` happy-path return (line 104).
* ``export_fda_spreadsheet`` no-events 404 (line 340), audit-log-write
  failure 503 (lines 385-398), PDF format (494-505), outer 500 handler
  (532-534).
* ``export_all_events`` — every major branch (lines 584-814).
* ``export_history`` endpoint (lines 830-843).
* ``export_recall_filtered`` missing-key_id 401 (line 891).
* ``export_fda_spreadsheet_v2`` — every branch (lines 996-1197).
* ``get_merkle_root`` / ``get_merkle_proof`` wrappers (1219, 1237).
* ``trace_transformation_graph`` happy + error (1263-1286).

All tests run against a stubbed SessionLocal / CTEPersistence so no DB
is required. Route-level helpers imported inside the handler bodies
(``fetch_v2_events``, ``log_v2_export``, ``fetch_trace_graph_data`` …)
are patched on the ``app.fda_export.router`` module object so the
router's reference is the one replaced.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
import types
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.authz import IngestionPrincipal, get_ingestion_principal
# Import the router.py module directly so monkeypatch can reach the
# helper-function bindings (``build_v2_where_clause``, ``fetch_v2_events``
# ...). ``from app.fda_export import router`` returns the APIRouter object
# because __init__ re-exports it; importlib avoids that package attribute.
router_module = importlib.import_module("app.fda_export.router")
from app.fda_export.router import router as fda_router
from app.fda_export_service import _generate_csv
from app.subscription_gate import require_active_subscription

import shared.cte_persistence as shared_cte_persistence


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeChainVerification:
    def __init__(self, valid: bool = True):
        self.valid = valid
        self.chain_length = 7
        self.errors: list[str] = []
        self.checked_at = "2026-03-10T10:00:00+00:00"


class _FakeMerkleVerification:
    def __init__(self):
        self.valid = True
        self.merkle_root = "abc123" * 10 + "dead"
        self.chain_length = 5
        self.tree_depth = 3
        self.errors: list[str] = []
        self.checked_at = "2026-03-10T10:00:00+00:00"


class _FakeResult:
    def __init__(self, *, row: Any = None, rows: Optional[list[Any]] = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(
        self,
        *,
        commit_raises: Optional[Exception] = None,
        export_log_row: Any = None,
    ):
        self._commit_raises = commit_raises
        self._export_log_row = export_log_row
        self.rolled_back = False
        self.closed = False

    def execute(self, *_args, **_kwargs):
        return _FakeResult(row=self._export_log_row)

    def commit(self):
        if self._commit_raises is not None:
            raise self._commit_raises

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


# A deterministic event shape the FDA CSV generator accepts. Coverage
# ratio of the required KDEs here is ~67%, below the #1222 threshold —
# tests that want the happy path must pass ``allow_incomplete=true``.
_SAMPLE_EVENT_1 = {
    "id": "evt-1",
    "event_type": "shipping",
    "traceability_lot_code": "TLC-2026-001",
    "product_description": "Romaine Hearts",
    "quantity": 120.0,
    "unit_of_measure": "cases",
    "location_gln": "0614141000005",
    "location_name": "Valley Fresh Farms",
    "event_timestamp": "2026-03-10T09:00:00+00:00",
    "sha256_hash": "a" * 64,
    "chain_hash": "b" * 64,
    "source": "webhook",
    "kdes": {
        "ship_date": "2026-03-10",
        "ship_from_location": "Valley Fresh Farms",
    },
}

_SAMPLE_EVENT_2 = {
    "id": "evt-2",
    "event_type": "receiving",
    "traceability_lot_code": "TLC-2026-002",
    "product_description": "Baby Spinach",
    "quantity": 80.0,
    "unit_of_measure": "cases",
    "location_gln": "0614141000006",
    "location_name": "Metro Distribution Center",
    "event_timestamp": "2026-03-10T10:00:00+00:00",
    "sha256_hash": "c" * 64,
    "chain_hash": "d" * 64,
    "source": "webhook",
    "kdes": {
        "receive_date": "2026-03-10",
        "receiving_location": "Metro Distribution Center",
    },
}

# Event with every required shipping KDE populated — coverage = 100% so
# ``_enforce_kde_coverage_gate`` returns silently (exercises line 104).
# Required shipping KDEs per REQUIRED_KDES_BY_CTE (§1.1340):
#   traceability_lot_code, product_description, quantity, unit_of_measure,
#   ship_date, ship_from_location, ship_to_location,
#   reference_document, tlc_source_reference.
_FULLY_POPULATED_EVENT = {
    "id": "evt-3",
    "event_type": "shipping",
    "traceability_lot_code": "TLC-2026-003",
    "product_description": "Cherry Tomatoes",
    "quantity": 50.0,
    "unit_of_measure": "cases",
    "location_gln": "0614141000007",
    "location_name": "Farm Direct",
    "event_timestamp": "2026-03-10T11:00:00+00:00",
    "sha256_hash": "e" * 64,
    "chain_hash": "f" * 64,
    "source": "webhook",
    "kdes": {
        "ship_date": "2026-03-10",
        "ship_from_location": "Farm Direct",
        "ship_to_location": "Metro DC",
        "reference_document": "PO-2026-003",
        "tlc_source_reference": "SRC-2026-003",
    },
}


class _FakePersistence:
    """Stub of :class:`shared.cte_persistence.CTEPersistence`."""

    def __init__(
        self,
        _session,
        *,
        events_by_tlc: Optional[dict[str, list[dict]]] = None,
        all_events: Optional[tuple[list[dict], int]] = None,
        log_export_raises: Optional[Exception] = None,
        verify_chain_result: Optional[_FakeChainVerification] = None,
        merkle_result: Optional[_FakeMerkleVerification] = None,
        linked_tlcs: Optional[list[str]] = None,
    ):
        self._events_by_tlc = events_by_tlc or {
            "TLC-2026-001": [_SAMPLE_EVENT_1],
            "TLC-2026-002": [_SAMPLE_EVENT_2],
            "TLC-2026-003": [_FULLY_POPULATED_EVENT],
        }
        self._all_events = all_events
        self._log_export_raises = log_export_raises
        self._chain_result = verify_chain_result or _FakeChainVerification()
        self._merkle_result = merkle_result or _FakeMerkleVerification()
        self._linked_tlcs = linked_tlcs or ["TLC-2026-001"]

    def query_events_by_tlc(self, tenant_id, tlc, start_date=None, end_date=None):
        _ = tenant_id, start_date, end_date
        return list(self._events_by_tlc.get(tlc, []))

    def query_all_events(
        self,
        tenant_id,
        start_date=None,
        end_date=None,
        event_type=None,
        limit=1000,
        offset=0,
    ):
        _ = tenant_id, start_date, end_date, event_type, limit, offset
        if self._all_events is not None:
            return self._all_events
        # Default: return the seed TLCs that _FakePersistence knows about.
        return (
            [{"traceability_lot_code": tlc} for tlc in self._events_by_tlc],
            len(self._events_by_tlc),
        )

    def verify_chain(self, tenant_id):
        _ = tenant_id
        return self._chain_result

    def verify_chain_merkle(self, tenant_id):
        _ = tenant_id
        return self._merkle_result

    def log_export(self, **_kwargs):
        if self._log_export_raises is not None:
            raise self._log_export_raises
        return "export-log-id"

    def _expand_tlcs_via_transformation_links(self, tenant_id, seed_tlc, depth):
        _ = tenant_id, seed_tlc, depth
        return self._linked_tlcs


def _install_fake_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_factory,
    persistence_cls,
):
    fake_db_module = types.ModuleType("shared.database")
    fake_db_module.SessionLocal = session_factory
    monkeypatch.setitem(sys.modules, "shared.database", fake_db_module)
    monkeypatch.setattr(shared_cte_persistence, "CTEPersistence", persistence_cls)


def _build_app_with_principal(
    *,
    scopes: list[str],
    key_id: str = "test-key",
    tenant_id: Optional[str] = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(fda_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id=key_id,
        scopes=scopes,
        tenant_id=tenant_id,
        auth_mode="test",
    )
    app.dependency_overrides[require_active_subscription] = lambda: None
    return app


def _all_events_params(**overrides) -> dict[str, str]:
    """Supply the required export window for ``/api/v1/fda/export/all``."""
    params = {
        "tenant_id": "tenant-a",
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
    }
    params.update(overrides)
    return params


# ---------------------------------------------------------------------------
# Helper-function coverage
# ---------------------------------------------------------------------------


class TestAuthorizePIIAccess:
    """_authorize_pii_access — lines 178-204."""

    def test_include_pii_without_permission_returns_403(self, monkeypatch):
        """Caller without ``fda.export.pii`` gets 403 when opting in."""
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export",
                params={
                    "tenant_id": "tenant-a",
                    "tlc": "TLC-2026-001",
                    "include_pii": "true",
                },
            )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "fda.export.pii" in detail

    def test_include_pii_with_permission_succeeds(self, monkeypatch):
        """Caller with ``fda.export.pii`` gets the export + audit line."""
        app = _build_app_with_principal(scopes=["fda.export", "fda.export.pii"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _FakePersistence(
                s, events_by_tlc={"TLC-2026-003": [_FULLY_POPULATED_EVENT]}
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export",
                params={
                    "tenant_id": "tenant-a",
                    "tlc": "TLC-2026-003",
                    "include_pii": "true",
                    "format": "csv",
                },
            )
        assert resp.status_code == 200
        assert resp.headers["x-pii-redacted"] == "false"


class TestEnforceKDECoverageGate:
    """_enforce_kde_coverage_gate happy return — line 104."""

    def test_coverage_above_threshold_passes_silently(self, monkeypatch):
        """When coverage >= 80% the gate returns with no warning."""
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _FakePersistence(
                s, events_by_tlc={"TLC-2026-003": [_FULLY_POPULATED_EVENT]}
            ),
        )
        with TestClient(app) as client:
            # Explicitly do NOT pass allow_incomplete; fully-populated
            # fixture should satisfy the gate on its own.
            resp = client.get(
                "/api/v1/fda/export",
                params={
                    "tenant_id": "tenant-a",
                    "tlc": "TLC-2026-003",
                    "format": "csv",
                },
            )
        assert resp.status_code == 200
        assert "x-compliance-warning" not in {k.lower() for k in resp.headers}


# ---------------------------------------------------------------------------
# /export — missing branches (no events 404, audit 503, PDF, outer 500)
# ---------------------------------------------------------------------------


class TestExportFDASpreadsheetMissingBranches:
    """Fills in the gaps around ``export_fda_spreadsheet``."""

    def test_no_events_returns_404(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _FakePersistence(s, events_by_tlc={}),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export",
                params={"tenant_id": "tenant-a", "tlc": "TLC-NOPE"},
            )
        assert resp.status_code == 404
        assert "TLC-NOPE" in resp.json()["detail"]

    def test_audit_log_write_failure_returns_503(self, monkeypatch):
        """Audit log insert raises → 503 + rollback (lines 385-398)."""
        sessions: list[_FakeSession] = []

        def _session_factory():
            sess = _FakeSession()
            sessions.append(sess)
            return sess

        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=_session_factory,
            persistence_cls=lambda s: _FakePersistence(
                s, log_export_raises=RuntimeError("db down")
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export",
                params={
                    "tenant_id": "tenant-a",
                    "tlc": "TLC-2026-001",
                    "allow_incomplete": "true",
                },
            )
        assert resp.status_code == 503
        assert "audit-log write failed" in resp.json()["detail"]
        assert sessions and sessions[-1].rolled_back is True

    def test_pdf_format_returns_pdf_stream(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export",
                params={
                    "tenant_id": "tenant-a",
                    "tlc": "TLC-2026-001",
                    "format": "pdf",
                    "allow_incomplete": "true",
                },
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")
        assert resp.headers["x-export-hash"]
        assert "fda_export_" in resp.headers["content-disposition"]

    def test_outer_exception_handler_returns_500(self, monkeypatch):
        """Non-HTTPException failures inside the try block → 500 (532-534)."""

        class _ExplodingPersistence(_FakePersistence):
            def query_events_by_tlc(self, *a, **kw):
                raise ValueError("query boom")

        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_ExplodingPersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export",
                params={"tenant_id": "tenant-a", "tlc": "TLC-2026-001"},
            )
        assert resp.status_code == 500
        assert "Export failed" in resp.json()["detail"]

    def test_missing_key_id_returns_401(self, monkeypatch):
        """Principal without a resolvable key_id → 401 (line 304)."""
        app = _build_app_with_principal(scopes=["fda.export"], key_id="")
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export",
                params={"tenant_id": "tenant-a", "tlc": "TLC-2026-001"},
            )
        assert resp.status_code == 401
        assert "resolvable key_id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /export/all — 230 lines, currently 0% covered
# ---------------------------------------------------------------------------


class TestExportAllEvents:
    """Covers all 230 lines of ``export_all_events`` (584-814)."""

    def test_csv_format_happy_path(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _FakePersistence(
                s, events_by_tlc={"TLC-2026-003": [_FULLY_POPULATED_EVENT]}
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(format="csv"),
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert resp.headers["x-record-count"] == "1"
        assert resp.headers["x-pii-redacted"] == "true"
        assert "x-truncated" not in {k.lower() for k in resp.headers}

    def test_package_format_returns_zip(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _FakePersistence(
                s, events_by_tlc={"TLC-2026-003": [_FULLY_POPULATED_EVENT]}
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(format="package"),
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/zip")
        assert resp.headers["x-package-hash"]

    def test_pdf_format_returns_pdf(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _FakePersistence(
                s, events_by_tlc={"TLC-2026-003": [_FULLY_POPULATED_EVENT]}
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(format="pdf"),
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")

    def test_missing_key_id_returns_401(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.export"], key_id="")
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(),
            )
        assert resp.status_code == 401
        assert "resolvable key_id" in resp.json()["detail"]

    def test_include_pii_without_permission_returns_403(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(format="csv", include_pii="true"),
            )
        assert resp.status_code == 403

    def test_audit_log_write_failure_returns_503(self, monkeypatch):
        sessions: list[_FakeSession] = []

        def _factory():
            s = _FakeSession()
            sessions.append(s)
            return s

        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=_factory,
            persistence_cls=lambda s: _FakePersistence(
                s,
                events_by_tlc={"TLC-2026-003": [_FULLY_POPULATED_EVENT]},
                log_export_raises=RuntimeError("db down"),
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(format="csv"),
            )
        assert resp.status_code == 503
        assert sessions and sessions[-1].rolled_back is True

    def test_kde_coverage_below_threshold_without_ack_returns_409(self, monkeypatch):
        """Incomplete events + allow_incomplete=false → 409."""
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _FakePersistence(
                s, events_by_tlc={"TLC-2026-001": [_SAMPLE_EVENT_1]}
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(format="csv"),
            )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["error"] == "kde_coverage_below_threshold"

    def test_outer_exception_handler_returns_500(self, monkeypatch):
        class _Boom(_FakePersistence):
            def query_all_events(self, *a, **kw):
                raise ValueError("bad query")

        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_Boom,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(),
            )
        assert resp.status_code == 500

    def test_truncation_header_emitted_when_total_exceeds_limit(self, monkeypatch):
        """Total > 10000 triggers the X-Truncated header."""

        class _HugePersistence(_FakePersistence):
            def query_all_events(self, *a, **kw):
                # Pretend there are 20000 events but we only return one TLC.
                return (
                    [{"traceability_lot_code": "TLC-2026-003"}],
                    20000,
                )

        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _HugePersistence(
                s, events_by_tlc={"TLC-2026-003": [_FULLY_POPULATED_EVENT]}
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(format="csv"),
            )
        assert resp.status_code == 200
        assert "x-truncated" in {k.lower() for k in resp.headers}

    def test_kde_coverage_below_threshold_with_ack_emits_warning_header(
        self, monkeypatch
    ):
        """allow_incomplete=true bypasses the 409 and the compliance-warning
        header is added when KDE coverage is below 0.80 (line 732)."""
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _FakePersistence(
                s, events_by_tlc={"TLC-2026-001": [_SAMPLE_EVENT_1]}
            ),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(
                    format="csv",
                    allow_incomplete="true",
                ),
            )
        assert resp.status_code == 200
        # KDE coverage < 0.80 triggers the compliance warning.
        assert float(resp.headers["x-kde-coverage"]) < 0.80
        assert "x-compliance-warning" in {k.lower() for k in resp.headers}
        assert (
            "KDE coverage below 80% threshold"
            in resp.headers["x-compliance-warning"]
        )

    def test_batch_fetch_over_50_tlcs_hits_second_loop_pass(self, monkeypatch):
        """>50 distinct TLCs exercises the batch-iteration path."""
        many_tlcs = [f"TLC-{i:03d}" for i in range(55)]
        events_by_tlc = {
            tlc: [dict(_FULLY_POPULATED_EVENT, id=f"evt-{tlc}",
                       traceability_lot_code=tlc)]
            for tlc in many_tlcs
        }

        class _ManyTLCs(_FakePersistence):
            def query_all_events(self, *a, **kw):
                return (
                    [{"traceability_lot_code": t} for t in many_tlcs],
                    len(many_tlcs),
                )

        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=lambda s: _ManyTLCs(s, events_by_tlc=events_by_tlc),
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/all",
                params=_all_events_params(format="csv"),
            )
        assert resp.status_code == 200
        assert int(resp.headers["x-record-count"]) == len(many_tlcs)


# ---------------------------------------------------------------------------
# /export/history — lines 830-843
# ---------------------------------------------------------------------------


class TestExportHistoryEndpoint:
    def test_history_happy_path(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.read"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )

        def _fake_fetch(db, tenant_id, limit):
            assert tenant_id == "tenant-a"
            assert limit == 10
            return [
                (
                    "log-id-1",
                    "fda_spreadsheet",
                    "TLC-2026-001",
                    None,
                    None,
                    1,
                    "h" * 64,
                    "user:test-key",
                    None,
                )
            ]

        def _fake_format(rows, tenant_id):
            return {
                "tenant_id": tenant_id,
                "exports": [
                    {
                        "id": str(rows[0][0]),
                        "export_type": "fda_spreadsheet",
                        "query_tlc": "TLC-2026-001",
                        "query_start_date": None,
                        "query_end_date": None,
                        "record_count": 1,
                        "export_hash": "h" * 64,
                        "generated_by": "user:test-key",
                        "generated_at": None,
                    }
                ],
                "total": 1,
            }

        monkeypatch.setattr(router_module, "fetch_export_log_history", _fake_fetch)
        monkeypatch.setattr(router_module, "format_export_log_rows", _fake_format)

        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/history",
                params={"tenant_id": "tenant-a", "limit": 10},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "tenant-a"
        assert body["total"] == 1

    def test_history_error_returns_500(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.read"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )

        def _boom(*a, **kw):
            raise RuntimeError("history down")

        monkeypatch.setattr(router_module, "fetch_export_log_history", _boom)
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/history",
                params={"tenant_id": "tenant-a"},
            )
        assert resp.status_code == 500
        assert "History query failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /export/recall — line 891 (missing key_id 401)
# ---------------------------------------------------------------------------


class TestExportRecallFiltered:
    def test_missing_key_id_returns_401(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.export"], key_id="")
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/recall",
                params={"tenant_id": "tenant-a", "product": "Romaine"},
            )
        assert resp.status_code == 401
        assert "resolvable key_id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /export/v2 — lines 996-1197, the big untested block
# ---------------------------------------------------------------------------


class TestExportV2:
    def _make_v2_events(self, *, with_rules: bool = True) -> list[dict]:
        rule_results = (
            [{"rule_name": "romaine_temp", "passed": True, "why_failed": None}]
            if with_rules
            else []
        )
        return [
            {
                **_FULLY_POPULATED_EVENT,
                "provenance": {"source_table": "fsma.traceability_events"},
                "rule_results": rule_results,
            }
        ]

    def _install_v2_helpers(
        self,
        monkeypatch,
        *,
        events: Optional[list[dict]] = None,
        log_v2_raises: Optional[Exception] = None,
    ):
        """Patch the row-fetch + transform helpers referenced by the v2 handler."""
        resolved_events = events if events is not None else self._make_v2_events()
        monkeypatch.setattr(
            router_module,
            "build_v2_where_clause",
            lambda **_: ("e.tenant_id = :tid", {"tid": "tenant-a"}),
        )
        monkeypatch.setattr(
            router_module,
            "fetch_v2_events",
            lambda *a, **kw: ["stub-row"] if resolved_events else [],
        )
        monkeypatch.setattr(
            router_module,
            "v2_rows_to_event_dicts",
            lambda rows: resolved_events,
        )

        def _log_v2(**_kwargs):
            if log_v2_raises is not None:
                raise log_v2_raises

        monkeypatch.setattr(router_module, "log_v2_export", _log_v2)

    def test_csv_happy_path(self, monkeypatch):
        self._install_v2_helpers(monkeypatch)
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={"tenant_id": "tenant-a", "tlc": "TLC-2026-003"},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert resp.headers["x-export-version"] == "2.0"
        assert float(resp.headers["x-compliance-rate"]) == 1.0

    def test_package_format_returns_zip(self, monkeypatch):
        self._install_v2_helpers(monkeypatch)
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={
                    "tenant_id": "tenant-a",
                    "tlc": "TLC-2026-003",
                    "format": "package",
                },
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/zip")
        assert resp.headers["x-export-version"] == "2.0"

    def test_no_events_returns_404_with_full_filter_detail(self, monkeypatch):
        """Exercises every ``detail_parts.append(...)`` line in the 404 branch."""
        self._install_v2_helpers(monkeypatch, events=[])
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={
                    "tenant_id": "tenant-a",
                    "tlc": "TLC-NONE",
                    "event_type": "shipping",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "tlc='TLC-NONE'" in detail
        assert "event_type='shipping'" in detail
        assert "from=2026-01-01" in detail
        assert "to=2026-01-31" in detail

    def test_missing_key_id_returns_401(self, monkeypatch):
        self._install_v2_helpers(monkeypatch)
        app = _build_app_with_principal(scopes=["fda.export"], key_id="")
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={
                    "tenant_id": "tenant-a",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
        assert resp.status_code == 401

    def test_include_pii_without_permission_returns_403(self, monkeypatch):
        self._install_v2_helpers(monkeypatch)
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={
                    "tenant_id": "tenant-a",
                    "tlc": "TLC-2026-003",
                    "include_pii": "true",
                },
            )
        assert resp.status_code == 403

    def test_audit_log_write_failure_returns_503(self, monkeypatch):
        self._install_v2_helpers(
            monkeypatch,
            log_v2_raises=router_module.AuditLogWriteError("audit down"),
        )
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={
                    "tenant_id": "tenant-a",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
        assert resp.status_code == 503
        assert "audit-log write failed" in resp.json()["detail"]

    def test_outer_exception_handler_returns_500(self, monkeypatch):
        # Make fetch_v2_events raise ValueError, which hits the outer except.
        monkeypatch.setattr(
            router_module,
            "build_v2_where_clause",
            lambda **_: ("e.tenant_id = :tid", {"tid": "tenant-a"}),
        )

        def _fetch_boom(*a, **kw):
            raise ValueError("bad v2 query")

        monkeypatch.setattr(router_module, "fetch_v2_events", _fetch_boom)
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={
                    "tenant_id": "tenant-a",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
        assert resp.status_code == 500
        assert "V2 export failed" in resp.json()["detail"]

    def test_compliance_stats_with_failing_and_no_rule_events(self, monkeypatch):
        """Exercises all three compliance branches: pass, fail, no-rules."""
        events = [
            {
                **_FULLY_POPULATED_EVENT,
                "id": "evt-pass",
                "provenance": {},
                "rule_results": [{"rule_name": "r1", "passed": True}],
            },
            {
                **_FULLY_POPULATED_EVENT,
                "id": "evt-fail",
                "provenance": {},
                "rule_results": [
                    {"rule_name": "r1", "passed": True},
                    {"rule_name": "r2", "passed": False, "why_failed": "tmp"},
                ],
            },
            {
                **_FULLY_POPULATED_EVENT,
                "id": "evt-no-rules",
                "provenance": {},
                "rule_results": [],
            },
        ]
        self._install_v2_helpers(monkeypatch, events=events)
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={
                    "tenant_id": "tenant-a",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
        assert resp.status_code == 200
        # 1 pass / 3 total = 0.3333
        assert float(resp.headers["x-compliance-rate"]) == pytest.approx(0.3333, abs=1e-3)

    def test_unbounded_full_tenant_export_returns_400(self, monkeypatch):
        self._install_v2_helpers(monkeypatch)
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={"tenant_id": "tenant-a"},
            )
        assert resp.status_code == 400
        assert "start_date is required" in resp.json()["detail"]

    def test_low_kde_coverage_without_ack_returns_409(self, monkeypatch):
        incomplete = [{**_SAMPLE_EVENT_1, "provenance": {}, "rule_results": []}]
        self._install_v2_helpers(monkeypatch, events=incomplete)
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={"tenant_id": "tenant-a", "tlc": "TLC-2026-003"},
            )
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "kde_coverage_below_threshold"

    def test_over_limit_v2_export_returns_413(self, monkeypatch):
        self._install_v2_helpers(monkeypatch, events=self._make_v2_events())
        monkeypatch.setattr(router_module, "fetch_v2_events", lambda *a, **kw: ["row"] * 10001)
        app = _build_app_with_principal(scopes=["fda.export"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/v2",
                params={
                    "tenant_id": "tenant-a",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
        assert resp.status_code == 413


# ---------------------------------------------------------------------------
# /export/merkle-root & /export/merkle-proof — lines 1219, 1237
# ---------------------------------------------------------------------------


class TestMerkleEndpoints:
    def test_merkle_root_endpoint(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.verify"])

        async def _fake_root_handler(tenant_id):
            return {"tenant_id": tenant_id, "merkle_root": "root-hash"}

        monkeypatch.setattr(router_module, "get_merkle_root_handler", _fake_root_handler)

        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/merkle-root",
                params={"tenant_id": "tenant-a"},
            )
        assert resp.status_code == 200
        assert resp.json()["merkle_root"] == "root-hash"

    def test_merkle_proof_endpoint(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.verify"])

        async def _fake_proof_handler(tenant_id, event_id):
            return {"tenant_id": tenant_id, "event_id": event_id, "proof": []}

        monkeypatch.setattr(router_module, "get_merkle_proof_handler", _fake_proof_handler)

        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/export/merkle-proof",
                params={"tenant_id": "tenant-a", "event_id": "evt-xyz"},
            )
        assert resp.status_code == 200
        assert resp.json()["event_id"] == "evt-xyz"


# ---------------------------------------------------------------------------
# /trace/{tlc} — lines 1263-1286
# ---------------------------------------------------------------------------


class TestTraceTransformationGraph:
    def test_trace_happy_path(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.read"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )

        def _fake_trace(db_session, persistence, tenant_id, tlc, depth):
            return {
                "seed_tlc": tlc,
                "tenant_id": tenant_id,
                "traversal_depth": depth,
                "node_count": 2,
                "edge_count": 1,
                "nodes": [{"tlc": tlc}, {"tlc": "TLC-DOWN"}],
                "edges": [{"input_tlc": tlc, "output_tlc": "TLC-DOWN"}],
                "total_events": 4,
            }

        monkeypatch.setattr(router_module, "fetch_trace_graph_data", _fake_trace)
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/trace/TLC-SEED",
                params={"tenant_id": "tenant-a", "depth": 3},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["seed_tlc"] == "TLC-SEED"
        assert body["traversal_depth"] == 3
        assert body["node_count"] == 2

    def test_trace_error_returns_500(self, monkeypatch):
        app = _build_app_with_principal(scopes=["fda.read"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )

        def _boom(**_kwargs):
            raise RuntimeError("trace blew up")

        monkeypatch.setattr(router_module, "fetch_trace_graph_data", _boom)
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/trace/TLC-SEED",
                params={"tenant_id": "tenant-a"},
            )
        assert resp.status_code == 500
        assert "Trace graph query failed" in resp.json()["detail"]

    def test_trace_passes_http_exception_through(self, monkeypatch):
        """An explicit HTTPException from the helper must not be wrapped."""
        app = _build_app_with_principal(scopes=["fda.read"])
        _install_fake_dependencies(
            monkeypatch,
            session_factory=lambda: _FakeSession(),
            persistence_cls=_FakePersistence,
        )

        def _forbidden(**_kwargs):
            raise HTTPException(status_code=403, detail="forbidden trace")

        monkeypatch.setattr(router_module, "fetch_trace_graph_data", _forbidden)
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/fda/trace/TLC-SEED",
                params={"tenant_id": "tenant-a"},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "forbidden trace"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
