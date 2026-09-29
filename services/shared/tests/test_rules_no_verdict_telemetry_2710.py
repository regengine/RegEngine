"""No-verdict enforcement behavior and legacy telemetry compatibility.

The old policy counted and warned when active enforcement accepted a
no-verdict event. Active modes now fail closed, so that legacy accept counter
must stay unchanged; ``off`` remains advisory and silent.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SHARED_DIR.parent
for _p in (_SHARED_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.rules import enforcement as enf  # noqa: E402
from shared.rules.types import EvaluationSummary  # noqa: E402


def _no_verdict_summary() -> EvaluationSummary:
    # total_rules=0 → the tri-state ``compliant`` property computes None.
    summary = EvaluationSummary(event_id="evt-1", total_rules=0)
    assert summary.compliant is None
    return summary


def _metric_value(mode: str, tenant: str) -> float:
    return enf.rules_no_verdict_accepted_total.labels(mode=mode, tenant_id=tenant)._value.get()


class TestNoVerdictEnforcement:
    def test_all_mode_rejects_without_incrementing_legacy_accept_counter(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")
        import shared.tenant_context as tc

        token = tc.set_rls_tenant_id("11111111-1111-1111-1111-111111111111")
        try:
            before = _metric_value("all", "11111111-1111-1111-1111-111111111111")
            reject, reason = enf.should_reject(_no_verdict_summary())
        finally:
            tc.reset_rls_tenant_id(token)

        assert reject is True
        assert reason == "nothing_evaluated"
        assert _metric_value("all", "11111111-1111-1111-1111-111111111111") == before

    def test_off_mode_stays_silent(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
        before = _metric_value("off", "unknown")
        reject, _ = enf.should_reject(_no_verdict_summary())
        assert reject is False
        assert _metric_value("off", "unknown") == before  # OFF is business as usual

    def test_real_verdicts_unaffected(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")
        failing = EvaluationSummary(event_id="evt-1", total_rules=1, failed=1)
        assert failing.compliant is False
        before = _metric_value("all", "unknown")
        reject, _ = enf.should_reject(failing)
        assert reject is True  # rejection path untouched
        assert _metric_value("all", "unknown") == before  # no no-verdict count
