"""Coverage for app/compliance_score.py — real-time FSMA 204 readiness score.

Locks:
- _compute_grade: all boundaries (A/B/C/D/F)
- _compute_scores: all 6 sub-scores across every branch
  * chain_integrity: chain_length=0, verified=True (with/without hash),
    verified=False (with/without error detail), verified=None w/ gaps,
    verified=None w/o gaps
  * kde_completeness: total_kdes=0, ratios w/ and w/o missing-time penalty
  * cte_completeness: 0 distinct, fallback-to-7, active_cte_types override,
    missing list, all tracked
  * product_coverage: event_count=0, ftl=0, events+ftl
  * obligation_coverage: event_count=0, total_rules=0, open_alerts>0, zero alerts
  * export_readiness: event_count=0, verified-chain bonus, chain w/o verify,
    no chain, kde_ratio<0.8, no KDEs, ≥3 CTEs, 1-2 CTEs, 0 CTEs
- _query_scoring_data: full happy path + active_cte_types fallback +
  obligations/obl_coverage/open_alerts/ftl/verify_chain per-branch failures
- _build_next_actions: event_count=0 early return, every gap branch,
  cap-at-5 behavior
- GET /score/{tid}: DB unavailable → F, query error → F, happy path,
  inner exception → 500
- GET /pending-reviews/{tid}: DB unavailable, happy path, identity-table
  missing fallback, outer query exception
- validate_tenant_id rejection (422)

Issue: #1342
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

from app import compliance_score as cs
from app.compliance_score import (
    ComplianceScoreResponse,
    NextAction,
    ScoreBreakdown,
    _build_next_actions,
    _compute_grade,
    _compute_scores,
    _query_scoring_data,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _app() -> FastAPI:
    """Minimal app with auth bypassed."""
    app = FastAPI()
    app.include_router(router)
    from app.webhook_compat import _verify_api_key
    bypass = lambda: None
    app.dependency_overrides[_verify_api_key] = bypass
    app.dependency_overrides[cs._verify_api_key] = bypass
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _row(*values):
    """Build an object supporting both index and len (SQLAlchemy Row mimic)."""
    return tuple(values)


class _FakeResult:
    """Mimics the result object returned by SQLAlchemy's execute()."""

    def __init__(self, *, row=None, scalar_value=None):
        self._row = row
        self._scalar = scalar_value

    def fetchone(self):
        return self._row

    def scalar(self):
        return self._scalar


class _RouteSession:
    """Session that dispatches execute() by SQL substring.

    Construct with a mapping of substring → row (or RuntimeError to raise).
    Also accepts ``raise_on`` for substring-matched exceptions.
    """

    def __init__(self, route=None, raise_on=None, scalar_route=None):
        self.route = route or {}
        self.raise_on = raise_on or {}
        self.scalar_route = scalar_route or {}
        self.closed = False
        self.rolled_back = 0
        self.executed: list[str] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append(sql)
        for pat, exc in self.raise_on.items():
            if pat in sql:
                raise exc
        # scalar routes take precedence for .scalar() consumers
        for pat, value in self.scalar_route.items():
            if pat in sql:
                return _FakeResult(scalar_value=value)
        for pat, row in self.route.items():
            if pat in sql:
                return _FakeResult(row=row)
        # Default: empty row
        return _FakeResult(row=None)

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# _compute_grade
# ---------------------------------------------------------------------------


class TestComputeGrade:
    @pytest.mark.parametrize("score,expected", [
        (100, "A"), (95, "A"), (90, "A"),
        (89, "B"), (85, "B"), (80, "B"),
        (79, "C"), (75, "C"), (70, "C"),
        (69, "D"), (65, "D"), (60, "D"),
        (59, "F"), (10, "F"), (0, "F"),
    ])
    def test_boundaries(self, score, expected):
        assert _compute_grade(score) == expected


# ---------------------------------------------------------------------------
# _compute_scores
# ---------------------------------------------------------------------------


def _base_data(**overrides) -> dict:
    base = {
        "event_count": 10,
        "distinct_cte_types": 5,
        "cte_types_present": ["harvesting", "cooling", "shipping", "receiving", "transformation"],
        "missing_cte_types": ["initial_packing", "first_land_based_receiving"],
        "active_cte_types": None,
        "total_kdes": 50,
        "filled_kdes": 50,
        "chain_length": 10,
        "last_chain_hash": "a" * 64,
        "chain_gaps": 0,
        "events_missing_time": 0,
        "obligation_count": 3,
        "applicable_obligation_rules": 8,
        "total_obligation_rules": 10,
        "open_obligation_alerts": 0,
        "ftl_category_count": 20,
        "chain_verified": True,
        "chain_verification_errors": [],
    }
    base.update(overrides)
    return base


