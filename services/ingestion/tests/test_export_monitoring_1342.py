"""Coverage for app/export_monitoring.py — FDA export pipeline monitoring.

Locks:
- Pydantic models (ExportMetrics, HealthCheckResult, ExportHealthCheck,
  MonitoringAlert) — defaults and required fields
- _query_export_logs: happy path, DB exception → None, row w/ null
  generated_at, statement names only real fsma.fda_export_log columns
- _check_db_connectivity: healthy, exception → critical
- _check_chain_integrity: valid chain, invalid w/ errors, invalid w/o
  errors attr, exception → warning
- _check_export_readiness: count>0 healthy, count=0 warning,
  exception → critical, empty row handled
- _check_kde_completeness: 0 events → warning, above threshold → healthy,
  below threshold → warning, unchecked-type events named, exception →
  warning, reads fsma.cte_events / fsma.cte_kdes for the tenant
- GET /exports/{tid}: DB unavailable, happy path w/ 24h+7d filtering,
  avg/type computations, empty logs, export_type null counted as unknown
- GET /health/{tid}: overall healthy, warning wins, critical wins
- GET /alerts/{tid}: critical/warning checks → alerts, stale export alert,
  naive datetime normalized, malformed timestamp silently skipped,
  logs missing generated_at skipped

Issue: #1342
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app import export_monitoring as em
from app.compliance_score import _required_fields_for
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
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    from app.webhook_compat import _verify_api_key

    from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override

    bypass = lambda: None
    app.dependency_overrides[_verify_api_key] = bypass
    install_tenant_context_override(app)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _row(**kwargs):
    """Row-like object supporting both attribute and getattr with default."""
    return SimpleNamespace(**kwargs)


class _FakeSession:
    def __init__(self, *, rows=None, row=None, raises=None, results=None):
        self._rows = rows or []
        self._row = row
        self._raises = raises
        self._results = list(results or [])  # per-call fetchall() results, consumed in order
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), dict(params or {})))
        if self._raises:
            raise self._raises
        rows = self._results.pop(0) if self._results else self._rows
        return SimpleNamespace(
            fetchall=lambda: rows,
            fetchone=lambda: self._row,
        )

    def close(self):
        self.closed = True


def _ddl_columns(sql_file: str, table: str) -> set[str]:
    """Column names of ``table`` as declared in an ``alembic/sql`` file."""
    ddl = (Path(__file__).resolve().parents[3] / "alembic/sql" / sql_file).read_text()
    body = ddl.split(f"CREATE TABLE IF NOT EXISTS {table} (", 1)[1].split("\n);", 1)[0]
    return set(re.findall(r"^ {4}([a-z_]+) ", body, flags=re.MULTILINE))


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
        assert m.last_export_at is None
        assert m.export_types == {}

    def test_health_check_result_fields(self):
        r = HealthCheckResult(
            name="test",
            status="healthy",
            message="ok",
        )
        assert r.details is None
        r2 = HealthCheckResult(
            name="x",
            status="critical",
            message="m",
            details={"k": 1},
        )
        assert r2.details == {"k": 1}

    def test_export_health_check_defaults(self):
        r = ExportHealthCheck(tenant_id="t")
        assert r.status == "healthy"
        assert r.checks == []
        assert r.checked_at  # auto-generated

    def test_monitoring_alert_fields(self):
        a = MonitoringAlert(
            id="a1",
            tenant_id="t",
            alert_type="x",
            severity="warning",
            message="msg",
        )
        assert a.created_at  # auto-generated


# ---------------------------------------------------------------------------
# _query_export_logs
# ---------------------------------------------------------------------------


class TestQueryExportLogs:
    def test_happy_path(self, monkeypatch):
        session = _FakeSession(
            rows=[
                _row(
                    id="e1",
                    tenant_id="t",
                    export_type="fda_spreadsheet",
                    record_count=5,
                    generated_at=datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc),
                ),
                _row(
                    id="e2",
                    tenant_id="t",
                    export_type="fda_export_all",
                    record_count=10,
                    generated_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
                ),
            ]
        )

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        logs = _query_export_logs("t")
        assert logs is not None
        assert len(logs) == 2
        assert logs[0] == {
            "id": "e1",
            "tenant_id": "t",
            "export_type": "fda_spreadsheet",
            "record_count": 5,
            "generated_at": "2026-04-17T10:00:00+00:00",
        }
        assert session.closed

    def test_generated_at_is_normalised_to_utc(self, monkeypatch):
        """A timestamptz read in another session time zone still compares with the UTC cut-offs."""
        local = timezone(timedelta(hours=-7))
        session = _FakeSession(
            rows=[
                _row(
                    id="e1",
                    tenant_id="t",
                    export_type="fda",
                    record_count=5,
                    generated_at=datetime(2026, 4, 17, 3, 0, tzinfo=local),
                )
            ]
        )

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        logs = _query_export_logs("t")
        assert logs[0]["generated_at"] == "2026-04-17T10:00:00+00:00"

    def test_null_generated_at(self, monkeypatch):
        session = _FakeSession(
            rows=[
                _row(
                    id="e1",
                    tenant_id="t",
                    export_type="fda",
                    record_count=5,
                    generated_at=None,
                ),
            ]
        )

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        logs = _query_export_logs("t")
        assert logs[0]["generated_at"] is None

    def test_statement_references_only_real_columns(self, monkeypatch):
        """The export-log statement names ``fsma.fda_export_log`` columns as V002 declares them.

        It read ``export_time_ms``, ``created_at`` and ``format``. None of
        them exists: the timestamp is ``generated_at``, and no column
        records an export's duration or file format. Postgres raised
        ``UndefinedColumn``, the except returned ``None``, and the metrics
        endpoint reported zero exports for every tenant while the
        stale-export alert never fired. The fake session above never parses
        SQL. ``test_export_monitoring_pg.py`` runs the statement on a live
        cluster; this is the copy that needs no database.
        """
        columns = _ddl_columns("V002__fsma_cte_persistence.sql", "fsma.fda_export_log")
        assert "generated_at" in columns  # the DDL parse itself still works
        assert not {"export_time_ms", "created_at", "format"} & columns

        session = _FakeSession(rows=[])

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)
        _query_export_logs("t")
        sql, params = session.calls[0]

        assert "FROM fsma.fda_export_log" in sql
        assert "WHERE tenant_id = :tenant_id" in sql
        assert params == {"tenant_id": "t"}

        # Keywords are upper-case in the statement, so every lower-case word
        # is an identifier. These are the ones that are not columns.
        not_columns = {"fsma", "fda_export_log"}
        referenced = set(re.findall(r"\b[a-z_]+\b", sql)) - not_columns
        assert referenced <= columns, f"not columns of fsma.fda_export_log: {sorted(referenced - columns)}"

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
            def __init__(self, s):
                pass

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
            def __init__(self, s):
                pass

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
            def __init__(self, s):
                pass

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
            def __init__(self, s):
                pass

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


def _coverage_session(events: int, present: int) -> _FakeSession:
    """Answers the two required-KDE coverage reads: ``events`` shipping events, ``present`` carrying each required field."""
    return _FakeSession(
        results=[
            [("shipping", events)],  # events per CTE type
            [("shipping", field, present) for field in _required_fields_for("shipping")],
        ]
    )


class TestCheckKdeCompleteness:
    def test_no_events_warning(self, monkeypatch):
        session = _FakeSession(results=[[], []])

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "warning"
        assert result.message == "No CTE events found for this tenant."
        assert result.details == {
            "required_fields": 0,
            "present_fields": 0,
            "events_unchecked_type": 0,
            "completeness_pct": None,
        }
        assert session.closed

    def test_above_threshold_healthy(self, monkeypatch):
        session = _coverage_session(events=10, present=9)

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "healthy"
        assert result.details["completeness_pct"] == 90.0
        assert result.details["required_fields"] == 10 * len(_required_fields_for("shipping"))

    def test_at_threshold_healthy(self, monkeypatch):
        """Exactly 80% should be healthy."""
        session = _coverage_session(events=10, present=8)

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "healthy"

    def test_below_threshold_warning(self, monkeypatch):
        session = _coverage_session(events=10, present=5)

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "warning"
        assert result.details["completeness_pct"] == 50.0

    def test_unchecked_event_types_are_named_never_counted_as_covered(self, monkeypatch):
        """Events whose type has no required-KDE checklist are reported, not scored as complete."""
        session = _FakeSession(results=[[("growing", 7)], []])

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        result = _check_kde_completeness("t")
        assert result.status == "warning"
        assert (
            result.message == "No CTE events with a required-KDE checklist; 7 event(s) have no required-KDE checklist."
        )
        assert result.details["events_unchecked_type"] == 7
        assert result.details["completeness_pct"] is None

    def test_statements_read_real_tables_for_the_tenant(self, monkeypatch):
        """The KDE check reads the tenant's ``fsma.cte_events`` / ``fsma.cte_kdes``, not ``kde_data``.

        It counted ``cte_events`` rows ``WHERE kde_data IS NOT NULL``. No
        such column exists — KDEs are ``fsma.cte_kdes`` rows — so Postgres
        raised ``UndefinedColumn`` and the check always reported "check
        unavailable". The measure itself ("event has any KDE") is the one
        #2962 rejected as vacuous; the check now reuses the compliance
        score's required-KDE coverage read, as ``disaster_recovery`` does.
        The fake session never parses SQL; ``test_export_monitoring_pg.py``
        runs it on a live cluster.
        """
        session = _FakeSession(results=[[], []])

        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)
        _check_kde_completeness("t")

        assert len(session.calls) == 2, "the coverage read issues one statement per aggregate"
        assert session.closed
        for sql, params in session.calls:
            # The events table may be aliased; its own tenant bind must not be.
            assert re.search(
                r"FROM fsma\.cte_events(?: (\w+))? WHERE (?:\1\.)?tenant_id = :tid\b",
                " ".join(sql.split()),
            )
            assert "kde_data" not in sql
            assert params == {"tid": "t"}
        assert "fsma.cte_kdes" in session.calls[1][0]

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
                "id": "e1",
                "tenant_id": "t1",
                "export_type": "fda_spreadsheet",
                "record_count": 10,
                "generated_at": (now - timedelta(hours=1)).isoformat(),
            },
            {  # 3d ago — counts for 7d only
                "id": "e2",
                "tenant_id": "t1",
                "export_type": "fda_export_all",
                "record_count": 20,
                "generated_at": (now - timedelta(days=3)).isoformat(),
            },
            {  # 30d ago — counts for neither
                "id": "e3",
                "tenant_id": "t1",
                "export_type": "fda_spreadsheet",
                "record_count": 5,
                "generated_at": (now - timedelta(days=30)).isoformat(),
            },
        ]
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: logs)

        r = client.get("/api/v1/monitoring/exports/t1")
        body = r.json()
        assert body["total_exports"] == 3
        assert body["exports_last_24h"] == 1
        assert body["exports_last_7d"] == 2
        assert body["avg_record_count"] == round((10 + 20 + 5) / 3, 1)
        assert body["last_export_at"] == logs[0]["generated_at"]
        assert body["export_types"] == {"fda_spreadsheet": 2, "fda_export_all": 1}
        assert "avg_export_time_ms" not in body  # no column records an export's duration

    def test_null_export_type_counted_as_unknown(self, client, monkeypatch):
        now = datetime.now(timezone.utc)
        logs = [
            {
                "id": "e1",
                "tenant_id": "t1",
                "export_type": None,
                "record_count": 10,
                "generated_at": now.isoformat(),
            },
        ]
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: logs)

        r = client.get("/api/v1/monitoring/exports/t1")
        body = r.json()
        assert body["export_types"] == {"unknown": 1}

    def test_missing_record_count_excluded_from_average(self, client, monkeypatch):
        """record_count=0 or missing should be excluded from avg to avoid bias."""
        now = datetime.now(timezone.utc)
        logs = [
            {
                "id": "e1",
                "tenant_id": "t1",
                "export_type": "fda",
                "record_count": 10,
                "generated_at": now.isoformat(),
            },
            {
                "id": "e2",
                "tenant_id": "t1",
                "export_type": "fda",
                "record_count": 0,  # 0 is falsy → excluded
                "generated_at": now.isoformat(),
            },
        ]
        monkeypatch.setattr(em, "_query_export_logs", lambda tid: logs)

        r = client.get("/api/v1/monitoring/exports/t1")
        body = r.json()
        assert body["avg_record_count"] == 10.0  # only e1 counted


# ---------------------------------------------------------------------------
# GET /health/{tenant_id}
# ---------------------------------------------------------------------------


def _stub_all_healthy(monkeypatch):
    monkeypatch.setattr(
        em, "_check_db_connectivity", lambda: HealthCheckResult(name="db_connectivity", status="healthy", message="ok")
    )
    monkeypatch.setattr(
        em,
        "_check_chain_integrity",
        lambda tid: HealthCheckResult(name="chain_integrity", status="healthy", message="ok"),
    )
    monkeypatch.setattr(
        em,
        "_check_export_readiness",
        lambda tid: HealthCheckResult(name="export_readiness", status="healthy", message="ok"),
    )
    monkeypatch.setattr(
        em,
        "_check_kde_completeness",
        lambda tid: HealthCheckResult(name="kde_completeness", status="healthy", message="ok"),
    )


class TestHealthCheckEndpoint:
    def test_all_healthy(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        r = client.get("/api/v1/monitoring/health/t1")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert len(body["checks"]) == 4

    def test_warning_wins_over_healthy(self, client, monkeypatch):
        monkeypatch.setattr(
            em,
            "_check_db_connectivity",
            lambda: HealthCheckResult(name="db_connectivity", status="healthy", message="ok"),
        )
        monkeypatch.setattr(
            em,
            "_check_chain_integrity",
            lambda tid: HealthCheckResult(name="chain_integrity", status="warning", message="slow"),
        )
        monkeypatch.setattr(
            em,
            "_check_export_readiness",
            lambda tid: HealthCheckResult(name="export_readiness", status="healthy", message="ok"),
        )
        monkeypatch.setattr(
            em,
            "_check_kde_completeness",
            lambda tid: HealthCheckResult(name="kde_completeness", status="healthy", message="ok"),
        )

        r = client.get("/api/v1/monitoring/health/t1")
        assert r.json()["status"] == "warning"

    def test_critical_wins_over_warning(self, client, monkeypatch):
        monkeypatch.setattr(
            em,
            "_check_db_connectivity",
            lambda: HealthCheckResult(name="db_connectivity", status="critical", message="down"),
        )
        monkeypatch.setattr(
            em,
            "_check_chain_integrity",
            lambda tid: HealthCheckResult(name="chain_integrity", status="warning", message="slow"),
        )
        monkeypatch.setattr(
            em,
            "_check_export_readiness",
            lambda tid: HealthCheckResult(name="export_readiness", status="warning", message="none"),
        )
        monkeypatch.setattr(
            em,
            "_check_kde_completeness",
            lambda tid: HealthCheckResult(name="kde_completeness", status="warning", message="low"),
        )

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
        monkeypatch.setattr(
            em,
            "_check_db_connectivity",
            lambda: HealthCheckResult(name="db_connectivity", status="critical", message="down"),
        )
        monkeypatch.setattr(
            em,
            "_check_chain_integrity",
            lambda tid: HealthCheckResult(name="chain_integrity", status="warning", message="slow"),
        )
        monkeypatch.setattr(
            em,
            "_check_export_readiness",
            lambda tid: HealthCheckResult(name="export_readiness", status="healthy", message="ok"),
        )
        monkeypatch.setattr(
            em,
            "_check_kde_completeness",
            lambda tid: HealthCheckResult(name="kde_completeness", status="healthy", message="ok"),
        )
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
        monkeypatch.setattr(
            em,
            "_query_export_logs",
            lambda tid: [
                {"generated_at": (now - timedelta(days=10)).isoformat()},
            ],
        )

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        assert body["count"] == 1
        assert body["alerts"][0]["alert_type"] == "stale_exports"

    def test_recent_export_no_stale_alert(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        now = datetime.now(timezone.utc)
        monkeypatch.setattr(
            em,
            "_query_export_logs",
            lambda tid: [
                {"generated_at": (now - timedelta(days=2)).isoformat()},
            ],
        )

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        assert body["count"] == 0

    def test_naive_datetime_normalized_to_utc(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        # Naive datetime 10 days ago (no tz) should still trigger stale check
        naive = (datetime.now() - timedelta(days=10)).isoformat()
        monkeypatch.setattr(
            em,
            "_query_export_logs",
            lambda tid: [
                {"generated_at": naive},
            ],
        )

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        # Should trigger stale alert (datetime normalized to UTC)
        assert body["count"] == 1
        assert body["alerts"][0]["alert_type"] == "stale_exports"

    def test_malformed_timestamp_silently_skipped(self, client, monkeypatch):
        _stub_all_healthy(monkeypatch)
        monkeypatch.setattr(
            em,
            "_query_export_logs",
            lambda tid: [
                {"generated_at": "not-a-date"},
            ],
        )

        r = client.get("/api/v1/monitoring/alerts/t1")
        body = r.json()
        # ValueError caught — no stale alert emitted
        assert body["count"] == 0

    def test_logs_missing_generated_at_skipped(self, client, monkeypatch):
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
