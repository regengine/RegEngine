"""
Unit of Measure conversion and CTE lifecycle ordering.

Weight: converts common food industry units to a canonical base unit (lbs).

Container weights (case/box/bin/pallet/...) in ``_UOM_TO_LBS`` are
commodity-INDEPENDENT industry approximations. They MUST NOT be used to drive
a regulatory mass-balance verdict (``pass``/``fail``) without an explicit,
authoritative tenant/product container-weight mapping — a "24 lb case" of
lettuce, shrimp, and berries are not the same mass (#2520). For compliance
decisions, use ``normalize_to_mass`` (which only converts true mass units
unless a ``weights`` mapping is supplied) and ``is_mass_uom`` to classify
units. ``normalize_to_lbs`` retains the legacy approximations and is used only
by the non-evidence sandbox/preflight diagnosis path.

Temperature (#1364): converts Fahrenheit↔Celsius so numeric-range evaluators
can compare a recorded reading against an operational cold-chain threshold
regardless of the unit the operator recorded it in.
"""

from typing import Dict, Optional, Tuple

# True mass units → lbs. Converting between any of these is physically exact
# and commodity-independent, so they are safe to drive a compliance verdict.
_MASS_UOM_TO_LBS: Dict[str, float] = {
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
}

# Container / count units. The weights here are commodity-INDEPENDENT
# approximations (a "case" is 24 lbs regardless of contents). They are NOT a
# valid basis for a compliance mass-balance verdict — see module docstring.
_CONTAINER_UOM_TO_LBS: Dict[str, float] = {
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

# Legacy combined table. Retained for the non-evidence sandbox/preflight
# diagnosis path which still surfaces approximate cross-UOM comparisons to a
# human. Do NOT use this to stamp a compliance verdict.
_UOM_TO_LBS: Dict[str, float] = {**_MASS_UOM_TO_LBS, **_CONTAINER_UOM_TO_LBS}

# Canonical sets for classifying a UOM without converting it.
MASS_UOMS = frozenset(_MASS_UOM_TO_LBS)
CONTAINER_UOMS = frozenset(_CONTAINER_UOM_TO_LBS)


def _uom_key(uom: str) -> str:
    return uom.lower().strip().rstrip(".")


def is_mass_uom(uom: Optional[str]) -> bool:
    """True if ``uom`` is a true mass unit (lb/kg/oz/ton family)."""
    if not uom:
        return False
    return _uom_key(uom) in _MASS_UOM_TO_LBS


def normalize_to_lbs(quantity: float, uom: str) -> Optional[float]:
    """Convert a quantity to lbs using the legacy UOM lookup table.

    Includes commodity-independent container approximations. Returns None if
    the UOM is not recognized. NOTE: not safe for compliance verdicts — use
    ``normalize_to_mass`` for those. Retained for the sandbox/preflight path.
    """
    factor = _UOM_TO_LBS.get(_uom_key(uom))
    if factor is None:
        return None
    return quantity * factor


def normalize_to_mass(
    quantity: float,
    uom: str,
    *,
    weights: Optional[Dict[str, float]] = None,
) -> Optional[float]:
    """Convert ``quantity`` of ``uom`` to lbs for a compliance mass comparison.

    True mass units (lb/kg/oz/ton family) always convert. Container/count
    units (case/box/bin/...) convert ONLY when an authoritative ``weights``
    mapping (e.g. tenant/product container weights, keyed by lowercased UOM)
    is supplied; otherwise this returns ``None`` so the caller can decline to
    render a verdict rather than rely on a commodity-independent guess.

    Returns ``None`` when the unit cannot be converted to mass safely.
    """
    key = _uom_key(uom)
    factor = _MASS_UOM_TO_LBS.get(key)
    if factor is not None:
        return quantity * factor
    if weights:
        override = weights.get(key)
        if override is not None:
            return quantity * float(override)
    return None


# ---------------------------------------------------------------------------
# Temperature conversions (#1364)
# ---------------------------------------------------------------------------

# Recognized temperature unit aliases. Canonical form is "c" (Celsius) or
# "f" (Fahrenheit). Everything else is normalized to one of those.
_TEMP_UNIT_ALIASES: Dict[str, str] = {
    "c": "c",
    "°c": "c",
    "celsius": "c",
    "centigrade": "c",
    "degc": "c",
    "deg_c": "c",
    "degrees_c": "c",
    "degrees_celsius": "c",
    "f": "f",
    "°f": "f",
    "fahrenheit": "f",
    "degf": "f",
    "deg_f": "f",
    "degrees_f": "f",
    "degrees_fahrenheit": "f",
}


def _normalize_temp_unit(unit: Optional[str]) -> Optional[str]:
    """Return 'c' | 'f' | None for a free-form temperature unit label."""
    if unit is None:
        return None
    key = unit.strip().lower().rstrip(".")
    return _TEMP_UNIT_ALIASES.get(key)


def fahrenheit_to_celsius(value_f: float) -> float:
    """Convert Fahrenheit to Celsius. C = (F - 32) × 5/9."""
    return (float(value_f) - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(value_c: float) -> float:
    """Convert Celsius to Fahrenheit. F = C × 9/5 + 32."""
    return float(value_c) * 9.0 / 5.0 + 32.0


def normalize_temperature(
    value: float,
    unit: str,
    target: str = "c",
) -> Optional[float]:
    """Convert a temperature ``value`` in ``unit`` to ``target`` (default °C).

    Returns ``None`` if either the source or target unit is not recognized.
    Use to canonicalize operator-entered readings before comparing against
    an FDA threshold that is expressed in a fixed scale.
    """
    source = _normalize_temp_unit(unit)
    dest = _normalize_temp_unit(target)
    if source is None or dest is None:
        return None
    if source == dest:
        return float(value)
    if source == "f" and dest == "c":
        return fahrenheit_to_celsius(value)
    if source == "c" and dest == "f":
        return celsius_to_fahrenheit(value)
    return None


def resolve_temperature_reading(
    fields: Dict[str, object],
) -> Optional[Tuple[float, str]]:
    """Pick a temperature reading out of a KDE dict and return (°C, source_key).

    Understands these field names (case-insensitive on the suffix):

    - ``temperature_celsius`` / ``cooling_temperature_celsius`` → treated as °C
    - ``temperature_fahrenheit`` / ``cooling_temperature_fahrenheit`` → °F
    - ``temperature`` / ``cooling_temperature`` with a sibling
      ``temperature_unit`` (or ``..._unit``) → unit-qualified
    - ``temperature`` / ``cooling_temperature`` with no unit → inferred from
      the value. Small decimal readings common in cooler exports are treated as
      °C; larger readings common in US receiving/shipping logs are treated as
      °F.

    Returns ``None`` if nothing parseable was found. The tuple's second
    element is the KDE key the reading came from so evidence can cite it.
    """

    def _get(name: str):
        # Try dot-notation-free direct lookups and common camelcase variants.
        for key in (name, name.lower(), name.upper()):
            if key in fields and fields[key] is not None:
                return fields[key]
        return None

    def _as_temp_float(raw: object) -> Optional[float]:
        # Reject bools — ``True``/``False`` is an accidental checkbox, not a
        # thermometer reading. ``bool`` is a subclass of ``int`` so we must
        # screen it explicitly.
        if isinstance(raw, bool):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    # 1. Explicit-scale fields win — zero ambiguity.
    for key in ("cooling_temperature_celsius", "temperature_celsius"):
        raw = _get(key)
        if raw is None:
            continue
        value = _as_temp_float(raw)
        if value is not None:
            return value, key

    for key in ("cooling_temperature_fahrenheit", "temperature_fahrenheit"):
        raw = _get(key)
        if raw is None:
            continue
        value = _as_temp_float(raw)
        if value is not None:
            return fahrenheit_to_celsius(value), key

    # 2. Unit-qualified generic field.
    for value_key, unit_key in (
        ("cooling_temperature", "cooling_temperature_unit"),
        ("temperature", "temperature_unit"),
    ):
        raw = _get(value_key)
        if raw is None:
            continue
        value = _as_temp_float(raw)
        if value is None:
            continue
        unit_raw = _get(unit_key)
        canonical_unit = _normalize_temp_unit(unit_raw) if unit_raw else None
        if canonical_unit is None:
            # Bare "temp" columns in cooler ERP exports are often Celsius
            # decimals (e.g. 1.8); bare receiving/shipping temperatures are
            # often Fahrenheit (e.g. 34). Infer conservatively from magnitude.
            canonical_unit = "c" if -5.0 <= value <= 10.0 else "f"
        if canonical_unit == "c":
            return value, value_key
        return fahrenheit_to_celsius(value), value_key

    return None


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
