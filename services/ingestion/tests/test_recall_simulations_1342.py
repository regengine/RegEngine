"""Full-coverage tests for ``app.recall_simulations`` (#1342).

Complements ``tests/test_recall_simulations_api.py`` by driving the
branches it doesn't touch:

- ``_query_tenant_recall_metrics`` — success, empty-tenant fallback,
  and exception swallow (lines 29-63).
- ``_get_simulation_or_404`` DB fallback path (lines 266-273).
- ``_csv_rows_for_view`` ``impact_graph`` view (lines 326-340).
- ``_build_csv_export`` empty-rows early return (line 367).
- ``run_recall_simulation`` tenant-scaling branch including the
  ``has_export`` response-time adjustment (lines 414-434).
- ``set_tenant_data`` write-through exception swallow (lines 452-453).
- ``get_simulation`` endpoint (line 471).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

pytest.importorskip("fastapi")

from app.authz import IngestionPrincipal, get_ingestion_principal
import app.recall_simulations as rs_module
from app.recall_simulations import (
    _build_csv_export,
    _csv_rows_for_view,
    _get_simulation_or_404,
    _query_tenant_recall_metrics,
    _simulation_store,
    router as recall_simulations_router,
)
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _client(scopes: list[str] | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(recall_simulations_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=scopes or ["*"],
        auth_mode="test",
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_store() -> None:
    _simulation_store.clear()
    yield
    _simulation_store.clear()


# ---------------------------------------------------------------------------
# _query_tenant_recall_metrics
# ---------------------------------------------------------------------------


class _FakeScalarResult:
    """Mimics ``db.execute(...).scalar()``."""

    def __init__(self, value) -> None:
        self._value = value

    def scalar(self):
        return self._value


class _FakeDB:
    """Programmable ``SessionLocal()`` return value.

    Each ``.execute()`` call pops the next preset scalar from the queue.
    """

    def __init__(self, scalars: list) -> None:
        self._scalars = list(scalars)
        self.closed = False

    def execute(self, *_args, **_kwargs):
        return _FakeScalarResult(self._scalars.pop(0) if self._scalars else 0)

    def close(self) -> None:
        self.closed = True


class TestQueryTenantRecallMetrics:
    def test_returns_aggregated_metrics_when_ctes_exist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_db = _FakeDB([
            5,   # cte_count
            2,   # supplier_count
            3,   # tlc_count
            1,   # has_export count (> 0 → True)
        ])
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: fake_db)

        result = _query_tenant_recall_metrics("tenant-A")
        assert result == {
            "cte_count": 5,
            "supplier_count": 2,
            "tlc_count": 3,
            "has_export": True,
        }
        assert fake_db.closed is True

    def test_has_export_false_when_zero_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_db = _FakeDB([5, 2, 3, 0])
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: fake_db)

        result = _query_tenant_recall_metrics("tenant-A")
        assert result is not None
        assert result["has_export"] is False

    def test_returns_none_when_no_ctes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # cte_count = 0 triggers the early-return branch (line 38-39).
        fake_db = _FakeDB([0])
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: fake_db)

        assert _query_tenant_recall_metrics("tenant-B") is None
        # Connection still closed (finally clause).
        assert fake_db.closed is True

    def test_returns_none_on_scalar_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``.scalar() or 0`` fallback: if the DB returns None, we treat
        # that as 0 and take the early-return path.
        class _NoneScalar:
            def execute(self, *_a, **_kw):
                return _FakeScalarResult(None)

            def close(self) -> None:
                pass

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: _NoneScalar())
        assert _query_tenant_recall_metrics("tenant-C") is None

    def test_swallows_exceptions_and_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Any exception during the outer ``try`` block returns None.
        def _raising_session_local():
            raise RuntimeError("db down")

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", _raising_session_local)
        assert _query_tenant_recall_metrics("tenant-D") is None


# ---------------------------------------------------------------------------
# _get_simulation_or_404 DB fallback
# ---------------------------------------------------------------------------


class TestGetSimulationOr404DBFallback:
    def test_falls_back_to_db_and_repopulates_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # In-memory store is empty; get_tenant_data returns the simulation.
        stored = {"id": "sim-fallback", "scenario_id": "x", "metrics": {}}
        monkeypatch.setattr(
            rs_module, "get_tenant_data",
            lambda tid, ns, key: stored if key == "sim-fallback" else None,
        )

        result = _get_simulation_or_404("sim-fallback", tenant_id="tenant-A")
        assert result is stored
        # Cache was re-populated.
        assert _simulation_store["sim-fallback"] is stored

    def test_falls_back_with_default_tenant_when_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = {}

        def _capture_get(tid, ns, key):
            captured["tid"] = tid
            return {"id": key}

        monkeypatch.setattr(rs_module, "get_tenant_data", _capture_get)
        result = _get_simulation_or_404("sim-default", tenant_id=None)
        assert result == {"id": "sim-default"}
        assert captured["tid"] == "default"

    def test_db_error_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the DB lookup raises, the function still falls through to 404."""
        def _raising(*_args, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(rs_module, "get_tenant_data", _raising)
        with pytest.raises(HTTPException) as excinfo:
            _get_simulation_or_404("missing", tenant_id="tenant-A")
        assert excinfo.value.status_code == 404
        assert "'missing'" in excinfo.value.detail

    def test_db_returns_none_raises_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rs_module, "get_tenant_data", lambda *a, **kw: None)
        with pytest.raises(HTTPException) as excinfo:
            _get_simulation_or_404("nowhere")
        assert excinfo.value.status_code == 404


