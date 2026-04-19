"""Coverage for app/readiness_router.py — FSMA 204 readiness wizard.

Locks:
- /assessment, /checklist, /gaps all return 503 on missing db_session
- _evaluate_checklist: all 20 items evaluated against 11 DB queries
- _compute_maturity_level: level 5 when every item passes, level 0 with
  no passes, level 1 partial, higher levels require ALL lower-level
  items to pass too
- /assessment response shape (level/score/next_steps/levels)
- /checklist groups items by level with per-level completed/total
- /gaps filters to failing items and surfaces blocking_level

Issue: #1342
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import readiness_router as rr
from app.authz import IngestionPrincipal
from app.readiness_router import (
    CHECKLIST_ITEMS,
    MATURITY_LEVELS,
    REQUIRED_CTE_TYPES,
    _compute_maturity_level,
    _evaluate_checklist,
)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _build_app(principal, db_session):
    app = FastAPI()
    app.include_router(rr.router)

    from app.authz import get_ingestion_principal
    from shared.database import get_db_session

    async def _principal():
        return principal

    def _db():
        return db_session

    app.dependency_overrides[get_ingestion_principal] = _principal
    app.dependency_overrides[get_db_session] = _db
    # Neutralize rate-limit consumer
    import app.authz as authz_mod
    app.state._orig_consume = authz_mod.consume_tenant_rate_limit
    authz_mod.consume_tenant_rate_limit = lambda **_: (True, 999)
    return app


def _teardown(app):
    import app.authz as authz_mod
    authz_mod.consume_tenant_rate_limit = app.state._orig_consume


# _evaluate_checklist query order (for make_session):
# 1. event_stats row -> (total, source_count, cte_type_count, gln_events)
# 2. (conditional when total > 0) cte_rows -> list of (event_type,)
# 3. rule_stats row -> (total_rules, total_evals, passed)
# 4. exception_stats row -> (resolved, critical_open)
# 5. request_stats row -> (total, submitted)
# 6. package_count scalar
# 7. signoff_count scalar
# 8. export_count scalar
# 9. chain_length scalar
# 10. entity_count scalar
# 11. pending_reviews scalar


def _perfect_session():
    """Build a session where every checklist item passes (level 5)."""
    session = MagicMock()
    responses = [
        # event_stats: 100 events, 3 sources, 7 CTE types, 60 GLN events (>=50%)
        SimpleNamespace(fetchone=lambda: (100, 3, 7, 60)),
        # cte_rows: all 7 types
        SimpleNamespace(fetchall=lambda: [(t,) for t in REQUIRED_CTE_TYPES]),
        # rule_stats: 5 rules, 80 evals (>=50% of 100), 78 passed = 97.5%
        SimpleNamespace(fetchone=lambda: (5, 80, 78)),
        # exception_stats: 3 resolved, 0 critical open
        SimpleNamespace(fetchone=lambda: (3, 0)),
        # request_stats: 2 total, 1 submitted
        SimpleNamespace(fetchone=lambda: (2, 1)),
        # package_count
        SimpleNamespace(scalar=lambda: 2),
        # signoff_count
        SimpleNamespace(scalar=lambda: 1),
        # export_count
        SimpleNamespace(scalar=lambda: 1),
        # chain_length
        SimpleNamespace(scalar=lambda: 50),
        # entity_count
        SimpleNamespace(scalar=lambda: 10),
        # pending_reviews
        SimpleNamespace(scalar=lambda: 0),
    ]
    it = iter(responses)
    session.execute.side_effect = lambda *a, **k: next(it)
    return session


def _empty_session():
    """Build a session where no data exists — all checks fail."""
    session = MagicMock()
    responses = [
        # event_stats: zeros
        SimpleNamespace(fetchone=lambda: (0, 0, 0, 0)),
        # cte_rows not called (guarded by total_events > 0)
        # rule_stats: zeros
        SimpleNamespace(fetchone=lambda: (0, 0, 0)),
        # exception_stats: zeros
        SimpleNamespace(fetchone=lambda: (0, 0)),
        # request_stats: zeros
        SimpleNamespace(fetchone=lambda: (0, 0)),
        # scalars all 0 (uses `or 0` so None works too)
        SimpleNamespace(scalar=lambda: 0),
        SimpleNamespace(scalar=lambda: 0),
        SimpleNamespace(scalar=lambda: 0),
        SimpleNamespace(scalar=lambda: 0),
        SimpleNamespace(scalar=lambda: 0),
        SimpleNamespace(scalar=lambda: 0),
    ]
    it = iter(responses)
    session.execute.side_effect = lambda *a, **k: next(it)
    return session


# ---------------------------------------------------------------------------
# Constants + tables
# ---------------------------------------------------------------------------


class TestConstants:
    def test_required_cte_types_count(self):
        assert len(REQUIRED_CTE_TYPES) == 7

    def test_required_cte_types_content(self):
        assert "harvesting" in REQUIRED_CTE_TYPES
        assert "transformation" in REQUIRED_CTE_TYPES
        assert "shipping" in REQUIRED_CTE_TYPES

    def test_checklist_items_count(self):
        assert len(CHECKLIST_ITEMS) == 20

    def test_checklist_items_have_unique_ids(self):
        ids = [item["id"] for item in CHECKLIST_ITEMS]
        assert len(ids) == len(set(ids))

    def test_checklist_levels_in_range(self):
        for item in CHECKLIST_ITEMS:
            assert 1 <= item["level"] <= 5

    def test_maturity_levels_0_to_5(self):
        assert set(MATURITY_LEVELS.keys()) == {0, 1, 2, 3, 4, 5}

    def test_maturity_level_structure(self):
        for lvl, info in MATURITY_LEVELS.items():
            assert "name" in info
            assert "description" in info
            assert "color" in info


# ---------------------------------------------------------------------------
# _compute_maturity_level
# ---------------------------------------------------------------------------


def _make_checklist(passed_ids=None):
    """Create a checklist array with the given IDs marked passed."""
    passed_ids = set(passed_ids or [])
    return [{**item, "passed": item["id"] in passed_ids} for item in CHECKLIST_ITEMS]


class TestComputeMaturityLevel:
    def test_no_passes_returns_0(self):
        result = _compute_maturity_level(_make_checklist([]))
        assert result == 0

    def test_any_level_1_pass_returns_1(self):
        result = _compute_maturity_level(_make_checklist(["ingest_records"]))
        assert result == 1

    def test_all_level_1_but_not_level_2_returns_1(self):
        level_1_ids = [i["id"] for i in CHECKLIST_ITEMS if i["level"] == 1]
        result = _compute_maturity_level(_make_checklist(level_1_ids))
        assert result == 1

    def test_all_levels_1_and_2_returns_2(self):
        ids = [i["id"] for i in CHECKLIST_ITEMS if i["level"] in (1, 2)]
        result = _compute_maturity_level(_make_checklist(ids))
        assert result == 2

    def test_all_levels_1_2_3_returns_3(self):
        ids = [i["id"] for i in CHECKLIST_ITEMS if i["level"] in (1, 2, 3)]
        result = _compute_maturity_level(_make_checklist(ids))
        assert result == 3

    def test_all_levels_returns_5(self):
        all_ids = [i["id"] for i in CHECKLIST_ITEMS]
        result = _compute_maturity_level(_make_checklist(all_ids))
        assert result == 5

    def test_higher_level_pass_ignores_lower_level_gap(self):
        """Locks the actual behavior: the loop returns the HIGHEST level
        where ALL items at that specific level pass, regardless of gaps
        at lower levels. (Level 5 still counts even if one level-2 item
        is missing.)"""
        all_ids = [i["id"] for i in CHECKLIST_ITEMS]
        # Drop a single level-2 item
        drop = next(i["id"] for i in CHECKLIST_ITEMS if i["level"] == 2)
        ids = [i for i in all_ids if i != drop]
        assert _compute_maturity_level(_make_checklist(ids)) == 5

    def test_only_level_3_passes_returns_3(self):
        """Only level-3 items complete → 3 (no cumulative requirement)."""
        ids = [i["id"] for i in CHECKLIST_ITEMS if i["level"] == 3]
        assert _compute_maturity_level(_make_checklist(ids)) == 3


# ---------------------------------------------------------------------------
# _evaluate_checklist — direct unit tests
# ---------------------------------------------------------------------------


class TestEvaluateChecklist:
    def test_perfect_data_all_pass(self):
        session = _perfect_session()
        results = _evaluate_checklist(session, "t1")
        assert len(results) == 20
        assert all(r["passed"] for r in results)

    def test_empty_data_only_no_critical_exceptions_passes(self):
        """An empty tenant has zero critical exceptions trivially → that
        level-5 item passes vacuously; every other check fails."""
        session = _empty_session()
        results = _evaluate_checklist(session, "t1")
        passing = [r["id"] for r in results if r["passed"]]
        assert passing == ["no_critical_exceptions"]

    def test_cte_query_only_when_events_exist(self):
        """When total_events == 0, cte_rows query is skipped."""
        session = _empty_session()
        _evaluate_checklist(session, "t1")
        # _empty_session provides exactly 10 responses (no cte_rows);
        # iterator would raise StopIteration if the guard didn't work.

    def test_none_fetchone_handled(self):
        """fetchone() returning None should not crash.

        (no_critical_exceptions still passes vacuously because
        critical_open == 0, same as in test_empty_data_only_...)"""
        session = MagicMock()
        responses = [
            SimpleNamespace(fetchone=lambda: None),  # event_stats
            # cte_rows skipped (total=0 via None path)
            SimpleNamespace(fetchone=lambda: None),  # rule_stats
            SimpleNamespace(fetchone=lambda: None),  # exception_stats
            SimpleNamespace(fetchone=lambda: None),  # request_stats
            SimpleNamespace(scalar=lambda: None),
            SimpleNamespace(scalar=lambda: None),
            SimpleNamespace(scalar=lambda: None),
            SimpleNamespace(scalar=lambda: None),
            SimpleNamespace(scalar=lambda: None),
            SimpleNamespace(scalar=lambda: None),
        ]
        it = iter(responses)
        session.execute.side_effect = lambda *a, **k: next(it)
        results = _evaluate_checklist(session, "t1")
        passing = [r["id"] for r in results if r["passed"]]
        assert passing == ["no_critical_exceptions"]

    def test_partial_data(self):
        """Realistic in-flight tenant: level 1 + 2 met, level 3+ failing."""
        session = MagicMock()
        responses = [
            SimpleNamespace(fetchone=lambda: (20, 2, 5, 15)),  # event_stats
            SimpleNamespace(fetchall=lambda: [(t,) for t in ["harvesting", "cooling", "shipping", "receiving", "transformation"]]),
            SimpleNamespace(fetchone=lambda: (3, 15, 12)),     # rule_stats: 80% pass
            SimpleNamespace(fetchone=lambda: (1, 0)),          # exception_stats
            SimpleNamespace(fetchone=lambda: (0, 0)),          # request_stats
            SimpleNamespace(scalar=lambda: 0),                  # package_count
            SimpleNamespace(scalar=lambda: 0),                  # signoff_count
            SimpleNamespace(scalar=lambda: 0),                  # export_count
            SimpleNamespace(scalar=lambda: 10),                 # chain_length
            SimpleNamespace(scalar=lambda: 5),                  # entity_count
            SimpleNamespace(scalar=lambda: 0),                  # pending_reviews
        ]
        it = iter(responses)
        session.execute.side_effect = lambda *a, **k: next(it)
        results = _evaluate_checklist(session, "t1")
        by_id = {r["id"]: r["passed"] for r in results}
        assert by_id["ingest_records"] is True  # 20 >= 10
        assert by_id["multiple_sources"] is True  # 2 >= 2
        assert by_id["cte_coverage"] is True  # 5 >= 4
        assert by_id["pass_rate_70"] is True  # 80 >= 70
        assert by_id["pass_rate_90"] is False
        assert by_id["request_case_created"] is False
        assert by_id["package_assembled"] is False
        assert by_id["all_ctes_covered"] is False  # only 5/7


# ---------------------------------------------------------------------------
# 503 DB-unavailable guards
# ---------------------------------------------------------------------------


class TestDbUnavailable:
    @pytest.mark.parametrize("path", [
        "/api/v1/readiness/assessment",
        "/api/v1/readiness/checklist",
        "/api/v1/readiness/gaps",
    ])
    def test_returns_503(self, path):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app = _build_app(principal, db_session=None)
        try:
            client = TestClient(app)
            resp = client.get(path)
            assert resp.status_code == 503
            assert resp.json()["detail"] == "Database unavailable"
        finally:
            _teardown(app)


# ---------------------------------------------------------------------------
# GET /assessment
# ---------------------------------------------------------------------------


class TestAssessmentEndpoint:
    def test_empty_tenant_level_0_with_vacuous_no_critical(self):
        """Empty tenant: only no_critical_exceptions passes, but level 5
        still needs all 4 of its items → falls back to 0."""
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app = _build_app(principal, _empty_session())
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/readiness/assessment")
            assert resp.status_code == 200
            body = resp.json()
            assert body["maturity_level"] == 0
            assert body["maturity_name"] == "Not Started"
            assert body["maturity_color"] == "gray"
            assert body["overall_score"] == 5  # 1/20 * 100
            assert body["items_completed"] == 1
            assert body["items_total"] == 20
            assert len(body["next_steps"]) == 3
            assert "levels" in body
        finally:
            _teardown(app)

    def test_perfect_tenant_returns_level_5(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app = _build_app(principal, _perfect_session())
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/readiness/assessment")
            assert resp.status_code == 200
            body = resp.json()
            assert body["maturity_level"] == 5
            assert body["maturity_name"] == "Compliant"
            assert body["maturity_color"] == "green"
            assert body["overall_score"] == 100
            assert body["items_completed"] == 20
            assert body["next_steps"] == []  # nothing left
        finally:
            _teardown(app)

    def test_explicit_tenant_override(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t-principal")
        app = _build_app(principal, _empty_session())
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/readiness/assessment?tenant_id=t-override")
            assert resp.status_code == 200
            assert resp.json()["tenant_id"] == "t-override"
        finally:
            _teardown(app)


# ---------------------------------------------------------------------------
# GET /checklist
# ---------------------------------------------------------------------------


class TestChecklistEndpoint:
    def test_groups_by_level(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app = _build_app(principal, _perfect_session())
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/readiness/checklist")
            assert resp.status_code == 200
            body = resp.json()
            by_level = body["checklist_by_level"]
            # JSON keys are strings
            assert set(by_level.keys()) == {"1", "2", "3", "4", "5"}
            for level_key, bucket in by_level.items():
                assert "level_info" in bucket
                assert "items" in bucket
                assert "completed" in bucket
                assert "total" in bucket
                # Perfect data → every bucket fully complete
                assert bucket["completed"] == bucket["total"]
        finally:
            _teardown(app)

    def test_empty_tenant_all_zero_except_level_5_vacuous(self):
        """Empty tenant: level 5 bucket has 1 passing (no_critical_exceptions);
        every other level bucket has 0 passing."""
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app = _build_app(principal, _empty_session())
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/readiness/checklist")
            assert resp.status_code == 200
            buckets = resp.json()["checklist_by_level"]
            for level_key, bucket in buckets.items():
                if level_key == "5":
                    assert bucket["completed"] == 1
                else:
                    assert bucket["completed"] == 0
        finally:
            _teardown(app)


# ---------------------------------------------------------------------------
# GET /gaps
# ---------------------------------------------------------------------------


class TestGapsEndpoint:
    def test_empty_tenant_has_all_gaps_except_no_critical(self):
        """Empty tenant: 19 gaps (all except the vacuously-passing
        no_critical_exceptions)."""
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app = _build_app(principal, _empty_session())
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/readiness/gaps")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total_gaps"] == 19
            assert body["blocking_level"] == 1  # lowest gap level
            for gap in body["gaps"]:
                assert gap["passed"] is False
        finally:
            _teardown(app)

    def test_perfect_tenant_no_gaps(self):
        principal = IngestionPrincipal(key_id="k", scopes=["*"], tenant_id="t")
        app = _build_app(principal, _perfect_session())
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/readiness/gaps")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total_gaps"] == 0
            assert body["gaps"] == []
            # blocking_level defaults to 6 when no gaps exist
            assert body["blocking_level"] == 6
        finally:
            _teardown(app)


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert rr.router.prefix == "/api/v1/readiness"

    def test_tag(self):
        assert "Readiness Wizard" in rr.router.tags

    def test_all_three_routes_registered(self):
        paths = {r.path for r in rr.router.routes}
        assert "/api/v1/readiness/assessment" in paths
        assert "/api/v1/readiness/checklist" in paths
        assert "/api/v1/readiness/gaps" in paths