class TestComputeScoresChainIntegrity:
    def test_no_events(self):
        scores = _compute_scores(_base_data(chain_length=0, event_count=0))
        assert scores["chain_integrity"][0] == 0
        assert "No events" in scores["chain_integrity"][1]

    def test_verified_with_hash(self):
        scores = _compute_scores(_base_data(chain_verified=True, last_chain_hash="b" * 64))
        assert scores["chain_integrity"][0] == 100
        assert "cryptographically verified" in scores["chain_integrity"][1]

    def test_verified_without_hash(self):
        scores = _compute_scores(_base_data(chain_verified=True, last_chain_hash=None))
        assert scores["chain_integrity"][0] == 100
        assert "All entries verified" in scores["chain_integrity"][1]

    def test_verification_failed_with_errors(self):
        scores = _compute_scores(_base_data(
            chain_verified=False,
            chain_verification_errors=["block 3 hash mismatch", "block 7 bad link"],
        ))
        # 2 errors × 25 = 50 penalty → score 50
        assert scores["chain_integrity"][0] == 50
        assert "TAMPER DETECTED" in scores["chain_integrity"][1]
        assert "block 3 hash mismatch" in scores["chain_integrity"][1]

    def test_verification_failed_no_error_detail(self):
        scores = _compute_scores(_base_data(
            chain_verified=False,
            chain_verification_errors=[],
        ))
        # 0 errors → 0 penalty, but "TAMPER DETECTED" still appears
        assert scores["chain_integrity"][0] == 100
        assert "TAMPER DETECTED" in scores["chain_integrity"][1]

    def test_verification_failed_penalty_capped(self):
        # 20 errors × 25 = 500, capped at 100
        scores = _compute_scores(_base_data(
            chain_verified=False,
            chain_verification_errors=["e"] * 20,
        ))
        assert scores["chain_integrity"][0] == 0

    def test_unknown_verify_with_gaps(self):
        scores = _compute_scores(_base_data(
            chain_verified=None, chain_gaps=3, chain_length=10,
        ))
        # 3 × 10 = 30 penalty → 70
        assert scores["chain_integrity"][0] == 70
        assert "3 gap" in scores["chain_integrity"][1]

    def test_unknown_verify_capped_gap_penalty(self):
        scores = _compute_scores(_base_data(
            chain_verified=None, chain_gaps=50, chain_length=100,
        ))
        # penalty capped at 50 → score 50
        assert scores["chain_integrity"][0] == 50

    def test_unknown_verify_no_gaps(self):
        scores = _compute_scores(_base_data(
            chain_verified=None, chain_gaps=0, chain_length=10,
        ))
        # pending crypto verification → 90
        assert scores["chain_integrity"][0] == 90
        assert "pending" in scores["chain_integrity"][1]


class TestComputeScoresKdeCompleteness:
    def test_no_kdes(self):
        scores = _compute_scores(_base_data(total_kdes=0, filled_kdes=0))
        assert scores["kde_completeness"][0] == 0

    def test_all_filled_no_time_issue(self):
        scores = _compute_scores(_base_data(total_kdes=10, filled_kdes=10, events_missing_time=0))
        assert scores["kde_completeness"][0] == 100
        assert "All 10 KDE fields populated" in scores["kde_completeness"][1]

    def test_partial_missing(self):
        scores = _compute_scores(_base_data(total_kdes=10, filled_kdes=6, events_missing_time=0))
        # 60% → 60
        assert scores["kde_completeness"][0] == 60
        assert "6/10" in scores["kde_completeness"][1]
        assert "4 blank" in scores["kde_completeness"][1]

    def test_all_filled_with_time_penalty(self):
        scores = _compute_scores(_base_data(
            total_kdes=10, filled_kdes=10, events_missing_time=5, event_count=10,
        ))
        # kde_score=100, time_penalty=min(10, int(5/10*10))=5 → 95
        assert scores["kde_completeness"][0] == 95
        assert "5 events lack precise time" in scores["kde_completeness"][1]

    def test_partial_with_time_penalty(self):
        scores = _compute_scores(_base_data(
            total_kdes=10, filled_kdes=8, events_missing_time=10, event_count=10,
        ))
        # kde_score=80, time_penalty=min(10, int(10/10*10))=10 → 70
        assert scores["kde_completeness"][0] == 70


