"""Focused coverage for services/shared/rules/evaluators/relational.py.

The three relational evaluators (temporal_order, identity_consistency,
mass_balance) plus fetch_related_events had no dedicated test file.
All tests below pass ``related_events`` explicitly so no database is
touched, except the fetch_related_events tests which use a fake session.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from shared.rules.evaluators.relational import (
    RELATIONAL_EVALUATORS,
    evaluate_identity_consistency,
    evaluate_mass_balance,
    evaluate_temporal_order,
    fetch_related_events,
)
from shared.rules.types import RuleDefinition


def _make_rule(rule_id: str = "r-test") -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        rule_version=1,
        title=f"Rule {rule_id}",
        description="",
        severity="critical",
        category="cross_event_integrity",
        applicability_conditions={},
        citation_reference="21 CFR 1.1310",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "relational"},
        failure_reason_template="",
        remediation_suggestion="fix it",
    )


def _make_event(**overrides: Any) -> Dict[str, Any]:
    evt: Dict[str, Any] = {
        "event_id": "11111111-1111-1111-1111-111111111111",
        "event_type": "receiving",
        "traceability_lot_code": "TLC-A",
        "product_reference": "Romaine",
        "quantity": 100.0,
        "unit_of_measure": "lbs",
        "event_timestamp": datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
    }
    evt.update(overrides)
    return evt


def _related(
    event_type: str = "shipping",
    ts: Optional[datetime] = None,
    product: str = "Romaine",
    quantity: Any = 100.0,
    uom: str = "lbs",
    event_id: str = "22222222-2222-2222-2222-222222222222",
) -> Dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_timestamp": ts or datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc),
        "product_reference": product,
        "quantity": quantity,
        "unit_of_measure": uom,
    }


class _FakeResult:
    def __init__(self, rows: List[tuple]):
        self._rows = rows

    def fetchall(self) -> List[tuple]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows: List[tuple]):
        self._rows = rows
        self.last_params: Optional[Dict[str, Any]] = None
        self.calls = 0

    def execute(self, _stmt: Any, params: Optional[Dict[str, Any]] = None) -> _FakeResult:
        self.calls += 1
        self.last_params = params
        return _FakeResult(self._rows)


class TestDispatch:
    def test_relational_evaluators_has_all_three(self) -> None:
        assert set(RELATIONAL_EVALUATORS) == {
            "temporal_order",
            "identity_consistency",
            "mass_balance",
        }
        assert RELATIONAL_EVALUATORS["temporal_order"] is evaluate_temporal_order
        assert RELATIONAL_EVALUATORS["identity_consistency"] is evaluate_identity_consistency
        assert RELATIONAL_EVALUATORS["mass_balance"] is evaluate_mass_balance


class TestFetchRelatedEvents:
    def test_maps_rows_and_binds_params(self) -> None:
        ts = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
        session = _FakeSession(
            rows=[
                ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "shipping", ts, "Romaine", 50, "lbs"),
                ("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "harvesting", ts, "Romaine", None, "kg"),
            ]
        )
        out = fetch_related_events(
            session,  # type: ignore[arg-type]
            "TLC-A",
            "tenant-a",
            exclude_event_id="11111111-1111-1111-1111-111111111111",
        )
        assert session.calls == 1
        assert session.last_params == {
            "tlc": "TLC-A",
            "tenant_id": "tenant-a",
            "exclude_id": "11111111-1111-1111-1111-111111111111",
        }
        assert out[0]["event_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        assert out[0]["quantity"] == 50.0
        assert out[1]["quantity"] is None
        assert out[1]["event_timestamp"] is ts

    def test_empty_result(self) -> None:
        session = _FakeSession(rows=[])
        assert fetch_related_events(session, "TLC-X", "t1") == []  # type: ignore[arg-type]


class TestTemporalOrder:
    def test_pass_when_chronology_consistent(self) -> None:
        rule = _make_rule("r-temp")
        evt = _make_event(
            event_type="shipping",
            event_timestamp=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
        )
        related = [_related("harvesting", datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc))]
        result = evaluate_temporal_order(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result == "pass"

    def test_fail_on_chronology_paradox(self) -> None:
        rule = _make_rule("r-temp")
        evt = _make_event(
            event_type="receiving",  # stage 6
            event_timestamp=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        )
        related = [_related("shipping", datetime(2026, 4, 10, 8, 0, tzinfo=timezone.utc))]  # earlier stage, later time
        result = evaluate_temporal_order(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result == "fail"
        assert "TLC-A" in (result.why_failed or "")

    def test_pass_with_no_related_events(self) -> None:
        rule = _make_rule("r-temp")
        result = evaluate_temporal_order(_make_event(), {}, rule, MagicMock(), tenant_id="t1", related_events=[])
        assert result.result == "pass"

    def test_skip_when_missing_tlc_or_tenant(self) -> None:
        rule = _make_rule("r-temp")
        assert (
            evaluate_temporal_order(
                _make_event(traceability_lot_code=""), {}, rule, MagicMock(), tenant_id="t1", related_events=[]
            ).result
            == "skip"
        )
        assert (
            evaluate_temporal_order(_make_event(), {}, rule, MagicMock(), tenant_id=None, related_events=[]).result
            == "skip"
        )

    def test_skip_when_timestamp_missing(self) -> None:
        rule = _make_rule("r-temp")
        evt = _make_event(event_timestamp=None)
        result = evaluate_temporal_order(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=[_related()])
        assert result.result == "skip"

    def test_skip_on_unknown_cte_type(self) -> None:
        rule = _make_rule("r-temp")
        evt = _make_event(event_type="not-a-cte")
        result = evaluate_temporal_order(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=[_related()])
        assert result.result == "skip"
        assert "not-a-cte" in (result.why_failed or "")

    def test_payload_tenant_id_is_ignored(self) -> None:
        rule = _make_rule("r-temp")
        evt = _make_event(tenant_id="attacker-tenant")
        result = evaluate_temporal_order(evt, {}, rule, MagicMock(), tenant_id="real-tenant", related_events=[])
        assert result.result == "pass"

    def test_iso_string_timestamps_are_parsed(self) -> None:
        rule = _make_rule("r-temp")
        evt = _make_event(event_type="shipping", event_timestamp="2026-04-10T12:00:00Z")
        related = [_related("harvesting", "2026-04-01T08:00:00Z")]  # type: ignore[dict-item]
        result = evaluate_temporal_order(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result == "pass"


class TestIdentityConsistency:
    def test_pass_when_products_match(self) -> None:
        rule = _make_rule("r-ident")
        result = evaluate_identity_consistency(
            _make_event(), {}, rule, MagicMock(), tenant_id="t1", related_events=[_related()]
        )
        assert result.result == "pass"

    def test_pass_ignores_case_and_whitespace(self) -> None:
        rule = _make_rule("r-ident")
        evt = _make_event(product_reference="  ROMAINE   hearts ")
        related = [_related(product="romaine hearts")]
        result = evaluate_identity_consistency(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result == "pass"

    def test_fail_on_product_drift(self) -> None:
        rule = _make_rule("r-ident")
        related = [_related(product="Spinach")]
        result = evaluate_identity_consistency(
            _make_event(), {}, rule, MagicMock(), tenant_id="t1", related_events=related
        )
        assert result.result == "fail"
        assert "Spinach" in (result.why_failed or "")

    def test_skip_when_missing_product_tlc_or_tenant(self) -> None:
        rule = _make_rule("r-ident")
        assert (
            evaluate_identity_consistency(
                _make_event(product_reference=""), {}, rule, MagicMock(), tenant_id="t1", related_events=[]
            ).result
            == "skip"
        )
        assert (
            evaluate_identity_consistency(
                _make_event(), {}, rule, MagicMock(), tenant_id=None, related_events=[]
            ).result
            == "skip"
        )

    def test_skips_related_events_without_product(self) -> None:
        rule = _make_rule("r-ident")
        related = [_related(product="")]
        result = evaluate_identity_consistency(
            _make_event(), {}, rule, MagicMock(), tenant_id="t1", related_events=related
        )
        assert result.result == "pass"


class TestMassBalance:
    def test_pass_when_output_within_input(self) -> None:
        rule = _make_rule("r-mass")
        evt = _make_event(event_type="shipping", quantity=50.0, unit_of_measure="lbs")
        related = [_related(event_type="harvesting", quantity=100.0, uom="lbs")]
        result = evaluate_mass_balance(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result == "pass"

    def test_fail_when_output_exceeds_input(self) -> None:
        rule = _make_rule("r-mass")
        evt = _make_event(event_type="shipping", quantity=150.0, unit_of_measure="lbs")
        related = [_related(event_type="harvesting", quantity=100.0, uom="lbs")]
        result = evaluate_mass_balance(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result == "fail"

    def test_pass_with_no_related_events(self) -> None:
        rule = _make_rule("r-mass")
        result = evaluate_mass_balance(
            _make_event(event_type="shipping"), {}, rule, MagicMock(), tenant_id="t1", related_events=[]
        )
        assert result.result == "pass"

    def test_warn_when_output_but_no_input(self) -> None:
        rule = _make_rule("r-mass")
        evt = _make_event(event_type="shipping", quantity=10.0, unit_of_measure="lbs")
        related = [_related(event_type="shipping", quantity=5.0, uom="lbs")]
        result = evaluate_mass_balance(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result == "warn"
        assert "no input" in (result.why_failed or "").lower()

    def test_warn_on_mixed_mass_and_container_units(self) -> None:
        rule = _make_rule("r-mass")
        evt = _make_event(event_type="shipping", quantity=2.0, unit_of_measure="case")
        related = [_related(event_type="harvesting", quantity=100.0, uom="lbs")]
        result = evaluate_mass_balance(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result == "warn"

    def test_converted_mass_units_render_verdict(self) -> None:
        rule = _make_rule("r-mass")
        evt = _make_event(event_type="shipping", quantity=50.0, unit_of_measure="kg")
        related = [_related(event_type="harvesting", quantity=200.0, uom="lbs")]
        result = evaluate_mass_balance(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=related)
        assert result.result in ("pass", "fail")

    def test_skip_when_quantity_missing(self) -> None:
        rule = _make_rule("r-mass")
        evt = _make_event(quantity=None)
        result = evaluate_mass_balance(evt, {}, rule, MagicMock(), tenant_id="t1", related_events=[])
        assert result.result == "skip"