# ---------------------------------------------------------------------------
# _csv_rows_for_view — impact_graph + empty rows
# ---------------------------------------------------------------------------


class TestCSVRowsImpactGraph:
    def _sim(self, links: list[dict]) -> dict:
        return {
            "id": "sim-1",
            "scenario_id": "test",
            "metrics": {
                "scenario": "Test Scenario",
                "supply_chain_graph": {"nodes": [], "links": links},
            },
        }

    def test_impact_graph_rows_include_lot_codes_joined(self) -> None:
        sim = self._sim([
            {
                "source": "loc-1",
                "target": "loc-2",
                "affected": True,
                "lot_codes": ["LOT-A", "LOT-B"],
            },
        ])
        rows = _csv_rows_for_view(sim, view="impact_graph")
        assert rows == [{
            "simulation_id": "sim-1",
            "scenario_id": "test",
            "scenario_name": "Test Scenario",
            "source": "loc-1",
            "target": "loc-2",
            "affected": True,
            "lot_codes": "LOT-A,LOT-B",
        }]

    def test_impact_graph_affected_coerced_to_bool(self) -> None:
        sim = self._sim([
            {"source": "s", "target": "t", "affected": 0, "lot_codes": []},
        ])
        rows = _csv_rows_for_view(sim, view="impact_graph")
        assert rows[0]["affected"] is False
        assert rows[0]["lot_codes"] == ""

    def test_impact_graph_empty_links_returns_empty_rows(self) -> None:
        sim = self._sim([])
        assert _csv_rows_for_view(sim, view="impact_graph") == []


class TestBuildCSVExportEmpty:
    def test_empty_rows_returns_empty_string(self) -> None:
        # contact_list with no affected nodes → empty rows → early return.
        sim = {
            "id": "sim-2",
            "scenario_id": "x",
            "metrics": {
                "scenario": "S",
                "supply_chain_graph": {"nodes": [], "links": []},
            },
        }
        assert _build_csv_export(sim, view="contact_list") == ""


# ---------------------------------------------------------------------------
# run_recall_simulation — tenant-scaling branch
# ---------------------------------------------------------------------------