class TestComputeScoresCteCompleteness:
    def test_no_distinct_types(self):
        scores = _compute_scores(_base_data(distinct_cte_types=0))
        assert scores["cte_completeness"][0] == 0
        assert "No CTEs tracked" in scores["cte_completeness"][1]

    def test_partial_fallback_seven(self):
        scores = _compute_scores(_base_data(
            distinct_cte_types=5,
            missing_cte_types=["initial_packing", "first_land_based_receiving"],
            active_cte_types=None,
        ))
        # 5/7 = 71
        assert scores["cte_completeness"][0] == 71
        assert "5/7" in scores["cte_completeness"][1]
        assert "first_land_based_receiving" in scores["cte_completeness"][1]

    def test_all_tracked_with_default_seven(self):
        scores = _compute_scores(_base_data(
            distinct_cte_types=7,
            missing_cte_types=[],
            active_cte_types=None,
        ))
        assert scores["cte_completeness"][0] == 100
        assert "All 7 CTE types" in scores["cte_completeness"][1]

    def test_active_cte_types_override(self):
        """Tenant with only 3 active CTE types scores 100% at 3/3."""
        scores = _compute_scores(_base_data(
            distinct_cte_types=3,
            missing_cte_types=[],
            active_cte_types=["receiving", "shipping", "transformation"],
        ))
        assert scores["cte_completeness"][0] == 100

    def test_active_cte_types_partial(self):
        scores = _compute_scores(_base_data(
            distinct_cte_types=2,
            missing_cte_types=["transformation"],
            active_cte_types=["receiving", "shipping", "transformation"],
        ))
        # 2/3 = 66
        assert scores["cte_completeness"][0] == 66
        assert "2/3" in scores["cte_completeness"][1]


class TestComputeScoresProductCoverage:
    def test_no_events(self):
        scores = _compute_scores(_base_data(event_count=0, chain_length=0))
        assert scores["product_coverage"][0] == 0

    def test_no_ftl(self):
        scores = _compute_scores(_base_data(event_count=5, ftl_category_count=0))
        assert scores["product_coverage"][0] == 50
        assert "FTL category mapping needed" in scores["product_coverage"][1]

    def test_with_ftl_bonus_capped(self):
        scores = _compute_scores(_base_data(event_count=100, ftl_category_count=20))
        # 60 + min(40, 100*5)=40 → 100
        assert scores["product_coverage"][0] == 100

    def test_with_ftl_small_event_bonus(self):
        scores = _compute_scores(_base_data(event_count=3, ftl_category_count=20))
        # 60 + 3*5=15 → 75
        assert scores["product_coverage"][0] == 75


class TestComputeScoresObligationCoverage:
    def test_no_events(self):
        scores = _compute_scores(_base_data(event_count=0, chain_length=0))
        assert scores["obligation_coverage"][0] == 0
        assert "not yet assessed" in scores["obligation_coverage"][1]

    def test_no_rules(self):
        scores = _compute_scores(_base_data(total_obligation_rules=0, applicable_obligation_rules=0))
        assert scores["obligation_coverage"][0] == 50
        assert "seed regulatory data" in scores["obligation_coverage"][1]

    def test_full_coverage_no_alerts(self):
        scores = _compute_scores(_base_data(
            total_obligation_rules=10, applicable_obligation_rules=10,
            open_obligation_alerts=0,
        ))
        # 10/10*80 = 80 + 20 bonus = 100
        assert scores["obligation_coverage"][0] == 100

    def test_full_coverage_with_alerts(self):
        scores = _compute_scores(_base_data(
            total_obligation_rules=10, applicable_obligation_rules=10,
            open_obligation_alerts=5,
        ))
        # 10/10*80 = 80 - min(5*3, 30) = 80 - 15 = 65
        assert scores["obligation_coverage"][0] == 65
        assert "5 open compliance alert" in scores["obligation_coverage"][1]

    def test_partial_coverage_alert_cap(self):
        scores = _compute_scores(_base_data(
            total_obligation_rules=10, applicable_obligation_rules=5,
            open_obligation_alerts=20,
        ))
        # 5/10*80 = 40 - min(20*3, 30) = 40 - 30 = 10
        assert scores["obligation_coverage"][0] == 10

    def test_partial_no_alerts_bonus(self):
        scores = _compute_scores(_base_data(
            total_obligation_rules=10, applicable_obligation_rules=5,
            open_obligation_alerts=0,
        ))
        # 5/10*80 = 40 + 20 = 60
        assert scores["obligation_coverage"][0] == 60


