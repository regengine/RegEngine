"""Coverage for app/recall_report.py — recall readiness report endpoint.

Locks:
- _grade / _status helpers — all threshold bands
- _query_scoring_data: happy path with gaps, chain_length=0 path
  (no max_seq query), SessionLocal raise → None, execute raise → None
- Pydantic models — RecallDimension, RecallReport
- GET /{tenant_id}/report: demo mode (None scoring), demo mode
  (cte_count=0), real mode (low suppliers + no chain + no export),
  real mode (medium suppliers + chain gaps + has export), real mode
  (high suppliers + clean chain + has export)

Issue: #1342
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import recall_report as rr
from app.recall_report import (
    RecallDimension,
    RecallReport,
    _grade,
    _query_scoring_data,
    _status,
    router,
)


# ---------------------------------------------------------------------------
# Test fixtures / helpers
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


class _ScoringSession:
    """SQL-substring-routing session for _query_scoring_data.

    Pass a dict of {sql_substring: scalar_value}. Optional `raise_on`
    maps substrings → exceptions to simulate mid-query failures.
    """
    def __init__(self, route=None, raise_on=None):
        self.route = route or {}
        self.raise_on = raise_on or {}
        self.closed = False

    def execute(self, stmt, params=None):
        sql = str(stmt)
        for pat, exc in self.raise_on.items():
            if pat in sql:
                raise exc
        for pat, value in self.route.items():
            if pat in sql:
                return SimpleNamespace(scalar=lambda v=value: v)
        return SimpleNamespace(scalar=lambda: None)

    def close(self):
        self.closed = True


# Substrings used to route execute() calls:
#   "COUNT(*) FROM fsma.cte_events"     → cte_count
#   "COUNT(DISTINCT traceability_lot"   → tlc_count
#   "COUNT(DISTINCT event_type)"        → cte_types
#   "COUNT(*) FROM fsma.fda_export_log" → has_export
#   "COUNT(*) FROM fsma.tenant_suppliers" → supplier_count
#   "COUNT(*) FROM fsma.hash_chain"     → chain_length
#   "MAX(sequence_num)"                 → max_seq (gaps branch)


def _full_route(
    cte_count=50,
    tlc_count=8,
    cte_types=4,
    has_export=3,
    supplier_count=12,
    chain_length=100,
    max_seq=100,
):
    """Build a full route dict for _query_scoring_data."""
    return {
        "COUNT(*) FROM fsma.cte_events": cte_count,
        "COUNT(DISTINCT traceability_lot": tlc_count,
        "COUNT(DISTINCT event_type)": cte_types,
        "COUNT(*) FROM fsma.fda_export_log": has_export,
        "COUNT(*) FROM fsma.tenant_suppliers": supplier_count,
        "COUNT(*) FROM fsma.hash_chain": chain_length,
        "MAX(sequence_num)": max_seq,
    }


# ---------------------------------------------------------------------------
# _grade / _status helpers
# ---------------------------------------------------------------------------


class TestGradeHelper:
    @pytest.mark.parametrize("score,expected", [
        (100, "A"), (95, "A"), (90, "A"),
        (89, "B"), (85, "B"), (80, "B"),
        (79, "C"), (75, "C"), (70, "C"),
        (69, "D"), (65, "D"), (60, "D"),
        (59, "F"), (30, "F"), (0, "F"),
    ])
    def test_grade_threshold(self, score, expected):
        assert _grade(score) == expected


class TestStatusHelper:
    @pytest.mark.parametrize("score,expected", [
        (100, "excellent"), (90, "excellent"),
        (89, "good"), (80, "good"),
        (79, "needs_improvement"), (70, "needs_improvement"),
        (69, "critical"), (0, "critical"),
    ])
    def test_status_threshold(self, score, expected):
        assert _status(score) == expected


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_recall_dimension_defaults(self):
        d = RecallDimension(
            id="x", name="X", score=80, grade="B", status="good",
            findings=[], recommendations=[],
        )
        assert d.max_score == 100

    def test_recall_report_demo_defaults(self):
        r = RecallReport(
            tenant_id="t", generated_at="now", report_title="r",
            overall_score=80, overall_grade="B", overall_status="good",
            time_to_respond_estimate="1h",
            dimensions=[], executive_summary="s",
            action_items=[], regulatory_citations=[],
        )
        assert r.demo_mode is False
        assert r.demo_disclaimer is None


# ---------------------------------------------------------------------------
# _query_scoring_data
# ---------------------------------------------------------------------------


class TestQueryScoringData:
    def test_happy_path_with_gaps(self, monkeypatch):
        sess = _ScoringSession(route=_full_route(chain_length=50, max_seq=55))
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: sess)

        data = _query_scoring_data("t1")
        assert data is not None
        assert data["cte_count"] == 50
        assert data["tlc_count"] == 8
        assert data["cte_types"] == 4
        assert data["has_export"] is True  # 3 > 0
        assert data["supplier_count"] == 12
        assert data["chain_length"] == 50
        assert data["chain_gap_count"] == 5  # 55 - 50
        assert sess.closed is True

    def test_happy_path_no_gaps(self, monkeypatch):
        """max_seq <= chain_length → gap_count clamps to 0 via max(0, ...)."""
        sess = _ScoringSession(route=_full_route(chain_length=50, max_seq=50))
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: sess)

        data = _query_scoring_data("t1")
        assert data["chain_gap_count"] == 0

    def test_has_export_false_when_count_zero(self, monkeypatch):
        sess = _ScoringSession(route=_full_route(has_export=0))
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: sess)

        data = _query_scoring_data("t1")
        assert data["has_export"] is False

    def test_chain_length_zero_skips_max_seq(self, monkeypatch):
        """If chain_length is zero, max_seq query is not issued and
        chain_gap_count stays at zero."""
        route = _full_route(chain_length=0)
        # Make max_seq throw to prove it isn't called
        sess = _ScoringSession(
            route=route,
            raise_on={"MAX(sequence_num)": RuntimeError("should not be called")},
        )
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: sess)

        data = _query_scoring_data("t1")
        assert data["chain_length"] == 0
        assert data["chain_gap_count"] == 0

    def test_scalar_returns_none_coalesces_to_zero(self, monkeypatch):
        """When db.execute().scalar() returns None, we coalesce to 0."""
        # Empty route means every scalar() returns None
        sess = _ScoringSession(route={})
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: sess)

        data = _query_scoring_data("t1")
        assert data is not None
        assert data["cte_count"] == 0
        assert data["chain_length"] == 0
        assert data["chain_gap_count"] == 0

    def test_sessionlocal_raises_returns_none(self, monkeypatch):
        """SessionLocal() itself raising is caught and returns None."""
        import shared.database as db_mod

        def _boom():
            raise RuntimeError("connection refused")

        monkeypatch.setattr(db_mod, "SessionLocal", _boom)
        assert _query_scoring_data("t1") is None

    def test_execute_raises_returns_none(self, monkeypatch):
        """An execute() exception is caught and returns None."""
        sess = _ScoringSession(
            raise_on={"COUNT(*) FROM fsma.cte_events": ValueError("boom")},
        )
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: sess)

        assert _query_scoring_data("t1") is None
        # db.close() was still called via finally
        assert sess.closed is True


# ---------------------------------------------------------------------------
# GET /{tenant_id}/report — demo mode
# ---------------------------------------------------------------------------


class TestGenerateReportDemoMode:
    def test_demo_mode_when_scoring_returns_none(self, client, monkeypatch):
        monkeypatch.setattr(rr, "_query_scoring_data", lambda tid: None)

        r = client.get("/api/v1/recall/acme/report")
        assert r.status_code == 200
        body = r.json()
        assert body["demo_mode"] is True
        assert body["demo_disclaimer"] is not None
        assert body["tenant_id"] == "acme"
        # Demo mode uses hardcoded "4.2 hours" estimate
        assert "4.2 hours" in body["time_to_respond_estimate"]
        # Demo dimensions total is (78+85+95+65+88+72)/6 = 80.5 → 80
        assert body["overall_score"] == 80

    def test_demo_mode_when_cte_count_zero(self, client, monkeypatch):
        monkeypatch.setattr(rr, "_query_scoring_data", lambda tid: {"cte_count": 0})

        r = client.get("/api/v1/recall/empty-tenant/report")
        assert r.status_code == 200
        body = r.json()
        assert body["demo_mode"] is True
        assert body["demo_disclaimer"] is not None
        # Overall score is demo dimensions average
        assert body["overall_grade"] in {"B", "C"}


# ---------------------------------------------------------------------------
# GET /{tenant_id}/report — real mode
# ---------------------------------------------------------------------------


class TestGenerateReportRealMode:
    def _mock_scoring(self, monkeypatch, **overrides):
        """Install a fake _query_scoring_data returning the overrides."""
        data = {
            "cte_count": 100,
            "tlc_count": 10,
            "cte_types": 5,
            "has_export": True,
            "supplier_count": 20,
            "chain_length": 100,
            "chain_gap_count": 0,
        }
        data.update(overrides)
        monkeypatch.setattr(rr, "_query_scoring_data", lambda tid: data)

    def test_real_mode_high_scores(self, client, monkeypatch):
        """High suppliers (>=10), clean chain, has export → near-perfect."""
        self._mock_scoring(
            monkeypatch,
            supplier_count=20,
            has_export=True,
            chain_length=100,
            chain_gap_count=0,
            cte_types=7,
            cte_count=500,
        )

        r = client.get("/api/v1/recall/strong/report")
        body = r.json()
        assert body["demo_mode"] is False
        assert body["demo_disclaimer"] is None
        # time_to_respond_estimate is computed, not hardcoded
        assert "hour(s) estimated" in body["time_to_respond_estimate"]

        dims = {d["id"]: d for d in body["dimensions"]}
        # Trace speed: has_export → 90
        assert dims["trace_speed"]["score"] == 90
        assert dims["trace_speed"]["recommendations"] == ["Maintain current export practices"]
        # Chain integrity: gaps=0 → 100
        assert dims["chain_integrity"]["score"] == 100
        assert "No gaps in event sequence" in dims["chain_integrity"]["findings"]
        # Supplier coverage: supplier_count >= 10 → "Supply chain coverage is strong"
        assert dims["supplier_coverage"]["recommendations"] == ["Supply chain coverage is strong"]
        # Data completeness: supplier_count >= 5 → "Continue current data collection practices"
        assert dims["data_completeness"]["recommendations"] == ["Continue current data collection practices"]
        # Export readiness: has_export → 90
        assert dims["export_readiness"]["score"] == 90
        assert dims["export_readiness"]["recommendations"] == ["Test with additional retailer portals"]
        assert "functional" in dims["export_readiness"]["findings"][0]
        # Trace depth score = min(100, 5/7*100) = 71 → team readiness = 500//10 = 50
        assert dims["team_readiness"]["score"] == 50

    def test_real_mode_low_suppliers_no_export_no_chain(self, client, monkeypatch):
        """Covers supplier_count<5, chain_length=0, has_export=False."""
        self._mock_scoring(
            monkeypatch,
            supplier_count=3,
            has_export=False,
            chain_length=0,
            chain_gap_count=0,
            cte_count=5,
            cte_types=2,
        )

        r = client.get("/api/v1/recall/weak/report")
        body = r.json()
        assert body["demo_mode"] is False

        dims = {d["id"]: d for d in body["dimensions"]}
        # Trace speed: no export → 65
        assert dims["trace_speed"]["score"] == 65
        # Trace speed findings should note export not enabled
        assert any("not yet enabled" in f for f in dims["trace_speed"]["findings"])
        # Trace speed recommendations include enabling FDA export
        assert any("FDA export" in r for r in dims["trace_speed"]["recommendations"])
        # Chain integrity: chain_length=0 → 50
        assert dims["chain_integrity"]["score"] == 50
        # Chain integrity findings reflect empty chain
        assert any("No hash chain entries" in f for f in dims["chain_integrity"]["findings"])
        # Data completeness: supplier_count=3 < 5 → onboarding recommendations
        assert any("Onboard additional suppliers" in r for r in dims["data_completeness"]["recommendations"])
        # Supplier coverage: supplier_count=3 < 10 → expand recommendations
        assert any("Expand supplier network" in r for r in dims["supplier_coverage"]["recommendations"])
        # Export readiness: no export → 50
        assert dims["export_readiness"]["score"] == 50
        assert any("Enable FDA export" in r for r in dims["export_readiness"]["recommendations"])

    def test_real_mode_medium_suppliers_with_chain_gaps(self, client, monkeypatch):
        """Covers 5 <= supplier_count < 10 and chain_gap_count > 0 branches."""
        self._mock_scoring(
            monkeypatch,
            supplier_count=7,
            has_export=True,
            chain_length=20,
            chain_gap_count=2,
            cte_count=50,
            cte_types=3,
        )

        r = client.get("/api/v1/recall/midsize/report")
        body = r.json()
        assert body["demo_mode"] is False

        dims = {d["id"]: d for d in body["dimensions"]}
        # Chain integrity: chain_length>0, 2 gaps → 100 - 25*2 = 50
        assert dims["chain_integrity"]["score"] == 50
        # Chain integrity findings list the gaps
        assert any("Sequence gaps detected: 2" in f for f in dims["chain_integrity"]["findings"])
        # Chain integrity recommendations include investigate
        assert any("Investigate 2 sequence gap" in r for r in dims["chain_integrity"]["recommendations"])
        # Data completeness: supplier=7 >= 5 → "Continue current data collection practices"
        assert dims["data_completeness"]["recommendations"] == ["Continue current data collection practices"]
        # Supplier coverage: 5 <= supplier_count < 10 → expand recommendations
        assert any("Expand supplier network" in r for r in dims["supplier_coverage"]["recommendations"])

    def test_real_mode_chain_gap_saturates_to_zero(self, client, monkeypatch):
        """Enough gaps drive chain_integrity_score to 0 (max(0, 100-25*N))."""
        self._mock_scoring(
            monkeypatch,
            supplier_count=15,
            has_export=True,
            chain_length=10,
            chain_gap_count=10,  # 100 - 250 → clamped to 0
            cte_count=100,
            cte_types=5,
        )

        r = client.get("/api/v1/recall/disaster/report")
        body = r.json()

        dims = {d["id"]: d for d in body["dimensions"]}
        assert dims["chain_integrity"]["score"] == 0
        assert dims["chain_integrity"]["grade"] == "F"
        assert dims["chain_integrity"]["status"] == "critical"

    def test_real_mode_zero_suppliers(self, client, monkeypatch):
        """supplier_count=0 → data_completeness=0 and supply_chain=0."""
        self._mock_scoring(
            monkeypatch,
            supplier_count=0,
            has_export=False,
            chain_length=0,
            cte_count=0,  # Would trigger demo — override
        )
        # Force not-demo by pretending cte_count>0 via the scoring dict
        monkeypatch.setattr(rr, "_query_scoring_data", lambda tid: {
            "cte_count": 1,  # non-zero to stay in real mode
            "tlc_count": 0,
            "cte_types": 0,
            "has_export": False,
            "supplier_count": 0,
            "chain_length": 0,
            "chain_gap_count": 0,
        })

        r = client.get("/api/v1/recall/lonely/report")
        body = r.json()
        dims = {d["id"]: d for d in body["dimensions"]}
        # Zero suppliers → zero scores on both suppler-linked dims
        assert dims["data_completeness"]["score"] == 0
        assert dims["supplier_coverage"]["score"] == 0
        # Zero cte_count (well, 1) → team_readiness = 1//10 = 0
        assert dims["team_readiness"]["score"] == 0


# ---------------------------------------------------------------------------
# Executive summary and action items always populated
# ---------------------------------------------------------------------------


class TestReportShape:
    def test_summary_and_citations_present(self, client, monkeypatch):
        monkeypatch.setattr(rr, "_query_scoring_data", lambda tid: None)
        r = client.get("/api/v1/recall/abc/report")
        body = r.json()

        # Executive summary mentions tenant id + score
        assert "abc" in body["executive_summary"]
        assert "21 CFR 1.1455" in body["executive_summary"] or \
               "21 CFR 1.1455" in " ".join(body["regulatory_citations"])
        # Regulatory citations fully populated
        assert len(body["regulatory_citations"]) == 4
        # Action items populated
        assert len(body["action_items"]) >= 5
        # All action items have required fields
        for item in body["action_items"]:
            assert item["priority"] in {"HIGH", "MEDIUM", "LOW"}
            assert item["action"]
            assert item["impact"]
            assert item["effort"]


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_route_registered(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/recall/{tenant_id}/report" in paths
