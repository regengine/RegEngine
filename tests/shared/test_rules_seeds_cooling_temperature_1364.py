"""Regression tests for #1364 — COOLING CTE must have a temperature
threshold rule and a cooling duration presence rule.

Before this fix the COOLING CTE had only presence checks (date,
location, temperature reading). The rules engine never compared the
reported temperature against a regulatory threshold and never checked
that a cooling duration was recorded. Paired with #1110 (COOLING
allowed for wrong industries), COOLING was effectively a checkbox.

These tests lock:

1. A ``numeric_range`` seed rule exists for cooling temperature with
   the 21 CFR §1.1330(b)(5) cold-chain ceiling (5 °C / 41 °F).
2. A presence seed rule exists for ``cooling_duration`` scoped to
   the COOLING CTE.
3. Both rules cite 21 CFR §1.1330 so the FDA export pipeline can
   surface the citation alongside a failure.

We assert on rule attributes, not on the seed list ordering or count —
adding more COOLING rules is welcome.
"""

from __future__ import annotations

from typing import List

import pytest

from shared.rules.seeds import FSMA_RULE_SEEDS


def _cooling_rules() -> List[dict]:
    return [
        s for s in FSMA_RULE_SEEDS
        if "cooling" in (s.get("applicability_conditions") or {}).get("cte_types", [])
    ]


class TestCoolingTemperatureThreshold_Issue1364:
    def test_cooling_temperature_threshold_rule_exists(self):
        rules = [
            s for s in _cooling_rules()
            if s.get("evaluation_logic", {}).get("type") == "numeric_range"
            and s.get("evaluation_logic", {}).get("field", "").endswith("cooling_temperature")
        ]
        assert rules, (
            "Expected a numeric_range seed rule on kdes.cooling_temperature "
            "for the COOLING CTE — #1364"
        )
        rule = rules[0]
        params = rule["evaluation_logic"]["params"]
        assert params.get("max") is not None, "cold-chain ceiling needs a max"
        # 21 CFR §1.1330(b)(5) — FDA cold-chain ceiling is 5 °C / 41 °F.
        assert params["max"] == pytest.approx(5), (
            f"cold-chain ceiling must be 5 °C per 21 CFR §1.1330; "
            f"got max={params['max']}"
        )
        assert params.get("unit") == "celsius"

    def test_threshold_rule_cites_21_cfr_1_1330(self):
        rules = [
            s for s in _cooling_rules()
            if s.get("evaluation_logic", {}).get("type") == "numeric_range"
        ]
        assert rules, "no COOLING numeric_range rule found"
        for r in rules:
            citation = r.get("citation_reference") or ""
            assert "1.1330" in citation, (
                f"rule '{r.get('title')}' must cite 21 CFR §1.1330; "
                f"got {citation!r}"
            )

    def test_threshold_rule_is_critical(self):
        rules = [
            s for s in _cooling_rules()
            if s.get("evaluation_logic", {}).get("type") == "numeric_range"
        ]
        assert rules
        for r in rules:
            assert r.get("severity") == "critical", (
                "temperature-threshold violations must be 'critical' — "
                "they break the cold-chain compliance stamp"
            )

    def test_threshold_rule_supports_unit_field(self):
        """The rule must point at a unit KDE so Fahrenheit readings
        get converted before comparison — otherwise 80 °F would pass
        a ≤ 5 °C rule silently."""
        rules = [
            s for s in _cooling_rules()
            if s.get("evaluation_logic", {}).get("type") == "numeric_range"
        ]
        for r in rules:
            params = r["evaluation_logic"]["params"]
            assert "unit_field" in params, (
                f"rule '{r['title']}' must declare a unit_field so the "
                f"evaluator can normalize °F/°C readings (#1364)"
            )


class TestCoolingDurationPresence_Issue1364:
    def test_cooling_duration_presence_rule_exists(self):
        rules = [
            s for s in _cooling_rules()
            if s.get("evaluation_logic", {}).get("type") == "multi_field_presence"
            and any(
                f.endswith("cooling_duration")
                or f.endswith("cooling_duration_minutes")
                or f.endswith("cooling_hold_time")
                for f in (
                    s.get("evaluation_logic", {}).get("params", {}) or {}
                ).get("fields", [])
            )
        ]
        assert rules, (
            "Expected a multi_field_presence rule covering "
            "kdes.cooling_duration on the COOLING CTE — #1364"
        )
        rule = rules[0]
        assert rule.get("severity") == "critical"
        assert "1.1330" in (rule.get("citation_reference") or "")


class TestCoolingKdeFloorRaised_Issue1364:
    """Guardrail: COOLING must keep at least 4 kde_presence rules
    (date, location, temperature reading, duration) after this fix —
    regression against dropping duration alone."""

    def test_cooling_has_at_least_four_kde_presence_rules(self):
        count = sum(
            1
            for s in _cooling_rules()
            if s.get("category") == "kde_presence"
        )
        assert count >= 4, (
            f"COOLING should have \u2265 4 kde_presence seeds after #1364; "
            f"got {count}"
        )

    def test_cooling_has_threshold_category_rule(self):
        """The threshold rule lives in ``kde_threshold``, not
        ``kde_presence``, so it can be reported separately in the
        compliance dashboard."""
        count = sum(
            1
            for s in _cooling_rules()
            if s.get("category") == "kde_threshold"
        )
        assert count >= 1, (
            "COOLING must have at least one kde_threshold rule after #1364 "
            "(the cold-chain temperature gate)"
        )
