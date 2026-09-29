"""Matrix tests for ``shared.rules.verdict.classify_event_verdict`` and the
``EvaluationSummary.verdict`` / ``verdict_reason`` projection the engine
persists to ``fsma.traceability_events`` (v121).

The point of this module is the invariant that closes the flattening bug:
**PASS is only ever produced by an affirmative, applicable verdict.**
``error``, ``skip``-only, non-FTL no-verdict, and no-rules events each get
their own distinct token and never collapse into PASS.
"""

from __future__ import annotations

import pytest
from shared.rules import verdict as v
from shared.rules.types import EvaluationSummary, RuleEvaluationResult


def _row(result: str, name: str = "r", why: str | None = None, **extra):
    d = {"rule_name": name, "result": result, "why_failed": why}
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# rule_result_token
# ---------------------------------------------------------------------------


class TestRuleResultToken:
    @pytest.mark.parametrize("raw", ["pass", "fail", "warn", "skip", "error"])
    def test_prefers_raw_result_enum(self, raw):
        assert v.rule_result_token({"result": raw, "passed": True}) == raw

    def test_uppercase_normalised(self):
        assert v.rule_result_token({"result": "ERROR"}) == "error"

    def test_legacy_passed_true_maps_to_pass(self):
        assert v.rule_result_token({"passed": True}) == "pass"

    def test_legacy_passed_false_maps_to_fail(self):
        assert v.rule_result_token({"passed": False}) == "fail"

    def test_missing_everything_is_fail_closed(self):
        assert v.rule_result_token({}) == "fail"


# ---------------------------------------------------------------------------
# classify_event_verdict — the matrix
# ---------------------------------------------------------------------------


class TestClassifyMatrix:
    """One case per persisted shape: pass / fail / warn / skip / error /
    no-rules / non-FTL (persisted no_verdict)."""

    def test_pass_rows_are_pass(self):
        out = v.classify_event_verdict([_row("pass"), _row("pass")])
        assert out.status == v.PASS
        assert out.status_label == "PASS"
        assert out.failed == [] and out.errored == []

    def test_fail_row_is_fail_and_lists_failures(self):
        f = _row("fail", "r2", "missing KDE")
        out = v.classify_event_verdict([_row("pass"), f])
        assert out.status == v.FAIL
        assert out.failed == [f]

    def test_warn_counts_as_affirmative(self):
        assert v.classify_event_verdict([_row("warn")]).status == v.PASS

    def test_skip_only_is_no_verdict_not_pass(self):
        out = v.classify_event_verdict([_row("skip"), _row("skip")])
        assert out.status == v.NO_VERDICT
        assert out.reason == "all_rules_skipped"
        assert out.status_label == "NO_VERDICT:all_rules_skipped"

    def test_skip_alongside_pass_is_pass(self):
        assert v.classify_event_verdict([_row("skip"), _row("pass")]).status == v.PASS

    def test_error_only_is_evaluation_error_never_pass(self):
        e = _row("error", "r1", "KeyError")
        out = v.classify_event_verdict([e])
        assert out.status == v.EVALUATION_ERROR
        assert out.errored == [e]
        assert out.status != v.PASS

    def test_error_alongside_pass_is_evaluation_error(self):
        out = v.classify_event_verdict([_row("pass"), _row("error")])
        assert out.status == v.EVALUATION_ERROR

    def test_error_with_flattened_passed_true_is_still_error(self):
        """The raw enum beats a stale/flattened boolean."""
        out = v.classify_event_verdict([_row("error", passed=True)])
        assert out.status == v.EVALUATION_ERROR

    def test_fail_outranks_error(self):
        out = v.classify_event_verdict([_row("error"), _row("fail")])
        assert out.status == v.FAIL
        assert len(out.failed) == 1 and len(out.errored) == 1

    def test_no_rows_no_verdict_is_no_rules_evaluated(self):
        assert v.classify_event_verdict([]).status == v.NO_RULES_EVALUATED
        assert v.classify_event_verdict(None).status == v.NO_RULES_EVALUATED

    def test_non_ftl_meta_pass_with_persisted_no_verdict_is_no_verdict(self):
        """The bug: a non-FTL event's only rows are passing NON_FTL
        meta-rules. Per-row inspection says PASS; the engine's summary said
        no-verdict. The persisted event stamp must win."""
        out = v.classify_event_verdict(
            [_row("pass", "NON_FTL_META")],
            evaluation_verdict="no_verdict",
            no_verdict_reason="not_ftl_scoped",
        )
        assert out.status == v.NO_VERDICT
        assert out.reason == "not_ftl_scoped"
        assert out.status_label == "NO_VERDICT:not_ftl_scoped"

    def test_persisted_no_verdict_without_rows_is_no_verdict_not_no_rules(self):
        out = v.classify_event_verdict([], evaluation_verdict="no_verdict", no_verdict_reason="nothing_evaluated")
        assert out.status == v.NO_VERDICT
        assert out.reason == "nothing_evaluated"

    def test_persisted_no_verdict_without_reason_gets_placeholder(self):
        out = v.classify_event_verdict([], evaluation_verdict="no_verdict")
        assert out.status_label == "NO_VERDICT:unspecified"

    def test_persisted_fail_verdict_outranks_passing_rows(self):
        out = v.classify_event_verdict([_row("pass")], evaluation_verdict="fail")
        assert out.status == v.FAIL
        assert out.reason == "persisted_verdict_fail"

    def test_persisted_pass_verdict_does_not_override_row_evidence(self):
        """A stale 'pass' stamp cannot launder a later fail/error row."""
        assert v.classify_event_verdict([_row("fail")], evaluation_verdict="pass").status == v.FAIL
        assert v.classify_event_verdict([_row("error")], evaluation_verdict="pass").status == v.EVALUATION_ERROR

    def test_persisted_pass_verdict_with_no_rows_is_no_rules_evaluated(self):
        # Rows are the evidence; a bare stamp with nothing behind it is not
        # positively reported.
        assert v.classify_event_verdict([], evaluation_verdict="pass").status == v.NO_RULES_EVALUATED

    def test_verdict_case_insensitive(self):
        assert v.classify_event_verdict([_row("pass")], evaluation_verdict="NO_VERDICT").status == v.NO_VERDICT

    @pytest.mark.parametrize(
        "rows, verdict, expected",
        [
            ([_row("pass")], None, v.PASS),
            ([_row("warn")], None, v.PASS),
            ([_row("fail")], None, v.FAIL),
            ([_row("skip")], None, v.NO_VERDICT),
            ([_row("error")], None, v.EVALUATION_ERROR),
            ([], None, v.NO_RULES_EVALUATED),
            ([_row("pass")], "no_verdict", v.NO_VERDICT),
        ],
    )
    def test_only_affirmative_pass_yields_pass(self, rows, verdict, expected):
        out = v.classify_event_verdict(rows, evaluation_verdict=verdict, no_verdict_reason="x" if verdict else None)
        assert out.status == expected
        assert (out.status == v.PASS) == (expected == v.PASS)


