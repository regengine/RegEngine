"""Event-level compliance verdict for persisted rule evaluations.

``fsma.rule_evaluations.result`` is a raw enum (``pass`` / ``fail`` /
``warn`` / ``skip`` / ``error``) and ``fsma.traceability_events`` carries
the engine's tri-state ``evaluation_verdict`` (v121). Consumers that render
a regulator-facing status (FDA export v2 CSV/package, export summaries)
must classify from those two inputs together, never from a flattened
``passed`` boolean — that boolean is what turned evaluator crashes and
non-FTL no-verdicts into ``PASS`` before this module existed.

Status tokens (stable, greppable):

    PASS                — affirmative verdict: ≥1 pass/warn row, no fail, no
                          error, and no persisted no-verdict marker
    FAIL                — ≥1 fail row, or the persisted verdict is 'fail'
    EVALUATION_ERROR    — no fail row but ≥1 evaluator error row
    NO_VERDICT          — persisted verdict 'no_verdict' (reason attached),
                          or only skip rows were recorded
    NO_RULES_EVALUATED  — no rows and no persisted verdict
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PASS = "PASS"
FAIL = "FAIL"
EVALUATION_ERROR = "EVALUATION_ERROR"
NO_VERDICT = "NO_VERDICT"
NO_RULES_EVALUATED = "NO_RULES_EVALUATED"

_AFFIRMATIVE_RESULTS = frozenset({"pass", "warn"})


@dataclass
class EventVerdict:
    status: str
    reason: Optional[str] = None
    failed: List[Dict[str, Any]] = field(default_factory=list)
    errored: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def status_label(self) -> str:
        """``NO_VERDICT:not_ftl_scoped`` style label for CSV cells."""
        if self.status == NO_VERDICT and self.reason:
            return f"{NO_VERDICT}:{self.reason}"
        return self.status


def rule_result_token(rule_result: Dict[str, Any]) -> str:
    """Return the raw result enum for one persisted rule row.

    Prefers the ``result`` key. Falls back to the legacy ``passed`` boolean
    for callers/tests that pre-date the raw enum, mapping ``False`` to
    ``fail`` (fail-closed) and ``True`` to ``pass``.
    """
    raw = rule_result.get("result")
    if isinstance(raw, str) and raw:
        return raw.lower()
    return "pass" if rule_result.get("passed") else "fail"


def classify_event_verdict(
    rule_results: Optional[List[Dict[str, Any]]],
    *,
    evaluation_verdict: Optional[str] = None,
    no_verdict_reason: Optional[str] = None,
) -> EventVerdict:
    rows = rule_results or []
    failed = [r for r in rows if rule_result_token(r) == "fail"]
    errored = [r for r in rows if rule_result_token(r) == "error"]

    # Row-level evidence of failure always wins.
    if failed:
        return EventVerdict(FAIL, failed=failed, errored=errored)
    if errored:
        return EventVerdict(EVALUATION_ERROR, errored=errored)

    verdict = (evaluation_verdict or "").lower() or None
    if verdict == "fail":
        # Engine recorded a failure but no fail/error row survived
        # (e.g. rows dead-lettered). Never upgrade to PASS.
        return EventVerdict(FAIL, reason="persisted_verdict_fail")
    if verdict == "no_verdict":
        return EventVerdict(NO_VERDICT, reason=no_verdict_reason or "unspecified")

    if not rows:
        return EventVerdict(NO_RULES_EVALUATED)
    if any(rule_result_token(r) in _AFFIRMATIVE_RESULTS for r in rows):
        return EventVerdict(PASS)
    # Only skip rows — nothing was actually asserted about this event.
    return EventVerdict(NO_VERDICT, reason="all_rules_skipped")
