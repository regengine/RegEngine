"""Under ``all``, a warning caused only by a deferred KDE does not reject.

EDI shipments are stored with an open data gap when X12 can't carry the TLC
source reference. The seeded rule for that KDE is a warning, and ``all``
rejects on warnings, so without this the gap could never be stored.
"""

from __future__ import annotations

import pytest

from shared.rules.enforcement import should_reject
from shared.rules.types import EvaluationSummary, RuleEvaluationResult

DEFERRED = frozenset({"tlc_source_reference"})


def _field(name: str, present: bool = False) -> dict:
    return {"field": name, "value": None, "present": present}


def _tlc_source_warning(severity: str = "warning") -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id="tlc-source",
        severity=severity,
        result="fail",
        why_failed="missing TLC source",
        evidence_fields_inspected=[_field("kdes.tlc_source_reference"), _field("kdes.tlc_source_gln")],
    )


def _other_warning() -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id="other",
        severity="warning",
        result="fail",
        why_failed="other failure",
        evidence_fields_inspected=[_field("kdes.carrier")],
    )


def _summary(*results: RuleEvaluationResult, errored: int = 0) -> EvaluationSummary:
    failed = sum(1 for result in results if result.result == "fail")
    return EvaluationSummary(
        total_rules=len(results) + 1,
        passed=1,
        failed=failed,
        errored=errored,
        results=list(results),
        critical_failures=[result for result in results if result.severity == "critical"],
    )


@pytest.fixture(autouse=True)
def _all_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")


def test_deferred_failure_does_not_reject_and_stays_noncompliant() -> None:
    summary = _summary(_tlc_source_warning())

    assert should_reject(summary, deferred_kdes=DEFERRED) == (False, None)
    assert summary.compliant is False


def test_without_deferred_kdes_the_warning_still_rejects() -> None:
    assert should_reject(_summary(_tlc_source_warning()))[0] is True


def test_another_failure_still_rejects_and_is_the_reason() -> None:
    reject, reason = should_reject(_summary(_tlc_source_warning(), _other_warning()), deferred_kdes=DEFERRED)

    assert reject is True
    assert reason == "other: other failure"


def test_critical_rule_on_the_same_kde_still_rejects() -> None:
    assert should_reject(_summary(_tlc_source_warning("critical")), deferred_kdes=DEFERRED)[0] is True


def test_rule_needing_another_missing_field_still_rejects() -> None:
    result = _tlc_source_warning()
    result.evidence_fields_inspected.append(_field("kdes.carrier"))

    assert should_reject(_summary(result), deferred_kdes=DEFERRED)[0] is True


def test_evaluator_error_still_rejects() -> None:
    assert should_reject(_summary(_tlc_source_warning(), errored=1), deferred_kdes=DEFERRED)[0] is True


def test_unexplained_failure_count_fails_closed() -> None:
    summary = _summary(_tlc_source_warning())
    summary.failed = 2

    assert should_reject(summary, deferred_kdes=DEFERRED)[0] is True
