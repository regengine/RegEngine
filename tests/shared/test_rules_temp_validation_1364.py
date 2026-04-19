"""Regression tests for #1364 — COOLING CTE temperature validation.

Before: ``uom.py`` had weight-only conversions (no C↔F), and the COOLING
seed rule ``Cooling: Temperature Reading Required`` only checked that
*some* temperature field was present. A tenant could record
``kdes.cooling_temperature = 72`` (i.e. room-temperature °F) and the
rule engine would stamp the event compliant — exactly the opposite of
what 21 CFR §1.1330(b)(5) calls for.

After:
- ``shared.rules.uom`` exposes ``fahrenheit_to_celsius``,
  ``celsius_to_fahrenheit``, ``normalize_temperature``, and
  ``resolve_temperature_reading`` (pulls the right field out of a KDE
  dict and returns a canonical °C reading).
- ``shared.rules.evaluators.stateless`` adds ``evaluate_numeric_range``
  registered as ``"numeric_range"`` in ``EVALUATORS``. Missing values
  fail (not skip) so blank fields don't fail-open.
- ``shared.rules.seeds.FSMA_RULE_SEEDS`` adds two rules for COOLING:
  - ``Cooling: Temperature Within Cold-Chain Window`` — numeric_range
    0–5 °C, °F readings normalized before comparison.
  - ``Cooling: Duration Required`` — presence of cooling duration /
    start time, so FDA can reconstruct the temperature-time combination.

Pure-Python; no DB, no live evaluator machinery beyond the bits under
test.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest


# Ensure ``services/shared`` is on sys.path under the "shared" namespace so
# ``from shared.rules...`` works when tests are run from the repo root.
_ROOT = Path(__file__).resolve().parents[2]
_SHARED = _ROOT / "services" / "shared"
for p in (_ROOT, _SHARED):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


from shared.rules import uom  # noqa: E402
from shared.rules.evaluators.stateless import EVALUATORS, evaluate_numeric_range  # noqa: E402
from shared.rules.seeds import FSMA_RULE_SEEDS  # noqa: E402
from shared.rules.types import RuleDefinition  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(**overrides) -> RuleDefinition:
    """Factory — returns a rule with a ``numeric_range`` evaluation by default."""
    defaults = dict(
        rule_id="test-rule-1364",
        rule_version=1,
        title="Cooling: Temperature Within Cold-Chain Window",
        description="unit-test fixture",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["cooling"], "ftl_scope": ["ALL"]},
        citation_reference="21 CFR §1.1330(b)(5)",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={
            "type": "numeric_range",
            "params": {
                "source": "temperature",
                "root": "kdes",
                "min": 0.0,
                "max": 5.0,
                "unit": "C",
            },
        },
        failure_reason_template=(
            "Cooling temperature {value} {unit} is outside [{min}, {max}] {unit} ({citation})"
        ),
        remediation_suggestion="Re-cool to 0–5 °C",
    )
    defaults.update(overrides)
    return RuleDefinition(**defaults)


def _cooling_event(**kde_overrides) -> dict:
    kdes: dict = {}
    kdes.update(kde_overrides)
    return {
        "event_id": "evt-cooling-1",
        "event_type": "cooling",
        "kdes": kdes,
    }


# ===========================================================================
# uom.py temperature conversion
# ===========================================================================


class TestTemperatureConversion_Issue1364:
    def test_fahrenheit_to_celsius_known_values(self):
        # Water freezing.
        assert uom.fahrenheit_to_celsius(32) == pytest.approx(0.0)
        # Water boiling at sea level.
        assert uom.fahrenheit_to_celsius(212) == pytest.approx(100.0, abs=1e-6)
        # FDA cold-chain ceiling.
        assert uom.fahrenheit_to_celsius(41) == pytest.approx(5.0, abs=1e-6)
        # Room temperature.
        assert uom.fahrenheit_to_celsius(72) == pytest.approx(22.222, abs=1e-3)

    def test_celsius_to_fahrenheit_known_values(self):
        assert uom.celsius_to_fahrenheit(0) == pytest.approx(32.0)
        assert uom.celsius_to_fahrenheit(100) == pytest.approx(212.0, abs=1e-6)
        assert uom.celsius_to_fahrenheit(5) == pytest.approx(41.0, abs=1e-6)
        assert uom.celsius_to_fahrenheit(-40) == pytest.approx(-40.0, abs=1e-6)

    def test_round_trip_f_to_c_to_f(self):
        """Any °F reading passed through both conversions must come back unchanged."""
        for f in (-40.0, 0.0, 32.0, 41.0, 72.0, 212.0):
            out = uom.celsius_to_fahrenheit(uom.fahrenheit_to_celsius(f))
            assert out == pytest.approx(f, abs=1e-6), f"round-trip failed for {f}°F"

    def test_normalize_temperature_same_unit_pass_through(self):
        assert uom.normalize_temperature(41, "F", "F") == pytest.approx(41.0)
        assert uom.normalize_temperature(5, "C", "C") == pytest.approx(5.0)

    def test_normalize_temperature_cross_unit(self):
        # 41°F → 5°C
        assert uom.normalize_temperature(41, "F", "C") == pytest.approx(5.0, abs=1e-6)
        # 5°C → 41°F
        assert uom.normalize_temperature(5, "C", "F") == pytest.approx(41.0, abs=1e-6)

    def test_normalize_temperature_accepts_aliases(self):
        """Operator-friendly unit labels must all normalize."""
        for label in ("F", "°F", "fahrenheit", "degF", "deg_F", "degrees_Fahrenheit"):
            assert uom.normalize_temperature(32, label, "C") == pytest.approx(0.0, abs=1e-6), (
                f"unit label {label!r} did not normalize"
            )
        for label in ("C", "°C", "celsius", "centigrade", "degC"):
            assert uom.normalize_temperature(0, label, "F") == pytest.approx(32.0, abs=1e-6)

    def test_normalize_temperature_unknown_unit_returns_none(self):
        assert uom.normalize_temperature(5, "kelvin", "C") is None
        assert uom.normalize_temperature(5, "C", "kelvin") is None


# ===========================================================================
# resolve_temperature_reading — KDE dict interpretation
# ===========================================================================


class TestResolveTemperatureReading_Issue1364:
    def test_explicit_celsius_field_wins(self):
        got = uom.resolve_temperature_reading({"temperature_celsius": 3.5})
        assert got is not None
        value_c, source = got
        assert value_c == pytest.approx(3.5)
        assert source == "temperature_celsius"

    def test_explicit_fahrenheit_field_normalizes(self):
        got = uom.resolve_temperature_reading({"temperature_fahrenheit": 41})
        assert got is not None
        value_c, source = got
        assert value_c == pytest.approx(5.0, abs=1e-6)
        assert source == "temperature_fahrenheit"

    def test_cooling_specific_fields_preferred_over_generic(self):
        """When both ``cooling_temperature_celsius`` and ``temperature_celsius`` are
        present, the cooling-specific field must win — it's the one FDA asks for."""
        got = uom.resolve_temperature_reading({
            "cooling_temperature_celsius": 2.0,
            "temperature_celsius": 25.0,  # ambient, irrelevant
        })
        assert got is not None
        value_c, source = got
        assert value_c == pytest.approx(2.0)
        assert source == "cooling_temperature_celsius"

    def test_generic_temperature_with_unit(self):
        got = uom.resolve_temperature_reading({"temperature": 41, "temperature_unit": "F"})
        assert got is not None
        value_c, source = got
        assert value_c == pytest.approx(5.0, abs=1e-6)
        assert source == "temperature"

    def test_generic_temperature_no_unit_defaults_to_fahrenheit(self):
        """US produce/seafood convention — operators entering a bare number
        almost always mean °F. Document the policy and hold it here."""
        got = uom.resolve_temperature_reading({"temperature": 41})
        assert got is not None
        value_c, source = got
        assert value_c == pytest.approx(5.0, abs=1e-6)
        assert source == "temperature"

    def test_no_temperature_field_returns_none(self):
        assert uom.resolve_temperature_reading({}) is None
        assert uom.resolve_temperature_reading({"unrelated": 42}) is None

    def test_non_numeric_value_skipped(self):
        """A string that can't coerce should be treated as 'no reading'."""
        got = uom.resolve_temperature_reading({"temperature_celsius": "not a number"})
        assert got is None


