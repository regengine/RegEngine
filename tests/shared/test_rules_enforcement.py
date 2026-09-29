"""Unit tests for ``services.shared.rules.enforcement``.

Covers every combination of:
  - RULES_ENGINE_ENFORCE value (off | cte_only | all | unknown | unset | mixed case)
  - EvaluationSummary verdict (compliant=True | False | None)
  - critical_failures present vs empty

The central invariant: ``compliant is None`` stays advisory in ``off`` mode,
but fails closed whenever enforcement is active. An active compliance gate
cannot accept an event the rules engine did not actually evaluate.
"""

from __future__ import annotations

import pytest

from services.shared.rules.enforcement import (
    EnforcementMode,
    current_mode,
    rejection_code,
    should_reject,
)
from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult

# ---------------------------------------------------------------------------
# Fixtures — summary builders
# ---------------------------------------------------------------------------


def _result(
    *,
    rule_id: str = "R1",
    severity: str = "critical",
    result: str = "fail",
    why_failed: str = "missing_kde",
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_version=1,
        rule_title=rule_id,
        severity=severity,
        result=result,
        why_failed=why_failed,
    )


def _summary_compliant_true() -> EvaluationSummary:
    """All rules passed, non-empty result set → compliant=True."""
    return EvaluationSummary(
        total_rules=2,
        passed=2,
        results=[
            _result(rule_id="R1", result="pass", why_failed=None),
            _result(rule_id="R2", result="pass", why_failed=None),
        ],
    )


def _summary_compliant_false_critical() -> EvaluationSummary:
    """One critical rule failed → compliant=False, critical_failures non-empty."""
    crit = _result(rule_id="R_CRITICAL", severity="critical", result="fail")
    return EvaluationSummary(
        total_rules=1,
        failed=1,
        results=[crit],
        critical_failures=[crit],
    )


def _summary_compliant_false_warning_only() -> EvaluationSummary:
    """One warning-severity rule failed → compliant=False, no critical_failures."""
    warn = _result(rule_id="R_WARN", severity="warning", result="fail")
    return EvaluationSummary(
        total_rules=1,
        failed=1,
        results=[warn],
        critical_failures=[],
    )


def _summary_warning_failure_with_classification_gap() -> EvaluationSummary:
    """A warning failed, but FTL classification still has no verdict."""
    warn = _result(rule_id="R_WARN", severity="warning", result="fail")
    return EvaluationSummary(
        total_rules=1,
        failed=1,
        results=[warn],
        critical_failures=[],
        no_verdict_reason="ftl_classification_missing",
    )


def _summary_no_verdict(reason: str) -> EvaluationSummary:
    """Build each supported no-verdict shape with a literal expected reason."""
    if reason == "no_rules_loaded":
        return EvaluationSummary(total_rules=0, no_verdict_reason=reason)
    if reason == "ftl_classification_missing":
        return EvaluationSummary(total_rules=1, no_verdict_reason=reason)
    if reason == "not_ftl_scoped":
        return EvaluationSummary(
            total_rules=3,
            not_ftl_scoped=3,
            no_verdict_reason=reason,
            results=[_result(rule_id=f"R{i}", result="not_ftl_scoped") for i in range(3)],
        )
    if reason == "all_rules_skipped":
        return EvaluationSummary(
            total_rules=2,
            skipped=2,
            results=[_result(rule_id=f"R{i}", result="skip") for i in range(2)],
        )
    if reason == "nothing_evaluated":
        return EvaluationSummary(total_rules=0)
    raise AssertionError(f"unsupported test reason: {reason}")


_NO_VERDICT_REASONS = (
    "no_rules_loaded",
    "ftl_classification_missing",
    "not_ftl_scoped",
    "all_rules_skipped",
    "nothing_evaluated",
)

_NO_VERDICT_RESPONSE_CODES = {
    "ftl_classification_missing": "rules_no_verdict",
    "not_ftl_scoped": "rules_no_verdict",
    "no_rules_loaded": "rules_unavailable",
    "all_rules_skipped": "rules_unavailable",
    "nothing_evaluated": "rules_unavailable",
}


# ---------------------------------------------------------------------------
# current_mode()
# ---------------------------------------------------------------------------