class TestRunSimulationTenantBranch:
    ENDPOINT = "/api/v1/simulations/run"

    def _setup_tenant_metrics(
        self, monkeypatch: pytest.MonkeyPatch, tenant_data: dict | None
    ) -> None:
        monkeypatch.setattr(
            rs_module, "_query_tenant_recall_metrics",
            lambda tid: tenant_data,
        )
        # Stub out set_tenant_data so DB writes don't touch real infra.
        monkeypatch.setattr(rs_module, "set_tenant_data", lambda *a, **kw: None)

    def test_tenant_branch_marks_non_illustrative_and_scales_metrics(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup_tenant_metrics(
            monkeypatch,
            {
                "cte_count": 200,
                "supplier_count": 5,
                "tlc_count": 80,
                "has_export": True,
            },
        )
        resp = _client().post(
            self.ENDPOINT,
            params={"tenant_id": "tenant-X"},
            json={"scenario_id": "romaine-ecoli"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_illustrative"] is False
        assert body["data_source"] == "tenant"
        assert body["tenant_metrics"] == {
            "cte_events": 200,
            "suppliers": 5,
            "tlcs": 80,
            "export_ready": True,
        }
        # Scaled metrics: tlc_count=80 replaces total_lots_in_system.
        assert body["metrics"]["total_lots_in_system"] == 80
        # has_export=True subtracts 10 minutes (42 → 32).
        assert body["metrics"]["with_regengine"]["response_time_minutes"] == 32
        # Completeness bumped by +0.01, capped at 1.0 (0.98 + 0.01 = 0.99).
        assert body["metrics"]["with_regengine"]["kde_completeness"] == pytest.approx(0.99)
        # Disclaimer suppressed for non-illustrative runs.
        assert body["demo_disclaimer"] is None

    def test_tenant_branch_without_export_keeps_baseline_response_minutes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup_tenant_metrics(
            monkeypatch,
            {
                "cte_count": 10,
                "supplier_count": 2,
                "tlc_count": 0,  # 0 → falls back to scenario.total_lots
                "has_export": False,
            },
        )
        resp = _client().post(
            self.ENDPOINT,
            params={"tenant_id": "tenant-Y"},
            json={"scenario_id": "romaine-ecoli"},
        )
        assert resp.status_code == 201
        body = resp.json()
        # tlc_count=0 falsy → scenario.total_lots (47) kept.
        assert body["metrics"]["total_lots_in_system"] == 47
        # has_export=False → no adjustment, original 42 preserved.
        assert body["metrics"]["with_regengine"]["response_time_minutes"] == 42

    def test_tenant_branch_skipped_when_cte_count_is_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Real tenant_data returned with cte_count=0 falls through to the
        # is_illustrative=True default (the ``> 0`` guard).
        self._setup_tenant_metrics(
            monkeypatch,
            {
                "cte_count": 0,
                "supplier_count": 0,
                "tlc_count": 0,
                "has_export": False,
            },
        )
        resp = _client().post(
            self.ENDPOINT,
            params={"tenant_id": "tenant-Z"},
            json={"scenario_id": "romaine-ecoli"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_illustrative"] is True
        assert body["data_source"] == "demo"
        assert body["tenant_metrics"] is None

    def test_tenant_branch_skipped_when_metrics_query_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``_query_tenant_recall_metrics`` returning None → demo path.
        self._setup_tenant_metrics(monkeypatch, None)
        resp = _client().post(
            self.ENDPOINT,
            params={"tenant_id": "tenant-NO-DATA"},
            json={"scenario_id": "romaine-ecoli"},
        )
        assert resp.status_code == 201
        assert resp.json()["is_illustrative"] is True


class TestPersistTenantDataErrorSwallowed:
    def test_set_tenant_data_exception_does_not_fail_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            rs_module, "_query_tenant_recall_metrics", lambda tid: None
        )

        def _raising(*_args, **_kwargs):
            raise RuntimeError("write boom")

        monkeypatch.setattr(rs_module, "set_tenant_data", _raising)

        resp = _client().post(
            "/api/v1/simulations/run",
            params={"tenant_id": "tenant-ERR"},
            json={"scenario_id": "romaine-ecoli"},
        )
        # Endpoint still succeeds despite the write-through failure.
        assert resp.status_code == 201
        assert resp.json()["scenario_id"] == "romaine-ecoli"


# ---------------------------------------------------------------------------
# get_simulation endpoint — line 471
# ---------------------------------------------------------------------------


class TestGetSimulationEndpoint:
    def test_returns_simulation_from_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Seed the in-memory store directly so the GET path exercises the
        # cache-hit branch (no DB fallback).
        monkeypatch.setattr(
            rs_module, "_query_tenant_recall_metrics", lambda tid: None
        )
        monkeypatch.setattr(rs_module, "set_tenant_data", lambda *a, **kw: None)
        client = _client()
        # Run to seed.
        run = client.post(
            "/api/v1/simulations/run",
            json={"scenario_id": "cheese-listeria"},
        )
        assert run.status_code == 201
        sim_id = run.json()["id"]

        # Now fetch via GET /{simulation_id}.
        resp = client.get(f"/api/v1/simulations/{sim_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == sim_id
        assert body["scenario_id"] == "cheese-listeria"

    def test_404_when_simulation_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # DB fallback also returns None so the 404 path fires.
        monkeypatch.setattr(rs_module, "get_tenant_data", lambda *a, **kw: None)
        resp = _client().get("/api/v1/simulations/does-not-exist")
        assert resp.status_code == 404
        assert "'does-not-exist'" in resp.json()["detail"]
