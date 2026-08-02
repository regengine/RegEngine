"""temporal_order must degrade to skip — not crash — on missing timestamps.

Regression for the evaluation-durability incident: an eval payload without
``event_timestamp`` made ``evaluate_temporal_order`` raise
``TypeError: '>' not supported between 'datetime' and 'NoneType'``, the
engine converted that to ``result='error'``, the DB CHECK constraint
rejected the row, and the whole evaluation batch was lost (see v108
migration docstring). Chronology is unknowable without a timestamp, so the
evaluator returns an explicit skip and ignores related rows with NULL
timestamps instead of raising.
"""

from datetime import date, datetime, timezone

from shared.rules.evaluators.relational import evaluate_temporal_order
from shared.rules.types import RuleDefinition

TENANT = "11111111-1111-1111-1111-111111111111"


def _rule() -> RuleDefinition:
    return RuleDefinition(
        rule_id="r-temporal",
        rule_version=1,
        title="Temporal Order: CTE Chronology Must Be Causal",
        description="",
        severity="critical",
        category="temporal_ordering",
        applicability_conditions={"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
        citation_reference="21 CFR §1.1310",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "temporal_order"},
        failure_reason_template="",
        remediation_suggestion="",
    )


def _event(**overrides) -> dict:
    evt = {
        "event_id": "22222222-2222-2222-2222-222222222222",
        "event_type": "receiving",
        "traceability_lot_code": "TLC-A",
        "product_reference": "Romaine",
        "quantity": 100.0,
        "unit_of_measure": "lbs",
        "event_timestamp": datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
    }
    evt.update(overrides)
    return evt


def _related(event_type: str, ts) -> dict:
    return {
        "event_id": "33333333-3333-3333-3333-333333333333",
        "event_type": event_type,
        "event_timestamp": ts,
        "product_reference": "Romaine",
        "quantity": 100.0,
        "unit_of_measure": "lbs",
    }


class TestNoneCurrentTimestamp:
    def test_returns_skip_not_error(self):
        result = evaluate_temporal_order(
            _event(event_timestamp=None),
            {"type": "temporal_order"},
            _rule(),
            session=None,
            tenant_id=TENANT,
            related_events=[_related("harvesting", datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc))],
        )
        assert result.result == "skip"
        assert "event_timestamp" in (result.why_failed or "")

    def test_no_related_events_still_passes_before_timestamp_check(self):
        # Empty related list short-circuits to pass regardless of timestamp.
        result = evaluate_temporal_order(
            _event(event_timestamp=None),
            {"type": "temporal_order"},
            _rule(),
            session=None,
            tenant_id=TENANT,
            related_events=[],
        )
        assert result.result == "pass"


class TestNoneRelatedTimestamp:
    def test_related_row_with_null_timestamp_is_ignored(self):
        # A NULL-timestamp sibling used to raise TypeError; now it is
        # excluded from chronology comparison and the rest still evaluate.
        result = evaluate_temporal_order(
            _event(),
            {"type": "temporal_order"},
            _rule(),
            session=None,
            tenant_id=TENANT,
            related_events=[_related("harvesting", None)],
        )
        assert result.result == "pass"

    def test_violation_still_detected_alongside_null_timestamp_row(self):
        # Guard must not mask real violations: harvesting AFTER receiving
        # is out of causal order and must still fail.
        result = evaluate_temporal_order(
            _event(),
            {"type": "temporal_order"},
            _rule(),
            session=None,
            tenant_id=TENANT,
            related_events=[
                _related("harvesting", None),
                _related("harvesting", datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc)),
            ],
        )
        assert result.result == "fail"

    def test_string_timestamps_still_parse(self):
        result = evaluate_temporal_order(
            _event(event_timestamp="2026-04-10T12:00:00Z"),
            {"type": "temporal_order"},
            _rule(),
            session=None,
            tenant_id=TENANT,
            related_events=[_related("harvesting", "2026-04-09T08:00:00Z")],
        )
        assert result.result == "pass"
