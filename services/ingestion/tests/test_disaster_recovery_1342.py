"""Regression tests for ``services/ingestion/app/disaster_recovery.py``.

Part of the #1342 ingestion coverage sweep. Covers DR readiness checks,
backup status, and recovery simulation endpoints including all helper
paths (db unavailable, empty results, SQL errors, success branches).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app import disaster_recovery as dr
from app.disaster_recovery import (
    DRCheck,
    DRReport,
    _check_data_volume,
    _check_db_connectivity,
    _check_export_completeness,
    _check_hash_chain_integrity,
    _check_supplier_health,
    _compile_recommendations,
    _estimate_recovery_time,
    _overall_status,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, row: Optional[tuple]):
        self._row = row

    def fetchone(self) -> Optional[tuple]:
        return self._row


class _FakeSession:
    """Tiny SQLAlchemy-session stand-in.

    ``rows`` is consumed in call order by ``execute()``; after exhaustion,
    subsequent calls return ``None`` rows. ``raises`` may be a list of
    exceptions (None for 'no raise') that is interleaved with rows.
    """

    def __init__(
        self,
        rows: Optional[list[Optional[tuple]]] = None,
        raises: Optional[list[Optional[Exception]]] = None,
    ):
        self.rows = list(rows or [])
        self.raises = list(raises or [])
        self.closed = False
        self.calls: list[tuple[str, dict]] = []

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), dict(params or {})))
        if self.raises:
            exc = self.raises.pop(0)
            if exc is not None:
                raise exc
        row = self.rows.pop(0) if self.rows else None
        return _FakeResult(row)

    def close(self) -> None:
        self.closed = True


def _set_db(monkeypatch, session_or_factory):
    if callable(session_or_factory):
        monkeypatch.setattr(dr, "get_db_safe", session_or_factory)
    else:
        monkeypatch.setattr(dr, "get_db_safe", lambda: session_or_factory)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_dr_check_requires_all_fields(self):
        c = DRCheck(name="x", status="pass", details="ok", checked_at="t")
        assert c.name == "x"
        assert c.status == "pass"

    def test_dr_report_defaults(self):
        r = DRReport(
            tenant_id="t1",
            overall_status="ready",
            generated_at="t",
            recovery_time_estimate="5m",
        )
        assert r.checks == []
        assert r.recommendations == []

    def test_dr_report_lists_are_independent(self):
        r1 = DRReport(
            tenant_id="t1",
            overall_status="ready",
            generated_at="t",
            recovery_time_estimate="5m",
        )
        r2 = DRReport(
            tenant_id="t2",
            overall_status="ready",
            generated_at="t",
            recovery_time_estimate="5m",
        )
        r1.checks.append(DRCheck(name="x", status="pass", details="", checked_at="t"))
        assert r2.checks == []


# ---------------------------------------------------------------------------
# _check_db_connectivity
# ---------------------------------------------------------------------------


class TestCheckDbConnectivity:
    def test_no_db_returns_fail(self, monkeypatch):
        _set_db(monkeypatch, None)
        check = _check_db_connectivity()
        assert check.status == "fail"
        assert "Unable to connect" in check.details

    def test_select_1_with_replication_row(self, monkeypatch):
        session = _FakeSession(rows=[(1,), ("streaming",)])
        _set_db(monkeypatch, session)
        check = _check_db_connectivity()
        assert check.status == "pass"
        assert "streaming" in check.details
        assert session.closed is True

    def test_select_1_replication_empty(self, monkeypatch):
        session = _FakeSession(rows=[(1,), None])
        _set_db(monkeypatch, session)
        check = _check_db_connectivity()
        assert check.status == "pass"
        assert "replication status unavailable" in check.details
        assert session.closed is True

    def test_select_1_replication_raises(self, monkeypatch):
        session = _FakeSession(
            rows=[(1,), None],
            raises=[None, SQLAlchemyError("no pg_stat_replication")],
        )
        _set_db(monkeypatch, session)
        check = _check_db_connectivity()
        # The raise happens on the replication query, so connectivity still passes
        assert check.status == "pass"
        assert "replication status unavailable" in check.details
        assert session.closed is True

    def test_select_1_unexpected_row(self, monkeypatch):
        session = _FakeSession(rows=[(999,)])
        _set_db(monkeypatch, session)
        check = _check_db_connectivity()
        assert check.status == "fail"
        assert "unexpected" in check.details

    def test_select_1_raises(self, monkeypatch):
        session = _FakeSession(raises=[SQLAlchemyError("boom")])
        _set_db(monkeypatch, session)
        check = _check_db_connectivity()
        assert check.status == "fail"
        assert "Database query failed" in check.details
        assert session.closed is True


# ---------------------------------------------------------------------------
# _check_hash_chain_integrity
# ---------------------------------------------------------------------------


class TestCheckHashChain:
    def test_no_db(self, monkeypatch):
        _set_db(monkeypatch, None)
        check = _check_hash_chain_integrity("t1")
        assert check.status == "warn"
        assert "database unavailable" in check.details

    def test_no_records(self, monkeypatch):
        session = _FakeSession(rows=[(0, 0)])
        _set_db(monkeypatch, session)
        check = _check_hash_chain_integrity("t1")
        assert check.status == "warn"
        assert "No hash chain" in check.details

    def test_intact(self, monkeypatch):
        session = _FakeSession(rows=[(100, 0)])
        _set_db(monkeypatch, session)
        check = _check_hash_chain_integrity("t1")
        assert check.status == "pass"
        assert "100 entries" in check.details

    def test_intact_null_gaps(self, monkeypatch):
        session = _FakeSession(rows=[(100, None)])
        _set_db(monkeypatch, session)
        check = _check_hash_chain_integrity("t1")
        # `int(row[1]) if row[1] else 0` -> 0
        assert check.status == "pass"

    def test_has_gaps(self, monkeypatch):
        session = _FakeSession(rows=[(100, 3)])
        _set_db(monkeypatch, session)
        check = _check_hash_chain_integrity("t1")
        assert check.status == "fail"
        assert "3 gap(s)" in check.details

    def test_sql_error(self, monkeypatch):
        session = _FakeSession(raises=[SQLAlchemyError("oops")])
        _set_db(monkeypatch, session)
        check = _check_hash_chain_integrity("t1")
        assert check.status == "warn"
        assert "Hash chain check error" in check.details


# ---------------------------------------------------------------------------
# _check_export_completeness
# ---------------------------------------------------------------------------


class TestCheckExportCompleteness:
    def test_no_db(self, monkeypatch):
        _set_db(monkeypatch, None)
        check = _check_export_completeness("t1")
        assert check.status == "warn"

    def test_no_exports(self, monkeypatch):
        session = _FakeSession(rows=[(0, None)])
        _set_db(monkeypatch, session)
        check = _check_export_completeness("t1")
        assert check.status == "warn"
        assert "No exports" in check.details

    def test_has_exports(self, monkeypatch):
        session = _FakeSession(rows=[(5, "2026-04-18")])
        _set_db(monkeypatch, session)
        check = _check_export_completeness("t1")
        assert check.status == "pass"
        assert "5 export(s)" in check.details

    def test_sql_error(self, monkeypatch):
        session = _FakeSession(raises=[SQLAlchemyError("err")])
        _set_db(monkeypatch, session)
        check = _check_export_completeness("t1")
        assert check.status == "warn"
        assert "Export check error" in check.details


# ---------------------------------------------------------------------------
# _check_data_volume
# ---------------------------------------------------------------------------


class TestCheckDataVolume:
    def test_no_db(self, monkeypatch):
        _set_db(monkeypatch, None)
        check, info = _check_data_volume("t1")
        assert check.status == "warn"
        assert info == {"total_events": 0, "total_tlcs": 0, "date_range_days": 0}

    def test_empty(self, monkeypatch):
        session = _FakeSession(rows=[(0, 0, 0)])
        _set_db(monkeypatch, session)
        check, info = _check_data_volume("t1")
        assert check.status == "warn"
        assert info["total_events"] == 0

    def test_success(self, monkeypatch):
        session = _FakeSession(rows=[(1500, 12, 30.0)])
        _set_db(monkeypatch, session)
        check, info = _check_data_volume("t1")
        assert check.status == "pass"
        assert info == {"total_events": 1500, "total_tlcs": 12, "date_range_days": 30}

    def test_null_days(self, monkeypatch):
        session = _FakeSession(rows=[(100, 2, None)])
        _set_db(monkeypatch, session)
        check, info = _check_data_volume("t1")
        assert check.status == "pass"
        assert info["date_range_days"] == 0

    def test_sql_error(self, monkeypatch):
        session = _FakeSession(raises=[SQLAlchemyError("bad")])
        _set_db(monkeypatch, session)
        check, info = _check_data_volume("t1")
        assert check.status == "warn"
        assert "Data volume check error" in check.details
        assert info == {"total_events": 0, "total_tlcs": 0, "date_range_days": 0}


# ---------------------------------------------------------------------------
# _check_supplier_health
# ---------------------------------------------------------------------------


class TestCheckSupplierHealth:
    def test_no_db(self, monkeypatch):
        _set_db(monkeypatch, None)
        check = _check_supplier_health("t1")
        assert check.status == "warn"

    def test_no_suppliers(self, monkeypatch):
        session = _FakeSession(rows=[(0, 0)])
        _set_db(monkeypatch, session)
        check = _check_supplier_health("t1")
        assert check.status == "warn"
        assert "No suppliers" in check.details

    def test_healthy_pass(self, monkeypatch):
        session = _FakeSession(rows=[(10, 9)])  # 90%
        _set_db(monkeypatch, session)
        check = _check_supplier_health("t1")
        assert check.status == "pass"
        assert "9/10" in check.details

    def test_mid_warn(self, monkeypatch):
        session = _FakeSession(rows=[(10, 6)])  # 60%
        _set_db(monkeypatch, session)
        check = _check_supplier_health("t1")
        assert check.status == "warn"

    def test_low_fail(self, monkeypatch):
        session = _FakeSession(rows=[(10, 3)])  # 30%
        _set_db(monkeypatch, session)
        check = _check_supplier_health("t1")
        assert check.status == "fail"

    def test_null_active_count(self, monkeypatch):
        session = _FakeSession(rows=[(10, None)])
        _set_db(monkeypatch, session)
        check = _check_supplier_health("t1")
        # `int(row[1]) if row[1] else 0` -> 0
        assert check.status == "fail"

    def test_sql_error(self, monkeypatch):
        session = _FakeSession(raises=[SQLAlchemyError("err")])
        _set_db(monkeypatch, session)
        check = _check_supplier_health("t1")
        assert check.status == "warn"
        assert "Supplier health check error" in check.details


# ---------------------------------------------------------------------------
# _estimate_recovery_time
# ---------------------------------------------------------------------------


class TestEstimateRecoveryTime:
    def test_zero_events(self):
        assert _estimate_recovery_time({"total_events": 0}) == "< 5m"

    def test_missing_key_defaults_to_zero(self):
        assert _estimate_recovery_time({}) == "< 5m"

    def test_low_events_min_five(self):
        assert _estimate_recovery_time({"total_events": 1000}) == "5m"

    def test_below_hour(self):
        assert _estimate_recovery_time({"total_events": 300000}) == "30m"

    def test_over_hour(self):
        # 700k events -> 70 min -> 1h 10m
        assert _estimate_recovery_time({"total_events": 700000}) == "1h 10m"

    def test_exactly_one_hour(self):
        # 600k events -> 60 min -> 1h 0m
        assert _estimate_recovery_time({"total_events": 600000}) == "1h 0m"

    def test_very_large(self):
        # 6_000_000 events -> 600 min -> 10h 0m
        assert _estimate_recovery_time({"total_events": 6_000_000}) == "10h 0m"


# ---------------------------------------------------------------------------
# _compile_recommendations
# ---------------------------------------------------------------------------


def _chk(name, status):
    return DRCheck(name=name, status=status, details="", checked_at="t")


class TestCompileRecommendations:
    def test_all_pass_returns_default(self):
        recs = _compile_recommendations([_chk("database_connectivity", "pass")])
        assert len(recs) == 1
        assert "All checks passed" in recs[0]

    def test_fail_database(self):
        recs = _compile_recommendations([_chk("database_connectivity", "fail")])
        assert any("Restore database" in r for r in recs)

    def test_fail_hash_chain(self):
        recs = _compile_recommendations([_chk("hash_chain_integrity", "fail")])
        assert any("hash chain gaps" in r for r in recs)

    def test_fail_supplier(self):
        recs = _compile_recommendations([_chk("supplier_network_health", "fail")])
        assert any("Re-engage" in r for r in recs)

    def test_warn_export(self):
        recs = _compile_recommendations([_chk("export_completeness", "warn")])
        assert any("regular data exports" in r for r in recs)

    def test_warn_data_volume(self):
        recs = _compile_recommendations([_chk("data_volume", "warn")])
        assert any("event ingestion pipeline" in r for r in recs)

    def test_warn_hash_chain(self):
        recs = _compile_recommendations([_chk("hash_chain_integrity", "warn")])
        assert any("hash chain audit" in r for r in recs)

    def test_warn_supplier(self):
        recs = _compile_recommendations([_chk("supplier_network_health", "warn")])
        assert any("active supplier participation" in r for r in recs)

    def test_multiple_checks(self):
        recs = _compile_recommendations([
            _chk("database_connectivity", "fail"),
            _chk("hash_chain_integrity", "fail"),
            _chk("export_completeness", "warn"),
        ])
        assert any("Restore database" in r for r in recs)
        assert any("hash chain gaps" in r for r in recs)
        assert any("regular data exports" in r for r in recs)

    def test_pass_status_ignored(self):
        recs = _compile_recommendations([
            _chk("database_connectivity", "pass"),
            _chk("hash_chain_integrity", "pass"),
        ])
        # Pass status never adds recs, so default fallback applies
        assert len(recs) == 1
        assert "All checks passed" in recs[0]


# ---------------------------------------------------------------------------
# _overall_status
# ---------------------------------------------------------------------------


class TestOverallStatus:
    def test_all_pass(self):
        assert _overall_status([_chk("x", "pass"), _chk("y", "pass")]) == "ready"

    def test_one_fail(self):
        assert _overall_status([_chk("x", "fail"), _chk("y", "pass")]) == "at_risk"

    def test_two_fail(self):
        assert _overall_status([_chk("x", "fail"), _chk("y", "fail")]) == "critical"

    def test_three_warn(self):
        assert (
            _overall_status([_chk("x", "warn"), _chk("y", "warn"), _chk("z", "warn")])
            == "at_risk"
        )

    def test_two_warn_is_ready(self):
        assert _overall_status([_chk("x", "warn"), _chk("y", "warn")]) == "ready"

    def test_many_fails_and_warns_critical(self):
        assert (
            _overall_status([
                _chk("a", "fail"),
                _chk("b", "fail"),
                _chk("c", "warn"),
            ])
            == "critical"
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


class _CountedSession:
    """Returns pre-seeded rows in call-order; count must match module usage."""

    def __init__(self, rows: list[Optional[tuple]]):
        self.rows = list(rows)
        self.closed = False

    def execute(self, stmt, params=None):
        return _FakeResult(self.rows.pop(0) if self.rows else None)

    def close(self):
        self.closed = True


class TestReadinessEndpoint:
    def test_all_pass_flow(self, monkeypatch):
        # Each check calls get_db_safe() once; we need a fresh session each call
        def factory():
            return _CountedSession([
                (1,),              # SELECT 1
                ("streaming",),    # replication
            ])

        # Different helpers call get_db_safe separately → need separate mocks
        calls = {"n": 0}
        sessions = [
            _CountedSession([(1,), ("streaming",)]),   # db connectivity
            _CountedSession([(100, 0)]),               # hash chain
            _CountedSession([(5, "2026-04-18")]),      # export
            _CountedSession([(1500, 12, 30.0)]),       # data volume
            _CountedSession([(10, 9)]),                # supplier
        ]

        def _next():
            s = sessions[calls["n"]]
            calls["n"] += 1
            return s

        monkeypatch.setattr(dr, "get_db_safe", _next)

        client = TestClient(_build_app())
        resp = client.get("/api/v1/dr/t1/readiness")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        assert body["overall_status"] == "ready"
        assert len(body["checks"]) == 5
        names = {c["name"] for c in body["checks"]}
        assert {
            "database_connectivity",
            "hash_chain_integrity",
            "export_completeness",
            "data_volume",
            "supplier_network_health",
        }.issubset(names)

    def test_all_checks_db_unavailable(self, monkeypatch):
        monkeypatch.setattr(dr, "get_db_safe", lambda: None)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/dr/t1/readiness")
        assert resp.status_code == 200
        body = resp.json()
        # db check fails, others warn → 1 fail + 4 warn -> at_risk
        assert body["overall_status"] == "at_risk"
        assert body["recovery_time_estimate"] == "< 5m"


class TestBackupStatusEndpoint:
    def test_normal_flow(self, monkeypatch):
        sessions = [
            _CountedSession([(1,), ("streaming",)]),   # db
            _CountedSession([(3, "2026-04-18")]),      # export
            _CountedSession([(200, 5, 10.0)]),         # volume
        ]
        it = iter(sessions)
        monkeypatch.setattr(dr, "get_db_safe", lambda: next(it))

        client = TestClient(_build_app())
        resp = client.get("/api/v1/dr/t1/backup-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        assert body["database"]["status"] == "pass"
        assert body["exports"]["status"] == "pass"
        assert body["data_volume"]["total_events"] == 200
        assert "checked_at" in body

    def test_db_unavailable(self, monkeypatch):
        monkeypatch.setattr(dr, "get_db_safe", lambda: None)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/dr/t1/backup-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["database"]["status"] == "fail"
        assert body["data_volume"]["total_events"] == 0


class TestRecoverySimulationEndpoint:
    def test_successful_recovery(self, monkeypatch):
        sessions = [
            _CountedSession([(1500, 12, 30.0)]),       # data volume
            _CountedSession([(100, 0)]),               # hash chain
            _CountedSession([(85.5,)]),                # KDE
        ]
        it = iter(sessions)
        monkeypatch.setattr(dr, "get_db_safe", lambda: next(it))

        client = TestClient(_build_app())
        resp = client.post("/api/v1/dr/t1/test-recovery")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        names = [c["name"] for c in body["checks"]]
        assert "data_volume" in names
        assert "re_export_estimate" in names
        assert "hash_chain_integrity" in names
        assert "chain_rebuild_feasibility" in names
        assert "kde_recovery_completeness" in names
        kde = next(c for c in body["checks"] if c["name"] == "kde_recovery_completeness")
        assert kde["status"] == "pass"
        assert "85.5" in kde["details"]

    def test_chain_failure_blocks_rebuild(self, monkeypatch):
        sessions = [
            _CountedSession([(1000, 10, 5.0)]),        # data volume
            _CountedSession([(50, 5)]),                # hash chain: gaps → fail
            _CountedSession([(None,)]),                # KDE: row exists but value is None
        ]
        it = iter(sessions)
        monkeypatch.setattr(dr, "get_db_safe", lambda: next(it))

        client = TestClient(_build_app())
        resp = client.post("/api/v1/dr/t1/test-recovery")
        assert resp.status_code == 200
        body = resp.json()
        rebuild = next(c for c in body["checks"] if c["name"] == "chain_rebuild_feasibility")
        assert rebuild["status"] == "fail"
        kde = next(c for c in body["checks"] if c["name"] == "kde_recovery_completeness")
        assert kde["status"] == "warn"
        assert "No KDE completeness data" in kde["details"]

    def test_kde_low_average(self, monkeypatch):
        sessions = [
            _CountedSession([(500, 5, 2.0)]),
            _CountedSession([(50, 0)]),                # hash chain: pass
            _CountedSession([(45.0,)]),                # KDE: < 80 → warn
        ]
        it = iter(sessions)
        monkeypatch.setattr(dr, "get_db_safe", lambda: next(it))

        client = TestClient(_build_app())
        resp = client.post("/api/v1/dr/t1/test-recovery")
        assert resp.status_code == 200
        body = resp.json()
        kde = next(c for c in body["checks"] if c["name"] == "kde_recovery_completeness")
        assert kde["status"] == "warn"
        assert "45.0" in kde["details"]

    def test_kde_sql_error(self, monkeypatch):
        calls = {"n": 0}

        def _db():
            calls["n"] += 1
            if calls["n"] == 1:
                return _CountedSession([(1000, 5, 2.0)])
            if calls["n"] == 2:
                return _CountedSession([(50, 0)])
            # Third call is the KDE query — raise on execute
            class _RaisingSession:
                closed = False
                def execute(self, *a, **k):
                    raise SQLAlchemyError("kde boom")
                def close(self):
                    self.closed = True
            return _RaisingSession()

        monkeypatch.setattr(dr, "get_db_safe", _db)

        client = TestClient(_build_app())
        resp = client.post("/api/v1/dr/t1/test-recovery")
        assert resp.status_code == 200
        body = resp.json()
        kde = next(c for c in body["checks"] if c["name"] == "kde_recovery_completeness")
        assert kde["status"] == "warn"
        assert "KDE check error" in kde["details"]

    def test_kde_db_unavailable(self, monkeypatch):
        calls = {"n": 0}
        sessions = [
            _CountedSession([(1000, 5, 2.0)]),  # volume
            _CountedSession([(50, 0)]),          # chain
        ]

        def _db():
            if calls["n"] < len(sessions):
                s = sessions[calls["n"]]
                calls["n"] += 1
                return s
            calls["n"] += 1
            return None  # KDE: no DB

        monkeypatch.setattr(dr, "get_db_safe", _db)

        client = TestClient(_build_app())
        resp = client.post("/api/v1/dr/t1/test-recovery")
        assert resp.status_code == 200
        body = resp.json()
        kde = next(c for c in body["checks"] if c["name"] == "kde_recovery_completeness")
        assert kde["status"] == "warn"
        assert "database unavailable" in kde["details"]

    def test_zero_events_flags_re_export_warn(self, monkeypatch):
        sessions = [
            _CountedSession([(0, 0, 0)]),              # zero events → warn
            _CountedSession([(100, 0)]),
            _CountedSession([(90.0,)]),
        ]
        it = iter(sessions)
        monkeypatch.setattr(dr, "get_db_safe", lambda: next(it))

        client = TestClient(_build_app())
        resp = client.post("/api/v1/dr/t1/test-recovery")
        assert resp.status_code == 200
        body = resp.json()
        re_export = next(c for c in body["checks"] if c["name"] == "re_export_estimate")
        assert re_export["status"] == "warn"


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert router.prefix == "/api/v1/dr"

    def test_tags(self):
        assert "Disaster Recovery" in router.tags

    def test_endpoints_registered(self):
        paths = {route.path for route in router.routes}
        assert "/api/v1/dr/{tenant_id}/readiness" in paths
        assert "/api/v1/dr/{tenant_id}/backup-status" in paths
        assert "/api/v1/dr/{tenant_id}/test-recovery" in paths
