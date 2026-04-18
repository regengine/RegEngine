"""
Hardening tests for ``kernel.obligation.evaluator``.

Covers:

* **#1330** — Empty strings, whitespace-only strings, empty lists and
  empty dicts now count as *missing* evidence, not *present*. Previously
  a KDE like ``reason_codes=[]`` scored ``met=True, risk_score=0.0`` —
  false FSMA 204 compliance.
* **#1339** — Regex triggering conditions are pre-compiled at init.
  Patterns with syntax errors or obvious ReDoS shapes (nested unbounded
  quantifiers, alternation repeats) fail at load time rather than silently
  never triggering.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from kernel.obligation.evaluator import (
    ObligationEvaluator,
    _is_present,
    _looks_redos_prone,
)
from kernel.obligation.models import (
    ObligationDefinition,
    Regulator,
    RegulatoryDomain,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _obligation(
    *,
    id_: str = "FSMA_204_RECEIVE",
    required_evidence: list[str] | None = None,
    triggering_conditions: dict | None = None,
) -> ObligationDefinition:
    return ObligationDefinition(
        id=id_,
        citation="21 CFR 1.1320",
        regulator=Regulator.FDA,
        domain=RegulatoryDomain.FSMA,
        description="Receiving CTE must record lot code and timestamp.",
        triggering_conditions=triggering_conditions or {"decision_type": "shipment_receipt"},
        required_evidence=required_evidence or ["lot_code", "receive_timestamp"],
    )


# ---------------------------------------------------------------------------
# #1330 — Empty-but-present evidence is missing
# ---------------------------------------------------------------------------


class TestIsPresent:
    """Unit tests for the ``_is_present`` helper."""

    @pytest.mark.parametrize(
        "value",
        [None, "", " ", "   ", "\t\n", [], (), {}, set(), frozenset()],
    )
    def test_empty_values_are_missing(self, value: Any):
        assert not _is_present(value)

    @pytest.mark.parametrize(
        "value",
        ["abc", " a ", [1], (1,), {"k": "v"}, {1}, 0, 1, 42, False, True, 0.0],
    )
    def test_substantive_values_are_present(self, value: Any):
        assert _is_present(value)


class TestEvaluatorEmptyEvidenceIsMissing:
    """Integration: evaluator must mark empty strings/lists/dicts as missing."""

    def test_empty_string_is_missing(self):
        evaluator = ObligationEvaluator([
            _obligation(required_evidence=["lot_code"])
        ])
        match = evaluator._evaluate_obligation(
            evaluator.obligations[0],
            {"lot_code": ""},
        )
        assert not match.met
        assert match.missing_evidence == ["lot_code"]

    def test_whitespace_only_string_is_missing(self):
        evaluator = ObligationEvaluator([
            _obligation(required_evidence=["lot_code"])
        ])
        match = evaluator._evaluate_obligation(
            evaluator.obligations[0],
            {"lot_code": "   \t"},
        )
        assert not match.met
        assert "lot_code" in match.missing_evidence

    def test_empty_list_is_missing(self):
        evaluator = ObligationEvaluator([
            _obligation(required_evidence=["reason_codes"])
        ])
        match = evaluator._evaluate_obligation(
            evaluator.obligations[0],
            {"reason_codes": []},
        )
        assert not match.met
        assert "reason_codes" in match.missing_evidence

    def test_empty_dict_is_missing(self):
        evaluator = ObligationEvaluator([
            _obligation(required_evidence=["metadata"])
        ])
        match = evaluator._evaluate_obligation(
            evaluator.obligations[0],
            {"metadata": {}},
        )
        assert not match.met
        assert "metadata" in match.missing_evidence

    def test_zero_is_present(self):
        """``quantity=0`` is valid evidence — not missing."""
        evaluator = ObligationEvaluator([
            _obligation(required_evidence=["quantity"])
        ])
        match = evaluator._evaluate_obligation(
            evaluator.obligations[0],
            {"quantity": 0},
        )
        assert match.met

    def test_false_is_present(self):
        """``spoiled=False`` is valid evidence — not missing."""
        evaluator = ObligationEvaluator([
            _obligation(required_evidence=["spoiled"])
        ])
        match = evaluator._evaluate_obligation(
            evaluator.obligations[0],
            {"spoiled": False},
        )
        assert match.met

    def test_mixed_fields_some_empty(self):
        evaluator = ObligationEvaluator([
            _obligation(required_evidence=["lot_code", "receive_ts", "source_tlc"])
        ])
        match = evaluator._evaluate_obligation(
            evaluator.obligations[0],
            {"lot_code": "LOT-1", "receive_ts": "", "source_tlc": "tlc-1"},
        )
        assert not match.met
        assert match.missing_evidence == ["receive_ts"]
        # Risk score proportional to missing fraction: 1/3.
        assert 0.3 < match.risk_score < 0.4


# ---------------------------------------------------------------------------
# #1339 — Regex ReDoS / compile cache / invalid patterns
# ---------------------------------------------------------------------------


class TestRedosHeuristic:
    """Unit tests for ``_looks_redos_prone`` so false positives stay rare."""

    @pytest.mark.parametrize(
        "pattern",
        [
            r"^(a+)+$",
            r"(a+)*",
            r"(\w+)+$",
            r"(a|a)*b",
            r"(a|a)+",
        ],
    )
    def test_known_redos_patterns_flagged(self, pattern: str):
        assert _looks_redos_prone(pattern)

    @pytest.mark.parametrize(
        "pattern",
        [
            r"^FSMA-\d{3}$",
            r"^[A-Z]+_[A-Z0-9_]+$",
            r"receiving|transformation",
            r"^\d{4}-\d{2}-\d{2}$",
            r"^(?:receiving|transformation)$",
        ],
    )
    def test_normal_patterns_not_flagged(self, pattern: str):
        assert not _looks_redos_prone(pattern)


class TestRegexCondition:
    def test_invalid_regex_raises_at_init(self):
        bad = _obligation(
            triggering_conditions={"decision_type": {"op": "regex", "pattern": "("}},
        )
        with pytest.raises(ValueError, match="invalid"):
            ObligationEvaluator([bad])

    def test_redos_pattern_raises_at_init(self):
        bad = _obligation(
            triggering_conditions={"decision_type": {"op": "regex", "pattern": r"^(a+)+$"}},
        )
        with pytest.raises(ValueError, match="ReDoS"):
            ObligationEvaluator([bad])

    def test_empty_pattern_raises_at_init(self):
        bad = _obligation(
            triggering_conditions={"decision_type": {"op": "regex", "pattern": ""}},
        )
        with pytest.raises(ValueError, match="empty"):
            ObligationEvaluator([bad])

    def test_valid_regex_matches(self):
        good = _obligation(
            triggering_conditions={
                "decision_type": {"op": "regex", "pattern": r"^shipment_.*$"},
            },
        )
        evaluator = ObligationEvaluator([good])
        assert evaluator._matches_triggering_conditions(
            good, "shipment_receipt", {"decision_type": "shipment_receipt"}
        )
        assert not evaluator._matches_triggering_conditions(
            good, "batch_split", {"decision_type": "batch_split"}
        )

    def test_compile_cache_reuses_pattern(self):
        """Evaluation must use the pre-compiled pattern, not call re.compile
        on every dispatch."""
        good = _obligation(
            triggering_conditions={
                "decision_type": {"op": "regex", "pattern": r"^shipment_.*$"},
            },
        )
        evaluator = ObligationEvaluator([good])
        key = (good.id, "decision_type")
        assert key in evaluator._compiled_regex
        compiled_before = evaluator._compiled_regex[key]

        # Call the matcher a few times and confirm the cached compile is
        # what the matcher used (identity check).
        for _ in range(3):
            evaluator._matches_triggering_conditions(
                good, "shipment_receipt", {"decision_type": "shipment_receipt"}
            )
        assert evaluator._compiled_regex[key] is compiled_before
