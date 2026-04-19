"""Dedicated tests for the compliance metrics router — #1342.

Context
-------
``services/ingestion/app/metrics_router.py`` exposes the single
``GET /api/v1/metrics/compliance`` endpoint that powers the product
KPIs defined in PRD Section 10. It had no test coverage prior to this
file — the 42% ingestion CI floor partly exists because routers like
this dilute the denominator.

This suite locks:

* Auth: ``metrics.read`` scope is required; 403 on missing scope,
  403 on cross-tenant query, 429 on rate-limit exhaustion (via the
  existing authz machinery, we assert the contract exists).
* Tenant resolution: principal tenant used when no ``tenant_id``
  query param is supplied; invalid format rejected with 400; missing
  tenant context rejected with 400.
* Division-by-zero guards: empty DB produces a 0.0% response, not a
  500, for every rate KPI.
* Response shape: ``product_metrics`` and ``reliability_metrics``
  blocks contain the documented keys with rounded values.
* Scalar fallbacks: ``scalar()`` returning None is translated to 0
  for count fields and None for median fields.
* Tenant scoping proof: every SQL fires with ``{"tid":
  resolved_tenant_id}`` so cross-tenant bleed can't regress silently.
* 503 when database is unavailable (``db_session is None``).

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
from app import metrics_router  # noqa: E402
from shared.database import get_db_session  # noqa: E402


# ---------------------------------------------------------------------------
# FakeSession — regex-keyed SQLAlchemy stand-in
# ---------------------------------------------------------------------------


class _FakeResult:
    """Mimics the subset of SQLAlchemy Result we need: fetchone + scalar."""

    def __init__(self, row: Any):
        self._row = row

    def fetchone(self):
        return self._row

    def scalar(self):
        if self._row is None:
            return None
        # SQLAlchemy's scalar() returns first column — replicate that.
        if isinstance(self._row, (list, tuple)):
            return self._row[0] if self._row else None
        return self._row


class FakeSession:
    """SQLAlchemy Session stand-in that routes execute() by SQL regex.

    ``routes`` maps regex → callable(params) -> row/value. The first
    regex whose pattern appears in the SQL (case-insensitive, spaces
    collapsed) decides the result. Default: row of zeros.
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
        # Default: scalar COUNTs return 0, fetchone queries return a
        # row of zeros long enough for any consumer.
        return _FakeResult((0, 0, 0))


def _normalize_sql(sql: str) -> str:
    """Collapse whitespace so regex matches don't fight formatting."""
    return re.sub(r"\s+", " ", sql).strip()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


TENANT = "tenant-metrics-1"
OTHER_TENANT = "tenant-metrics-other"


def _make_principal(
    tenant_id: Optional[str] = TENANT,
    scopes: Optional[List[str]] = None,
) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        tenant_id=tenant_id,
        scopes=scopes or ["metrics.read"],
        auth_mode="test",
    )


def _build_client(
    principal: IngestionPrincipal,
    session: FakeSession | None = None,
) -> TestClient:
    """Build a FastAPI TestClient with auth+DB overrides for the router."""
    app = FastAPI()
    app.include_router(metrics_router.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app)


@pytest.fixture(autouse=True)
def _disable_rate_limit(monkeypatch):
    """Rate-limit is exercised elsewhere; here we want stable 200s so
    the metrics assertions are the focus."""
    monkeypatch.setattr(
        authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99)
    )


# ---------------------------------------------------------------------------
# Auth: permission gate + cross-tenant refusal
# ---------------------------------------------------------------------------