class TestComputeScoresExportReadiness:
    def test_no_events(self):
        scores = _compute_scores(_base_data(event_count=0, chain_length=0))
        assert scores["export_readiness"][0] == 0
        assert "no data" in scores["export_readiness"][1]

    def test_fully_ready(self):
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=True,
            total_kdes=10, filled_kdes=10,
            distinct_cte_types=5,
        ))
        # 40 (verified) + 30 (kde) + 30 (≥3 CTEs) = 100
        assert scores["export_readiness"][0] == 100
        assert "FDA export ready" in scores["export_readiness"][1]

    def test_chain_not_verified_but_intact(self):
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=None,  # verification couldn't run
            chain_length=10, chain_gaps=0,
            total_kdes=10, filled_kdes=10,
            distinct_cte_types=5,
        ))
        # 30 + 30 + 30 = 90 — score ≥80 so "FDA export ready" wins
        assert scores["export_readiness"][0] == 90
        assert "FDA export ready" in scores["export_readiness"][1]

    def test_chain_not_verified_surfaces_issue_when_below_80(self):
        """When score <80, the chain-unverified issue surfaces in the detail."""
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=None,
            chain_length=10, chain_gaps=0,
            total_kdes=10, filled_kdes=10,
            distinct_cte_types=2,  # +15, pulls total below 80
        ))
        # 30 + 30 + 15 = 75
        assert scores["export_readiness"][0] == 75
        assert "chain not cryptographically verified" in scores["export_readiness"][1]
        assert "limited CTE coverage" in scores["export_readiness"][1]

    def test_no_chain_integrity(self):
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=None,
            chain_length=0, chain_gaps=0,
            total_kdes=10, filled_kdes=10,
            distinct_cte_types=5,
        ))
        # 0 (chain) + 30 + 30 = 60 → fails "FDA export ready"
        assert scores["export_readiness"][0] == 60
        assert "chain integrity" in scores["export_readiness"][1]

    def test_kde_gap_flagged(self):
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=True,
            total_kdes=10, filled_kdes=5,  # 0.5 ratio
            distinct_cte_types=5,
        ))
        # 40 + int(0.5*30)=15 + 30 = 85
        assert scores["export_readiness"][0] == 85
        # export_score=85 >= 80 so "FDA export ready" wins (edge case)
        # Actually detail = "FDA export ready" when score >= 80 even if KDE gap noted

    def test_kde_gap_sub_80(self):
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=None,
            chain_length=10, chain_gaps=0,
            total_kdes=10, filled_kdes=3,  # 0.3 → 9 pts
            distinct_cte_types=2,  # 15 pts
        ))
        # 30 + 9 + 15 = 54
        assert scores["export_readiness"][0] == 54
        assert "KDE gaps" in scores["export_readiness"][1]
        assert "limited CTE coverage" in scores["export_readiness"][1]

    def test_no_kdes(self):
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=True,
            total_kdes=0, filled_kdes=0,
            distinct_cte_types=5,
        ))
        # 40 + 0 + 30 = 70
        assert scores["export_readiness"][0] == 70
        assert "no KDEs" in scores["export_readiness"][1]

    def test_no_cte_types(self):
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=True,
            total_kdes=10, filled_kdes=10,
            distinct_cte_types=0,
        ))
        # 40 + 30 + 0 = 70
        assert scores["export_readiness"][0] == 70
        assert "no CTE types" in scores["export_readiness"][1]

    def test_limited_cte_coverage(self):
        scores = _compute_scores(_base_data(
            event_count=10,
            chain_verified=True,
            total_kdes=10, filled_kdes=10,
            distinct_cte_types=1,
        ))
        # 40 + 30 + 15 = 85
        assert scores["export_readiness"][0] == 85


# ---------------------------------------------------------------------------
# _build_next_actions
# ---------------------------------------------------------------------------


def _build_scores(**overrides) -> dict:
    base = {
        "chain_integrity": (100, "ok"),
        "kde_completeness": (100, "ok"),
        "cte_completeness": (100, "ok"),
        "product_coverage": (100, "ok"),
        "obligation_coverage": (100, "ok"),
        "export_readiness": (100, "ok"),
    }
    base.update(overrides)
    return base


