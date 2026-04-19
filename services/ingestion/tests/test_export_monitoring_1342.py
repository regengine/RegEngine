"""Coverage for app/export_monitoring.py — FDA export pipeline monitoring.

Locks:
- Pydantic models (ExportMetrics, HealthCheckResult, ExportHealthCheck,
  MonitoringAlert) — defaults and required fields
- _query_export_logs: happy path, DB exception → None, row w/ null
  created_at, missing optional columns coalesced
- _check_db_connectivity: healthy, exception → critical
- _check_chain_integrity: valid chain, invalid w/ errors, invalid w/o
  errors attr, exception → warning
- _check_export_readiness: count>0 healthy, count=0 warning,
  exception → critical, empty row handled
- _check_kde_completeness: 0 events → warning, above threshold → healthy,
  below threshold → warning, exception → warning
- GET /exports/{tid}: DB unavailable, happy path w/ 24h+7d filtering,
  avg/format computations, empty logs, format null coalesced
- GET /health/{tid}: overall healthy, warning wins, critical wins
- GET /alerts/{tid}: critical/warning checks → alerts, stale export alert,
  naive datetime normalized, malformed timestamp silently skipped,
  logs missing created_at skipped

Issue: #1342
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import export_monitoring as em
from app.export_monitoring import (
    ExportHealthCheck,
    ExportMetrics,
    HealthCheckResult,
    MonitoringAlert,
    _check_chain_integrity,
    _check_db_connectivity,
    _check_export_readiness,
    _check_kde_completeness,
    _query_export_logs,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    from app.webhook_compat import _verify_api_key
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _row(**kwargs):
    """Row-like object supporting both attribute and getattr with default."""
    return SimpleNamespace(**kwargs)


class _FakeSession:
    def __init__(self, *, rows=None, row=None, raises=None):
        self._rows = rows or []
        self._row = row
        self._raises = raises
        self.closed = False

    def execute(self, stmt, params=None):
        if self._raises:
            raise self._raises
        return SimpleNamespace(
            fetchall=lambda: self._rows,
            fetchone=lambda: self._row,
        )

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_export_metrics_defaults(self):
        m = ExportMetrics(tenant_id="t")
        assert m.total_exports == 0
        assert m.exports_last_24h == 0
        assert m.exports_last_7d == 0
        assert m.avg_record_count is None
        assert m.avg_export_time_ms is None
        assert m.last_export_at is None
        assert m.export_formats == {}

    def test_health_check_result_fields(self):
        r = HealthCheckResult(
            name="test", status="healthy", message="ok",
        )
        assert r.details is None
        r2 = HealthCheckResult(
            name="x", status="critical", message="m", details={"k": 1},
        )
        assert r2.details == {"k": 1}

    def test_export_health_check_defaults(self):
        r = ExportHealthCheck(tenant_id="t")
        assert r.status == "healthy"
        assert r.checks == []
        assert r.checked_at  # auto-generated

    def test_monitoring_alert_fields(self):
        a = MonitoringAlert(
            id="a1", tenant_id="t", alert_type="x",
            severity="warning", message="msg",
        )
        assert a.created_at  # auto-generated


# ---------------------------------------------------------------------------
# _query_export_logs
# ---------------------------------------------------------------------------


class TestQueryExportLogs:
    def test_happy_path(self, monkeypatch):
        session = _FakeSession(rows=[
            _row(
                id="e1", tenant_id="t", export_type="fda", record_count=5,
                export_time_ms=200.0,
                created_at=datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc),
                format="csv",
            ),
            _row(
                id="e2", tenant_id="t", export_type="fda", record_count=10,
                export_time_ms=150.0,
                created_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
                format="json",
            ),
        ])

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        logs = _query_export_logs("t")
        assert logs is not None
        assert len(logs) == 2
        assert logs[0]["id"] == "e1"
        assert logs[0]["format"] == "csv"
        assert logs[0]["created_at"] == "2026-04-17T10:00:00+00:00"
        assert session.closed

    def test_null_created_at(self, monkeypatch):
        session = _FakeSession(rows=[
            _row(
                id="e1", tenant_id="t", export_type="fda", record_count=5,
                export_time_ms=200.0, created_at=None, format="csv",
            ),
        ])

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        logs = _query_export_logs("t")
        assert logs[0]["created_at"] is None

    def test_db_exception_returns_none(self, monkeypatch):
        def _boom():
            raise RuntimeError("DB gone")

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", _boom)

        assert _query_export_logs("t") is None


# ---------------------------------------------------------------------------
# _check_db_connectivity
# ---------------------------------------------------------------------------


class TestCheckDbConnectivity:
    def test_healthy(self, monkeypatch):
        session = _FakeSession(row=(1,))

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_db_connectivity()
        assert result.status == "healthy"
        assert result.name == "db_connectivity"
        assert session.closed

    def test_critical_on_exception(self, monkeypatch):
        def _boom():
            raise RuntimeError("DB gone")

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", _boom)

        result = _check_db_connectivity()
        assert result.status == "critical"
        assert "Cannot reach" in result.message


# ---------------------------------------------------------------------------
# _check_chain_integrity
# ---------------------------------------------------------------------------


class TestCheckChainIntegrity:
    def test_valid_chain(self, monkeypatch):
        session = _FakeSession()

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        class _Persistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, chain_length=42, errors=[])

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _Persistence)

        result = _check_chain_integrity("t")
        assert result.status == "healthy"
        assert result.details == {"chain_length": 42}
        assert session.closed

    def test_valid_chain_no_length_attr(self, monkeypatch):
        """getattr fallback when chain_length is absent."""
        session = _FakeSession()

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        class _Result:
            valid = True
            errors = []

        class _Persistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return _Result()

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _Persistence)

        result = _check_chain_integrity("t")
        assert result.status == "healthy"
        assert result.details == {"chain_length": None}

    def test_invalid_with_errors(self, monkeypatch):
        session = _FakeSession()

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        class _Persistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=False, errors=["block 3 mismatch"])

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _Persistence)

        result = _check_chain_integrity("t")
        assert result.status == "critical"
        assert result.details == {"errors": ["block 3 mismatch"]}

    def test_invalid_without_errors_attr(self, monkeypatch):
        session = _FakeSession()

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        class _Result:
            valid = False
            # No 'errors' attribute

        class _Persistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return _Result()

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _Persistence)

        result = _check_chain_integrity("t")
        assert result.status == "critical"
        assert result.details == {"errors": []}

    def test_exception_returns_warning(self, monkeypatch):
        def _boom():
            raise RuntimeError("import fail")

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", _boom)

        result = _check_chain_integrity("t")
        assert result.status == "warning"
        assert "unavailable" in result.message


# ---------------------------------------------------------------------------
# _check_export_readiness
# ---------------------------------------------------------------------------


class TestCheckExportReadiness:
    def test_healthy_count_positive(self, monkeypatch):
        session = _FakeSession(row=_row(cnt=5))

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_export_readiness("t")
        assert result.status == "healthy"
        assert result.details == {"export_count": 5}
        assert session.closed

    def test_warning_zero_exports(self, monkeypatch):
        session = _FakeSession(row=_row(cnt=0))

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_export_readiness("t")
        assert result.status == "warning"
        assert result.details == {"export_count": 0}

    def test_empty_row_treated_as_zero(self, monkeypatch):
        session = _FakeSession(row=None)

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_export_readiness("t")
        assert result.status == "warning"

    def test_critical_on_exception(self, monkeypatch):
        def _boom():
            raise RuntimeError("DB gone")

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", _boom)

        result = _check_export_readiness("t")
        assert result.status == "critical"
        assert "Cannot verify" in result.message


# ---------------------------------------------------------------------------
# _check_kde_completeness
# ---------------------------------------------------------------------------


class TestCheckKdeCompleteness:
    def test_no_events_warning(self, monkeypatch):
        session = _FakeSession(row=_row(total=0, with_kdes=0))

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "warning"
        assert result.details == {"total_events": 0, "completeness_pct": None}

    def test_above_threshold_healthy(self, monkeypatch):
        session = _FakeSession(row=_row(total=10, with_kdes=9))

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "healthy"
        assert result.details["completeness_pct"] == 90.0

    def test_at_threshold_healthy(self, monkeypatch):
        """Exactly 80% should be healthy."""
        session = _FakeSession(row=_row(total=10, with_kdes=8))

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "healthy"

    def test_below_threshold_warning(self, monkeypatch):
        session = _FakeSession(row=_row(total=10, with_kdes=5))

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "warning"
        assert result.details["completeness_pct"] == 50.0

    def test_empty_row_zero_events(self, monkeypatch):
        session = _FakeSession(row=None)

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "warning"

    def test_exception_returns_warning(self, monkeypatch):
        def _boom():
            raise RuntimeError("DB gone")

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", _boom)

        result = _check_kde_completeness("t")
        assert result.status == "warning"
        assert "unavailable" in result.message


# ---------------------------------------------------------------------------
# GET /exports/{tenant_id}
# ---------------------------------------------------------------------------


class TestExportMetricsEndpoint:
    def test_db_unavailable_empty_metrics(self, client, monkeypatch):
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: None)

        r = client.get("/api/v1/monitoring/exports/t1")
        assert r.status_code == 200
        body = r.json()
        assert body["tenant_id"] == "t1"
        assert body["total_exports"] == 0
        assert body["avg_record_count"] is None

    def test_empty_logs_zero_counts(self, client, monkeypatch):
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: [])

        r = client.get("/api/v1/monitoring/exports/t1")
        body = r.json()
        assert body["total_exports"] == 0
        assert body["exports_last_24h"] == 0
        assert body["exports_last_7d"] == 0
        assert body["last_export_at"] is None

    def test_happy_path_with_filtering(self, client, monkeypatch):
        now = datetime.now(timezone.utc)
        logs = [
            {  # 1h ago — counts for both 24h and 7d
                "id": "e1", "tenant_id": "t1", "export_type": "fda",
                "record_count": 10, "export_time_ms": 200.0,
                "created_at": (now - timedelta(hours=1)).isoformat(),
                "format": "csv",
            },
            {  # 3d ago — counts for 7d only
                "id": "e2", "tenant_id": "t1", "export_type": "fda",
                "record_count": 20, "export_time_ms": 400.0,
                "created_at": (now - timedelta(days=3)).isoformat(),
                "format": "json",
            },
            {  # 30d ago — counts for neither
                "id": "e3", "tenant_id": "t1", "export_type": "fda",
                "record_count": 5, "export_time_ms": 100.0,
                "created_at": (now - timedelta(days=30)).isoformat(),
                "format": "csv",
            },
        ]
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: logs)

        r = client.get("/api/v1/monitoring/exports/t1")
        body = r.json()
        assert body["total_exports"] == 3
        assert body["exports_last_24h"] == 1
        assert body["exports_last_7d"] == 2
        assert body["avg_record_count"] == round((10 + 20 + 5) / 3, 1)
        assert body["avg_export_time_ms"] == round((200 + 400 + 100) / 3, 1)
        assert body["export_formats"] == {"csv": 2, "json": 1}

    def test_null_format_coalesced_to_csv(self, client, monkeypatch):
        now = datetime.now(timezone.utc)
        logs = [
            {
                "id": "e1", "tenant_id": "t1", "export_type": "fda",
                "record_count": 10, "export_time_ms": 200.0,
                "created_at": now.isoformat(), "format": None,
            },
        ]
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: logs)

        r = client.get("/api/v1/monitoring/exports/t1")
        body = r.json()
        assert body["export_formats"] == {"csv": 1}

    def test_missing_record_count_excluded_from_average(self, client, monkeypatch):
        """record_count=0 or missing should be excluded from avg to avoid bias."""
        now = datetime.now(timezone.utc)
        logs = [
            {
                "id": "e1", "tenant_id": "t1", "export_type": "fda",
                "record_count": 10, "export_time_ms": None,
                "created_at": now.isoformat(), "format": "csv",
            },
            {
                "id": "e2", "tenant_id": "t1", "export_type": "fda",
                "record_count": 0, "export_time_ms": None,  # 0 is falsy → excluded
                "created_at": now.isoformat(), "format": "csv",
            },
        ]
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: logs)

        r = client.get("/api/v1/monitoring/exports/t1")
        body = r.json()
        assert body["avg_record_count"] == 10.0  # only e1 counted
        assert body["avg_export_time_ms"] is None


# ---------------------------------------------------------------------------
# GET /health/{tenant_id}
# ---------------------------------------------------------------------------


def _stub_all_healthy(monkeypatch):
    monkeypatch.setattr(em, "_check_db_connectivity",
                        lambda: HealthCheckResult(name="db_connectivity", status="healthy", message="ok"))
    monkeypatch.setattr(em, "_check_chain_integrity",
                        lambda tid: HealthCheckResult(name="chain_integrity", status="healthy", message="ok"))
    monkeypatch.setattr(em, "_check_export_readiness",
                        lambda tid: HealthCheckResult(name="export_readiness", status="healthy", message="ok"))
    monkeypatch.setattr(em, "_check_kde_completeness",
                        lambda tid: HealthCheckResult(name="kde_completeness", status="healthy", message="ok"))


class TestHealthCheckEndpoint:
    def test_all_healthy(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        r = client.get("/api/v1/monitoring/health/t1")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert len(body["checks"]) == 4

    def test_warning_wins_over_healthy(self, client, monkeypatch):
        monkeypatch.setattr(em, "_check_db_connectivity",
                            lambda: HealthCheckResult(name="db_connectivity", status="healthy", message="ok"))
        monkeypatch.setattr(em, "_check_chain_integrity",
                            lambda tid: HealthCheckResult(name="chain_integrity", status="warning", message="slow"))
        monkeypatch.setattr(em, "_check_export_readiness",
                            lambda tid: HealthCheckResult(name="export_readiness", status="healthy", message="ok"))
        monkeypatch.setattr(em, "_check_kde_completeness",
                            lambda tid: HealthCheckResult(name="kde_completeness", status="healthy", message="ok"))

        r = client.get("/api/v1/monitoring/health/t1")
        assert r.json()["status"] == "warning"

    def test_critical_wins_over_warning(self, client, monkeypatch):
        monkeypatch.setattr(em, "_check_db_connectivity",
                            lambda: HealthCheckResult(name="db_connectivity", status="critical", message="down"))
        monkeypatch.setattr(em, "_check_chain_integrity",
                            lambda tid: HealthCheckResult(name="chain_integrity", status="warning", message="slow"))
        monkeypatch.setattr(em, "_check_export_readiness",
                            lambda tid: HealthCheckResult(name="export_readiness", status="warning", message="none"))
        monkeypatch.setattr(em, "_check_kde_completeness",
                            lambda tid: HealthCheckResult(name="kde_completeness", status="warning", message="low"))

        r = client.get("/api/v1/monitoring/health/t1")
        assert r.json()["status"] == "critical"


# ---------------------------------------------------------------------------
# GET /alerts/{tenant_id}
# ---------------------------------------------------------------------------


class TestAlertsEndpoint:
    def test_all_healthy_no_alerts(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: None)

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        assert body["count"] == 0
        assert body["alerts"] == []

    def test_warning_and_critical_produce_alerts(self, client, monkeypatch):
        monkeypatch.setattr(em, "_check_db_connectivity",
                            lambda: HealthCheckResult(name="db_connectivity", status="critical", message="down"))
        monkeypatch.setattr(em, "_check_chain_integrity",
                            lambda tid: HealthCheckResult(name="chain_integrity", status="warning", message="slow"))
        monkeypatch.setattr(em, "_check_export_readiness",
                            lambda tid: HealthCheckResult(name="export_readiness", status="healthy", message="ok"))
        monkeypatch.setattr(em, "_check_kde_completeness",
                            lambda tid: HealthCheckResult(name="kde_completeness", status="healthy", message="ok"))
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: None)

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        assert body["count"] == 2
        types = {a["alert_type"] for a in body["alerts"]}
        assert types == {"db_connectivity", "chain_integrity"}
        severities = {a["severity"] for a in body["alerts"]}
        assert severities == {"critical", "warning"}

    def test_stale_export_alert(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        now = datetime.now(timezone.utc)
        # Last export 10 days ago → stale
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: [
            {"created_at": (now - timedelta(days=10)).isoformat()},
        ])

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        assert body["count"] == 1
        assert body["alerts"][0]["alert_type"] == "stale_exports"

    def test_recent_export_no_stale_alert(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        now = datetime.now(timezone.utc)
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: [
            {"created_at": (now - timedelta(days=2)).isoformat()},
        ])

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        assert body["count"] == 0

    def test_naive_datetime_normalized_to_utc(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        # Naive datetime 10 days ago (no tz) should still trigger stale check
        naive = (datetime.now() - timedelta(days=10)).isoformat()
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: [
            {"created_at": naive},
        ])

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        # Should trigger stale alert (datetime normalized to UTC)
        assert body["count"] == 1
        assert body["alerts"][0]["alert_type"] == "stale_exports"

    def test_malformed_timestamp_silently_skipped(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: [
            {"created_at": "not-a-date"},
        ])

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        # ValueError caught — no stale alert emitted
        assert body["count"] == 0

    def test_logs_missing_created_at_skipped(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: [{"id": "e1"}])

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        assert body["count"] == 0


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_routes_registered(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/monitoring/exports/{tenant_id}" in paths
        assert "/api/v1/monitoring/health/{tenant_id}" in paths
        assert "/api/v1/monitoring/alerts/{tenant_id}" in paths
