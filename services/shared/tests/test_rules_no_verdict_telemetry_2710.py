"""#2710: no-verdict accepts under an enforcement mode are counted + warned.

Decision (b) from the enforcement-GA issue: the accept contract stays
(#1346/#1347 — blocking on non-evaluation would break unseeded tenants),
but under ``cte_only``/``all`` each no-verdict accept increments
``rules_no_verdict_accepted_total{mode, tenant_id}`` and warns once per
(tenant, mode) per process.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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


@pytest.fixture(autouse=True)
def _reset_warned_set():
    enf._no_verdict_warned.clear()
    yield
    enf._no_verdict_warned.clear()


def _metric_value(mode: str, tenant: str) -> float:
    return enf.rules_no_verdict_accepted_total.labels(mode=mode, tenant_id=tenant)._value.get()


class TestNoVerdictTelemetry:
    def test_all_mode_counts_and_accepts(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")
        import shared.tenant_context as tc

        token = tc.set_rls_tenant_id("11111111-1111-1111-1111-111111111111")
        try:
            before = _metric_value("all", "11111111-1111-1111-1111-111111111111")
            reject, reason = enf.should_reject(_no_verdict_summary())
        finally:
            tc.reset_rls_tenant_id(token)

        assert reject is False and reason is None  # contract unchanged
        assert _metric_value("all", "11111111-1111-1111-1111-111111111111") == before + 1

    def test_warning_once_per_tenant_and_mode(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        import logging as _logging

        fake_logger = MagicMock()
        monkeypatch.setattr(_logging, "getLogger", lambda name=None: fake_logger)

        enf.should_reject(_no_verdict_summary())
        enf.should_reject(_no_verdict_summary())

        warns = [c for c in fake_logger.warning.call_args_list if "rules_no_verdict_accepted" in c.args[0]]
        assert len(warns) == 1  # second accept counts but does not re-warn

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
