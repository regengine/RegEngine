"""Unit tests for ``services.shared.rules.enforcement``.

Covers every combination of:
  - RULES_ENGINE_ENFORCE value (off | cte_only | all | unknown | unset | mixed case)
  - EvaluationSummary verdict (compliant=True | False | None)
  - critical_failures present vs empty

The central invariant: ``compliant is None`` is NEVER a reject, in any
mode. Blocking an event on non-evaluation would silently break ingestion
for tenants without seeded rules and for non-FTL products.
"""
from __future__ import annotations

import pytest

from services.shared.rules.enforcement import (
    EnforcementMode,
    current_mode,
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


def _summary_no_verdict_empty_rules() -> EvaluationSummary:
    """No rules loaded → compliant=None."""
    return EvaluationSummary(total_rules=0, no_verdict_reason="no_rules_loaded")


def _summary_no_verdict_not_ftl() -> EvaluationSummary:
    """Non-FTL product → compliant=None even with passing rules."""
    return EvaluationSummary(
        total_rules=3,
        not_ftl_scoped=3,
        no_verdict_reason="not_ftl_scoped",
        results=[_result(rule_id=f"R{i}", result="not_ftl_scoped") for i in range(3)],
    )


# ---------------------------------------------------------------------------
# current_mode()
# ---------------------------------------------------------------------------

class TestCurrentMode:
    def test_default_is_off(self, monkeypatch):
        monkeypatch.delenv("RULES_ENGINE_ENFORCE", raising=False)
        assert current_mode() == EnforcementMode.OFF

    @pytest.mark.parametrize("value,expected", [
        ("off", EnforcementMode.OFF),
        ("OFF", EnforcementMode.OFF),
        ("  off  ", EnforcementMode.OFF),
        ("cte_only", EnforcementMode.CTE_ONLY),
        ("CTE_ONLY", EnforcementMode.CTE_ONLY),
        ("all", EnforcementMode.ALL),
        ("ALL", EnforcementMode.ALL),
    ])
    def test_valid_values_parsed(self, monkeypatch, value, expected):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", value)
        assert current_mode() == expected

    @pytest.mark.parametrize("bad", ["on", "yes", "true", "1", "strict", ""])
    def test_unknown_values_fall_back_to_off(self, monkeypatch, bad):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", bad)
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

    @pytest.mark.parametrize("summary_factory", [
        _summary_compliant_true,
        _summary_compliant_false_critical,
        _summary_compliant_false_warning_only,
        _summary_no_verdict_empty_rules,
        _summary_no_verdict_not_ftl,
    ])
    def test_never_rejects(self, summary_factory):
        reject, reason = should_reject(summary_factory())
        assert reject is False
        assert reason is None


# ---------------------------------------------------------------------------
# should_reject() — CTE_ONLY mode
# ---------------------------------------------------------------------------

class TestShouldRejectCteOnly:
    """CTE_ONLY rejects only when critical_failures is non-empty."""

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

    def test_accepts_when_compliant(self):
        reject, _ = should_reject(_summary_compliant_true())
        assert reject is False

    def test_accepts_no_verdict_empty_rules(self):
        """no_rules_loaded must never reject — would block every tenant
        without seed data."""
        reject, reason = should_reject(_summary_no_verdict_empty_rules())
        assert reject is False
        assert reason is None

    def test_accepts_no_verdict_not_ftl(self):
        """Non-FTL products must never reject — would block every
        non-FTL event even though rules don't apply."""
        reject, reason = should_reject(_summary_no_verdict_not_ftl())
        assert reject is False
        assert reason is None


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

    def test_accepts_no_verdict_empty_rules(self):
        reject, _ = should_reject(_summary_no_verdict_empty_rules())
        assert reject is False

    def test_accepts_no_verdict_not_ftl(self):
        reject, _ = should_reject(_summary_no_verdict_not_ftl())
        assert reject is False


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