class TestCurrentMode:
    def test_default_is_off(self, monkeypatch):
        monkeypatch.delenv("RULES_ENGINE_ENFORCE", raising=False)
        assert current_mode() == EnforcementMode.OFF

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("off", EnforcementMode.OFF),
            ("OFF", EnforcementMode.OFF),
            ("  off  ", EnforcementMode.OFF),
            ("cte_only", EnforcementMode.CTE_ONLY),
            ("CTE_ONLY", EnforcementMode.CTE_ONLY),
            ("all", EnforcementMode.ALL),
            ("ALL", EnforcementMode.ALL),
        ],
    )
    def test_valid_values_parsed(self, monkeypatch, value, expected):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", value)
        assert current_mode() == expected

    @pytest.mark.parametrize("bad", ["on", "yes", "true", "1", "strict", "cte-only"])
    def test_unknown_values_fail_closed_to_all(self, monkeypatch, bad):
        """A PRESENT but unrecognized value means the operator intended
        enforcement — silently reverting to ``off`` on a typo disables the
        compliance gate while everyone believes it is on (#2662 shape).
        Fail closed to the strictest mode instead."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", bad)
        assert current_mode() == EnforcementMode.ALL

    def test_unknown_value_logs_error_once_per_value(self, monkeypatch, caplog):
        import logging

        from shared.rules import enforcement as enf

        monkeypatch.setattr(enf, "_reported_invalid_modes", set())
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "definitely-bogus")
        with caplog.at_level(logging.ERROR):
            assert current_mode() == EnforcementMode.ALL
            assert current_mode() == EnforcementMode.ALL
        errors = [r for r in caplog.records if "rules_enforce_invalid_value" in r.getMessage()]
        assert len(errors) == 1

    def test_empty_value_means_off(self, monkeypatch):
        """Empty string is 'unset-ish' (RULES_ENGINE_ENFORCE= in an env
        file), not a typo'd enforcement request — stays off."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "")
        assert current_mode() == EnforcementMode.OFF

    def test_reads_env_on_each_call_not_cached(self, monkeypatch):
        """Operator flipping the flag at runtime takes effect immediately."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
        assert current_mode() == EnforcementMode.OFF
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")
        assert current_mode() == EnforcementMode.ALL


# ---------------------------------------------------------------------------
# should_reject() — OFF mode
# ---------------------------------------------------------------------------


class TestShouldRejectOff:
    """In OFF mode, never reject — matches current prod behavior."""

    @pytest.fixture(autouse=True)
    def _off(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")

    @pytest.mark.parametrize(
        "summary_factory",
        [_summary_compliant_true, _summary_compliant_false_critical, _summary_compliant_false_warning_only],
    )
    def test_never_rejects(self, summary_factory):
        reject, reason = should_reject(summary_factory())
        assert reject is False
        assert reason is None

    @pytest.mark.parametrize("no_verdict_reason", _NO_VERDICT_REASONS)
    def test_no_verdict_stays_advisory(self, no_verdict_reason):
        reject, reason = should_reject(_summary_no_verdict(no_verdict_reason))
        assert reject is False
        assert reason is None


# ---------------------------------------------------------------------------
# should_reject() — CTE_ONLY mode
# ---------------------------------------------------------------------------


class TestShouldRejectCteOnly:
    """CTE_ONLY rejects critical failures and every no-verdict outcome."""

    @pytest.fixture(autouse=True)
    def _cte_only(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")

    def test_rejects_on_critical_failure(self):
        reject, reason = should_reject(_summary_compliant_false_critical())
        assert reject is True
        assert "R_CRITICAL" in reason
        assert "missing_kde" in reason

    def test_accepts_when_only_warnings_failed(self):
        """Warning-severity failures don't populate critical_failures."""
        reject, reason = should_reject(_summary_compliant_false_warning_only())
        assert reject is False
        assert reason is None

    def test_warning_failure_cannot_hide_classification_gap(self):
        summary = _summary_warning_failure_with_classification_gap()

        assert summary.compliant is False
        assert should_reject(summary) == (True, "ftl_classification_missing")

    def test_accepts_when_compliant(self):
        reject, _ = should_reject(_summary_compliant_true())
        assert reject is False


# ---------------------------------------------------------------------------
# should_reject() — ALL mode
# ---------------------------------------------------------------------------


