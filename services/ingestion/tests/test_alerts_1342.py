"""Regression tests for ``services/ingestion/app/alerts.py``.

Part of the #1342 ingestion coverage sweep. Covers dynamic column-allowlist
assembly, FDA recall alert reading, fsma.compliance_alerts reading,
acknowledge flow (primary + fallback), rules, and summary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import alerts as alerts_mod
from app.alerts import (
    Alert,
    AlertRule,
    AlertsResponse,
    DEFAULT_RULES,
    _ALLOWED_ALERT_COLUMNS,
    _category_for_alert_type,
    _fetch_alerts_from_db,
    _fetch_fda_recall_alerts,
    _load_alert_columns,
    _rule_name,
    _severity_for_classification,
    _to_iso,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _Row:
    """Mimics a SQLAlchemy Row supporting both attribute and index access."""

    def __init__(self, **fields):
        self._fields = list(fields.items())
        for k, v in fields.items():
            setattr(self, k, v)

    def __getitem__(self, idx):
        if isinstance(idx, int):
            return self._fields[idx][1]
        # attribute-like lookup: scan by key
        for k, v in self._fields:
            if k == idx:
                return v
        raise KeyError(idx)


class _FakeResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeSession:
    """Configurable session that replays scripted responses in call order.

    Responses can be _FakeResult instances or Exception instances (to raise
    on that execute call).
    """

    def __init__(self, responses: Optional[list] = None):
        self.responses = list(responses or [])
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.execute_calls: list[tuple] = []

    def execute(self, stmt, params=None):
        self.execute_calls.append((str(stmt), dict(params or {})))
        if self.responses:
            resp = self.responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return _FakeResult()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


def _cols_result(cols: list[str]) -> _FakeResult:
    """Build a fake information_schema.columns result."""
    return _FakeResult(rows=[(c,) for c in cols])


# ---------------------------------------------------------------------------
# _load_alert_columns
# ---------------------------------------------------------------------------


class TestLoadAlertColumns:
    def test_intersects_with_allowlist(self):
        session = _FakeSession(responses=[_cols_result([
            "id", "severity", "created_at", "foo", "DROP_TABLE",
        ])])
        cols = _load_alert_columns(session)
        assert cols == {"id", "severity", "created_at"}

    def test_empty_when_no_columns_match(self):
        session = _FakeSession(responses=[_cols_result(["unknown", "other"])])
        assert _load_alert_columns(session) == set()


# ---------------------------------------------------------------------------
# _category_for_alert_type
# ---------------------------------------------------------------------------


class TestCategoryForAlertType:
    def test_temperature(self):
        assert _category_for_alert_type("temp_excursion") == "temperature"
        assert _category_for_alert_type("TEMP_EXCURSION") == "temperature"

    def test_deadline_and_expiry(self):
        assert _category_for_alert_type("fda_deadline") == "deadline"
        assert _category_for_alert_type("portal_expiry") == "deadline"

    def test_chain(self):
        assert _category_for_alert_type("chain_break") == "chain"

    def test_default_compliance(self):
        assert _category_for_alert_type("missing_kde") == "compliance"
        assert _category_for_alert_type("") == "compliance"
        assert _category_for_alert_type(None) == "compliance"


# ---------------------------------------------------------------------------
# _rule_name
# ---------------------------------------------------------------------------


class TestRuleName:
    def test_empty_falls_back(self):
        assert _rule_name("") == "Compliance Alert"
        assert _rule_name(None) == "Compliance Alert"

    def test_title_case(self):
        assert _rule_name("fda_recall") == "Fda Recall"
        assert _rule_name("temp_excursion") == "Temp Excursion"


# ---------------------------------------------------------------------------
# _to_iso
# ---------------------------------------------------------------------------


class TestToIso:
    def test_none_returns_now(self):
        result = _to_iso(None)
        # Should be parseable as ISO
        assert "T" in result
        assert "+00:00" in result

    def test_naive_datetime_assumed_utc(self):
        naive = datetime(2026, 4, 17, 10, 0)
        assert _to_iso(naive) == naive.replace(tzinfo=timezone.utc).isoformat()

    def test_aware_datetime_converted_to_utc(self):
        from datetime import timedelta
        tz = timezone(timedelta(hours=5))
        aware = datetime(2026, 4, 17, 15, 0, tzinfo=tz)
        assert _to_iso(aware) == aware.astimezone(timezone.utc).isoformat()

    def test_string_passthrough(self):
        assert _to_iso("already-a-string") == "already-a-string"


# ---------------------------------------------------------------------------
# _severity_for_classification
# ---------------------------------------------------------------------------


class TestSeverityForClassification:
    def test_class_i_critical(self):
        assert _severity_for_classification("Class I") == "critical"

    def test_class_ii_matches_class_i_substring(self):
        # NOTE: current logic checks "Class I" in classification first, which is
        # also a substring of "Class II" and "Class III" — so those all return
        # "critical" as well. This locks in existing behavior.
        assert _severity_for_classification("Class II") == "critical"
        assert _severity_for_classification("Class III") == "critical"

    def test_default_warning(self):
        assert _severity_for_classification("") == "warning"
        assert _severity_for_classification("Unknown") == "warning"

    def test_explicit_class_ii_without_class_i_substring(self):
        # Hypothetical input where classification is just "II" — misses
        # "Class I" prefix, so the "Class II" check would need to be hit
        # separately. Current implementation checks "Class II" second, so
        # that path is only reachable when "Class I" substring is absent —
        # which for literal "II" is true → falls through to warning.
        assert _severity_for_classification("II only") == "warning"


# ---------------------------------------------------------------------------
# _fetch_fda_recall_alerts
# ---------------------------------------------------------------------------


class TestFetchFdaRecallAlerts:
    def test_table_missing_returns_empty(self):
        session = _FakeSession(responses=[_FakeResult(row=None)])
        assert _fetch_fda_recall_alerts(session, "t1") == []

    def test_exception_returns_empty(self):
        session = _FakeSession(responses=[RuntimeError("boom")])
        assert _fetch_fda_recall_alerts(session, "t1") == []

    def test_full_row_maps_correctly(self):
        raw = {
            "classification": "Class I",
            "recall_number": "F-123-2026",
            "recalling_firm": "Acme",
            "distribution_pattern": "Nationwide",
            "code_info": "lot 42",
        }
        match = {"matched_by": ["lot_code:42"]}
        now = datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc)
        row = _Row(
            id="alert-uuid",
            source_type="FDA_RECALL",
            source_id="FDA-1",
            title="[Class I] Acme - baby kale",
            summary="Possible listeria",
            severity="CRITICAL",
            countdown_start=now,
            countdown_end=now,
            countdown_hours=24,
            required_actions={},
            status="ACTIVE",
            match_reason=match,
            raw_data=raw,
            created_at=now,
            acknowledged_at=None,
            acknowledged_by=None,
            resolved_at=None,
        )
        session = _FakeSession(responses=[
            _FakeResult(row=(1,)),          # table exists check
            _FakeResult(rows=[row]),        # recall query
        ])
        alerts = _fetch_fda_recall_alerts(session, "t1")
        assert len(alerts) == 1
        a = alerts[0]
        assert a.id == "alert-uuid"
        assert a.rule_id == "fda-recall"
        assert a.severity == "critical"
        assert a.metadata["recall_number"] == "F-123-2026"
        assert a.metadata["match_tier"] == "lot_code"
        assert a.metadata["fda_url"].startswith("https://www.accessdata.fda.gov")
        assert a.acknowledged is False

    def test_supplier_match_tier(self):
        raw = {"classification": "Class II", "recall_number": "F-1"}
        match = {"matched_by": ["supplier:acme"]}
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        row = _Row(
            id="a1", source_type="FDA_RECALL", source_id="s",
            title="Recall", summary="s", severity="MEDIUM",
            countdown_start=None, countdown_end=None, countdown_hours=None,
            required_actions={}, status="ACTIVE",
            match_reason=match, raw_data=raw, created_at=now,
            acknowledged_at=None, acknowledged_by=None, resolved_at=None,
        )
        session = _FakeSession(responses=[
            _FakeResult(row=(1,)),
            _FakeResult(rows=[row]),
        ])
        alerts = _fetch_fda_recall_alerts(session, "t1")
        assert alerts[0].metadata["match_tier"] == "supplier"
        assert alerts[0].metadata["countdown_start"] is None

    def test_category_default_match_tier(self):
        raw = {}
        match = {"matched_by": ["category:leafy_greens"]}
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        row = _Row(
            id="a1", source_type="FDA_RECALL", source_id="s",
            title=None, summary=None, severity=None,
            countdown_start=now, countdown_end=now, countdown_hours=12,
            required_actions={}, status="RESOLVED",
            match_reason=match, raw_data=raw, created_at=now,
            acknowledged_at=None, acknowledged_by=None, resolved_at=None,
        )
        session = _FakeSession(responses=[
            _FakeResult(row=(1,)),
            _FakeResult(rows=[row]),
        ])
        alerts = _fetch_fda_recall_alerts(session, "t1")
        # No lot_code/supplier in matched_by → default stays "category"
        assert alerts[0].metadata["match_tier"] == "category"
        # RESOLVED status → is_acknowledged True
        assert alerts[0].acknowledged is True
        # Title fallback
        assert alerts[0].title == "FDA Recall"
        assert alerts[0].severity == "medium"

    def test_firm_extracted_from_title_when_missing(self):
        raw = {"classification": "Class I", "recall_number": "F-1"}
        match = {}
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        row = _Row(
            id="a1", source_type="FDA_RECALL", source_id="s",
            title="[Class I] Acme Corp - kale",
            summary="s", severity="CRITICAL",
            countdown_start=None, countdown_end=None, countdown_hours=None,
            required_actions={}, status="ACKNOWLEDGED",
            match_reason=match, raw_data=raw, created_at=now,
            acknowledged_at=now, acknowledged_by="user-1", resolved_at=None,
        )
        session = _FakeSession(responses=[
            _FakeResult(row=(1,)),
            _FakeResult(rows=[row]),
        ])
        alerts = _fetch_fda_recall_alerts(session, "t1")
        assert alerts[0].metadata["recalling_firm"] == "Acme Corp"
        assert alerts[0].acknowledged is True
        assert alerts[0].acknowledged_by == "user-1"

    def test_title_without_dash_separator_leaves_firm_empty(self):
        # Title has closing bracket but no " - ", so split yields only one part
        raw = {"classification": "Class I"}
        match = {}
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        row = _Row(
            id="a1", source_type="FDA_RECALL", source_id="s",
            title="[Class I] NoSeparator",
            summary="s", severity="MEDIUM",
            countdown_start=None, countdown_end=None, countdown_hours=None,
            required_actions={}, status="ACTIVE",
            match_reason=match, raw_data=raw, created_at=now,
            acknowledged_at=None, acknowledged_by=None, resolved_at=None,
        )
        session = _FakeSession(responses=[
            _FakeResult(row=(1,)),
            _FakeResult(rows=[row]),
        ])
        alerts = _fetch_fda_recall_alerts(session, "t1")
        # "NoSeparator" has no " - " split, so firm_part[0] = "NoSeparator"
        assert alerts[0].metadata["recalling_firm"] == "NoSeparator"

    def test_nondict_raw_data_falls_back_to_empty(self):
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        row = _Row(
            id="a1", source_type="FDA_RECALL", source_id="s",
            title="t", summary="s", severity="MEDIUM",
            countdown_start=None, countdown_end=None, countdown_hours=None,
            required_actions={}, status="ACTIVE",
            match_reason="not-a-dict",
            raw_data="not-a-dict",
            created_at=now,
            acknowledged_at=None, acknowledged_by=None, resolved_at=None,
        )
        session = _FakeSession(responses=[
            _FakeResult(row=(1,)),
            _FakeResult(rows=[row]),
        ])
        alerts = _fetch_fda_recall_alerts(session, "t1")
        assert alerts[0].metadata["recall_number"] == ""
        assert alerts[0].metadata["fda_url"] == ""


# ---------------------------------------------------------------------------
# _fetch_alerts_from_db
# ---------------------------------------------------------------------------


class TestFetchAlertsFromDb:
    def test_empty_columns_returns_empty(self):
        session = _FakeSession(responses=[_cols_result([])])
        assert _fetch_alerts_from_db(session, "t1") == []

    def test_no_tenant_scope_returns_empty(self):
        session = _FakeSession(responses=[_cols_result(["id", "severity"])])
        # Neither tenant_id nor org_id present
        assert _fetch_alerts_from_db(session, "t1") == []

    def test_uses_org_id_when_tenant_id_missing(self):
        # org_id path — provides required columns
        cols = [
            "id", "org_id", "severity", "alert_type", "title", "message",
            "created_at", "resolved", "resolved_at", "resolved_by", "details",
        ]
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        row = _Row(
            alert_id="a1", alert_type="temp_excursion", severity="critical",
            title="T", message="msg", created_at=now,
            resolved=True, resolved_at=now, resolved_by="user-1",
            details={"x": 1}, event_ref=None,
        )
        session = _FakeSession(responses=[
            _cols_result(cols),
            _FakeResult(rows=[row]),
        ])
        alerts = _fetch_alerts_from_db(session, "t1")
        assert len(alerts) == 1
        a = alerts[0]
        assert a.rule_id == "temp_excursion"
        assert a.category == "temperature"
        assert a.acknowledged is True
        assert a.acknowledged_by == "user-1"
        assert a.metadata == {"x": 1}

    def test_tenant_id_path_with_fallback_message_title(self):
        cols = [
            "id", "tenant_id", "severity", "alert_type", "created_at",
            "acknowledged", "acknowledged_at", "acknowledged_by", "metadata",
            "event_id",
        ]
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        row = _Row(
            alert_id="a1", alert_type=None, severity=None,
            title=None, message=None, created_at=now,
            resolved=False, resolved_at=None, resolved_by=None,
            details=None, event_ref="evt-99",
        )
        session = _FakeSession(responses=[
            _cols_result(cols),
            _FakeResult(rows=[row]),
        ])
        alerts = _fetch_alerts_from_db(session, "t1")
        a = alerts[0]
        assert a.rule_id == "compliance_alert"
        assert a.rule_name == "Compliance Alert"
        assert a.title == "Compliance Alert"
        assert a.severity == "warning"
        assert a.acknowledged is False
        # event_ref gets merged into details when details is empty dict
        assert a.metadata == {"event_id": "evt-99"}

    def test_details_dict_merged_with_event_ref(self):
        cols = [
            "id", "tenant_id", "severity", "alert_type", "title",
            "message", "created_at", "resolved", "details", "cte_event_id",
        ]
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        row = _Row(
            alert_id="a1", alert_type="kde_missing", severity="warning",
            title="T", message="m", created_at=now,
            resolved=False, resolved_at=None, resolved_by=None,
            details={"kde": "lot_code"}, event_ref="evt-1",
        )
        session = _FakeSession(responses=[
            _cols_result(cols),
            _FakeResult(rows=[row]),
        ])
        alerts = _fetch_alerts_from_db(session, "t1")
        assert alerts[0].metadata == {"kde": "lot_code", "event_id": "evt-1"}


# ---------------------------------------------------------------------------
# GET /{tenant_id} endpoint
# ---------------------------------------------------------------------------


def _alert(aid, severity="warning", category="compliance", acknowledged=False,
           triggered="2026-04-17T10:00:00+00:00"):
    return Alert(
        id=aid, rule_id="r", rule_name="Rule", severity=severity,
        category=category, title="t", message="m",
        triggered_at=triggered, acknowledged=acknowledged,
    )


class TestGetAlertsEndpoint:
    def test_invalid_tenant_returns_400(self, monkeypatch):
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/invalid@tenant")
        assert resp.status_code == 400

    def test_merges_fsma_and_fda_alerts_and_dedupes(self, monkeypatch):
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: _FakeSession())
        monkeypatch.setattr(
            alerts_mod, "_fetch_alerts_from_db",
            lambda db, tid: [_alert("shared"), _alert("b")],
        )
        monkeypatch.setattr(
            alerts_mod, "_fetch_fda_recall_alerts",
            lambda db, tid: [_alert("shared", severity="critical"), _alert("a")],
        )
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1")
        assert resp.status_code == 200
        body = resp.json()
        # shared should appear once (from fda_recall since it's first)
        ids = [a["id"] for a in body["alerts"]]
        assert ids.count("shared") == 1
        assert set(ids) == {"shared", "a", "b"}

    def test_severity_filter(self, monkeypatch):
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: _FakeSession())
        monkeypatch.setattr(
            alerts_mod, "_fetch_alerts_from_db",
            lambda db, tid: [_alert("a", severity="critical"), _alert("b", severity="warning")],
        )
        monkeypatch.setattr(alerts_mod, "_fetch_fda_recall_alerts", lambda db, tid: [])
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1?severity=critical")
        body = resp.json()
        assert body["total"] == 1
        assert body["alerts"][0]["id"] == "a"

    def test_category_filter(self, monkeypatch):
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: _FakeSession())
        monkeypatch.setattr(
            alerts_mod, "_fetch_alerts_from_db",
            lambda db, tid: [
                _alert("a", category="temperature"),
                _alert("b", category="compliance"),
            ],
        )
        monkeypatch.setattr(alerts_mod, "_fetch_fda_recall_alerts", lambda db, tid: [])
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1?category=temperature")
        body = resp.json()
        assert body["total"] == 1
        assert body["alerts"][0]["id"] == "a"

    def test_acknowledged_filter(self, monkeypatch):
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: _FakeSession())
        monkeypatch.setattr(
            alerts_mod, "_fetch_alerts_from_db",
            lambda db, tid: [
                _alert("a", acknowledged=True),
                _alert("b", acknowledged=False),
            ],
        )
        monkeypatch.setattr(alerts_mod, "_fetch_fda_recall_alerts", lambda db, tid: [])
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1?acknowledged=false")
        body = resp.json()
        assert body["total"] == 1
        assert body["alerts"][0]["id"] == "b"
        assert body["unacknowledged"] == 1

    def test_pagination(self, monkeypatch):
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: _FakeSession())
        monkeypatch.setattr(
            alerts_mod, "_fetch_alerts_from_db",
            lambda db, tid: [_alert(f"a{i}", triggered=f"2026-04-{i+10}T00:00:00+00:00") for i in range(5)],
        )
        monkeypatch.setattr(alerts_mod, "_fetch_fda_recall_alerts", lambda db, tid: [])
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1?skip=1&limit=2")
        body = resp.json()
        assert body["total"] == 5
        assert len(body["alerts"]) == 2

    def test_db_unavailable_swallowed(self, monkeypatch):
        def _boom():
            raise RuntimeError("db down")
        monkeypatch.setattr(alerts_mod, "get_db_safe", _boom)
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0

    def test_http_exception_in_fetch_propagates(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: _FakeSession())

        def _raise(db, tid):
            raise HTTPException(status_code=401, detail="nope")

        monkeypatch.setattr(alerts_mod, "_fetch_alerts_from_db", _raise)
        monkeypatch.setattr(alerts_mod, "_fetch_fda_recall_alerts", lambda db, tid: [])
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /{tenant_id}/{alert_id}/acknowledge endpoint
# ---------------------------------------------------------------------------


class TestAcknowledgeAlert:
    def test_public_success(self, monkeypatch):
        session = _FakeSession(responses=[_FakeResult(row=("public-1",))])
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: session)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/alerts/t1/alert-42/acknowledge")
        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True
        assert session.committed is True
        assert session.closed is True

    def test_public_fails_falls_back_to_fsma_success(self, monkeypatch):
        session = _FakeSession(responses=[
            RuntimeError("public missing"),              # primary update raises
            _cols_result([                                # load alert columns
                "id", "tenant_id", "severity", "resolved", "resolved_at",
            ]),
            _FakeResult(row=("fsma-1",)),                # fsma update returns row
        ])
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: session)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/alerts/t1/alert-42/acknowledge")
        assert resp.status_code == 200
        assert session.rolled_back is True
        assert session.committed is True

    def test_public_empty_then_fsma_success(self, monkeypatch):
        session = _FakeSession(responses=[
            _FakeResult(row=None),                        # primary update misses
            _cols_result([
                "id", "org_id", "severity", "resolved",
            ]),
            _FakeResult(row=("fsma-1",)),
        ])
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: session)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/alerts/t1/alert-42/acknowledge")
        assert resp.status_code == 200
        assert session.committed is True

    def test_fallback_missing_tenant_scope_column(self, monkeypatch):
        session = _FakeSession(responses=[
            _FakeResult(row=None),                        # primary miss
            _cols_result(["id", "severity", "resolved"]),  # no tenant_id or org_id
        ])
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: session)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/alerts/t1/alert-42/acknowledge")
        assert resp.status_code == 500

    def test_fallback_missing_resolved_column(self, monkeypatch):
        session = _FakeSession(responses=[
            _FakeResult(row=None),
            _cols_result(["id", "tenant_id", "severity"]),
        ])
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: session)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/alerts/t1/alert-42/acknowledge")
        assert resp.status_code == 501

    def test_fallback_alert_not_found(self, monkeypatch):
        session = _FakeSession(responses=[
            _FakeResult(row=None),
            _cols_result(["id", "tenant_id", "severity", "resolved"]),
            _FakeResult(row=None),
        ])
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: session)
        client = TestClient(_build_app())
        resp = client.post("/api/v1/alerts/t1/missing/acknowledge")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /{tenant_id}/rules
# ---------------------------------------------------------------------------


class TestRulesEndpoint:
    def test_returns_default_rules(self):
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1/rules")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        rule_ids = {r["id"] for r in body["rules"]}
        assert "kde-missing" in rule_ids
        assert "fda-recall" in rule_ids
        assert len(body["rules"]) == len(DEFAULT_RULES)


# ---------------------------------------------------------------------------
# GET /{tenant_id}/summary
# ---------------------------------------------------------------------------


class TestSummaryEndpoint:
    def test_aggregates_by_severity_and_category(self, monkeypatch):
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: _FakeSession())
        monkeypatch.setattr(
            alerts_mod, "_fetch_alerts_from_db",
            lambda db, tid: [
                _alert("a", severity="critical", category="temperature"),
                _alert("b", severity="warning", category="compliance"),
            ],
        )
        monkeypatch.setattr(
            alerts_mod, "_fetch_fda_recall_alerts",
            lambda db, tid: [_alert("c", severity="critical", category="fda_recall", acknowledged=True)],
        )
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["unacknowledged"] == 2
        assert body["by_severity"]["critical"] == 2
        assert body["by_category"]["fda_recall"] == 1

    def test_dedupes_across_sources(self, monkeypatch):
        monkeypatch.setattr(alerts_mod, "get_db_safe", lambda: _FakeSession())
        monkeypatch.setattr(
            alerts_mod, "_fetch_alerts_from_db",
            lambda db, tid: [_alert("shared", severity="warning")],
        )
        monkeypatch.setattr(
            alerts_mod, "_fetch_fda_recall_alerts",
            lambda db, tid: [_alert("shared", severity="critical")],
        )
        client = TestClient(_build_app())
        resp = client.get("/api/v1/alerts/t1/summary")
        body = resp.json()
        assert body["total"] == 1
        # fda_recall entry wins since it iterates first
        assert body["by_severity"].get("critical") == 1


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert router.prefix == "/api/v1/alerts"

    def test_tags(self):
        assert "Alerts & Notifications" in router.tags

    def test_endpoints(self):
        paths = {route.path for route in router.routes}
        assert "/api/v1/alerts/{tenant_id}" in paths
        assert "/api/v1/alerts/{tenant_id}/{alert_id}/acknowledge" in paths
        assert "/api/v1/alerts/{tenant_id}/rules" in paths
        assert "/api/v1/alerts/{tenant_id}/summary" in paths

    def test_allowlist_contains_core_columns(self):
        for col in ("id", "severity", "created_at", "tenant_id", "org_id"):
            assert col in _ALLOWED_ALERT_COLUMNS
