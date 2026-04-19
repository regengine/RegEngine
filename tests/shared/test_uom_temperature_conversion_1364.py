"""Regression tests for #1364 — temperature conversion in ``uom.py``.

Before this fix, ``services/shared/rules/uom.py`` exposed only weight
conversions (lbs/kg/oz). The COOLING CTE rule therefore could not
compare an achieved temperature against a cold-chain threshold, because
ingestion payloads arrive in a mix of °F and °C and the rule DSL had no
way to normalize the two.

The fix adds three helpers:

* ``celsius_to_fahrenheit`` / ``fahrenheit_to_celsius`` — pure math
  conversions that reject non-numeric input (including ``True``/``False``,
  which would otherwise silently coerce to 1/0).
* ``normalize_temperature_to_celsius(value, unit)`` — returns the value
  in Celsius for any recognized unit token, or ``None`` for an
  unrecognized unit so the caller can decide how to handle the
  ambiguity.

The rules engine's ``numeric_range`` evaluator uses these helpers to
compare a reading against FDA cold-chain thresholds in a unit-agnostic
way — see ``tests/shared/test_numeric_range_evaluator_1364.py`` for the
evaluator-level tests.
"""

from __future__ import annotations

import math

import pytest

from shared.rules.uom import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    normalize_temperature_to_celsius,
)


# ---------------------------------------------------------------------------
# Known reference points — the "if someone rewrites this, it must still
# produce these exact values" lock.
# ---------------------------------------------------------------------------


class TestKnownReferencePoints_Issue1364:
    @pytest.mark.parametrize(
        "celsius, expected_f",
        [
            (0.0, 32.0),          # freezing
            (100.0, 212.0),       # boiling at sea level
            (-40.0, -40.0),       # scales cross here
            (37.0, 98.6),         # human body temp
            (5.0, 41.0),          # FDA cold-chain ceiling (21 CFR §1.1330)
            (-17.77777777777778, -0.0000000000000142),  # round-trip edge
        ],
    )
    def test_celsius_to_fahrenheit_known_points(self, celsius, expected_f):
        assert celsius_to_fahrenheit(celsius) == pytest.approx(expected_f, abs=1e-6)

    @pytest.mark.parametrize(
        "fahrenheit, expected_c",
        [
            (32.0, 0.0),
            (212.0, 100.0),
            (-40.0, -40.0),
            (98.6, 37.0),
            (41.0, 5.0),         # cold-chain ceiling expressed in °F
            (0.0, -17.7777777777),
        ],
    )
    def test_fahrenheit_to_celsius_known_points(self, fahrenheit, expected_c):
        assert fahrenheit_to_celsius(fahrenheit) == pytest.approx(expected_c, abs=1e-6)


# ---------------------------------------------------------------------------
# Round-trip property — C→F→C returns the original within tolerance.
# ---------------------------------------------------------------------------


class TestRoundTrip_Issue1364:
    @pytest.mark.parametrize("c", [-273.15, -40, 0, 4.0, 5.0, 21.0, 100.0, 400.0])
    def test_celsius_round_trip(self, c):
        assert fahrenheit_to_celsius(celsius_to_fahrenheit(c)) == pytest.approx(c, abs=1e-9)

    @pytest.mark.parametrize("f", [-459.67, -40, 0, 32.0, 41.0, 100.0, 212.0])
    def test_fahrenheit_round_trip(self, f):
        assert celsius_to_fahrenheit(fahrenheit_to_celsius(f)) == pytest.approx(f, abs=1e-9)


# ---------------------------------------------------------------------------
# Input validation — reject booleans / non-numerics so they don't
# silently coerce through the rule engine.
# ---------------------------------------------------------------------------


class TestRejectsNonNumeric_Issue1364:
    @pytest.mark.parametrize(
        "bad", [None, "5", "5.0", True, False, [], {}, object(), b"5"]
    )
    def test_celsius_to_fahrenheit_rejects_non_numeric(self, bad):
        with pytest.raises(ValueError):
            celsius_to_fahrenheit(bad)

    @pytest.mark.parametrize(
        "bad", [None, "41", "41.0", True, False, [], {}, object(), b"41"]
    )
    def test_fahrenheit_to_celsius_rejects_non_numeric(self, bad):
        with pytest.raises(ValueError):
            fahrenheit_to_celsius(bad)