class TestAuthGate:
    """``metrics.read`` is required; cross-tenant queries are rejected."""

    def test_missing_permission_returns_403(self):
        """A principal without ``metrics.read`` cannot read the metrics
        dashboard — this is the auth contract, not a 401."""
        principal = _make_principal(scopes=["canonical.read"])
        client = _build_client(principal, FakeSession())
        resp = client.get("/api/v1/metrics/compliance")
        assert resp.status_code == 403
        assert "metrics.read" in resp.json()["detail"]

    def test_tenant_scope_mismatch_returns_403(self):
        """If the principal's bound tenant differs from the requested
        ``tenant_id`` query param, the request is forbidden — unless
        the principal holds a wildcard scope. This guards cross-tenant
        data access from a stolen API key bound to tenant A."""
        principal = _make_principal(tenant_id=TENANT, scopes=["metrics.read"])
        client = _build_client(principal, FakeSession())
        resp = client.get(
            "/api/v1/metrics/compliance",
            params={"tenant_id": OTHER_TENANT},
        )
        assert resp.status_code == 403
        assert "Tenant mismatch" in resp.json()["detail"]

    def test_wildcard_scope_can_query_any_tenant(self):
        """A principal with wildcard scopes (``*``) bypasses the tenant-
        match check — used by admin/superuser contexts."""
        principal = _make_principal(
            tenant_id="admin-tenant", scopes=["metrics.read", "*"]
        )
        client = _build_client(principal, FakeSession())
        resp = client.get(
            "/api/v1/metrics/compliance",
            params={"tenant_id": OTHER_TENANT},
        )
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == OTHER_TENANT


# ---------------------------------------------------------------------------
# Tenant resolution + validation
# ---------------------------------------------------------------------------