class TestBuildNextActions:
    def test_no_events_returns_baseline_actions(self):
        data = _base_data(event_count=0)
        scores = _build_scores()
        actions = _build_next_actions(scores, data)
        assert len(actions) == 2
        assert actions[0].priority == "HIGH"
        assert "first traceability event" in actions[0].action
        assert "FTL Checker" in actions[1].action

    def test_chain_tampered_action(self):
        data = _base_data(event_count=5, chain_verified=False)
        scores = _build_scores(chain_integrity=(0, "bad"))
        actions = _build_next_actions(scores, data)
        assert any("tampering detected" in a.action for a in actions)

    def test_chain_integrity_unknown_action(self):
        data = _base_data(event_count=5, chain_verified=None)
        scores = _build_scores(chain_integrity=(70, "gaps"))
        actions = _build_next_actions(scores, data)
        assert any("possible data loss" in a.action for a in actions)

    def test_obligation_open_alerts(self):
        data = _base_data(event_count=5, open_obligation_alerts=3)
        scores = _build_scores(obligation_coverage=(50, "gaps"))
        actions = _build_next_actions(scores, data)
        assert any("Resolve 3 open obligation" in a.action for a in actions)

    def test_obligation_no_alerts_expand_cte(self):
        data = _base_data(event_count=5, open_obligation_alerts=0)
        scores = _build_scores(obligation_coverage=(50, "gaps"))
        actions = _build_next_actions(scores, data)
        assert any("Expand CTE type coverage" in a.action for a in actions)

    def test_kde_gap_action(self):
        data = _base_data(event_count=5)
        scores = _build_scores(kde_completeness=(60, "blanks"))
        actions = _build_next_actions(scores, data)
        assert any("Complete all required KDEs" in a.action for a in actions)

    def test_cte_gap_action(self):
        data = _base_data(
            event_count=5,
            missing_cte_types=["initial_packing", "cooling"],
        )
        scores = _build_scores(cte_completeness=(60, "gaps"))
        actions = _build_next_actions(scores, data)
        # Should pick the first alphabetically: cooling
        cte_actions = [a for a in actions if "cooling CTE" in a.action]
        assert len(cte_actions) == 1
        assert cte_actions[0].priority == "MEDIUM"

    def test_cte_gap_empty_missing_list_no_action(self):
        """cte_score<100 but missing_cte_types empty → no CTE action emitted."""
        data = _base_data(event_count=5, missing_cte_types=[])
        scores = _build_scores(cte_completeness=(60, "gaps"))
        actions = _build_next_actions(scores, data)
        assert not any("CTE tracking" in a.action for a in actions)

    def test_product_coverage_action(self):
        data = _base_data(event_count=5)
        scores = _build_scores(product_coverage=(50, "low"))
        actions = _build_next_actions(scores, data)
        assert any("FTL Checker" in a.action for a in actions)

    def test_export_readiness_action(self):
        data = _base_data(event_count=5)
        scores = _build_scores(export_readiness=(50, "low"))
        actions = _build_next_actions(scores, data)
        assert any("mock recall drill" in a.action for a in actions)

    def test_all_dimensions_low_caps_at_five(self):
        data = _base_data(
            event_count=5,
            chain_verified=False,
            open_obligation_alerts=5,
            missing_cte_types=["cooling"],
        )
        scores = _build_scores(
            chain_integrity=(10, "bad"),
            kde_completeness=(20, "bad"),
            cte_completeness=(30, "bad"),
            product_coverage=(40, "bad"),
            obligation_coverage=(50, "bad"),
            export_readiness=(60, "bad"),
        )
        actions = _build_next_actions(scores, data)
        assert len(actions) == 5  # Cap enforced

    def test_everything_at_100_no_actions(self):
        data = _base_data(event_count=5)
        scores = _build_scores()
        actions = _build_next_actions(scores, data)
        assert actions == []


# ---------------------------------------------------------------------------
# _query_scoring_data
# ---------------------------------------------------------------------------


class TestQueryScoringDataHappyPath:
    def test_full_data(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(
                    10, 5, ["harvesting", "cooling", "shipping", "receiving", "transformation"]
                ),
                "obligation_cte_rules ocr": _row(["harvesting", "cooling", "shipping"]),
                "fsma.cte_kdes": _row(50, 45),
                "fsma.hash_chain\n            WHERE": _row(10, 10, "abc123"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(2,),
                "FROM obligations WHERE tenant_id": _row(3,),
                "checkable_rules AS": _row(8, 10),
                "fsma.compliance_alerts": _row(1,),
                "food_traceability_list": _row(20,),
            },
        )

        # Stub CTEPersistence.verify_chain
        class _FakePersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, errors=[])

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)

        data = _query_scoring_data(session, "t1")

        assert data["event_count"] == 10
        assert data["distinct_cte_types"] == 5
        assert set(data["cte_types_present"]) == {
            "harvesting", "cooling", "shipping", "receiving", "transformation",
        }
        assert set(data["missing_cte_types"]) == {"initial_packing", "first_land_based_receiving"}
        assert data["active_cte_types"] == ["harvesting", "cooling", "shipping"]
        assert data["total_kdes"] == 50
        assert data["filled_kdes"] == 45
        assert data["chain_length"] == 10
        assert data["last_chain_hash"] == "abc123"
        assert data["chain_gaps"] == 0
        assert data["events_missing_time"] == 2
        assert data["obligation_count"] == 3
        assert data["applicable_obligation_rules"] == 8
        assert data["total_obligation_rules"] == 10
        assert data["open_obligation_alerts"] == 1
        assert data["ftl_category_count"] == 20
        assert data["chain_verified"] is True
        assert data["chain_verification_errors"] == []

    def test_zero_events_skips_conditional_queries(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(0, 0, None),
                "obligation_cte_rules ocr": _row(None,),
                "fsma.cte_kdes": _row(0, 0),
                "fsma.hash_chain\n            WHERE": _row(0, None, None),
                "FROM obligations WHERE tenant_id": _row(0,),
                "food_traceability_list": _row(0,),
            },
        )

        class _FakePersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, errors=[])

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)

        data = _query_scoring_data(session, "t1")
        assert data["chain_gaps"] == 0  # skipped when chain_length=0
        assert data["events_missing_time"] == 0  # skipped when event_count=0
        assert data["applicable_obligation_rules"] == 0
        assert data["total_obligation_rules"] == 0
        assert data["open_obligation_alerts"] == 0


