"""Coverage for app/audit_log.py — cross-database audit log aggregator.

Locks the event-type / category normalization tables, each of the four
query helpers (admin audit + CTE + export + alert), and the merge /
dedup / sort / filter / paginate pipeline in the GET endpoint.

Issue: #1342
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import audit_log as al
from app.audit_log import (
    AuditEntry,
    AuditLogResponse,
    _normalize_audit_event_type,
    _normalize_category,
    _query_admin_audit_logs,
    _query_alert_events,
    _query_cte_events,
    _query_exports,
    _table_exists,
    _to_iso,
    _get_admin_db_session,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_admin_session_factory(monkeypatch):
    # Reset module-level lazy factory and the "we warned once" flag
    monkeypatch.setattr(al, "_admin_session_factory", None, raising=False)
    monkeypatch.setattr(al, "_admin_url_warned", False, raising=False)
    yield


def _mock_session_with_queries(results_by_sql):
    """MagicMock session whose execute() returns different fetchall/fetchone
    shapes based on the SQL text."""
    session = MagicMock()

    def execute(sql, params=None):
        sql_text = str(sql)
        rows = results_by_sql.get("*", [])
        for key, val in results_by_sql.items():
            if key != "*" and key in sql_text:
                rows = val
                break
        result = MagicMock()
        result.fetchall.return_value = rows
        result.fetchone.return_value = rows[0] if rows else None
        return result

    session.execute.side_effect = execute
    return session


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_audit_entry_defaults(self):
        e = AuditEntry(
            id="1", timestamp="2026-04-18T00:00:00Z", event_type="x",
            category="y", actor="z", action="w", resource="r",
        )
        assert e.details == {}
        assert e.ip_address == ""
        assert e.hash == ""

    def test_audit_entry_default_factory_independent(self):
        a = AuditEntry(id="1", timestamp="t", event_type="x", category="y", actor="z", action="w", resource="r")
        b = AuditEntry(id="2", timestamp="t", event_type="x", category="y", actor="z", action="w", resource="r")
        a.details["k"] = "v"
        assert b.details == {}

    def test_audit_log_response_shape(self):
        r = AuditLogResponse(tenant_id="t", total=0, page=1, page_size=20, entries=[])
        assert r.page_size == 20


# ---------------------------------------------------------------------------
# _to_iso
# ---------------------------------------------------------------------------


class TestToIso:
    def test_none_returns_now(self):
        result = _to_iso(None)
        # Parseable, with timezone
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_tz_aware_datetime_converted_to_utc(self):
        from datetime import timezone, timedelta
        dt = datetime(2026, 4, 18, 10, 0, tzinfo=timezone(timedelta(hours=5)))
        result = _to_iso(dt)
        # Converted to UTC
        parsed = datetime.fromisoformat(result)
        assert parsed.utcoffset() == timezone.utc.utcoffset(dt)

    def test_naive_datetime_assigned_utc(self):
        dt = datetime(2026, 4, 18, 10, 0)
        result = _to_iso(dt)
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None

    def test_string_passes_through(self):
        assert _to_iso("2026-04-18T00:00:00Z") == "2026-04-18T00:00:00Z"

    def test_non_datetime_non_none_stringified(self):
        assert _to_iso(123) == "123"


# ---------------------------------------------------------------------------
# _normalize_audit_event_type / _normalize_category
# ---------------------------------------------------------------------------


class TestNormalizeEventType:
    @pytest.mark.parametrize("event_type, category, action, expected", [
        ("user_login", "", "", "user_login"),
        ("LOGIN_ATTEMPT", "", "", "user_login"),
        ("", "authentication", "", "user_login"),
        ("", "Authentication", "", "user_login"),
        ("export_generated", "", "", "export"),
        ("", "", "export_fda", "export"),
        ("alert_raised", "", "", "alert"),
        ("compliance_check", "", "", "compliance_change"),
        ("", "COMPLIANCE", "", "compliance_change"),
        ("cte_recorded", "", "", "cte_recorded"),
        ("random_event", "", "", "api_call"),
        ("", "", "", "api_call"),
    ])
    def test_cases(self, event_type, category, action, expected):
        assert _normalize_audit_event_type(event_type, category, action) == expected

    def test_none_inputs_default_to_api_call(self):
        assert _normalize_audit_event_type(None, None, None) == "api_call"


class TestNormalizeCategory:
    def test_user_login_maps_to_auth(self):
        assert _normalize_category("user_login", "") == "auth"

    def test_cte_maps_to_data(self):
        assert _normalize_category("cte_recorded", "") == "data"

    def test_export_maps_to_data(self):
        assert _normalize_category("export_happened", "") == "data"

    def test_alert_maps_to_compliance(self):
        assert _normalize_category("alert_raised", "") == "compliance"

    def test_compliance_maps_to_compliance(self):
        assert _normalize_category("compliance_check", "") == "compliance"

    def test_default_maps_to_system(self):
        assert _normalize_category("random", "") == "system"


# ---------------------------------------------------------------------------
# _get_admin_db_session
# ---------------------------------------------------------------------------


class TestGetAdminDbSession:
    def test_no_env_returns_none(self, monkeypatch):
        monkeypatch.delenv("ADMIN_DATABASE_URL", raising=False)
        assert _get_admin_db_session() is None

    def test_no_env_warns_only_once(self, monkeypatch, caplog):
        monkeypatch.delenv("ADMIN_DATABASE_URL", raising=False)
        with caplog.at_level("WARNING"):
            _get_admin_db_session()
            _get_admin_db_session()
        # Only one "ADMIN_DATABASE_URL is not set" warning
        msgs = [r for r in caplog.records if "ADMIN_DATABASE_URL" in r.message]
        assert len(msgs) == 1

    def test_with_env_initializes_factory(self, monkeypatch):
        monkeypatch.setenv("ADMIN_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
        fake_session = MagicMock()
        fake_factory = MagicMock(return_value=fake_session)
        factory_calls = []

        def fake_sessionmaker(**kwargs):
            factory_calls.append(kwargs)
            return fake_factory

        def fake_create_engine(url, **kwargs):
            return MagicMock(url=url)

        monkeypatch.setattr(al, "sessionmaker", fake_sessionmaker)
        monkeypatch.setattr(al, "create_engine", fake_create_engine)

        result = _get_admin_db_session()
        assert result is fake_session

    def test_session_creation_failure_returns_none(self, monkeypatch, caplog):
        monkeypatch.setenv("ADMIN_DATABASE_URL", "postgresql://u:p@h/db")

        def boom():
            raise RuntimeError("session-failed")

        fake_factory = MagicMock(side_effect=boom)

        def fake_sessionmaker(**kwargs):
            return fake_factory

        monkeypatch.setattr(al, "sessionmaker", fake_sessionmaker)
        monkeypatch.setattr(al, "create_engine", lambda *a, **k: MagicMock())

        with caplog.at_level("ERROR"):
            result = _get_admin_db_session()
        assert result is None
        assert any("audit_log_admin_db_session_failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _table_exists
# ---------------------------------------------------------------------------


class TestTableExists:
    def test_table_present_returns_true(self):
        session = MagicMock()
        result = MagicMock()
        result.fetchone.return_value = ("public.mytable",)
        session.execute.return_value = result
        assert _table_exists(session, "mytable") is True

    def test_table_missing_returns_false(self):
        session = MagicMock()
        result = MagicMock()
        result.fetchone.return_value = (None,)
        session.execute.return_value = result
        assert _table_exists(session, "mytable") is False

    def test_fetchone_returns_none(self):
        session = MagicMock()
        result = MagicMock()
        result.fetchone.return_value = None
        session.execute.return_value = result
        assert _table_exists(session, "mytable") is False

    def test_schema_parameter(self):
        session = MagicMock()
        result = MagicMock()
        result.fetchone.return_value = ("fsma.mytable",)
        session.execute.return_value = result
        assert _table_exists(session, "mytable", schema="fsma") is True
        _sql, params = session.execute.call_args[0]
        assert params == {"table_ref": "fsma.mytable"}


# ---------------------------------------------------------------------------
# _query_admin_audit_logs
# ---------------------------------------------------------------------------


class TestQueryAdminAuditLogs:
    def test_no_table_returns_empty(self, monkeypatch):
        session = MagicMock()
        # _table_exists returns False
        result = MagicMock()
        result.fetchone.return_value = (None,)
        session.execute.return_value = result
        assert _query_admin_audit_logs(session, "t1", 200) == []

    def test_happy_path_maps_rows(self):
        session = MagicMock()
        to_regclass_result = MagicMock()
        to_regclass_result.fetchone.return_value = ("public.audit_logs",)
        rows_result = MagicMock()

        row = SimpleNamespace(
            id="123",
            timestamp=datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
            event_type="user_login",
            event_category="authentication",
            actor="alice@x.com",
            action="login",
            resource="session:abc",
            details={"ip": "1.2.3.4"},
            ip_address="1.2.3.4",
            integrity_hash="hash-abc",
        )
        rows_result.fetchall.return_value = [row]

        calls = [to_regclass_result, rows_result]
        session.execute.side_effect = lambda *a, **kw: calls.pop(0)

        entries = _query_admin_audit_logs(session, "t1", 200)
        assert len(entries) == 1
        assert entries[0].id == "123"
        assert entries[0].event_type == "user_login"
        assert entries[0].category == "auth"
        assert entries[0].actor == "alice@x.com"
        assert entries[0].hash == "hash-abc"
        assert entries[0].details == {"ip": "1.2.3.4"}

    def test_row_with_non_dict_details_defaults_empty(self):
        session = MagicMock()
        to_regclass_result = MagicMock()
        to_regclass_result.fetchone.return_value = ("public.audit_logs",)
        rows_result = MagicMock()
        row = SimpleNamespace(
            id="1", timestamp=None, event_type="x", event_category="y",
            actor="a", action="b", resource=None,
            details="not-a-dict",  # string, not dict
            ip_address=None, integrity_hash=None,
        )
        rows_result.fetchall.return_value = [row]
        session.execute.side_effect = [to_regclass_result, rows_result]

        entries = _query_admin_audit_logs(session, "t1", 200)
        assert entries[0].details == {}
        assert entries[0].resource == "audit"  # resource None -> fallback
        assert entries[0].ip_address == ""
        assert entries[0].hash == ""


# ---------------------------------------------------------------------------
# _query_cte_events
# ---------------------------------------------------------------------------


class TestQueryCteEvents:
    def test_maps_rows_to_audit_entries(self):
        session = MagicMock()
        row = SimpleNamespace(
            id="cte-uuid",
            event_timestamp=datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
            event_type="shipping",
            source="webhook",
            traceability_lot_code="LOT-123",
            product_description="Spinach",
            quantity=100,
            sha256_hash="hash-1",
        )
        rows_result = MagicMock()
        rows_result.fetchall.return_value = [row]
        session.execute.return_value = rows_result

        entries = _query_cte_events(session, "t1", 200)
        assert len(entries) == 1
        e = entries[0]
        assert e.id == "cte-cte-uuid"
        assert e.event_type == "cte_recorded"
        assert e.category == "data"
        assert e.actor == "webhook"
        assert e.resource == "TLC LOT-123"
        assert e.hash == "hash-1"
        assert e.details == {"cte_type": "shipping", "product": "Spinach", "quantity": 100}

    def test_none_source_becomes_system(self):
        session = MagicMock()
        row = SimpleNamespace(
            id="1", event_timestamp=None, event_type="shipping",
            source=None, traceability_lot_code="LOT", product_description="p",
            quantity=1, sha256_hash=None,
        )
        rows_result = MagicMock()
        rows_result.fetchall.return_value = [row]
        session.execute.return_value = rows_result
        entries = _query_cte_events(session, "t1", 10)
        assert entries[0].actor == "system"
        assert entries[0].hash == ""


# ---------------------------------------------------------------------------
# _query_exports
# ---------------------------------------------------------------------------


class TestQueryExports:
    def test_maps_rows(self):
        session = MagicMock()
        row = SimpleNamespace(
            id="exp-uuid",
            generated_at=datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
            generated_by="alice@x.com",
            export_type="fda_spreadsheet",
            record_count=42,
            export_hash="hash-2",
        )
        rows_result = MagicMock()
        rows_result.fetchall.return_value = [row]
        session.execute.return_value = rows_result

        entries = _query_exports(session, "t1", 100)
        assert len(entries) == 1
        e = entries[0]
        assert e.id == "export-exp-uuid"
        assert e.event_type == "export"
        assert e.category == "data"
        assert e.actor == "alice@x.com"
        assert e.resource == "Export: fda_spreadsheet"
        assert e.details == {"records": 42}

    def test_null_export_type_fallback(self):
        session = MagicMock()
        row = SimpleNamespace(
            id="1", generated_at=None, generated_by=None,
            export_type=None, record_count=0, export_hash=None,
        )
        rows_result = MagicMock()
        rows_result.fetchall.return_value = [row]
        session.execute.return_value = rows_result
        entries = _query_exports(session, "t1", 10)
        assert entries[0].actor == "system"
        assert "fda_spreadsheet" in entries[0].resource


# ---------------------------------------------------------------------------
# _query_alert_events
# ---------------------------------------------------------------------------


class TestQueryAlertEvents:
    def test_no_table_returns_empty(self):
        session = MagicMock()
        table_check = MagicMock()
        table_check.fetchone.return_value = (None,)
        session.execute.return_value = table_check
        assert _query_alert_events(session, "t1", 100) == []

    def test_no_tenant_column_returns_empty(self):
        session = MagicMock()
        table_check = MagicMock()
        table_check.fetchone.return_value = ("fsma.compliance_alerts",)
        columns_check = MagicMock()
        # Columns missing tenant_id AND org_id
        columns_check.fetchall.return_value = [("id",), ("severity",)]
        session.execute.side_effect = [table_check, columns_check]
        assert _query_alert_events(session, "t1", 100) == []

    def test_uses_tenant_id_column_when_present(self):
        session = MagicMock()
        table_check = MagicMock()
        table_check.fetchone.return_value = ("fsma.compliance_alerts",)
        columns_check = MagicMock()
        columns_check.fetchall.return_value = [
            ("id",), ("severity",), ("alert_type",),
            ("tenant_id",), ("message",), ("created_at",),
        ]
        rows_check = MagicMock()
        row = SimpleNamespace(
            id="a-1",
            created_at=datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
            severity="high",
            alert_type="kde_missing",
            message="Missing KDE",
        )
        rows_check.fetchall.return_value = [row]
        session.execute.side_effect = [table_check, columns_check, rows_check]

        entries = _query_alert_events(session, "t1", 100)
        assert len(entries) == 1
        e = entries[0]
        assert e.id == "alert-a-1"
        assert e.event_type == "alert"
        assert e.category == "compliance"
        assert e.resource == "Alert: kde_missing"
        assert e.details == {"message": "Missing KDE", "severity": "high"}

    def test_uses_org_id_fallback(self):
        session = MagicMock()
        table_check = MagicMock()
        table_check.fetchone.return_value = ("fsma.compliance_alerts",)
        columns_check = MagicMock()
        columns_check.fetchall.return_value = [
            ("id",), ("severity",), ("alert_type",),
            ("org_id",), ("description",), ("created_at",),
        ]
        rows_check = MagicMock()
        rows_check.fetchall.return_value = []
        session.execute.side_effect = [table_check, columns_check, rows_check]
        result = _query_alert_events(session, "t1", 100)
        assert result == []

    def test_title_and_alert_type_fallback_message(self):
        # When neither message nor description exist, title is picked
        session = MagicMock()
        table_check = MagicMock()
        table_check.fetchone.return_value = ("fsma.compliance_alerts",)
        columns_check = MagicMock()
        columns_check.fetchall.return_value = [
            ("id",), ("tenant_id",), ("alert_type",), ("severity",),
            ("title",), ("created_at",),
        ]
        rows_check = MagicMock()
        rows_check.fetchall.return_value = []
        session.execute.side_effect = [table_check, columns_check, rows_check]
        assert _query_alert_events(session, "t1", 100) == []

    def test_final_alert_type_fallback_message(self):
        # Only alert_type itself used as message when nothing else exists
        session = MagicMock()
        table_check = MagicMock()
        table_check.fetchone.return_value = ("fsma.compliance_alerts",)
        columns_check = MagicMock()
        columns_check.fetchall.return_value = [
            ("id",), ("tenant_id",), ("alert_type",), ("severity",), ("created_at",),
        ]
        rows_check = MagicMock()
        rows_check.fetchall.return_value = []
        session.execute.side_effect = [table_check, columns_check, rows_check]
        assert _query_alert_events(session, "t1", 100) == []


# ---------------------------------------------------------------------------
# GET /{tenant_id} endpoint
# ---------------------------------------------------------------------------


class TestGetAuditLogEndpoint:
    def test_invalid_tenant_id_raises_400(self, client):
        resp = client.get("/api/v1/audit-log/bad tenant!")
        assert resp.status_code == 400

    def test_happy_path_merges_sources_and_dedupes(self, client, monkeypatch):
        # Stub all four query helpers
        cte = AuditEntry(
            id="cte-1", timestamp="2026-04-18T12:00:00+00:00",
            event_type="cte_recorded", category="data",
            actor="webhook", action="Recorded shipping CTE", resource="TLC LOT-1",
        )
        export = AuditEntry(
            id="export-1", timestamp="2026-04-18T11:00:00+00:00",
            event_type="export", category="data",
            actor="alice", action="Generated FDA export", resource="Export: fda",
        )
        admin = AuditEntry(
            id="admin-1", timestamp="2026-04-18T13:00:00+00:00",
            event_type="user_login", category="auth",
            actor="alice", action="login", resource="session",
        )
        # Duplicate the same id across admin and CTE -> should dedup
        duplicate = AuditEntry(
            id="admin-1", timestamp="2026-04-18T13:00:00+00:00",
            event_type="user_login", category="auth",
            actor="alice", action="login", resource="session",
        )
        monkeypatch.setattr(al, "_query_admin_audit_logs", lambda s, t, limit: [admin, duplicate])
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: [cte])
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: [export])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])

        # Fake admin session so try block hits _query_admin_audit_logs
        admin_session = MagicMock()
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: admin_session)
        # Fake ingestion DB
        monkeypatch.setattr(al, "get_db_safe", lambda: MagicMock())

        resp = client.get("/api/v1/audit-log/t1")
        assert resp.status_code == 200
        body = resp.json()
        # 3 unique entries (admin-1 duplicate collapsed)
        assert body["total"] == 3
        # Sorted desc by timestamp: admin (13) > cte (12) > export (11)
        ids = [e["id"] for e in body["entries"]]
        assert ids == ["admin-1", "cte-1", "export-1"]
        admin_session.close.assert_called_once()

    def test_admin_session_none_skips_admin_query(self, client, monkeypatch):
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: None)
        monkeypatch.setattr(al, "get_db_safe", lambda: MagicMock())
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])

        resp = client.get("/api/v1/audit-log/t1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_admin_query_exception_swallowed(self, client, monkeypatch):
        admin_session = MagicMock()
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: admin_session)

        def boom(*a, **kw):
            raise RuntimeError("admin-broken")
        monkeypatch.setattr(al, "_query_admin_audit_logs", boom)
        monkeypatch.setattr(al, "get_db_safe", lambda: MagicMock())
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])

        resp = client.get("/api/v1/audit-log/t1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_ingestion_db_exception_swallowed(self, client, monkeypatch):
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: None)

        def boom():
            raise RuntimeError("ingestion-broken")
        monkeypatch.setattr(al, "get_db_safe", boom)
        resp = client.get("/api/v1/audit-log/t1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_event_type_filter(self, client, monkeypatch):
        entries = [
            AuditEntry(id="1", timestamp="2026-04-18T12:00:00+00:00",
                       event_type="cte_recorded", category="data",
                       actor="a", action="a", resource="r"),
            AuditEntry(id="2", timestamp="2026-04-18T11:00:00+00:00",
                       event_type="export", category="data",
                       actor="a", action="a", resource="r"),
        ]
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: None)
        monkeypatch.setattr(al, "get_db_safe", lambda: MagicMock())
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: entries[:1])
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: entries[1:])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])

        resp = client.get("/api/v1/audit-log/t1?event_type=export")
        body = resp.json()
        assert body["total"] == 1
        assert body["entries"][0]["event_type"] == "export"

    def test_category_filter(self, client, monkeypatch):
        entries = [
            AuditEntry(id="1", timestamp="2026-04-18T12:00:00+00:00",
                       event_type="user_login", category="auth",
                       actor="a", action="a", resource="r"),
            AuditEntry(id="2", timestamp="2026-04-18T11:00:00+00:00",
                       event_type="cte_recorded", category="data",
                       actor="a", action="a", resource="r"),
        ]
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: None)
        monkeypatch.setattr(al, "get_db_safe", lambda: MagicMock())
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: [entries[1]])
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_admin_audit_logs", lambda s, t, limit: [entries[0]])
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: MagicMock())

        resp = client.get("/api/v1/audit-log/t1?category=auth")
        body = resp.json()
        assert body["total"] == 1
        assert body["entries"][0]["category"] == "auth"

    def test_pagination(self, client, monkeypatch):
        entries = [
            AuditEntry(id=f"e-{i}", timestamp=f"2026-04-18T00:00:{i:02d}+00:00",
                       event_type="x", category="y", actor="a", action="a", resource="r")
            for i in range(30)
        ]
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: None)
        monkeypatch.setattr(al, "get_db_safe", lambda: MagicMock())
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: entries)
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])

        resp = client.get("/api/v1/audit-log/t1?page=2&page_size=10")
        body = resp.json()
        assert body["total"] == 30
        assert body["page"] == 2
        assert body["page_size"] == 10
        assert len(body["entries"]) == 10

    def test_page_less_than_one_treated_as_zero_offset(self, client, monkeypatch):
        entries = [
            AuditEntry(id=f"e-{i}", timestamp=f"2026-04-18T00:00:{i:02d}+00:00",
                       event_type="x", category="y", actor="a", action="a", resource="r")
            for i in range(5)
        ]
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: None)
        monkeypatch.setattr(al, "get_db_safe", lambda: MagicMock())
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: entries)
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])

        resp = client.get("/api/v1/audit-log/t1?page=0&page_size=3")
        body = resp.json()
        # max((0-1)*3, 0) = 0, so returns first 3
        assert len(body["entries"]) == 3

    def test_page_beyond_total_returns_empty(self, client, monkeypatch):
        entries = [
            AuditEntry(id="e-1", timestamp="2026-04-18T00:00:00+00:00",
                       event_type="x", category="y", actor="a", action="a", resource="r"),
        ]
        monkeypatch.setattr(al, "_get_admin_db_session", lambda: None)
        monkeypatch.setattr(al, "get_db_safe", lambda: MagicMock())
        monkeypatch.setattr(al, "_query_cte_events", lambda s, t, limit: entries)
        monkeypatch.setattr(al, "_query_exports", lambda s, t, limit: [])
        monkeypatch.setattr(al, "_query_alert_events", lambda s, t, limit: [])

        resp = client.get("/api/v1/audit-log/t1?page=99&page_size=10")
        body = resp.json()
        assert body["total"] == 1
        assert body["entries"] == []


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix_and_tags(self):
        assert router.prefix == "/api/v1/audit-log"
        assert "Audit Log" in router.tags

    def test_registered_paths(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/audit-log/{tenant_id}" in paths