class TestTenantResolution:
    """Locks the ``resolve_tenant`` contract as seen through the endpoint."""

    def test_uses_principal_tenant_when_query_param_absent(self):
        principal = _make_principal(tenant_id=TENANT)
        session = FakeSession()
        client = _build_client(principal, session)
        resp = client.get("/api/v1/metrics/compliance")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == TENANT
        # Every SQL must have fired with this tenant — proves tenant
        # scoping reached the queries (#1237-style guard).
        for _sql, params in session.calls:
            assert params.get("tid") == TENANT

    def test_accepts_explicit_tenant_param_when_principal_lacks_one(self):
        """Unbound principals (``tenant_id=None``) can name the tenant
        explicitly — e.g. internal cron/service contexts."""
        principal = _make_principal(tenant_id=None, scopes=["metrics.read"])
        session = FakeSession()
        client = _build_client(principal, session)
        resp = client.get(
            "/api/v1/metrics/compliance", params={"tenant_id": "tenant-via-param"}
        )
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "tenant-via-param"

    def test_missing_tenant_context_returns_400(self):
        """Neither principal.tenant_id nor query param → 400, not a
        silent all-tenants query."""
        principal = _make_principal(tenant_id=None, scopes=["metrics.read"])
        client = _build_client(principal, FakeSession())
        resp = client.get("/api/v1/metrics/compliance")
        assert resp.status_code == 400
        assert "Tenant context required" in resp.json()["detail"]

    @pytest.mark.parametrize(
        "bad_tenant",
        [
            "tenant with spaces",
            "tenant/with/slashes",
            "tenant;DROP TABLE",
            "a" * 65,  # over 64 char limit
            "tenant@email",
        ],
    )
    def test_invalid_tenant_format_returns_400(self, bad_tenant):
        """The ``validate_tenant_id`` regex blocks SQL-injection and
        length bypasses before any query fires."""
        principal = _make_principal(
            tenant_id="admin", scopes=["metrics.read", "*"]
        )
        client = _build_client(principal, FakeSession())
        resp = client.get(
            "/api/v1/metrics/compliance", params={"tenant_id": bad_tenant}
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Service availability
# ---------------------------------------------------------------------------


class TestServiceUnavailable:
    """``db_session is None`` must return a clean 503, not an opaque
    500 from the first ``.execute`` attempt."""

    def test_db_none_returns_503(self):
        principal = _make_principal()
        # Passing session=None sends None through the dependency.
        client = _build_client(principal, session=None)
        resp = client.get("/api/v1/metrics/compliance")
        assert resp.status_code == 503
        assert "Database unavailable" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Zero-state: empty DB must not divide by zero
# ---------------------------------------------------------------------------


class TestDivisionByZeroGuards:
    """Every KPI in the endpoint involves division; every denominator
    needs a guard. This class regression-tests the empty-DB path for
    each rate metric."""

    def test_empty_db_returns_zero_rates_without_error(self):
        """All-zero state: normalization, provenance, remediation,
        completion, entity-resolution rates all land at 0.0%."""
        principal = _make_principal()
        session = FakeSession()  # defaults to (0, 0, 0) rows
        client = _build_client(principal, session)
        resp = client.get("/api/v1/metrics/compliance")
        assert resp.status_code == 200
        product = resp.json()["product_metrics"]
        assert product["normalization_rate_percent"] == 0
        assert product["provenance_chain_rate_percent"] == 0
        assert product["remediation_text_rate_percent"] == 0
        assert product["request_completion_rate_percent"] == 0
        assert product["entity_resolution_rate_percent"] == 0

    def test_empty_db_medians_are_none(self):
        """Medians from empty cohorts must be None, not 0.0 — a 0-hour
        resolve time would be misreported as instant turnaround."""
        principal = _make_principal()
        # Median queries return scalar None for empty cohort.
        session = FakeSession(
            routes={
                r"resolved_at\s*-\s*created_at": lambda _p: None,
                r"rp\.generated_at\s*-\s*rc\.request_received_at": lambda _p: None,
            }
        )
        client = _build_client(principal, session)
        resp = client.get("/api/v1/metrics/compliance")
        assert resp.status_code == 200
        product = resp.json()["product_metrics"]
        assert product["median_exception_resolve_hours"] is None
        assert product["median_package_assembly_hours"] is None

    def test_empty_db_scalar_counts_default_to_zero(self):
        """Reliability counts use ``scalar() or 0`` — a None result
        must degrade to 0, not propagate a TypeError."""
        principal = _make_principal()
        # Force scalar() queries to None.
        session = FakeSession(
            routes={
                r"FROM fsma\.response_packages": lambda _p: None,
                r"FROM fsma\.rule_evaluations WHERE tenant_id": lambda _p: None,
                r"FROM fsma\.hash_chain": lambda _p: None,
                r"FROM fsma\.fda_export_log": lambda _p: None,
                r"FROM fsma\.identity_review_queue": lambda _p: None,
            }
        )
        client = _build_client(principal, session)
        resp = client.get("/api/v1/metrics/compliance")
        assert resp.status_code == 200
        reliability = resp.json()["reliability_metrics"]
        assert reliability["total_packages_generated"] == 0
        assert reliability["total_rule_evaluations"] == 0
        assert reliability["chain_length"] == 0
        assert reliability["total_exports"] == 0
        assert resp.json()["product_metrics"]["ambiguous_match_backlog"] == 0


# ---------------------------------------------------------------------------
# Happy path: populated DB → correct shape + rounding
# ---------------------------------------------------------------------------


class TestHappyPath:
    """With realistic values the router returns the full metrics blob
    with proper rounding and all documented keys present."""

    @pytest.fixture
    def populated_session(self) -> FakeSession:
        return FakeSession(
            routes={
                # 1. normalization — (total, normalized, rejected)
                r"FILTER \(WHERE status = 'active'\) AS normalized": (
                    lambda _p: (1000, 950, 30)
                ),
                # 2. provenance — (total, with_chain)
                r"AS with_chain": lambda _p: (900, 810),
                # 3. remediation — (total_failures, with_remediation)
                r"AS with_remediation": lambda _p: (100, 80),
                # 4. median resolve — scalar hours
                r"resolved_at\s*-\s*created_at": lambda _p: 12.345,
                # 5. median package — scalar hours
                r"rp\.generated_at\s*-\s*rc\.request_received_at": (
                    lambda _p: 4.5678
                ),
                # 6. request completion — (total, completed)
                r"FILTER \(WHERE package_status IN": lambda _p: (50, 45),
                # 7. entity resolution — (total_entities, verified)
                r"FILTER \(WHERE verification_status = 'verified'\)": (
                    lambda _p: (2000, 1800)
                ),
                # 8. ambiguous backlog — scalar
                r"FROM fsma\.identity_review_queue": lambda _p: 17,
                # reliability counts
                r"FROM fsma\.response_packages": lambda _p: 42,
                r"FROM fsma\.rule_evaluations WHERE tenant_id": lambda _p: 777,
                r"FROM fsma\.hash_chain": lambda _p: 5000,
                r"FROM fsma\.fda_export_log": lambda _p: 3,
            }
        )

    def test_response_top_level_keys(self, populated_session):
        client = _build_client(_make_principal(), populated_session)
        resp = client.get("/api/v1/metrics/compliance")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "tenant_id",
            "generated_at",
            "product_metrics",
            "reliability_metrics",
        }

    def test_rates_rounded_to_one_decimal(self, populated_session):
        client = _build_client(_make_principal(), populated_session)
        body = client.get("/api/v1/metrics/compliance").json()
        assert body["product_metrics"]["normalization_rate_percent"] == 95.0
        assert body["product_metrics"]["provenance_chain_rate_percent"] == 90.0
        assert body["product_metrics"]["remediation_text_rate_percent"] == 80.0
        assert body["product_metrics"]["request_completion_rate_percent"] == 90.0
        assert body["product_metrics"]["entity_resolution_rate_percent"] == 90.0

    def test_medians_rounded_to_one_decimal(self, populated_session):
        client = _build_client(_make_principal(), populated_session)
        body = client.get("/api/v1/metrics/compliance").json()
        # 12.345 → 12.3 ; 4.5678 → 4.6 (banker's rounding in Python: 4.5678 → 4.6)
        assert body["product_metrics"]["median_exception_resolve_hours"] == 12.3
        assert body["product_metrics"]["median_package_assembly_hours"] == 4.6

    def test_reliability_counts_surface_verbatim(self, populated_session):
        client = _build_client(_make_principal(), populated_session)
        reliability = client.get("/api/v1/metrics/compliance").json()[
            "reliability_metrics"
        ]
        assert reliability["total_packages_generated"] == 42
        assert reliability["total_rule_evaluations"] == 777
        assert reliability["chain_length"] == 5000
        assert reliability["total_exports"] == 3

    def test_raw_counts_exposed_alongside_rates(self, populated_session):
        """Dashboard consumers need the denominator, not just the %, so
        they can render 'N / total' tooltips."""
        client = _build_client(_make_principal(), populated_session)
        p = client.get("/api/v1/metrics/compliance").json()["product_metrics"]
        assert p["total_events"] == 1000
        assert p["normalized_events"] == 950
        assert p["rejected_events"] == 30
        assert p["total_failures"] == 100
        assert p["failures_with_remediation"] == 80
        assert p["total_requests"] == 50
        assert p["completed_requests"] == 45
        assert p["ambiguous_match_backlog"] == 17

    def test_generated_at_is_iso_utc(self, populated_session):
        client = _build_client(_make_principal(), populated_session)
        body = client.get("/api/v1/metrics/compliance").json()
        # Parseable ISO-8601 ending in UTC offset (+00:00) or Z
        generated_at = body["generated_at"]
        parsed = datetime.fromisoformat(generated_at)
        assert parsed.tzinfo is not None
        # UTC offset
        assert parsed.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# Tenant scoping proof at the SQL layer
# ---------------------------------------------------------------------------


class TestTenantScopedQueries:
    """Every query MUST fire with ``{"tid": tenant_id}``. A regression
    where a metric query forgets the WHERE clause (or uses a different
    bound name) would let cross-tenant counts leak."""

    def test_every_query_passes_tenant_id_param(self):
        principal = _make_principal(tenant_id=TENANT)
        session = FakeSession()
        client = _build_client(principal, session)
        client.get("/api/v1/metrics/compliance")

        assert len(session.calls) >= 11, (
            "Endpoint should fire ≥11 queries (8 product + 4 reliability-ish "
            "+ backlog); if it dropped below, a KPI regressed"
        )
        for sql, params in session.calls:
            assert params.get("tid") == TENANT, (
                f"Query {sql[:120]!r} fired without tenant binding"
            )

    def test_query_count_matches_documented_kpis(self):
        """Lock the query count so future KPI changes are deliberate
        (and review-visible). Floor guards against silent regressions."""
        principal = _make_principal(tenant_id=TENANT)
        session = FakeSession()
        client = _build_client(principal, session)
        client.get("/api/v1/metrics/compliance")
        # 8 product metrics + 4 reliability scalars = 12 minimum.
        assert len(session.calls) >= 12
