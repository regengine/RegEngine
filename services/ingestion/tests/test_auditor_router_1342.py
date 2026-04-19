"""Dedicated tests for the auditor read-only router — #1342.

Context
-------
``services/ingestion/app/auditor_router.py`` exposes 8 read-only
endpoints under ``/api/v1/audit/*`` that external auditors, FDA
reviewers, and compliance officers rely on. Before this file there
was zero direct test coverage (579 LOC), so regressions in tenant
scoping, 404 semantics, division-by-zero guards, or pagination
controls could ship invisibly.

What this locks:

* Auth: ``audit.read`` scope gates every endpoint — 403 otherwise.
* Tenant resolution: principal's bound tenant is used when the query
  param is absent; cross-tenant queries are rejected (403) unless
  the principal holds the ``*`` wildcard.
* 503 when the database is unavailable (``db_session is None``).
* Per-endpoint shape: ``audit_summary`` division-by-zero guards, the
  status derivation in ``audit_events``, the 404 in
  ``audit_event_detail`` when the store returns ``None``, and the
  ``chain_integrity.status`` flip between ``VERIFIED`` and
  ``NO_RECORDS``.
* Tenant-scoping proof: every SQL fires with ``{"tid":
  resolved_tenant_id}``, so a cross-tenant bleed can't regress
  silently.

Pure-Python. No live Postgres required — the SQLAlchemy ``execute``
call is stubbed with a regex-keyed FakeSession.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Make services/ingestion importable as the ingestion service expects.
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app import auditor_router  # noqa: E402
from shared.database import get_db_session  # noqa: E402


# ---------------------------------------------------------------------------
# FakeSession — regex-keyed SQLAlchemy stand-in (fetchone / fetchall / scalar)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, row: Any):
        self._row = row

    def fetchone(self):
        # if the handler returned a list, assume fetchall semantics
        # and surface the first row for fetchone callers.
        if isinstance(self._row, list):
            return self._row[0] if self._row else None
        return self._row

    def fetchall(self):
        if self._row is None:
            return []
        if isinstance(self._row, list):
            return self._row
        return [self._row]

    def scalar(self):
        if self._row is None:
            return None
        if isinstance(self._row, list):
            return self._row[0][0] if self._row and self._row[0] else None
        if isinstance(self._row, (list, tuple)):
            return self._row[0] if self._row else None
        return self._row


class FakeSession:
    """SQLAlchemy Session stand-in — routes ``execute()`` by SQL regex.

    ``routes`` maps regex → callable(params) -> row/list/scalar. The
    first regex that matches the SQL (case-insensitive, whitespace
    collapsed) decides the result. Unmatched SQL falls back to a
    three-zero row so consumers can still index.
    """

    def __init__(self, routes: Dict[str, Callable[[Dict[str, Any]], Any]] | None = None):
        self.routes = routes or {}
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def execute(self, statement, params: Dict[str, Any] | None = None):
        sql = _normalize_sql(str(statement))
        self.calls.append((sql, params or {}))
        for pattern, handler in self.routes.items():
            if re.search(pattern, sql, re.IGNORECASE):
                return _FakeResult(handler(params or {}))
        return _FakeResult((0, 0, 0, 0))


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


TENANT = "tenant-audit-1"
OTHER_TENANT = "tenant-audit-other"


def _make_principal(
    tenant_id: Optional[str] = TENANT,
    scopes: Optional[List[str]] = None,
) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        tenant_id=tenant_id,
        scopes=scopes or ["audit.read"],
        auth_mode="test",
    )


def _build_client(
    principal: IngestionPrincipal,
    session: FakeSession | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(auditor_router.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app)


@pytest.fixture(autouse=True)
def _disable_rate_limit(monkeypatch):
    monkeypatch.setattr(
        authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99)
    )


# =========================================================================
# Auth gate: every endpoint requires audit.read
# =========================================================================


AUDIT_ENDPOINTS = [
    ("GET", "/api/v1/audit/summary"),
    ("GET", "/api/v1/audit/events"),
    ("GET", "/api/v1/audit/events/evt-1"),
    ("GET", "/api/v1/audit/rules"),
    ("GET", "/api/v1/audit/exceptions"),
    ("GET", "/api/v1/audit/requests"),
    ("GET", "/api/v1/audit/chain"),
    ("GET", "/api/v1/audit/export-log"),
]


class TestAuthGate:
    @pytest.mark.parametrize("method,url", AUDIT_ENDPOINTS)
    def test_missing_permission_returns_403(self, method, url):
        """Every audit endpoint must reject principals lacking
        ``audit.read``. This is the single-source auth gate."""
        principal = _make_principal(scopes=["canonical.read"])
        client = _build_client(principal, FakeSession())
        resp = client.request(method, url)
        assert resp.status_code == 403, (method, url, resp.text)
        assert "audit.read" in resp.json()["detail"]

    @pytest.mark.parametrize("method,url", AUDIT_ENDPOINTS)
    def test_cross_tenant_query_rejected(self, method, url):
        """Cross-tenant query param with a tenant-bound key must 403.
        Prevents a stolen key for tenant A from reading tenant B."""
        principal = _make_principal(tenant_id=TENANT, scopes=["audit.read"])
        client = _build_client(principal, FakeSession())
        resp = client.request(method, f"{url}?tenant_id={OTHER_TENANT}")
        assert resp.status_code == 403, (method, url, resp.text)
        assert "Tenant mismatch" in resp.json()["detail"]

    def test_wildcard_scope_bypasses_tenant_match(self):
        """A principal with ``*`` wildcard can query any tenant."""
        principal = _make_principal(
            tenant_id="admin", scopes=["audit.read", "*"]
        )
        client = _build_client(principal, FakeSession())
        resp = client.get(f"/api/v1/audit/summary?tenant_id={OTHER_TENANT}")
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == OTHER_TENANT


# =========================================================================
# 503 when DB is unavailable
# =========================================================================


class TestDbUnavailable:
    """Every endpoint must translate ``db_session is None`` to HTTP 503
    — not a 500 — so operators can distinguish an outage from a bug."""

    @pytest.mark.parametrize("method,url", AUDIT_ENDPOINTS)
    def test_db_none_returns_503(self, method, url):
        principal = _make_principal()
        client = _build_client(principal, session=None)
        resp = client.request(method, url)
        assert resp.status_code == 503, (method, url, resp.text)
        assert "Database unavailable" in resp.json()["detail"]


# =========================================================================
# Tenant resolution
# =========================================================================


class TestTenantResolution:
    def test_principal_tenant_used_when_query_omits(self):
        """With no ``tenant_id`` param the principal's bound tenant
        is used as the scoping key for every downstream SQL."""
        principal = _make_principal(tenant_id=TENANT)
        session = FakeSession(
            {r"COUNT\(\*\)\s+FROM\s+fsma\.traceability_events": lambda _: (0,)}
        )
        client = _build_client(principal, session)
        resp = client.get("/api/v1/audit/summary")
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == TENANT
        assert all(call[1].get("tid") == TENANT for call in session.calls)

    def test_missing_tenant_context_returns_400(self):
        principal = _make_principal(tenant_id=None)
        client = _build_client(principal, FakeSession())
        resp = client.get("/api/v1/audit/summary")
        assert resp.status_code == 400
        assert "Tenant context required" in resp.json()["detail"]

    def test_invalid_tenant_format_rejected(self):
        """Illegal characters in the query param are rejected before
        any SQL fires."""
        principal = _make_principal(
            tenant_id="admin", scopes=["audit.read", "*"]
        )
        session = FakeSession()
        client = _build_client(principal, session)
        resp = client.get("/api/v1/audit/summary?tenant_id=bad;tenant")
        assert resp.status_code == 400
        assert "Invalid tenant_id format" in resp.json()["detail"]
        assert session.calls == []


# =========================================================================
# GET /summary
# =========================================================================


class TestSummary:
    def test_empty_db_returns_zero_rates_no_div_by_zero(self):
        """Empty DB must produce a 200 with zero totals and 0% pass
        rate — never a 500 from division-by-zero."""
        session = FakeSession({
            r"COUNT\(\*\)\s+FROM\s+fsma\.traceability_events.*status": lambda _: (0,),
            r"COUNT\(\*\).*rule_evaluations": lambda _: (0, 0, 0, 0),
            r"COUNT\(\*\).*exception_cases": lambda _: (0, 0, 0),
            r"COUNT\(\*\).*request_cases": lambda _: (0, 0, 0),
            r"COUNT\(\*\)\s+FROM\s+fsma\.hash_chain": lambda _: (0,),
            r"source_system, COUNT": lambda _: [],
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["compliance"]["pass_rate_percent"] == 0
        assert body["compliance"]["total_evaluations"] == 0
        assert body["chain_integrity"]["status"] == "NO_RECORDS"
        assert body["chain_integrity"]["chain_length"] == 0
        assert body["records"]["ingestion_sources"] == {}

    def test_populated_db_computes_pass_rate_and_sources(self):
        session = FakeSession({
            r"COUNT\(\*\)\s+FROM\s+fsma\.traceability_events.*status": lambda _: (150,),
            r"COUNT\(\*\).*rule_evaluations": lambda _: (100, 70, 20, 10),
            r"COUNT\(\*\).*exception_cases": lambda _: (12, 5, 2),
            r"COUNT\(\*\).*request_cases": lambda _: (8, 3, 2),
            r"COUNT\(\*\)\s+FROM\s+fsma\.hash_chain": lambda _: (150,),
            r"source_system, COUNT": lambda _: [("SAP", 120), ("CSV", 30)],
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["records"]["total_canonical_events"] == 150
        assert body["records"]["ingestion_sources"] == {"SAP": 120, "CSV": 30}
        assert body["compliance"]["total_evaluations"] == 100
        assert body["compliance"]["passed"] == 70
        assert body["compliance"]["failed"] == 20
        assert body["compliance"]["warned"] == 10
        assert body["compliance"]["pass_rate_percent"] == 70.0
        assert body["exceptions"] == {
            "total": 12, "open": 5, "critical_open": 2,
        }
        assert body["requests"] == {
            "total": 8, "submitted": 3, "active": 2,
        }
        assert body["chain_integrity"]["chain_length"] == 150
        assert body["chain_integrity"]["status"] == "VERIFIED"
        # 'generated_at' is an ISO-8601 timestamp
        datetime.fromisoformat(body["generated_at"])

    def test_none_scalars_treated_as_zero(self):
        """``scalar()`` may return None on an empty aggregate — the
        router uses ``or 0`` to keep downstream math safe."""
        session = FakeSession({
            r"COUNT\(\*\)\s+FROM\s+fsma\.traceability_events.*status": lambda _: None,
            r"COUNT\(\*\).*rule_evaluations": lambda _: None,
            r"COUNT\(\*\).*exception_cases": lambda _: None,
            r"COUNT\(\*\).*request_cases": lambda _: None,
            r"COUNT\(\*\)\s+FROM\s+fsma\.hash_chain": lambda _: None,
            r"source_system, COUNT": lambda _: [],
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["records"]["total_canonical_events"] == 0
        assert body["compliance"]["total_evaluations"] == 0
        assert body["exceptions"]["total"] == 0


# =========================================================================
# GET /events
# =========================================================================


def _events_row(
    event_id: str = "evt-1",
    event_type: str = "receiving",
    total_rules: int = 3,
    passed: int = 3,
    failed: int = 0,
):
    return (
        event_id,
        event_type,
        "TLC-001",            # traceability_lot_code
        "PROD-REF",           # product_reference
        42.0,                 # quantity
        "kg",                 # unit_of_measure
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        "SAP",                # source_system
        0.95,                 # confidence_score
        "1.0",                # schema_version
        datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
        total_rules,
        passed,
        failed,
    )


class TestEvents:
    def test_returns_compliant_status_when_all_rules_pass(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: [_events_row()]
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        e = body["events"][0]
        assert e["event_id"] == "evt-1"
        assert e["compliance"]["status"] == "compliant"
        assert e["compliance"]["failed"] == 0

    def test_returns_non_compliant_when_any_rule_failed(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: [
                _events_row(total_rules=3, passed=2, failed=1)
            ]
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events")
        assert resp.json()["events"][0]["compliance"]["status"] == "non_compliant"

    def test_returns_unevaluated_when_no_rules(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: [
                _events_row(total_rules=0, passed=0, failed=0)
            ]
        })
        client = _build_client(_make_principal(), session)
        assert (
            client.get("/api/v1/audit/events").json()["events"][0]
            ["compliance"]["status"]
            == "unevaluated"
        )

    def test_tlc_filter_passes_through_to_sql_params(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events?tlc=TLC-XYZ")
        assert resp.status_code == 200
        assert any(c[1].get("tlc") == "TLC-XYZ" for c in session.calls)

    def test_event_type_filter_passes_through(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events?event_type=receiving")
        assert resp.status_code == 200
        assert any(c[1].get("event_type") == "receiving" for c in session.calls)

    def test_compliance_status_compliant_adds_sql_filter(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/events?compliance_status=compliant")
        last_sql = session.calls[-1][0]
        assert "failed" in last_sql.lower()
        assert "total_rules" in last_sql.lower()

    def test_compliance_status_non_compliant_adds_sql_filter(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/events?compliance_status=non_compliant")
        last_sql = session.calls[-1][0]
        assert "> 0" in last_sql

    def test_compliance_status_unevaluated_adds_sql_filter(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/events?compliance_status=unevaluated")
        last_sql = session.calls[-1][0]
        assert "= 0" in last_sql

    def test_limit_capped_at_200(self):
        """FastAPI's ``Query(..., le=200)`` rejects limit > 200 at
        validation time."""
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events?limit=500")
        assert resp.status_code == 422

    def test_limit_and_offset_propagate_to_sql(self):
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events?limit=25&offset=50")
        assert resp.status_code == 200
        # The WHERE/ORDER-BY SQL carried :lim and :off bindings
        params = session.calls[-1][1]
        assert params["lim"] == 25
        assert params["off"] == 50

    def test_null_timestamp_and_quantity_handled(self):
        """Defensive: missing timestamps and quantities don't crash
        the response assembly."""
        row = (
            "evt-null", "receiving", "TLC", "PROD", None, "kg",
            None, "SAP", None, "1.0", None,
            0, 0, 0,
        )
        session = FakeSession({
            r"FROM fsma\.traceability_events": lambda _: [row]
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events")
        assert resp.status_code == 200
        e = resp.json()["events"][0]
        assert e["quantity"] == 0
        assert e["event_timestamp"] is None
        assert e["created_at"] is None
        assert e["confidence_score"] == 1.0  # fallback default


# =========================================================================
# GET /events/{event_id}
# =========================================================================


class TestEventDetail:
    def test_404_when_store_returns_none(self, monkeypatch):
        # The store is instantiated inside the handler — patch the
        # class so the instance has a ``get_event`` returning None.
        class _FakeStore:
            def __init__(self, *a, **k): pass
            def get_event(self, *a, **k): return None

        from shared import canonical_persistence
        monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _FakeStore)

        client = _build_client(_make_principal(), FakeSession())
        resp = client.get("/api/v1/audit/events/evt-missing")
        assert resp.status_code == 404
        assert "Event not found" in resp.json()["detail"]

    def test_happy_path_merges_store_evals_chain_and_attachments(self, monkeypatch):
        """The detail endpoint enriches the base event with rule
        evaluations, hash-chain position, and evidence attachments.
        Each source is exercised independently."""
        event_payload: Dict[str, Any] = {
            "event_id": "evt-1",
            "event_type": "receiving",
            "tenant_id": TENANT,
        }

        class _FakeStore:
            def __init__(self, db, dual_write=False):
                self.db = db
                self.dual_write = dual_write
            def get_event(self, tenant_id, event_id, include_raw_payload=False):
                assert tenant_id == TENANT
                assert event_id == "evt-1"
                # The auditor endpoint MUST request raw payload —
                # this is a chain-of-custody requirement (#1297).
                assert include_raw_payload is True
                return dict(event_payload)

        from shared import canonical_persistence
        monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _FakeStore)

        eval_row = (
            "eval-1", "pass", None, '["field.a","field.b"]', 0.99,
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            "Rule title", "critical", "CTE", "21 CFR 1.1345",
            "Remediation text", "v1",
        )
        chain_row = (
            42,
            "eventhash",
            "prevhash",
            "chainhash",
            datetime(2026, 1, 3, tzinfo=timezone.utc),
        )
        attach_row = (
            "att-1", "invoice", "receipt.pdf", "sha256:deadbeef",
            "application/pdf", "s3://bucket/key",
            datetime(2026, 1, 4, tzinfo=timezone.utc),
        )

        session = FakeSession({
            r"FROM fsma\.rule_evaluations re": lambda _: [eval_row],
            r"FROM fsma\.hash_chain h": lambda _: chain_row,
            r"FROM fsma\.evidence_attachments": lambda _: [attach_row],
        })

        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events/evt-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_id"] == "evt-1"
        # Rule evaluation shape
        assert len(body["rule_evaluations"]) == 1
        re_entry = body["rule_evaluations"][0]
        assert re_entry["evaluation_id"] == "eval-1"
        assert re_entry["result"] == "pass"
        assert re_entry["evidence_fields_inspected"] == ["field.a", "field.b"]
        assert re_entry["rule_title"] == "Rule title"
        assert re_entry["citation_reference"] == "21 CFR 1.1345"
        # Chain position
        assert body["chain_position"]["sequence_num"] == 42
        assert body["chain_position"]["event_hash"] == "eventhash"
        assert body["chain_position"]["chain_hash"] == "chainhash"
        # Attachments
        assert len(body["evidence_attachments"]) == 1
        a = body["evidence_attachments"][0]
        assert a["file_name"] == "receipt.pdf"
        assert a["mime_type"] == "application/pdf"
        assert a["storage_uri"] == "s3://bucket/key"

    def test_evidence_fields_inspected_accepts_list_directly(self, monkeypatch):
        """Some DBs return JSONB as a Python list, others as a JSON
        string. Both paths must work."""

        class _FakeStore:
            def __init__(self, *a, **k): pass
            def get_event(self, *a, **k): return {"event_id": "evt-1"}

        from shared import canonical_persistence
        monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _FakeStore)

        eval_row = (
            "eval-1", "pass", None, ["a", "b"], 1.0, None,
            "Title", "warning", "CTE", "ref", "rem", "v1",
        )
        session = FakeSession({
            r"FROM fsma\.rule_evaluations re": lambda _: [eval_row],
            r"FROM fsma\.hash_chain h": lambda _: None,
            r"FROM fsma\.evidence_attachments": lambda _: [],
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events/evt-1")
        assert resp.status_code == 200
        assert resp.json()["rule_evaluations"][0]["evidence_fields_inspected"] == ["a", "b"]

    def test_evidence_fields_none_defaults_to_empty_list(self, monkeypatch):
        """``None`` in the JSONB slot → empty list, not a crash."""

        class _FakeStore:
            def __init__(self, *a, **k): pass
            def get_event(self, *a, **k): return {"event_id": "evt-1"}

        from shared import canonical_persistence
        monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _FakeStore)

        eval_row = (
            "eval-1", "pass", None, None, None, None,
            "Title", "warning", "CTE", "ref", "rem", "v1",
        )
        session = FakeSession({
            r"FROM fsma\.rule_evaluations re": lambda _: [eval_row],
            r"FROM fsma\.hash_chain h": lambda _: None,
            r"FROM fsma\.evidence_attachments": lambda _: [],
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events/evt-1")
        assert resp.status_code == 200
        assert resp.json()["rule_evaluations"][0]["evidence_fields_inspected"] == []
        assert resp.json()["rule_evaluations"][0]["confidence"] == 1.0

    def test_no_chain_position_when_hash_chain_row_absent(self, monkeypatch):
        class _FakeStore:
            def __init__(self, *a, **k): pass
            def get_event(self, *a, **k): return {"event_id": "evt-1"}

        from shared import canonical_persistence
        monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _FakeStore)

        session = FakeSession({
            r"FROM fsma\.rule_evaluations re": lambda _: [],
            r"FROM fsma\.hash_chain h": lambda _: None,
            r"FROM fsma\.evidence_attachments": lambda _: [],
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/events/evt-1")
        assert resp.status_code == 200
        assert "chain_position" not in resp.json()


# =========================================================================
# GET /rules
# =========================================================================


class TestRules:
    def test_returns_rule_catalog_with_pass_rate(self):
        rule_row = (
            "rule-1", "Receiving lot must reference a PO",
            "critical", "CTE_MISSING",
            "21 CFR 1.1345", datetime(2026, 1, 1).date(),
            100, 80, 15, 5,
        )
        session = FakeSession({
            r"FROM fsma\.rule_definitions": lambda _: [rule_row]
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/rules")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        r = body["rules"][0]
        assert r["rule_id"] == "rule-1"
        assert r["severity"] == "critical"
        assert r["citation_reference"] == "21 CFR 1.1345"
        assert r["evaluation_stats"] == {
            "total": 100, "passed": 80, "failed": 15,
            "warned": 5, "pass_rate_percent": 80.0,
        }

    def test_zero_evaluations_yields_none_pass_rate_not_divide_by_zero(self):
        """A newly-added rule has no evaluations yet — the router
        reports ``pass_rate_percent: null`` instead of blowing up."""
        rule_row = (
            "rule-new", "Brand new rule",
            "warning", "CTE_MISSING",
            "21 CFR 1.1345", None,
            0, 0, 0, 0,
        )
        session = FakeSession({
            r"FROM fsma\.rule_definitions": lambda _: [rule_row]
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/rules")
        assert resp.status_code == 200
        assert resp.json()["rules"][0]["evaluation_stats"]["pass_rate_percent"] is None

    def test_empty_catalog_returns_empty_list(self):
        session = FakeSession({
            r"FROM fsma\.rule_definitions": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        body = client.get("/api/v1/audit/rules").json()
        assert body["rules"] == []
        assert body["total"] == 0


# =========================================================================
# GET /exceptions
# =========================================================================


class TestExceptions:
    def test_returns_exception_history_rows(self):
        row = (
            "exc-1", "critical", "open", "CTE_MISSING",
            "ACME Farms", "Reingest", None, None, None,
            "user-42",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            None,
            2,
        )
        session = FakeSession({
            r"FROM fsma\.exception_cases": lambda _: [row]
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/exceptions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        case = body["cases"][0]
        assert case["case_id"] == "exc-1"
        assert case["severity"] == "critical"
        assert case["source_supplier"] == "ACME Farms"
        assert case["signoff_count"] == 2
        assert case["resolved_at"] is None

    def test_limit_capped_at_500(self):
        session = FakeSession()
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/exceptions?limit=9999")
        assert resp.status_code == 422

    def test_limit_propagated_to_sql(self):
        session = FakeSession({
            r"FROM fsma\.exception_cases": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/exceptions?limit=75")
        assert any(c[1].get("lim") == 75 for c in session.calls)

    def test_resolved_at_serialized_when_present(self):
        row = (
            "exc-2", "warning", "resolved", "CTE_MISSING",
            "SUP", "rem", "done", None, None, "user-1",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            0,
        )
        session = FakeSession({
            r"FROM fsma\.exception_cases": lambda _: [row]
        })
        client = _build_client(_make_principal(), session)
        body = client.get("/api/v1/audit/exceptions").json()
        assert body["cases"][0]["resolved_at"] is not None
        datetime.fromisoformat(body["cases"][0]["resolved_at"])


# =========================================================================
# GET /requests
# =========================================================================


class TestRequests:
    def test_returns_request_cases(self):
        row = (
            "req-1", "FDA", "email", "tlc", "submitted", 10, 0,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
            1, 1, 2,
        )
        session = FakeSession({
            r"FROM fsma\.request_cases": lambda _: [row]
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/requests")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        r = body["cases"][0]
        assert r["request_case_id"] == "req-1"
        assert r["requesting_party"] == "FDA"
        assert r["package_count"] == 1
        assert r["submission_count"] == 1
        assert r["signoff_count"] == 2
        # Timestamps round-trip through ISO-8601
        datetime.fromisoformat(r["request_received_at"])
        datetime.fromisoformat(r["response_due_at"])
        datetime.fromisoformat(r["submission_timestamp"])

    def test_null_timestamps_serialized_as_null(self):
        row = (
            "req-draft", "FDA", "email", "tlc", "draft", 0, 5,
            None, None, None, 0, 0, 0,
        )
        session = FakeSession({
            r"FROM fsma\.request_cases": lambda _: [row]
        })
        client = _build_client(_make_principal(), session)
        body = client.get("/api/v1/audit/requests").json()
        r = body["cases"][0]
        assert r["request_received_at"] is None
        assert r["response_due_at"] is None
        assert r["submission_timestamp"] is None

    def test_empty_returns_empty_cases(self):
        session = FakeSession({
            r"FROM fsma\.request_cases": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        body = client.get("/api/v1/audit/requests").json()
        assert body["cases"] == []
        assert body["total"] == 0


# =========================================================================
# GET /chain
# =========================================================================


class TestChain:
    def test_delegates_to_verify_chain(self, monkeypatch):
        """The handler constructs a ``CTEPersistence`` and delegates
        to ``verify_chain(tenant_id)`` — the test verifies the tenant
        is passed through and the response shape matches the
        documented contract."""

        captured = {}

        class _FakeResult:
            valid = True
            chain_length = 17
            errors = []
            checked_at = "2026-04-18T12:00:00+00:00"

        class _FakePersistence:
            def __init__(self, db):
                captured["db"] = db
            def verify_chain(self, tenant_id):
                captured["tenant"] = tenant_id
                return _FakeResult()

        from shared import cte_persistence
        monkeypatch.setattr(cte_persistence, "CTEPersistence", _FakePersistence)

        client = _build_client(_make_principal(), FakeSession())
        resp = client.get("/api/v1/audit/chain")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chain_valid"] is True
        assert body["chain_length"] == 17
        assert body["errors"] == []
        assert body["verified_at"] == "2026-04-18T12:00:00+00:00"
        assert body["verification_method"].startswith("SHA-256")
        assert captured["tenant"] == TENANT

    def test_chain_invalid_returns_errors(self, monkeypatch):
        class _FakeResult:
            valid = False
            chain_length = 5
            errors = ["seq 3: chain_hash mismatch", "seq 4: orphan"]
            checked_at = "2026-04-18T12:00:00+00:00"

        class _FakePersistence:
            def __init__(self, db): pass
            def verify_chain(self, tenant_id): return _FakeResult()

        from shared import cte_persistence
        monkeypatch.setattr(cte_persistence, "CTEPersistence", _FakePersistence)

        client = _build_client(_make_principal(), FakeSession())
        body = client.get("/api/v1/audit/chain").json()
        assert body["chain_valid"] is False
        assert len(body["errors"]) == 2


# =========================================================================
# GET /export-log
# =========================================================================


class TestExportLog:
    def test_returns_export_history(self):
        row = (
            "exp-1", "fda_csv", "TLC-001",
            datetime(2026, 1, 1).date(),
            datetime(2026, 1, 31).date(),
            250, "sha256:cafef00d", "admin-1",
            datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        session = FakeSession({
            r"FROM fsma\.fda_export_log": lambda _: [row]
        })
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/export-log")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        e = body["exports"][0]
        assert e["export_id"] == "exp-1"
        assert e["export_type"] == "fda_csv"
        assert e["record_count"] == 250
        assert e["export_hash"] == "sha256:cafef00d"
        # Date fields stringified
        assert e["query_start_date"] == "2026-01-01"
        assert e["query_end_date"] == "2026-01-31"
        # Generated_at is an ISO timestamp
        datetime.fromisoformat(e["generated_at"])

    def test_null_dates_serialized_as_null(self):
        row = (
            "exp-2", "epcis", None, None, None,
            0, "sha256:abc", "system", None,
        )
        session = FakeSession({
            r"FROM fsma\.fda_export_log": lambda _: [row]
        })
        client = _build_client(_make_principal(), session)
        body = client.get("/api/v1/audit/export-log").json()
        e = body["exports"][0]
        assert e["query_start_date"] is None
        assert e["query_end_date"] is None
        assert e["query_tlc"] is None
        assert e["generated_at"] is None

    def test_limit_capped_at_200(self):
        session = FakeSession()
        client = _build_client(_make_principal(), session)
        resp = client.get("/api/v1/audit/export-log?limit=5000")
        assert resp.status_code == 422

    def test_limit_propagated_to_sql(self):
        session = FakeSession({
            r"FROM fsma\.fda_export_log": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/export-log?limit=17")
        assert any(c[1].get("lim") == 17 for c in session.calls)

    def test_empty_returns_empty_exports(self):
        session = FakeSession({
            r"FROM fsma\.fda_export_log": lambda _: []
        })
        client = _build_client(_make_principal(), session)
        body = client.get("/api/v1/audit/export-log").json()
        assert body["exports"] == []
        assert body["total"] == 0


# =========================================================================
# Tenant-scoping proof: every endpoint's SQL uses :tid = resolved_tenant
# =========================================================================


class TestTenantScoping:
    """Regression guard: every SQL the router fires must bind ``:tid``
    to the resolved tenant. This makes a cross-tenant leak a test
    failure, not a silent production bug."""

    def test_summary_all_sqls_scoped_to_tenant(self):
        session = FakeSession()
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/summary")
        assert session.calls, "expected at least one SQL call"
        for sql, params in session.calls:
            assert params.get("tid") == TENANT, (sql, params)

    def test_events_scoped_to_tenant(self):
        session = FakeSession({r"FROM fsma\.traceability_events": lambda _: []})
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/events")
        for _, params in session.calls:
            assert params.get("tid") == TENANT

    def test_rules_scoped_to_tenant(self):
        session = FakeSession({r"FROM fsma\.rule_definitions": lambda _: []})
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/rules")
        for _, params in session.calls:
            assert params.get("tid") == TENANT

    def test_exceptions_scoped_to_tenant(self):
        session = FakeSession({r"FROM fsma\.exception_cases": lambda _: []})
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/exceptions")
        for _, params in session.calls:
            assert params.get("tid") == TENANT

    def test_requests_scoped_to_tenant(self):
        session = FakeSession({r"FROM fsma\.request_cases": lambda _: []})
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/requests")
        for _, params in session.calls:
            assert params.get("tid") == TENANT

    def test_export_log_scoped_to_tenant(self):
        session = FakeSession({r"FROM fsma\.fda_export_log": lambda _: []})
        client = _build_client(_make_principal(), session)
        client.get("/api/v1/audit/export-log")
        for _, params in session.calls:
            assert params.get("tid") == TENANT