# ---------------------------------------------------------------------------
# EvaluationSummary.verdict / verdict_reason (what the engine persists)
# ---------------------------------------------------------------------------


def _res(result: str, rule_id: str = "R1") -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id, rule_version=1, rule_title=rule_id, severity="critical", result=result, why_failed=None
    )


class TestSummaryVerdictProjection:
    def test_all_pass_is_pass(self):
        s = EvaluationSummary(event_id="e", total_rules=1, passed=1, results=[_res("pass")])
        assert (s.verdict, s.verdict_reason) == ("pass", None)

    def test_fail_is_fail(self):
        s = EvaluationSummary(event_id="e", total_rules=1, failed=1, results=[_res("fail")])
        assert (s.verdict, s.verdict_reason) == ("fail", None)

    def test_error_is_fail_not_pass(self):
        s = EvaluationSummary(event_id="e", total_rules=1, errored=1, results=[_res("error")])
        assert s.compliant is False
        assert s.verdict == "fail"

    def test_no_rules_is_no_verdict_nothing_evaluated(self):
        s = EvaluationSummary(event_id="e", total_rules=0)
        assert s.compliant is None
        assert (s.verdict, s.verdict_reason) == ("no_verdict", "nothing_evaluated")

    def test_no_verdict_reason_carries_through(self):
        s = EvaluationSummary(
            event_id="e", total_rules=1, passed=1, results=[_res("pass")], no_verdict_reason="not_ftl_scoped"
        )
        assert s.compliant is None
        assert (s.verdict, s.verdict_reason) == ("no_verdict", "not_ftl_scoped")

    def test_all_not_ftl_scoped_is_no_verdict(self):
        s = EvaluationSummary(event_id="e", total_rules=2, not_ftl_scoped=2)
        assert (s.verdict, s.verdict_reason) == ("no_verdict", "not_ftl_scoped")

    def test_all_skipped_is_no_verdict(self):
        s = EvaluationSummary(
            event_id="e",
            total_rules=2,
            skipped=2,
            results=[_res("skip", "R1"), _res("skip", "R2")],
        )
        assert s.compliant is None
        assert (s.verdict, s.verdict_reason) == ("no_verdict", "all_rules_skipped")

    def test_mixed_unevaluated_results_are_no_verdict(self):
        s = EvaluationSummary(
            event_id="e",
            total_rules=2,
            skipped=1,
            not_ftl_scoped=1,
            results=[_res("skip", "R1"), _res("not_ftl_scoped", "R2")],
        )
        assert s.compliant is None
        assert (s.verdict, s.verdict_reason) == ("no_verdict", "all_rules_skipped")

    @pytest.mark.parametrize("counter", ["failed", "errored"])
    def test_failure_evidence_outranks_no_verdict_metadata(self, counter):
        result = "fail" if counter == "failed" else "error"
        s = EvaluationSummary(
            event_id="e",
            total_rules=1,
            results=[_res(result, "R1")],
            no_verdict_reason="ftl_classification_missing",
            **{counter: 1},
        )
        assert (s.compliant, s.verdict, s.verdict_reason) == (False, "fail", None)

    def test_failure_evidence_is_not_masked_by_inconsistent_skip_count(self):
        s = EvaluationSummary(
            event_id="e",
            total_rules=1,
            failed=1,
            skipped=1,
            results=[_res("fail", "R1")],
        )
        assert (s.compliant, s.verdict, s.verdict_reason) == (False, "fail", None)