# ===========================================================================
# numeric_range evaluator
# ===========================================================================


class TestNumericRangeEvaluator_Issue1364:
    def test_registered_in_evaluators_dispatch(self):
        """Dispatch must carry the key; without it, seeded rules silently skip."""
        assert "numeric_range" in EVALUATORS
        assert EVALUATORS["numeric_range"] is evaluate_numeric_range

    def test_temperature_within_range_passes(self):
        rule = _make_rule()
        event = _cooling_event(cooling_temperature_celsius=3.0)
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "pass", res.why_failed
        assert res.evidence_fields_inspected[0]["value"] == pytest.approx(3.0)

    def test_temperature_at_range_boundary_passes(self):
        """Boundaries are inclusive — exactly 5.0°C must pass, not fail-by-one."""
        rule = _make_rule()
        for boundary in (0.0, 5.0):
            event = _cooling_event(cooling_temperature_celsius=boundary)
            res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
            assert res.result == "pass", (
                f"boundary {boundary}°C must be inclusive: got {res.result}"
            )

    def test_temperature_above_max_fails(self):
        rule = _make_rule()
        event = _cooling_event(cooling_temperature_celsius=22.0)
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "fail"
        assert "above maximum" in res.why_failed or "outside" in res.why_failed or "22" in res.why_failed

    def test_temperature_below_min_fails(self):
        rule = _make_rule()
        event = _cooling_event(cooling_temperature_celsius=-10.0)
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "fail"

    def test_fahrenheit_reading_normalized_before_comparison(self):
        """The key regression — 72°F room temp must FAIL a 0–5°C range check.
        Before #1364 the presence-only rule passed it, which is the bug."""
        rule = _make_rule()
        event = _cooling_event(cooling_temperature_fahrenheit=72.0)
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "fail", (
            "72°F (≈22°C) must fail the 0–5°C cold-chain window — fail-open "
            "regression: see #1364"
        )

    def test_fahrenheit_reading_in_range_passes(self):
        """41°F = 5°C exactly — must pass as boundary."""
        rule = _make_rule()
        event = _cooling_event(cooling_temperature_fahrenheit=41.0)
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "pass"

    def test_missing_temperature_fails_not_skips(self):
        """Blank field MUST fail, not skip. Skipping is the fail-open mode
        that caused the original issue (rule stamped compliant by absence)."""
        rule = _make_rule()
        event = _cooling_event()  # no temperature at all
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "fail"

    def test_non_numeric_temperature_fails(self):
        rule = _make_rule()
        event = _cooling_event(cooling_temperature_celsius="cold")
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "fail"

    def test_plain_field_mode_without_source(self):
        """``logic.field`` works without ``source: temperature`` — for
        future non-temperature ranges like duration or pH."""
        rule = _make_rule(
            evaluation_logic={
                "type": "numeric_range",
                "field": "kdes.ph",
                "params": {"min": 6.0, "max": 8.0},
            }
        )
        event = _cooling_event(ph=7.0)
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "pass"
        event2 = _cooling_event(ph=4.5)
        res2 = evaluate_numeric_range(event2, rule.evaluation_logic, rule)
        assert res2.result == "fail"

    def test_bool_rejected_as_non_numeric(self):
        """``True``/``False`` is a bool, not a temperature. Must not silently
        become 1.0/0.0 and pass."""
        rule = _make_rule()
        event = _cooling_event(cooling_temperature_celsius=True)
        res = evaluate_numeric_range(event, rule.evaluation_logic, rule)
        assert res.result == "fail"

    def test_range_only_min(self):
        """Lower bound without upper bound still works."""
        rule = _make_rule(
            evaluation_logic={
                "type": "numeric_range",
                "field": "kdes.cooling_duration_hours",
                "params": {"min": 0.0},
            },
            failure_reason_template="{field_name} = {value} below min {min}",
        )
        res = evaluate_numeric_range(
            _cooling_event(cooling_duration_hours=1.5),
            rule.evaluation_logic,
            rule,
        )
        assert res.result == "pass"
        res2 = evaluate_numeric_range(
            _cooling_event(cooling_duration_hours=-1.0),
            rule.evaluation_logic,
            rule,
        )
        assert res2.result == "fail"


