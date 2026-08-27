"""#2960 / #2962: export-readiness and KDE-completeness scoring must not
report readiness the platform has not actually verified.

#2960 — the export-readiness chain branch handled ``chain_verified is True``
(+40) and ``chain_verification_error`` (no credit) but never
``chain_verified is False``.  A chain that RAN cryptographic verification and
FAILED it fell through to the sequence-gap fallback and collected +30 of 40,
reaching 90 with complete KDEs and >=3 CTE types — rendered as the literal
string "FDA export ready" next to the issue "chain not cryptographically
verified", which is the opposite of what happened.  Hash tampering rewrites
payloads without deleting rows, so ``chain_gaps == 0`` holds for exactly the
case the branch exists to catch.

#2962 — ``kde_completeness`` was ``filled_kdes / total_kdes``, both sides a
``COUNT(*)`` over ``fsma.cte_kdes``.  Rows exist there only for KDEs the
ingest actually supplied, so a required KDE that was never provided appeared
in neither numerator nor denominator: a shipping event carrying 2 of its 9
FSMA-required KDEs scored 100/100.  The denominator must come from
``REQUIRED_KDES_BY_CTE`` (per CTE type, not one flat list).

Issues: #2960, #2962
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app import compliance_score as cs
from app.compliance_score import _compute_scores, _query_scoring_data
from app.webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType
from sqlalchemy.exc import ProgrammingError

from services.ingestion.tests.test_compliance_score_1342 import _RouteSession, _row


def _data(**overrides) -> dict:
    """A fully-covered tenant: every dimension at full credit.

    Deliberately self-contained (not the 1342 module's ``_base_data``) so the
    numbers these regressions lock cannot drift with that shared fixture.
    """
    base = {
        "event_count": 10,
        "distinct_cte_types": 5,
        "cte_types_present": ["harvesting", "cooling", "shipping", "receiving", "transformation"],
        "missing_cte_types": ["initial_packing", "first_land_based_receiving"],
        "active_cte_types": None,
        "total_kdes": 50,
        "filled_kdes": 50,
        "required_kde_checks_total": 50,
        "required_kde_checks_passed": 50,
        "events_unchecked_type": 0,
        "unchecked_event_types": [],
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


# ---------------------------------------------------------------------------
# #2960 — failed cryptographic verification must earn no export credit
# ---------------------------------------------------------------------------


class TestExportReadinessChainVerificationFailed:
    def test_tampered_contiguous_chain_scores_zero_not_ninety(self):
        """The exact reported state: verification ran, returned invalid, and
        the sequence numbers are contiguous because tampering rewrites
        payloads without deleting rows."""
        scores = _compute_scores(
            _data(
                chain_verified=False,
                chain_verification_errors=["hash mismatch at sequence 7"],
                chain_length=10,
                chain_gaps=0,
            )
        )
        score, detail = scores["export_readiness"]
        # Pre-fix: 30 (gap fallback) + 30 (KDE) + 30 (>=3 CTE types) = 90.
        assert score == 0
        assert "FDA export ready" not in detail

    def test_three_verification_states_score_differently(self):
        """PASSED, FAILED and NOT-RUN must be three distinct scores, and
        NOT-RUN must never score as PASSED."""
        passed = _compute_scores(_data(chain_verified=True))["export_readiness"][0]
        failed = _compute_scores(
            _data(chain_verified=False, chain_verification_errors=["hash mismatch at sequence 7"])
        )["export_readiness"][0]
        not_run = _compute_scores(
            _data(chain_verified=None, chain_verification_errors=[], chain_verification_error=True)
        )["export_readiness"][0]

        # 40+30+30 / clamped / 0+30+30
        assert (passed, failed, not_run) == (100, 0, 60)
        assert len({passed, failed, not_run}) == 3

    def test_issue_text_distinguishes_failed_from_not_performed(self):
        failed = _compute_scores(
            _data(chain_verified=False, chain_verification_errors=["hash mismatch at sequence 7"])
        )["export_readiness"][1]
        not_run = _compute_scores(
            _data(chain_verified=None, chain_verification_errors=[], chain_verification_error=True)
        )["export_readiness"][1]
        # verified=None with no error flag: verification never attempted,
        # gap detection only — distinct again from both of the above.
        not_attempted = _compute_scores(
            _data(chain_verified=None, chain_verification_errors=[], distinct_cte_types=2)
        )["export_readiness"][1]

        assert "chain verification FAILED" in failed
        # The false string the bug emitted for a chain that WAS verified.
        assert "chain not cryptographically verified" not in failed
        assert "chain verification unavailable" in not_run
        assert "chain not cryptographically verified" in not_attempted

    def test_chain_integrity_dimension_still_reports_tamper(self):
        """Guard: the fix must not disturb the dimension that already
        labelled this state correctly."""
        scores = _compute_scores(_data(chain_verified=False, chain_verification_errors=["hash mismatch"]))
        score, detail = scores["chain_integrity"]
        assert score == 75  # 100 - 1*25
        assert "TAMPER DETECTED" in detail


# ---------------------------------------------------------------------------
# #2962 — the denominator is the FSMA-required KDE set for the CTE type
# ---------------------------------------------------------------------------


class TestRequiredKdeCoverageDenominator:
    def test_denominator_is_per_cte_type_not_flat(self):
        """Harvesting requires 7 KDEs, shipping 9. A single flat required
        list for every CTE type would be a different bug."""
        harvesting = cs._required_kde_coverage({"harvesting": 1}, {})
        shipping = cs._required_kde_coverage({"shipping": 1}, {})

        assert harvesting["required_kde_checks_total"] == len(REQUIRED_KDES_BY_CTE[WebhookCTEType.HARVESTING]) == 7
        assert shipping["required_kde_checks_total"] == len(REQUIRED_KDES_BY_CTE[WebhookCTEType.SHIPPING]) == 9

    def test_two_of_seven_required_present(self):
        cov = cs._required_kde_coverage(
            {"harvesting": 1},
            {("harvesting", "traceability_lot_code"): 1, ("harvesting", "quantity"): 1},
        )
        assert cov["required_kde_checks_total"] == 7
        assert cov["required_kde_checks_passed"] == 2
        assert cov["events_unchecked_type"] == 0

    def test_denominator_scales_with_event_count(self):
        cov = cs._required_kde_coverage({"harvesting": 4}, {("harvesting", "quantity"): 3})
        assert cov["required_kde_checks_total"] == 28  # 4 events x 7 required
        assert cov["required_kde_checks_passed"] == 3

    def test_unknown_cte_type_is_unchecked_not_fully_covered(self):
        """#2698 pattern: an event type with no required-KDE checklist is
        UNCHECKED, never silently 100%."""
        cov = cs._required_kde_coverage({"aggregation": 3}, {})
        assert cov["required_kde_checks_total"] == 0
        assert cov["events_unchecked_type"] == 3
        assert cov["unchecked_event_types"] == ["aggregation"]

    def test_enum_member_without_checklist_does_not_raise(self):
        """``growing`` is a WebhookCTEType member but has no entry in
        REQUIRED_KDES_BY_CTE — it must route to UNCHECKED, not KeyError."""
        cov = cs._required_kde_coverage({"growing": 2}, {})
        assert cov["events_unchecked_type"] == 2

    def test_event_type_matching_is_case_insensitive(self):
        cov = cs._required_kde_coverage({"HARVESTING": 1}, {("HARVESTING", "quantity"): 1})
        assert cov["required_kde_checks_total"] == 7
        assert cov["required_kde_checks_passed"] == 1


class TestKdeCompletenessScoredAgainstRequiredSet:
    def test_partial_required_set_scores_materially_below_100(self):
        """A shipping/harvesting tenant recording 2 of 7 required KDEs must
        not read 100%, and the export KDE credit must be < 30."""
        scores = _compute_scores(
            _data(
                event_count=1,
                chain_length=1,
                distinct_cte_types=1,
                cte_types_present=["harvesting"],
                total_kdes=2,
                filled_kdes=2,
                required_kde_checks_total=7,
                required_kde_checks_passed=2,
            )
        )
        kde_score, kde_detail = scores["kde_completeness"]
        export_score, export_detail = scores["export_readiness"]

        # Pre-fix: filled_kdes/total_kdes == 2/2 == 100.
        assert kde_score == 28  # int(2/7 * 100)
        assert "2/7 required" in kde_detail
        assert "5 missing" in kde_detail

        # 40 (verified chain) + int(2/7*30)=8 + 15 (single CTE type) = 63.
        assert export_score == 63
        assert "FDA export ready" not in export_detail
        assert "KDE gaps" in export_detail

    def test_full_required_set_still_scores_100(self):
        """Guard against over-correction: complete tenants keep full credit."""
        scores = _compute_scores(_data(required_kde_checks_total=70, required_kde_checks_passed=70))
        assert scores["kde_completeness"][0] == 100
        assert scores["export_readiness"][0] == 100

    def test_only_unchecked_event_types_scores_zero_not_100(self):
        scores = _compute_scores(
            _data(
                event_count=3,
                total_kdes=12,
                filled_kdes=12,
                required_kde_checks_total=0,
                required_kde_checks_passed=0,
                events_unchecked_type=3,
                unchecked_event_types=["aggregation"],
            )
        )
        # Pre-fix: 12/12 -> 100.
        assert scores["kde_completeness"][0] == 0
        assert "no FSMA required-KDE checklist" in scores["kde_completeness"][1]
        # 40 (verified) + 0 (no assessable KDEs) + 30 (>=3 CTE types) = 70.
        assert scores["export_readiness"][0] == 70

    def test_required_coverage_read_failure_withholds_the_dimension(self):
        """Fail closed (#2694 pattern): an unavailable required-KDE read must
        poison the dimension, not fall back to the recorded-KDE ratio."""
        scores = _compute_scores(
            _data(
                total_kdes=50,
                filled_kdes=50,
                required_kde_checks_total=0,
                required_kde_checks_passed=0,
                required_kde_data_error=True,
            )
        )
        assert scores["kde_completeness"][0] == 0
        assert "withheld" in scores["kde_completeness"][1]
        # 40 (verified) + 0 (KDE credit withheld) + 30 (>=3 CTE types) = 70.
        assert scores["export_readiness"][0] == 70

    def test_time_precision_penalty_still_applies(self):
        scores = _compute_scores(
            _data(
                event_count=10,
                events_missing_time=5,
                required_kde_checks_total=70,
                required_kde_checks_passed=70,
            )
        )
        assert scores["kde_completeness"][0] == 95  # 100 - int(5/10*10)


# ---------------------------------------------------------------------------
# #2962 — the query layer must actually wire REQUIRED_KDES_BY_CTE in
# ---------------------------------------------------------------------------


def _fake_chain(monkeypatch, valid=True, errors=()):
    class _FakePersistence:
        def __init__(self, s):
            pass

        def verify_chain(self, tid):
            return SimpleNamespace(valid=valid, errors=list(errors))

    import shared.cte_persistence as cte_pkg

    monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)


def _base_routes(**extra):
    route = {
        "fsma.cte_events\n            WHERE": _row(1, 1, ["harvesting"]),
        "obligation_cte_rules ocr": _row(None),
        "fsma.cte_kdes": _row(2, 2),
        "fsma.hash_chain\n            WHERE": _row(1, 1, "abc"),
        "LAG(sequence_num)": _row(0),
        "EXTRACT(HOUR": _row(0),
        "FROM obligations WHERE tenant_id": _row(0),
        "checkable_rules AS": _row(0, 0),
        "fsma.compliance_alerts": _row(0),
        "food_traceability_list": _row(3),
    }
    route.update(extra)
    return route


class TestQueryScoringDataRequiredKdes:
    def test_query_derives_required_totals_from_the_checklist(self, monkeypatch):
        """One harvesting event with 2 of its 7 required KDEs present."""
        _fake_chain(monkeypatch)
        session = _RouteSession(route=_base_routes())
        # One harvesting event; traceability_lot_code + quantity present.
        session.rows_route = {
            "required_kde_presence": [
                ("harvesting", "traceability_lot_code", 1),
                ("harvesting", "quantity", 1),
            ],
            "required_kde_event_types": [("harvesting", 1)],
        }

        data = _query_scoring_data(session, "t1")

        assert data["required_kde_checks_total"] == 7
        assert data["required_kde_checks_passed"] == 2
        assert data.get("required_kde_data_error") is not True

    def test_query_fails_closed_when_required_read_errors(self, monkeypatch):
        _fake_chain(monkeypatch)
        session = _RouteSession(
            route=_base_routes(),
            raise_on={"required_kde_presence": ProgrammingError("stmt", {}, Exception("no such table"))},
        )
        session.rows_route = {"required_kde_event_types": [("harvesting", 1)]}

        data = _query_scoring_data(session, "t1")

        assert data["required_kde_data_error"] is True
        assert data["required_kde_checks_total"] == 0
