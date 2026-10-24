"""Data gap time to fix: pure logic and writer state transitions.

No database. The writer runs against a recording fake session so the tests
check which statements a validation outcome produces, not their effect.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from shared.data_gap_tracking import (
    AT_RISK_THRESHOLD,
    GAP_KIND_CTE_VALIDATION_FAILED,
    GAP_KIND_MISSING_KDE,
    Gap,
    ValidationOutcome,
    decide_transition,
    gap_from_rule_reason,
    gap_identity,
    gaps_from_kde_errors,
    is_at_risk,
    is_receipt_hash,
    median_seconds,
    oldest_opened_at,
    record_outcomes,
    summarize_supplier,
)

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
RECEIPT = hashlib.sha256(b"x").hexdigest()


# ---------------------------------------------------------------------------
# Median / oldest / at risk
# ---------------------------------------------------------------------------


def test_median_empty_is_none():
    assert median_seconds([]) is None


def test_median_odd_count():
    assert median_seconds([30.0, 10.0, 20.0]) == 20.0


def test_median_even_count_averages_middle_pair():
    # Matches percentile_cont(0.5): interpolates between the middle values.
    assert median_seconds([1.0, 2.0, 3.0, 10.0]) == 2.5


def test_oldest_opened_at():
    assert oldest_opened_at([]) is None
    assert oldest_opened_at([NOW, NOW - timedelta(hours=1)]) == NOW - timedelta(hours=1)


def test_at_risk_threshold_is_24_hours():
    assert AT_RISK_THRESHOLD == timedelta(hours=24)


def test_gap_open_exactly_24_hours_is_not_at_risk():
    assert is_at_risk([NOW - timedelta(hours=24)], NOW) is False


def test_gap_open_just_over_24_hours_is_at_risk():
    assert is_at_risk([NOW - timedelta(hours=24, microseconds=1)], NOW) is True


def test_no_open_gaps_is_not_at_risk():
    assert is_at_risk([], NOW) is False


def test_summary_without_history_has_no_data():
    assert summarize_supplier([], [], NOW) == {
        "open_gap_count": 0,
        "median_time_to_fix_seconds": None,
        "oldest_open_gap_opened_at": None,
        "at_risk": False,
        "has_data": False,
    }


def test_summary_with_only_closed_gaps_has_data():
    result = summarize_supplier([], [60.0], NOW)
    assert result["has_data"] is True
    assert result["open_gap_count"] == 0
    assert result["median_time_to_fix_seconds"] == 60.0


def test_summary_with_open_gaps():
    opened = NOW - timedelta(hours=30)
    result = summarize_supplier([opened, NOW], [], NOW)
    assert result["open_gap_count"] == 2
    assert result["oldest_open_gap_opened_at"] == opened.isoformat()
    assert result["at_risk"] is True


# ---------------------------------------------------------------------------
# Gap extraction and idempotency key
# ---------------------------------------------------------------------------


def test_missing_kde_errors_map_to_kde_names():
    errors = ["Missing required KDE 'a' for b CTE", "Missing required KDE 'c' for b CTE"]
    assert gaps_from_kde_errors(errors) == (Gap(GAP_KIND_MISSING_KDE, "a"), Gap(GAP_KIND_MISSING_KDE, "c"))


def test_harvester_phone_error_maps_to_kde_name():
    assert gaps_from_kde_errors(["Harvester business phone must be a non-empty string"]) == (
        Gap(GAP_KIND_MISSING_KDE, "harvester_business_phone"),
    )


def test_duplicate_kde_errors_collapse():
    errors = ["Missing required KDE 'a' for b CTE"] * 2
    assert gaps_from_kde_errors(errors) == (Gap(GAP_KIND_MISSING_KDE, "a"),)


def test_unrecognised_error_still_opens_a_gap():
    assert gaps_from_kde_errors(["z"]) == (Gap(GAP_KIND_MISSING_KDE, "z"),)


def test_rule_reason_keys_on_rule_id():
    assert gap_from_rule_reason("r1: why") == Gap(GAP_KIND_CTE_VALIDATION_FAILED, "r1")


def test_rule_reason_without_id_falls_back():
    assert gap_from_rule_reason(None) == Gap(GAP_KIND_CTE_VALIDATION_FAILED, "rule_violation")
    assert gap_from_rule_reason("") == Gap(GAP_KIND_CTE_VALIDATION_FAILED, "rule_violation")


def test_gap_identity_is_deterministic_and_normalized():
    gap = Gap(GAP_KIND_MISSING_KDE, "a")
    first = gap_identity("T", " s ", " l ", "Shipping", gap)
    assert first == gap_identity("t", "s", "l", "shipping", gap)
    assert first == ("t", "s", "l", "shipping", GAP_KIND_MISSING_KDE, "a")


def test_gap_identity_differs_by_kind_and_key():
    base = gap_identity("t", "s", "l", "c", Gap(GAP_KIND_MISSING_KDE, "a"))
    assert base != gap_identity("t", "s", "l", "c", Gap(GAP_KIND_CTE_VALIDATION_FAILED, "a"))
    assert base != gap_identity("t", "s", "l", "c", Gap(GAP_KIND_MISSING_KDE, "b"))


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def test_failing_record_opens_and_passing_record_closes():
    assert decide_transition([Gap(GAP_KIND_MISSING_KDE, "a")]) == "open"
    assert decide_transition([]) == "close"


def test_receipt_hash_validation():
    assert is_receipt_hash(RECEIPT) is True
    assert is_receipt_hash(RECEIPT.upper()) is False
    assert is_receipt_hash(RECEIPT[:-1]) is False
    assert is_receipt_hash(None) is False
    assert is_receipt_hash("") is False


class _Savepoint:
    def __init__(self, log: list[str]):
        self._log = log

    def commit(self):
        self._log.append("savepoint_commit")

    def rollback(self):
        self._log.append("savepoint_rollback")


class _RecordingSession:
    def __init__(self, fail_on: str | None = None):
        self.log: list[str] = []
        self.statements: list[tuple[str, dict]] = []
        self._fail_on = fail_on

    def begin_nested(self):
        return _Savepoint(self.log)

    def execute(self, statement, params):
        sql = str(statement).strip().split()[0].upper()
        if self._fail_on == sql:
            raise RuntimeError("boom")
        self.statements.append((sql, params))

    def commit(self):
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")


def _kinds(session: _RecordingSession) -> list[str]:
    return [sql for sql, _ in session.statements]


def test_failing_outcome_only_inserts_and_never_closes():
    session = _RecordingSession()
    outcome = ValidationOutcome(
        order=0,
        lot_code="l",
        cte_type="c",
        gaps=(Gap(GAP_KIND_MISSING_KDE, "a"), Gap(GAP_KIND_MISSING_KDE, "b")),
    )
    record_outcomes(session, "t", [outcome])
    assert _kinds(session) == ["INSERT", "INSERT"]
    assert session.log[-1] == "commit"


def test_passing_outcome_closes_with_unmodified_receipt():
    session = _RecordingSession()
    outcome = ValidationOutcome(order=0, lot_code="l", cte_type="c", closing_record_id="r", closing_record_hash=RECEIPT)
    record_outcomes(session, "t", [outcome])
    assert _kinds(session) == ["UPDATE"]
    params = session.statements[0][1]
    assert params["rhash"] == RECEIPT
    assert params["rid"] == "r"
    assert (params["lot"], params["cte"]) == ("l", "c")


def test_passing_outcome_without_receipt_does_not_close():
    session = _RecordingSession()
    record_outcomes(session, "t", [ValidationOutcome(order=0, lot_code="l", cte_type="c", closing_record_id="r")])
    assert _kinds(session) == []


def test_outcomes_apply_in_arrival_order():
    session = _RecordingSession()
    passed = ValidationOutcome(order=1, lot_code="l", cte_type="c", closing_record_id="r", closing_record_hash=RECEIPT)
    failed = ValidationOutcome(order=0, lot_code="l", cte_type="c", gaps=(Gap(GAP_KIND_MISSING_KDE, "a"),))
    record_outcomes(session, "t", [passed, failed])
    assert _kinds(session) == ["INSERT", "UPDATE"]


def test_write_errors_are_swallowed_per_outcome():
    session = _RecordingSession(fail_on="INSERT")
    failed = ValidationOutcome(order=0, lot_code="l", cte_type="c", gaps=(Gap(GAP_KIND_MISSING_KDE, "a"),))
    passed = ValidationOutcome(order=1, lot_code="l", cte_type="c", closing_record_id="r", closing_record_hash=RECEIPT)
    record_outcomes(session, "t", [failed, passed])
    assert "savepoint_rollback" in session.log
    assert _kinds(session) == ["UPDATE"]
    assert session.log[-1] == "commit"


def test_commit_failure_never_raises():
    class _CommitFails(_RecordingSession):
        def commit(self):
            raise RuntimeError("boom")

    session = _CommitFails()
    failed = ValidationOutcome(order=0, lot_code="l", cte_type="c", gaps=(Gap(GAP_KIND_MISSING_KDE, "a"),))
    record_outcomes(session, "t", [failed])
    assert session.log[-1] == "rollback"


def test_no_session_is_a_no_op():
    record_outcomes(None, "t", [ValidationOutcome(order=0, lot_code="l", cte_type="c")])
