"""
Unit of Measure conversion and CTE lifecycle ordering.

Converts common food industry units to a canonical base unit (lbs).
Used by mass balance evaluator to compare quantities across different UOMs.

Temperature conversion (#1364)
-----------------------------
COOLING CTE rules in 21 CFR §1.1330 reference temperature thresholds
without mandating a particular unit — upstream systems record in °F
(common in US packing/cold-chain) or °C (common in international/EDI
payloads). Before this module gained a temperature normalizer the
rules engine could not compare a reading against a regulatory threshold,
so temperature gates were impossible to write. The helpers below let
numeric-range rules convert any incoming reading to Celsius and compare
against a single canonical threshold, keeping the rule DSL
unit-agnostic.
"""

from typing import Any, Dict, Optional


# --- Temperature conversion (#1364) ------------------------------------
# Keep unit tokens normalized to lowercase, trimmed, and with the common
# symbol variants (°F, °C, degF, deg_c, ...) collapsed to a flat set.

_TEMPERATURE_UNITS_CELSIUS = frozenset({
    "c", "°c", "degc", "deg c", "deg_c", "celsius", "centigrade",
})
_TEMPERATURE_UNITS_FAHRENHEIT = frozenset({
    "f", "°f", "degf", "deg f", "deg_f", "fahrenheit",
})


def _normalize_temperature_unit_token(unit: str) -> str:
    """Strip degree sign, whitespace, and case so the allowlists above
    can be simple flat sets. Returns ``""`` if the input is not a string."""
    if not isinstance(unit, str):
        return ""
    token = unit.strip().lower()
    # Collapse repeated whitespace (e.g. "deg  c") to a single space.
    token = " ".join(token.split())
    return token


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert °C to °F. Raises ValueError on non-numeric input."""
    if isinstance(celsius, bool) or not isinstance(celsius, (int, float)):
        raise ValueError(f"celsius must be a number, got {celsius!r}")
    return (celsius * 9.0 / 5.0) + 32.0


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert °F to °C. Raises ValueError on non-numeric input."""
    if isinstance(fahrenheit, bool) or not isinstance(fahrenheit, (int, float)):
        raise ValueError(f"fahrenheit must be a number, got {fahrenheit!r}")
    return (fahrenheit - 32.0) * 5.0 / 9.0


def normalize_temperature_to_celsius(
    value: float, unit: str
) -> Optional[float]:
    """Convert ``value`` (in ``unit``) to Celsius.

    Returns None if the unit is not a recognized temperature unit so the
    caller can decide how to handle the ambiguity (typically: treat as
    rule error rather than silently pass).

    Accepts the canonical tokens above plus the common variants
    ("°F", "degC", "fahrenheit", ...). Booleans are rejected — Python
    treats ``True == 1`` so ``isinstance(True, int)`` is True and would
    silently coerce to 1°.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    token = _normalize_temperature_unit_token(unit)
    if token in _TEMPERATURE_UNITS_CELSIUS:
        return float(value)
    if token in _TEMPERATURE_UNITS_FAHRENHEIT:
        return fahrenheit_to_celsius(value)
    return None


_UOM_TO_LBS: Dict[str, float] = {
    # Weight (already in lbs)
    "lbs": 1.0,
    "lb": 1.0,
    "pound": 1.0,
    "pounds": 1.0,
    # Kilograms
    "kg": 2.20462,
    "kgs": 2.20462,
    "kilogram": 2.20462,
    "kilograms": 2.20462,
    # Ounces
    "oz": 0.0625,
    "ounce": 0.0625,
    "ounces": 0.0625,
    # Tons
    "ton": 2000.0,
    "tons": 2000.0,
    "short_ton": 2000.0,
    "metric_ton": 2204.62,
    "mt": 2204.62,
    # Produce containers (industry standard approximations)
    "case": 24.0,
    "cases": 24.0,
    "cs": 24.0,
    "carton": 24.0,
    "cartons": 24.0,
    "bin": 800.0,
    "bins": 800.0,
    "pallet": 2000.0,
    "pallets": 2000.0,
    "crate": 40.0,
    "crates": 40.0,
    "box": 24.0,
    "boxes": 24.0,
    "bag": 5.0,
    "bags": 5.0,
    "bunch": 1.5,
    "bunches": 1.5,
    "head": 2.0,
    "heads": 2.0,
    "each": 1.0,
    "ea": 1.0,
    "unit": 1.0,
    "units": 1.0,
    "piece": 1.0,
    "pieces": 1.0,
    "pc": 1.0,
    "pcs": 1.0,
}


def normalize_to_lbs(quantity: float, uom: str) -> Optional[float]:
    """Convert a quantity to lbs using the UOM lookup table.

    Returns None if the UOM is not recognized.
    """
    uom_key = uom.lower().strip().rstrip(".")
    factor = _UOM_TO_LBS.get(uom_key)
    if factor is None:
        return None
    return quantity * factor


# CTE lifecycle ordering per FSMA 204 supply chain flow
CTE_LIFECYCLE_ORDER = {
    "harvesting": 0,
    "cooling": 1,
    "initial_packing": 2,
    "first_land_based_receiving": 3,
    "transformation": 4,
    "shipping": 5,
    "receiving": 6,
}