class TestQueryScoringDataDegrades:
    def test_active_cte_types_query_fails(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(
                    5, 3, ["harvesting", "cooling", "shipping"]
                ),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "FROM obligations WHERE tenant_id": _row(1,),
                "checkable_rules AS": _row(5, 5),
                "fsma.compliance_alerts": _row(0,),
                "food_traceability_list": _row(10,),
            },
            raise_on={"obligation_cte_rules ocr": ProgrammingError("x", None, Exception())},
        )

        class _FakePersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, errors=[])

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)

        data = _query_scoring_data(session, "t1")
        assert data["active_cte_types"] is None
        assert session.rolled_back >= 1

    def test_active_cte_types_rollback_also_fails(self, monkeypatch):
        """Even if rollback() itself raises, we still get active_cte_types=None."""
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "FROM obligations WHERE tenant_id": _row(1,),
                "checkable_rules AS": _row(5, 5),
                "fsma.compliance_alerts": _row(0,),
                "food_traceability_list": _row(10,),
            },
            raise_on={"obligation_cte_rules ocr": ProgrammingError("x", None, Exception())},
        )
        # Make rollback itself raise
        def _bad_rollback():
            raise RuntimeError("rollback failed")
        session.rollback = _bad_rollback  # type: ignore

        class _FakePersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, errors=[])
        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)

        data = _query_scoring_data(session, "t1")
        assert data["active_cte_types"] is None

    def test_obligation_count_fails(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
                "obligation_cte_rules ocr": _row(None,),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "checkable_rules AS": _row(5, 5),
                "fsma.compliance_alerts": _row(0,),
                "food_traceability_list": _row(10,),
            },
            raise_on={
                "FROM obligations WHERE tenant_id": OperationalError("x", None, Exception()),
            },
        )

        class _FakePersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, errors=[])
        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)

        data = _query_scoring_data(session, "t1")
        assert data["obligation_count"] == 0

    def test_obl_coverage_fails(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
                "obligation_cte_rules ocr": _row(None,),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "FROM obligations WHERE tenant_id": _row(1,),
                "fsma.compliance_alerts": _row(0,),
                "food_traceability_list": _row(10,),
            },
            raise_on={"checkable_rules AS": OperationalError("x", None, Exception())},
        )

        class _FakePersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, errors=[])
        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)

        data = _query_scoring_data(session, "t1")
        assert data["applicable_obligation_rules"] == 0
        assert data["total_obligation_rules"] == 0

    def test_compliance_alerts_fails(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
                "obligation_cte_rules ocr": _row(None,),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "FROM obligations WHERE tenant_id": _row(1,),
                "checkable_rules AS": _row(5, 5),
                "food_traceability_list": _row(10,),
            },
            raise_on={"fsma.compliance_alerts": OperationalError("x", None, Exception())},
        )

        class _FakePersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, errors=[])
        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)

        data = _query_scoring_data(session, "t1")
        assert data["open_obligation_alerts"] == 0

    def test_ftl_fails(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
                "obligation_cte_rules ocr": _row(None,),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "FROM obligations WHERE tenant_id": _row(1,),
                "checkable_rules AS": _row(5, 5),
                "fsma.compliance_alerts": _row(0,),
            },
            raise_on={"food_traceability_list": OperationalError("x", None, Exception())},
        )

        class _FakePersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, errors=[])
        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)

        data = _query_scoring_data(session, "t1")
        assert data["ftl_category_count"] == 0

    def test_verify_chain_fails_gracefully(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
                "obligation_cte_rules ocr": _row(None,),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "FROM obligations WHERE tenant_id": _row(1,),
                "checkable_rules AS": _row(5, 5),
                "fsma.compliance_alerts": _row(0,),
                "food_traceability_list": _row(10,),
            },
        )

        class _BadPersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                raise OperationalError("fail", None, Exception())
        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _BadPersistence)

        data = _query_scoring_data(session, "t1")
        assert data["chain_verified"] is None
        assert data["chain_verification_errors"] == []

    def test_verify_chain_import_failure(self, monkeypatch):
        """If shared.cte_persistence can't be imported, degrade cleanly."""
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
                "obligation_cte_rules ocr": _row(None,),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "FROM obligations WHERE tenant_id": _row(1,),
                "checkable_rules AS": _row(5, 5),
                "fsma.compliance_alerts": _row(0,),
                "food_traceability_list": _row(10,),
            },
        )

        import builtins
        real_import = builtins.__import__

        def _bad_import(name, *a, **kw):
            if name == "shared.cte_persistence":
                raise ImportError("not found")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _bad_import)
        data = _query_scoring_data(session, "t1")
        assert data["chain_verified"] is None

    def test_chain_verified_false_surfaces_errors(self, monkeypatch):
        session = _RouteSession(
            route={
                "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
                "obligation_cte_rules ocr": _row(None,),
                "fsma.cte_kdes": _row(10, 10),
                "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
                "LAG(sequence_num)": _row(0,),
                "EXTRACT(HOUR": _row(0,),
                "FROM obligations WHERE tenant_id": _row(1,),
                "checkable_rules AS": _row(5, 5),
                "fsma.compliance_alerts": _row(0,),
                "food_traceability_list": _row(10,),
            },
        )

        class _FailPersistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=False, errors=["bad block 3"])
        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _FailPersistence)

        data = _query_scoring_data(session, "t1")
        assert data["chain_verified"] is False
        assert data["chain_verification_errors"] == ["bad block 3"]


