"""Unit tests for the rules engine router."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.rules_router import router as rules_router, _get_db_session


# ---------------------------------------------------------------------------
# Fake domain objects
# ---------------------------------------------------------------------------

class _FakeRule:
    """Mimics a rule definition returned by RulesEngine.load_active_rules."""

    def __init__(self, **kwargs):
        self.rule_id = kwargs.get("rule_id", "RULE-001")
        self.rule_version = kwargs.get("rule_version", 1)
        self.title = kwargs.get("title", "Test Rule")
        self.description = kwargs.get("description", "A test rule")
        self.severity = kwargs.get("severity", "critical")
        self.category = kwargs.get("category", "traceability")
        self.citation_reference = kwargs.get("citation_reference", "21 CFR 1.1315")
        self.applicability_conditions = kwargs.get("applicability_conditions", {})
        self.evaluation_logic = kwargs.get("evaluation_logic", {})
        self.failure_reason_template = kwargs.get("failure_reason_template", "Missing field")
        self.remediation_suggestion = kwargs.get("remediation_suggestion", "Add the field")
        self.effective_date = kwargs.get("effective_date", None)


class _FakeEvalResult:
    """Mimics a single rule evaluation result."""

    def __init__(self, **kwargs):
        self.rule_id = kwargs.get("rule_id", "RULE-001")
        self.rule_title = kwargs.get("rule_title", "Test Rule")
        self.severity = kwargs.get("severity", "critical")
        self.result = kwargs.get("result", "pass")
        self.why_failed = kwargs.get("why_failed", None)
        self.citation_reference = kwargs.get("citation_reference", "21 CFR 1.1315")
        self.remediation_suggestion = kwargs.get("remediation_suggestion", None)
        self.evidence_fields_inspected = kwargs.get("evidence_fields_inspected", [])
        self.category = kwargs.get("category", "traceability")


class _FakeEvalSummary:
    """Mimics the summary returned by RulesEngine.evaluate_event."""

    def __init__(self, **kwargs):
        self.event_id = kwargs.get("event_id", "EVT-001")
        self.compliant = kwargs.get("compliant", True)
        self.total_rules = kwargs.get("total_rules", 2)
        self.passed = kwargs.get("passed", 2)
        self.failed = kwargs.get("failed", 0)
        self.warned = kwargs.get("warned", 0)
        self.critical_failures: list = kwargs.get("critical_failures", [])
        self.results: list = kwargs.get("results", [])


class _FakeSession:
    """Minimal DB session mock."""

    def __init__(self, rows: Optional[list] = None):
        self._rows = rows or []

    def execute(self, *_args, **_kwargs):
        return self

    def fetchall(self):
        return self._rows

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


class _NullSession:
    """Session that raises on any operation — simulates DB unavailable."""

    def execute(self, *_args, **_kwargs):
        raise RuntimeError("Database unavailable")

    def commit(self) -> None:
        raise RuntimeError("Database unavailable")

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RULES = [
    _FakeRule(rule_id="RULE-001", severity="critical", category="traceability", title="TLC Required"),
    _FakeRule(rule_id="RULE-002", severity="warning", category="recordkeeping", title="Timestamp Format"),
    _FakeRule(rule_id="RULE-003", severity="critical", category="recordkeeping", title="Location GLN"),
]


_NO_DB = object()  # sentinel for "simulate DB unavailable"

def _build_client(
    principal: IngestionPrincipal,
    db_session: Any = _NO_DB,
) -> TestClient:
    app = FastAPI()
    app.include_router(rules_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    if db_session is not _NO_DB:
        app.dependency_overrides[_get_db_session] = lambda: db_session
    return TestClient(app, raise_server_exceptions=False)


def _default_principal(**overrides) -> IngestionPrincipal:
    defaults = dict(
        key_id="test-key",
        tenant_id="tenant-1",
        scopes=["*"],
        auth_mode="test",
    )
    defaults.update(overrides)
    return IngestionPrincipal(**defaults)


def _sample_event(**overrides) -> dict:
    defaults = dict(
        event_id="EVT-001",
        event_type="shipping",
        traceability_lot_code="TLC-2026-001",
        product_reference="Romaine Hearts",
        quantity=120.0,
        unit_of_measure="cases",
        from_facility_reference="FAC-001",
        to_facility_reference="FAC-002",
        kdes={},
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Tests: list rules
# ---------------------------------------------------------------------------

class TestListRules:
    def test_list_rules_returns_all(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))
        fake_session = _FakeSession()
        fake_engine = MagicMock()
        fake_engine.load_active_rules.return_value = SAMPLE_RULES

        monkeypatch.setattr(
            "app.rules_router._get_engine",
            lambda db_session: fake_engine,
        )

        with _build_client(_default_principal(), db_session=fake_session) as client:
            resp = client.get("/api/v1/rules")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["rules"]) == 3
        assert data["rules"][0]["rule_id"] == "RULE-001"

    def test_list_rules_filter_severity(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))
        fake_engine = MagicMock()
        fake_engine.load_active_rules.return_value = SAMPLE_RULES

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.get("/api/v1/rules", params={"severity": "warning"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["rules"][0]["rule_id"] == "RULE-002"

    def test_list_rules_filter_category(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))
        fake_engine = MagicMock()
        fake_engine.load_active_rules.return_value = SAMPLE_RULES

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.get("/api/v1/rules", params={"category": "recordkeeping"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        rule_ids = {r["rule_id"] for r in data["rules"]}
        assert rule_ids == {"RULE-002", "RULE-003"}

    def test_list_rules_filter_severity_and_category(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))
        fake_engine = MagicMock()
        fake_engine.load_active_rules.return_value = SAMPLE_RULES

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.get(
                "/api/v1/rules",
                params={"severity": "critical", "category": "recordkeeping"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["rules"][0]["rule_id"] == "RULE-003"

    def test_list_rules_filter_cte_type(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))
        fake_engine = MagicMock()
        fake_engine.load_active_rules.return_value = SAMPLE_RULES
        # get_applicable_rules should be called and its return used
        fake_engine.get_applicable_rules.return_value = [SAMPLE_RULES[0]]

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.get("/api/v1/rules", params={"cte_type": "shipping"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        fake_engine.get_applicable_rules.assert_called_once_with("shipping", SAMPLE_RULES)


# ---------------------------------------------------------------------------
# Tests: get rule detail
# ---------------------------------------------------------------------------

class TestGetRuleDetail:
    def test_get_existing_rule(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))
        fake_engine = MagicMock()
        fake_engine.load_active_rules.return_value = SAMPLE_RULES

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.get("/api/v1/rules/RULE-002")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rule_id"] == "RULE-002"
        assert data["title"] == "Timestamp Format"
        assert "evaluation_logic" in data

    def test_get_nonexistent_rule_returns_404(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))
        fake_engine = MagicMock()
        fake_engine.load_active_rules.return_value = SAMPLE_RULES

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.get("/api/v1/rules/RULE-NOPE")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Rule not found"


# ---------------------------------------------------------------------------
# Tests: evaluate single event
# ---------------------------------------------------------------------------

class TestEvaluateEvent:
    def test_evaluate_compliant_event(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        summary = _FakeEvalSummary(
            compliant=True,
            total_rules=2,
            passed=2,
            failed=0,
            warned=0,
            results=[
                _FakeEvalResult(rule_id="RULE-001", result="pass"),
                _FakeEvalResult(rule_id="RULE-002", result="pass"),
            ],
        )
        fake_engine = MagicMock()
        fake_engine.evaluate_event.return_value = summary

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.post(
                "/api/v1/rules/evaluate",
                json=_sample_event(),
                params={"tenant_id": "tenant-1"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["compliant"] is True
        assert data["event_id"] == "EVT-001"
        assert data["passed"] == 2
        assert data["failed"] == 0
        assert len(data["results"]) == 2

    def test_evaluate_noncompliant_event(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        failure = _FakeEvalResult(
            rule_id="RULE-001",
            rule_title="TLC Required",
            severity="critical",
            result="fail",
            why_failed="Missing traceability_lot_code",
            citation_reference="21 CFR 1.1315",
            remediation_suggestion="Add lot code",
            evidence_fields_inspected=["traceability_lot_code"],
        )
        summary = _FakeEvalSummary(
            compliant=False,
            total_rules=2,
            passed=1,
            failed=1,
            warned=0,
            critical_failures=[failure],
            results=[
                failure,
                _FakeEvalResult(rule_id="RULE-002", result="pass"),
            ],
        )
        fake_engine = MagicMock()
        fake_engine.evaluate_event.return_value = summary

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.post(
                "/api/v1/rules/evaluate",
                json=_sample_event(),
                params={"tenant_id": "tenant-1"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["compliant"] is False
        assert data["failed"] == 1
        assert len(data["critical_failures"]) == 1
        cf = data["critical_failures"][0]
        assert cf["rule_id"] == "RULE-001"
        assert cf["severity"] == "critical"
        assert cf["why_failed"] == "Missing traceability_lot_code"
        assert cf["citation_reference"] == "21 CFR 1.1315"

    def test_evaluate_persist_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        summary = _FakeEvalSummary(compliant=True, results=[])
        fake_engine = MagicMock()
        fake_engine.evaluate_event.return_value = summary
        captured_kwargs: dict = {}

        def _capture_evaluate(event_data, persist=True, tenant_id=None):
            captured_kwargs["persist"] = persist
            captured_kwargs["tenant_id"] = tenant_id
            return summary

        fake_engine.evaluate_event.side_effect = _capture_evaluate
        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.post(
                "/api/v1/rules/evaluate",
                json=_sample_event(),
                params={"tenant_id": "tenant-1", "persist": "false"},
            )

        assert resp.status_code == 200
        assert captured_kwargs["persist"] is False

    def test_evaluate_missing_tenant_returns_400(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))
        monkeypatch.setattr(
            "app.rules_router._get_engine",
            lambda db_session: MagicMock(),
        )

        principal = _default_principal(tenant_id=None)
        with _build_client(principal, db_session=_FakeSession()) as client:
            resp = client.post(
                "/api/v1/rules/evaluate",
                json=_sample_event(),
            )

        assert resp.status_code == 400
        assert "Tenant" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: evaluate batch
# ---------------------------------------------------------------------------

class TestEvaluateBatch:
    def test_evaluate_batch_multiple_events(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        summaries = [
            _FakeEvalSummary(event_id="EVT-001", compliant=True, passed=2, failed=0, warned=0, critical_failures=[]),
            _FakeEvalSummary(event_id="EVT-002", compliant=False, passed=1, failed=1, warned=0, critical_failures=[
                _FakeEvalResult(rule_id="RULE-001", result="fail"),
            ]),
        ]
        fake_engine = MagicMock()
        fake_engine.evaluate_events_batch.return_value = summaries

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        events = [
            _sample_event(event_id="EVT-001"),
            _sample_event(event_id="EVT-002"),
        ]
        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.post(
                "/api/v1/rules/evaluate-batch",
                json={"events": events},
                params={"tenant_id": "tenant-1"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 2
        assert data["compliant_count"] == 1
        assert data["non_compliant_count"] == 1
        assert len(data["summaries"]) == 2
        assert data["summaries"][0]["event_id"] == "EVT-001"
        assert data["summaries"][0]["compliant"] is True
        assert data["summaries"][1]["compliant"] is False

    def test_evaluate_batch_empty_list(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        fake_engine = MagicMock()
        fake_engine.evaluate_events_batch.return_value = []
        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: fake_engine)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.post(
                "/api/v1/rules/evaluate-batch",
                json={"events": []},
                params={"tenant_id": "tenant-1"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 0
        assert data["compliant_count"] == 0


# ---------------------------------------------------------------------------
# Tests: evaluation history
# ---------------------------------------------------------------------------

class TestGetEventEvaluations:
    def test_get_evaluations_returns_results(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        from datetime import datetime, timezone
        evaluated_at = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)

        fake_rows = [
            (
                "eval-1",          # evaluation_id
                "RULE-001",        # rule_id
                1,                 # rule_version
                "fail",            # result
                "Missing TLC",     # why_failed
                '["traceability_lot_code"]',  # evidence (JSON string)
                0.95,              # confidence
                evaluated_at,      # evaluated_at
                "TLC Required",    # title
                "critical",        # severity
                "traceability",    # category
                "21 CFR 1.1315",   # citation_reference
                "Add lot code",    # remediation_suggestion
            ),
        ]

        fake_session = MagicMock()
        fake_session.execute.return_value.fetchall.return_value = fake_rows

        monkeypatch.setattr("app.rules_router._get_engine", lambda db_session: MagicMock())

        with _build_client(_default_principal(), db_session=fake_session) as client:
            resp = client.get(
                "/api/v1/rules/evaluations/EVT-001",
                params={"tenant_id": "tenant-1"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == "EVT-001"
        assert data["total"] == 1
        ev = data["evaluations"][0]
        assert ev["evaluation_id"] == "eval-1"
        assert ev["rule_id"] == "RULE-001"
        assert ev["result"] == "fail"
        assert ev["why_failed"] == "Missing TLC"
        assert ev["severity"] == "critical"
        assert ev["confidence"] == 0.95
        assert ev["evidence_fields_inspected"] == ["traceability_lot_code"]

    def test_get_evaluations_with_result_filter(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        fake_session = MagicMock()
        fake_session.execute.return_value.fetchall.return_value = []

        with _build_client(_default_principal(), db_session=fake_session) as client:
            resp = client.get(
                "/api/v1/rules/evaluations/EVT-001",
                params={"tenant_id": "tenant-1", "result": "fail"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

        # Verify the SQL included the result filter
        call_args = fake_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "result" in sql_text.lower()

    def test_get_evaluations_empty(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        fake_session = MagicMock()
        fake_session.execute.return_value.fetchall.return_value = []

        with _build_client(_default_principal(), db_session=fake_session) as client:
            resp = client.get(
                "/api/v1/rules/evaluations/EVT-NONE",
                params={"tenant_id": "tenant-1"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == "EVT-NONE"
        assert data["total"] == 0
        assert data["evaluations"] == []


# ---------------------------------------------------------------------------
# Tests: seed rules
# ---------------------------------------------------------------------------

class TestSeedRules:
    def test_seed_rules_success(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        def _fake_seed(db_session):
            return 12

        monkeypatch.setattr("app.rules_router.seed_rule_definitions", _fake_seed, raising=False)
        # Also patch the import inside the function
        import types
        fake_shared = types.ModuleType("shared.rules_engine")
        fake_shared.seed_rule_definitions = _fake_seed
        monkeypatch.setitem(sys.modules, "shared.rules_engine", fake_shared)

        with _build_client(_default_principal(), db_session=_FakeSession()) as client:
            resp = client.post("/api/v1/rules/seed")

        assert resp.status_code == 200
        data = resp.json()
        assert data["seeded"] == 12
        assert data["status"] == "ok"

    def test_seed_rules_db_unavailable_returns_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        with _build_client(_default_principal(), db_session=_NullSession()) as client:
            resp = client.post("/api/v1/rules/seed")

        assert resp.status_code >= 500


# ---------------------------------------------------------------------------
# Tests: authentication / authorization
# ---------------------------------------------------------------------------

class TestAuth:
    def test_missing_api_key_returns_401(self, monkeypatch: pytest.MonkeyPatch):
        """When API_KEY is configured but no key header is sent, expect 401."""
        monkeypatch.setenv("API_KEY", "real-secret-key")

        app = FastAPI()
        app.include_router(rules_router)
        # Do NOT override get_ingestion_principal — let the real auth run
        app.dependency_overrides[_get_db_session] = lambda: _FakeSession()

        with TestClient(app) as client:
            resp = client.get("/api/v1/rules")

        assert resp.status_code == 401

    def test_wrong_permission_scope_returns_403(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        # Principal only has billing scope — no rules.read
        principal = _default_principal(scopes=["billing.invoices.read"])
        with _build_client(principal, db_session=_FakeSession()) as client:
            resp = client.get("/api/v1/rules")

        assert resp.status_code == 403

    def test_cross_tenant_access_denied(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        # Principal is tenant-1 but request asks for tenant-2
        principal = _default_principal(tenant_id="tenant-1", scopes=["rules.read"])
        with _build_client(principal, db_session=_FakeSession()) as client:
            resp = client.get("/api/v1/rules", params={"tenant_id": "tenant-2"})

        # Should be 403 due to cross-tenant check
        assert resp.status_code == 403
        assert "Tenant mismatch" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: DB unavailable
# ---------------------------------------------------------------------------

class TestDBUnavailable:
    def test_list_rules_db_unavailable_returns_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        with _build_client(_default_principal(), db_session=_NullSession()) as client:
            resp = client.get("/api/v1/rules")

        assert resp.status_code >= 500

    def test_evaluate_db_unavailable_returns_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_: (True, 99))

        with _build_client(_default_principal(), db_session=_NullSession()) as client:
            resp = client.post(
                "/api/v1/rules/evaluate",
                json=_sample_event(),
                params={"tenant_id": "tenant-1"},
            )

        assert resp.status_code >= 500