# ===========================================================================
# Seed rules — new COOLING rules are present & well-formed
# ===========================================================================


class TestCoolingSeedRules_Issue1364:
    def _cooling_seeds(self):
        return [
            s
            for s in FSMA_RULE_SEEDS
            if "cooling" in (s.get("applicability_conditions") or {}).get("cte_types", [])
        ]

    def test_cooling_temperature_numeric_range_rule_exists(self):
        seeds = self._cooling_seeds()
        range_rules = [
            s for s in seeds
            if s["evaluation_logic"].get("type") == "numeric_range"
        ]
        assert len(range_rules) >= 1, (
            "COOLING CTE must have at least one numeric_range rule validating "
            "the temperature is in the cold-chain window — #1364"
        )

    def test_cooling_temperature_numeric_range_rule_is_severe_and_cites_1330(self):
        seeds = self._cooling_seeds()
        numeric = [
            s for s in seeds
            if s["evaluation_logic"].get("type") == "numeric_range"
        ][0]
        assert numeric["severity"] == "critical", (
            "Out-of-range cooling temperature is a compliance failure, not a "
            "warning — this is the crux of #1364."
        )
        assert "1.1330" in (numeric.get("citation_reference") or ""), (
            "Cold-chain range rule must cite 21 CFR §1.1330"
        )

    def test_cooling_temperature_range_bounds_match_fda_cold_chain(self):
        seeds = self._cooling_seeds()
        numeric = [
            s for s in seeds
            if s["evaluation_logic"].get("type") == "numeric_range"
        ][0]
        params = numeric["evaluation_logic"]["params"]
        assert params.get("source") == "temperature"
        assert params.get("root") == "kdes"
        # 0–5°C = 32–41°F — FDA / HACCP cold-chain window.
        assert params.get("min") == pytest.approx(0.0)
        assert params.get("max") == pytest.approx(5.0)
        assert (params.get("unit") or "").upper() == "C"

    def test_cooling_duration_presence_rule_exists(self):
        seeds = self._cooling_seeds()
        has_duration = any(
            "duration" in s["title"].lower()
            for s in seeds
        )
        assert has_duration, (
            "COOLING CTE must require cooling_duration presence so the "
            "temperature-time combination can be reconstructed — #1364"
        )

    def test_cooling_duration_rule_cites_1330(self):
        seeds = self._cooling_seeds()
        duration_rule = next(
            s for s in seeds if "duration" in s["title"].lower()
        )
        assert "1.1330" in (duration_rule.get("citation_reference") or "")
        assert duration_rule["severity"] == "critical"