class TestShouldRejectAll:
    """ALL mode rejects any compliant=False, including warning-only failures."""

    @pytest.fixture(autouse=True)
    def _all(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")

    def test_rejects_on_critical_failure(self):
        reject, reason = should_reject(_summary_compliant_false_critical())
        assert reject is True
        assert "R_CRITICAL" in reason

    def test_rejects_on_warning_only_failure(self):
        """In ALL mode, warning-severity fails ALSO reject. This is the
        difference from CTE_ONLY — the mode name is literal."""
        reject, reason = should_reject(_summary_compliant_false_warning_only())
        assert reject is True
        assert "R_WARN" in reason

    def test_accepts_when_compliant(self):
        reject, _ = should_reject(_summary_compliant_true())
        assert reject is False


@pytest.mark.parametrize("mode", [EnforcementMode.CTE_ONLY, EnforcementMode.ALL])
@pytest.mark.parametrize("no_verdict_reason", _NO_VERDICT_REASONS)
def test_active_modes_reject_every_no_verdict_reason(monkeypatch, mode, no_verdict_reason):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", mode)
    assert should_reject(_summary_no_verdict(no_verdict_reason)) == (
        True,
        no_verdict_reason,
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (EnforcementMode.OFF, (False, None)),
        (EnforcementMode.CTE_ONLY, (True, "all_rules_skipped")),
        (EnforcementMode.ALL, (True, "all_rules_skipped")),
    ],
)
def test_mixed_unevaluated_results_follow_mode(monkeypatch, mode, expected):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", mode)
    summary = EvaluationSummary(total_rules=2, skipped=1, not_ftl_scoped=1)
    assert summary.verdict_reason == "all_rules_skipped"
    assert should_reject(summary) == expected


# ---------------------------------------------------------------------------
# Reason formatting
# ---------------------------------------------------------------------------


class TestReasonFormat:
    def test_reason_includes_rule_id_and_why(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        summary = _summary_compliant_false_critical()
        _, reason = should_reject(summary)
        assert summary.critical_failures[0].rule_id in reason
        assert summary.critical_failures[0].why_failed in reason

    def test_reason_defaults_when_rule_id_missing(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        crit = RuleEvaluationResult(rule_id="", severity="critical", result="fail", why_failed=None)
        summary = EvaluationSummary(
            total_rules=1,
            failed=1,
            results=[crit],
            critical_failures=[crit],
        )
        _, reason = should_reject(summary)
        assert reason is not None
        assert "unknown_rule" in reason

    def test_errored_rule_is_a_failure(self, monkeypatch):
        """Per #1354 — error is treated as fail for compliance."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")
        err = _result(rule_id="R_ERR", severity="critical", result="error", why_failed="evaluator_crash")
        summary = EvaluationSummary(
            total_rules=1,
            errored=1,
            results=[err],
            critical_failures=[err],
        )
        reject, reason = should_reject(summary)
        assert reject is True
        assert "R_ERR" in reason
        assert "evaluator_crash" in reason


class TestRejectionCode:
    @pytest.mark.parametrize("reason,expected_code", _NO_VERDICT_RESPONSE_CODES.items())
    def test_no_verdict_reasons_have_truthful_codes(self, reason, expected_code):
        summary = _summary_no_verdict(reason)
        assert rejection_code(summary, reason) == expected_code

    def test_real_rule_failure_remains_rule_violation(self):
        summary = _summary_compliant_false_critical()
        assert rejection_code(summary, "R_CRITICAL: missing_kde") == "rule_violation"

    def test_critical_failure_evidence_remains_rule_violation_when_no_verdict_metadata_is_present(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        critical = _result(rule_id="R_CRITICAL", severity="critical", result="fail")
        summary = EvaluationSummary(
            total_rules=1,
            failed=1,
            results=[critical],
            critical_failures=[critical],
            no_verdict_reason="ftl_classification_missing",
        )
        reject, reason = should_reject(summary)
        assert reject is True
        assert reason == "R_CRITICAL: missing_kde"
        assert rejection_code(summary, reason) == "rule_violation"

    def test_classification_gap_driving_cte_only_rejection_has_truthful_code(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        summary = _summary_warning_failure_with_classification_gap()
        reject, reason = should_reject(summary)

        assert reject is True
        assert reason == "ftl_classification_missing"
        assert rejection_code(summary, reason) == "rules_no_verdict"