# ---------------------------------------------------------------------------
# GET /api/v1/compliance/score/{tenant_id}
# ---------------------------------------------------------------------------


class TestGetComplianceScoreEndpoint:
    def test_invalid_tenant_id_rejected(self, client, monkeypatch):
        # Pass something that trivially fails validate_tenant_id
        r = client.get("/api/v1/compliance/score/invalid!tid")
        # validate_tenant_id raises HTTPException(400) for bad formats
        assert r.status_code in (400, 422)

    def test_db_unavailable_returns_zero_f(self, client, monkeypatch):
        """When shared.database.SessionLocal import raises, returns F."""
        import builtins
        real_import = builtins.__import__

        def _bad_import(name, *a, **kw):
            if name == "shared.database":
                raise ImportError("not found")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _bad_import)

        r = client.get("/api/v1/compliance/score/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 200
        body = r.json()
        assert body["overall_score"] == 0
        assert body["grade"] == "F"
        assert body["breakdown"]["chain_integrity"]["detail"] == "Database unavailable"
        assert any("Database connection required" in a["action"] for a in body["next_actions"])

    def test_query_error_returns_schema_not_initialized(self, client, monkeypatch):
        """When _query_scoring_data raises OperationalError, return F with schema hint."""
        session = MagicMock()
        session.close = MagicMock()

        class _BadSessionLocal:
            def __call__(self):
                return session

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", _BadSessionLocal())

        def _raise(*a, **k):
            raise ProgrammingError("missing table", None, Exception())

        monkeypatch.setattr(cs, "_query_scoring_data", _raise)

        r = client.get("/api/v1/compliance/score/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 200
        body = r.json()
        assert body["overall_score"] == 0
        assert body["grade"] == "F"
        assert "Schema not initialized" in body["breakdown"]["chain_integrity"]["detail"]
        assert session.close.called

    def test_happy_path(self, client, monkeypatch):
        session = MagicMock()
        session.close = MagicMock()

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        fake_data = _base_data(event_count=10, chain_verified=True, last_chain_hash="x" * 64)
        monkeypatch.setattr(cs, "_query_scoring_data", lambda s, t: fake_data)

        r = client.get("/api/v1/compliance/score/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 200
        body = r.json()
        assert body["tenant_id"] == "00000000-0000-0000-0000-000000000001"
        assert body["overall_score"] > 0
        assert body["grade"] in {"A", "B", "C", "D", "F"}
        assert "chain_integrity" in body["breakdown"]
        assert "export_readiness" in body["breakdown"]
        assert body["events_analyzed"] == 10
        assert body["last_chain_hash"] == "x" * 64
        assert session.close.called

    def test_scoring_inner_exception_returns_500(self, client, monkeypatch):
        session = MagicMock()
        session.close = MagicMock()

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        # _query_scoring_data succeeds, but _compute_scores blows up
        monkeypatch.setattr(cs, "_query_scoring_data", lambda s, t: _base_data(event_count=5))

        def _boom(data):
            raise RuntimeError("compute broke")

        monkeypatch.setattr(cs, "_compute_scores", _boom)

        r = client.get("/api/v1/compliance/score/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 500
        assert "Scoring error" in r.json()["detail"]
        assert session.close.called  # finally block still closes


# ---------------------------------------------------------------------------
# GET /api/v1/compliance/pending-reviews/{tenant_id}
# ---------------------------------------------------------------------------


class TestGetPendingReviewsEndpoint:
    def test_db_unavailable(self, client, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def _bad_import(name, *a, **kw):
            if name == "shared.database":
                raise ImportError("not found")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _bad_import)

        r = client.get("/api/v1/compliance/pending-reviews/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 200
        body = r.json()
        assert body["pending_reviews"] == 0
        assert body["db_available"] is False

    def test_happy_path(self, client, monkeypatch):
        # NOTE: match on unique substrings because the rule_evaluations query
        # also references fsma.exception_cases in its NOT EXISTS subquery.
        session = _RouteSession(
            scalar_route={
                "DISTINCT re.event_id": 4,
                "fsma.identity_review_queue": 1,
                "fsma.request_cases": 3,
                "status NOT IN ('resolved', 'waived')": 2,
            },
        )

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        r = client.get("/api/v1/compliance/pending-reviews/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 200
        body = r.json()
        assert body["pending_reviews"] == 10  # 2+1+3+4
        assert body["breakdown"]["unresolved_exceptions"] == 2
        assert body["breakdown"]["identity_reviews"] == 1
        assert body["breakdown"]["active_requests"] == 3
        assert body["breakdown"]["critical_failures"] == 4
        assert body["db_available"] is True
        assert session.closed

    def test_identity_table_missing_falls_back(self, client, monkeypatch):
        session = _RouteSession(
            scalar_route={
                "DISTINCT re.event_id": 0,
                "fsma.request_cases": 1,
                "status NOT IN ('resolved', 'waived')": 2,
            },
            raise_on={"fsma.identity_review_queue": ProgrammingError("x", None, Exception())},
        )

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        r = client.get("/api/v1/compliance/pending-reviews/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 200
        body = r.json()
        assert body["breakdown"]["identity_reviews"] == 0
        assert body["pending_reviews"] == 3  # 2+0+1+0

    def test_outer_query_exception_returns_error_body(self, client, monkeypatch):
        session = _RouteSession(
            raise_on={"status NOT IN ('resolved', 'waived')": RuntimeError("boom")},
        )

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        r = client.get("/api/v1/compliance/pending-reviews/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 200
        body = r.json()
        assert body["pending_reviews"] == 0
        assert body["db_available"] is False
        assert "error" in body
        assert session.closed  # finally block still closes

    def test_scalar_returns_none_coalesces_to_zero(self, client, monkeypatch):
        """When scalar() returns None (empty tables), count coalesces to 0."""
        session = _RouteSession(scalar_route={})  # all scalar() return None

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

        r = client.get("/api/v1/compliance/pending-reviews/00000000-0000-0000-0000-000000000001")
        assert r.status_code == 200
        body = r.json()
        assert body["pending_reviews"] == 0
        assert body["db_available"] is True


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_score_route_registered(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/compliance/score/{tenant_id}" in paths
        assert "/api/v1/compliance/pending-reviews/{tenant_id}" in paths


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_score_breakdown_bounds(self):
        with pytest.raises(Exception):
            ScoreBreakdown(score=-1, detail="x")
        with pytest.raises(Exception):
            ScoreBreakdown(score=101, detail="x")
        assert ScoreBreakdown(score=50, detail="x").score == 50

    def test_next_action_fields(self):
        a = NextAction(priority="HIGH", action="do X", impact="Y")
        assert a.priority == "HIGH"
        assert a.action == "do X"

    def test_compliance_score_response_defaults(self):
        r = ComplianceScoreResponse(
            tenant_id="t", overall_score=50, grade="C", breakdown={},
        )
        assert r.next_actions == []
        assert r.events_analyzed == 0
        assert r.last_chain_hash is None

    def test_compliance_score_response_score_bounds(self):
        with pytest.raises(Exception):
            ComplianceScoreResponse(
                tenant_id="t", overall_score=-1, grade="F", breakdown={},
            )
        with pytest.raises(Exception):
            ComplianceScoreResponse(
                tenant_id="t", overall_score=101, grade="A", breakdown={},
            )