# ===========================================================================
# End-to-end wiring — seeded rule fires on out-of-range real-world payload
# ===========================================================================


class TestCoolingRuleEndToEnd_Issue1364:
    def _seed_to_rule(self, seed: dict) -> RuleDefinition:
        """Materialize a dict-shaped seed into a RuleDefinition for evaluator
        consumption. Mirrors what ``seed_fsma_rules`` does in production."""
        return RuleDefinition(
            rule_id=f"seed-{seed['title'][:40]}",
            rule_version=1,
            title=seed["title"],
            description=seed.get("description"),
            severity=seed["severity"],
            category=seed["category"],
            applicability_conditions=seed["applicability_conditions"],
            citation_reference=seed.get("citation_reference"),
            effective_date=date(2026, 1, 1),
            retired_date=None,
            evaluation_logic=seed["evaluation_logic"],
            failure_reason_template=seed["failure_reason_template"],
            remediation_suggestion=seed.get("remediation_suggestion"),
        )

    def _numeric_cooling_seed(self) -> dict:
        cooling_seeds = [
            s
            for s in FSMA_RULE_SEEDS
            if "cooling" in (s.get("applicability_conditions") or {}).get("cte_types", [])
            and s["evaluation_logic"].get("type") == "numeric_range"
        ]
        assert cooling_seeds, "no numeric_range cooling seed found"
        return cooling_seeds[0]

    def test_seeded_rule_fires_on_room_temp_fahrenheit(self):
        """The regression: operator records 72°F cooling temp (room temp),
        the old presence-only rule passed it. Now the range rule must fail."""
        rule = self._seed_to_rule(self._numeric_cooling_seed())
        event = {
            "event_id": "evt-1",
            "event_type": "cooling",
            "kdes": {"cooling_temperature_fahrenheit": 72.0},
        }
        res = EVALUATORS["numeric_range"](event, rule.evaluation_logic, rule)
        assert res.result == "fail"
        assert res.severity == "critical"

    def test_seeded_rule_passes_on_in_range_celsius(self):
        rule = self._seed_to_rule(self._numeric_cooling_seed())
        event = {
            "event_id": "evt-1",
            "event_type": "cooling",
            "kdes": {"cooling_temperature_celsius": 3.5},
        }
        res = EVALUATORS["numeric_range"](event, rule.evaluation_logic, rule)
        assert res.result == "pass"

    def test_seeded_rule_passes_on_41f_boundary(self):
        """41°F is the FDA ceiling — must be inclusive, not off-by-one."""
        rule = self._seed_to_rule(self._numeric_cooling_seed())
        event = {
            "event_id": "evt-1",
            "event_type": "cooling",
            "kdes": {"cooling_temperature_fahrenheit": 41.0},
        }
        res = EVALUATORS["numeric_range"](event, rule.evaluation_logic, rule)
        assert res.result == "pass"