# ---------------------------------------------------------------------------
# normalize_temperature_to_celsius — accept varied unit tokens,
# return None for unrecognized units (caller decides how to fail).
# ---------------------------------------------------------------------------


class TestNormalizeTemperatureToCelsius_Issue1364:
    @pytest.mark.parametrize(
        "unit",
        ["C", "c", "°C", "°c", "degC", "deg C", "deg_c", "Celsius", "celsius", "CENTIGRADE"],
    )
    def test_celsius_units_pass_through(self, unit):
        assert normalize_temperature_to_celsius(5.0, unit) == pytest.approx(5.0)

    @pytest.mark.parametrize(
        "unit",
        ["F", "f", "°F", "°f", "degF", "deg F", "deg_f", "Fahrenheit", "fahrenheit"],
    )
    def test_fahrenheit_units_convert(self, unit):
        # 41 °F is exactly 5 °C — the FDA cold-chain ceiling.
        assert normalize_temperature_to_celsius(41.0, unit) == pytest.approx(5.0, abs=1e-6)

    def test_unknown_unit_returns_none(self):
        # Kelvin, Rankine, Réaumur — all outside our conversion table.
        # Returning None lets the numeric_range evaluator fail closed
        # rather than silently comparing a reading in the wrong scale.
        assert normalize_temperature_to_celsius(5.0, "kelvin") is None
        assert normalize_temperature_to_celsius(5.0, "rankine") is None
        assert normalize_temperature_to_celsius(5.0, "K") is None

    @pytest.mark.parametrize(
        "bad_unit", [None, "", 0, 1, 1.0, [], {}, b"C"]
    )
    def test_non_string_unit_returns_none(self, bad_unit):
        assert normalize_temperature_to_celsius(5.0, bad_unit) is None

    @pytest.mark.parametrize(
        "bad_value", [None, "5.0", True, False, [], {}, object()]
    )
    def test_non_numeric_value_returns_none(self, bad_value):
        # Reject booleans explicitly (True == 1 in Python) so a
        # ``cooling_temperature: true`` never silently normalizes to 1°C.
        assert normalize_temperature_to_celsius(bad_value, "C") is None

    def test_whitespace_in_unit_tolerated(self):
        assert normalize_temperature_to_celsius(41.0, "  °F  ") == pytest.approx(5.0, abs=1e-6)
        assert normalize_temperature_to_celsius(5.0, "  deg   c  ") == pytest.approx(5.0)

    def test_cold_chain_ceiling_round_trip(self):
        """FDA 21 CFR §1.1330 cold-chain ceiling is 5 °C / 41 °F.
        The normalizer must make those two inputs indistinguishable to
        a downstream threshold comparison."""
        assert normalize_temperature_to_celsius(5.0, "C") == pytest.approx(
            normalize_temperature_to_celsius(41.0, "F"), abs=1e-9
        )


# ---------------------------------------------------------------------------
# Back-compat — the existing weight helpers must keep working.
# ---------------------------------------------------------------------------


class TestExistingUomHelpersUnchanged_Issue1364:
    def test_normalize_to_lbs_still_works(self):
        from shared.rules.uom import normalize_to_lbs
        assert normalize_to_lbs(2.0, "kg") == pytest.approx(2.0 * 2.20462)
        assert normalize_to_lbs(10.0, "lbs") == pytest.approx(10.0)
        assert normalize_to_lbs(1.0, "unknown_unit") is None

    def test_cte_lifecycle_order_intact(self):
        from shared.rules.uom import CTE_LIFECYCLE_ORDER
        assert CTE_LIFECYCLE_ORDER["harvesting"] == 0
        assert CTE_LIFECYCLE_ORDER["receiving"] == 6
        assert len(CTE_LIFECYCLE_ORDER) == 7
