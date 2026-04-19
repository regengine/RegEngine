"""Coverage for app/metrics_router.py — FSMA 204 compliance KPIs.

Locks:
- GET /api/v1/metrics/compliance returns 503 when db_session is None
- Full product + reliability metrics payload with realistic data
- Safe math on empty tables (no ZeroDivisionError; rates default to 0)
- scalar() → None paths for median queries and counters
- resolve_tenant fallback chain (explicit query > principal.tenant_id > 400)

Issue: #1342
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import metrics_router as mr
from app.authz import IngestionPrincipal


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _build_app(principal, db_session):
    """Mount the router on a clean FastAPI and override both deps."""
    app = FastAPI()
    app.include_router(mr.router)

    # Override the outer require_permission and get_db_session dependencies
    # by patching the callables each Depends wraps.
    from app.authz import get_ingestion_principal
    from shared.database import get_db_session

    async def _principal():
        return principal

    def _db():
        return db_session

    app.dependency_overrides[get_ingestion_principal] = _principal
    app.dependency_overrides[get_db_session] = _db
    # Disable the rate-limit consumer so tests don't need Redis
    import app.authz as authz_mod
    app.state._mr_original = authz_mod.consume_tenant_rate_limit
    authz_mod.consume_tenant_rate_limit = lambda **_: (True, 999)
    return app


def _teardown(app):
    import app.authz as authz_mod
    authz_mod.consume_tenant_rate_limit = app.state._mr_original


def _make_session(*, rows=None, scalars=None):
    """Build a MagicMock Session where execute() returns ordered responses.

    rows: list of (mode, value) pairs where mode is 'row' (fetchone() returns
      a tuple) or 'scalar' (scalar() returns value). Each execute() call
      consumes one entry in order.
    """
    session = MagicMock()

    calls = iter(rows or [])

    def _execute(stmt, params=None):
        mode, value = next(calls)
        if mode == "row":
            return SimpleNamespace(
                fetchone=lambda: value,
                scalar=lambda: value[0] if value else None,
            )
        # scalar mode
        return SimpleNamespace(
            fetchone=lambda: (value,) if value is not None else None,
            scalar=lambda: value,
        )

    session.execute.side_effect = _execute
    return session


# ---------------------------------------------------------------------------
# 503 when DB unavailable
# ---------------------------------------------------------------------------


class TestDbUnavailable:
    def test_returns_503_when_db_session_none(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app = _build_app(principal, db_session=None)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/metrics/compliance?tenant_id=t")
            assert resp.status_code == 503
            assert resp.json()["detail"] == "Database unavailable"
        finally:
            _teardown(app)


# ---------------------------------------------------------------------------
# Happy path — full metrics payload
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_full_metrics_payload(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t1")
        # Order of queries inside the endpoint:
        # 1. normalization (row) -> (total, normalized, rejected)
        # 2. provenance (row) -> (total, with_chain)
        # 3. remediation (row) -> (total_failures, with_remediation)
        # 4. median_resolve (scalar)
        # 5. median_package (scalar)
        # 6. requests_stats (row) -> (total, completed)
        # 7. entity_stats (row) -> (total_entities, verified)
        # 8. ambiguous_backlog (scalar)
        # 9. package_stats (scalar)
        # 10. eval_count (scalar)
        # 11. chain_length (scalar)
        # 12. export_count (scalar)
        session = _make_session(rows=[
            ("row", (100, 80, 5)),            # normalization
            ("row", (80, 72)),                # provenance
            ("row", (20, 18)),                # remediation
            ("scalar", 4.5),                  # median_resolve hours
            ("scalar", 1.25),                 # median_package hours
            ("row", (50, 40)),                # requests_stats
            ("row", (200, 150)),              # entity_stats
            ("scalar", 3),                    # ambiguous_backlog
            ("scalar", 25),                   # package_stats
            ("scalar", 500),                  # eval_count
            ("scalar", 1000),                 # chain_length
            ("scalar", 10),                   # export_count
        ])
        app = _build_app(principal, db_session=session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/metrics/compliance")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["tenant_id"] == "t1"
            assert "generated_at" in body
            pm = body["product_metrics"]
            assert pm["normalization_rate_percent"] == 80.0  # 80/100
            assert pm["total_events"] == 100
            assert pm["normalized_events"] == 80
            assert pm["rejected_events"] == 5
            assert pm["provenance_chain_rate_percent"] == 90.0  # 72/80
            assert pm["remediation_text_rate_percent"] == 90.0  # 18/20
            assert pm["total_failures"] == 20
            assert pm["failures_with_remediation"] == 18
            assert pm["median_exception_resolve_hours"] == 4.5
            assert pm["median_package_assembly_hours"] == 1.2  # rounded
            assert pm["request_completion_rate_percent"] == 80.0  # 40/50
            assert pm["total_requests"] == 50
            assert pm["completed_requests"] == 40
            assert pm["entity_resolution_rate_percent"] == 75.0  # 150/200
            assert pm["ambiguous_match_backlog"] == 3
            rm = body["reliability_metrics"]
            assert rm["total_packages_generated"] == 25
            assert rm["total_rule_evaluations"] == 500
            assert rm["chain_length"] == 1000
            assert rm["total_exports"] == 10
        finally:
            _teardown(app)

    def test_explicit_tenant_id_overrides_principal(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t1")
        session = _make_session(rows=[
            ("row", (0, 0, 0)),  # normalization
            ("row", (0, 0)),      # provenance
            ("row", (0, 0)),      # remediation
            ("scalar", None),     # median_resolve
            ("scalar", None),     # median_package
            ("row", (0, 0)),      # requests_stats
            ("row", (0, 0)),      # entity_stats
            ("scalar", None),     # ambiguous_backlog (None branch)
            ("scalar", None),     # package_stats
            ("scalar", None),     # eval_count
            ("scalar", None),     # chain_length
            ("scalar", None),     # export_count
        ])
        app = _build_app(principal, db_session=session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/metrics/compliance?tenant_id=query-tid")
            assert resp.status_code == 200
            assert resp.json()["tenant_id"] == "query-tid"
        finally:
            _teardown(app)


# ---------------------------------------------------------------------------
# Safe-math edge cases — empty tables and None scalars
# ---------------------------------------------------------------------------


class TestEmptyTables:
    def test_all_zeros_no_division_error(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        session = _make_session(rows=[
            ("row", (0, 0, 0)),   # normalization
            ("row", (0, 0)),      # provenance
            ("row", (0, 0)),      # remediation
            ("scalar", None),     # median_resolve
            ("scalar", None),     # median_package
            ("row", (0, 0)),      # requests_stats
            ("row", (0, 0)),      # entity_stats
            ("scalar", None),     # ambiguous_backlog
            ("scalar", None),     # package_stats
            ("scalar", None),     # eval_count
            ("scalar", None),     # chain_length
            ("scalar", None),     # export_count
        ])
        app = _build_app(principal, db_session=session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/metrics/compliance")
            assert resp.status_code == 200
            pm = resp.json()["product_metrics"]
            assert pm["normalization_rate_percent"] == 0
            assert pm["provenance_chain_rate_percent"] == 0
            assert pm["remediation_text_rate_percent"] == 0
            assert pm["median_exception_resolve_hours"] is None
            assert pm["median_package_assembly_hours"] is None
            assert pm["request_completion_rate_percent"] == 0
            assert pm["entity_resolution_rate_percent"] == 0
            assert pm["ambiguous_match_backlog"] == 0  # coerced from None
            rm = resp.json()["reliability_metrics"]
            assert rm["total_packages_generated"] == 0
            assert rm["total_rule_evaluations"] == 0
            assert rm["chain_length"] == 0
            assert rm["total_exports"] == 0
        finally:
            _teardown(app)

    def test_none_row_objects_treated_as_empty(self):
        """Simulates fetchone() returning None (empty result set)."""
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        session = MagicMock()
        # Chain: each call returns an obj whose fetchone() returns None
        def _exec(stmt, params=None):
            return SimpleNamespace(fetchone=lambda: None, scalar=lambda: None)
        session.execute.side_effect = _exec
        app = _build_app(principal, db_session=session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/metrics/compliance")
            assert resp.status_code == 200
            pm = resp.json()["product_metrics"]
            assert pm["total_events"] == 0
            assert pm["normalized_events"] == 0
            assert pm["rejected_events"] == 0
            assert pm["total_failures"] == 0
            assert pm["failures_with_remediation"] == 0
            assert pm["total_requests"] == 0
            assert pm["completed_requests"] == 0
            assert pm["ambiguous_match_backlog"] == 0
        finally:
            _teardown(app)


# ---------------------------------------------------------------------------
# Tenant resolution
# ---------------------------------------------------------------------------


class TestTenantResolution:
    def test_missing_tenant_context_400(self):
        """Principal has no tenant_id and no ?tenant_id → 400."""
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id=None)
        session = MagicMock()
        session.execute = MagicMock()
        app = _build_app(principal, db_session=session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/metrics/compliance")
            assert resp.status_code == 400
            assert resp.json()["detail"] == "Tenant context required"
        finally:
            _teardown(app)

    def test_invalid_tenant_id_400(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id=None)
        session = MagicMock()
        app = _build_app(principal, db_session=session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/metrics/compliance?tenant_id=bad!@#")
            assert resp.status_code == 400
            assert "Invalid tenant_id format" in resp.json()["detail"]
        finally:
            _teardown(app)


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert mr.router.prefix == "/api/v1/metrics"

    def test_tag(self):
        assert "Compliance Metrics" in mr.router.tags

    def test_compliance_route_registered(self):
        paths = [r.path for r in mr.router.routes]
        assert "/api/v1/metrics/compliance" in paths
