"""
Unit of Measure conversion and CTE lifecycle ordering.

Converts common food industry units to a canonical base unit (lbs) and
temperature scales to Celsius. Used by mass-balance and cooling rule
evaluators.

Conversion layers (for mass):
  1. Direct mass units (lbs, kg, oz, tons, metric_ton) — deterministic
     from physical constants. No product dimension needed.
  2. Container units (case, bin, pallet, crate, bag, …) — REQUIRES a
     product-specific factor looked up via container_factors.py.
     Returning a single global factor (e.g. "24 lbs/case for ALL
     products") produces nonsensical mass-balance verdicts (#1363).
  3. Count / piece units (each, unit, piece) — mass is unknowable
     without a per-product factor. We DO NOT silently treat 1 piece as
     1 lb.

Temperature conversion (#1364):
  convert_temperature(value, from_unit, to_unit) — supports C, F, K in
  both directions. Used by the COOLING CTE rule to validate recorded
  temperatures in whatever unit the source ERP emitted them in.

Any failure to convert is a ``UnitConversionError``. Callers MUST catch
and translate into a fail-closed rule verdict; the engine treats mass-
balance checks that cannot complete as ``compliant=None`` with reason
(#1362).
"""

from __future__ import annotations

from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class UnitConversionError(ValueError):
    """Raised when a value cannot be converted between the given UoMs.

    Attributes:
        value: the quantity that could not be converted.
        from_unit: the source UoM string (may be normalized or empty).
        to_unit: the target UoM string.
        reason: short human-readable explanation — "unknown unit",
                "container factor missing for product", etc.
    """

    def __init__(
        self,
        value,
        from_unit: Optional[str],
        to_unit: str,
        reason: str,
    ):
        self.value = value
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.reason = reason
        super().__init__(
            f"Cannot convert {value!r} from {from_unit!r} to {to_unit!r}: {reason}"
        )


# ---------------------------------------------------------------------------
# Direct mass units — physical constants, no product dimension.
# ---------------------------------------------------------------------------


_DIRECT_MASS_TO_LBS: Dict[str, float] = {
    # Pounds
    "lbs": 1.0,
    "lb": 1.0,
    "pound": 1.0,
    "pounds": 1.0,
    "#": 1.0,  # common industry shorthand
    # Kilograms
    "kg": 2.20462,
    "kgs": 2.20462,
    "kilogram": 2.20462,
    "kilograms": 2.20462,
    # Grams
    "g": 0.00220462,
    "gram": 0.00220462,
    "grams": 0.00220462,
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


# Container / package units. Presence in this set means the caller MUST
# supply a per-product factor via container_factors; we refuse to guess
# a global value (#1363).
CONTAINER_UOMS = frozenset({
    "case", "cases", "cs",
    "carton", "cartons",
    "bin", "bins",
    "pallet", "pallets",
    "crate", "crates",
    "box", "boxes",
    "bag", "bags",
    "bunch", "bunches",
    "head", "heads",
    "flat", "flats",
})


# Count / piece units. Mass is per-item and per-product; the evaluator
# must supply a factor.
COUNT_UOMS = frozenset({
    "each", "ea",
    "unit", "units",
    "piece", "pieces",
    "pc", "pcs",
    "count", "ct",
})


def _normalize_uom(uom: Optional[str]) -> str:
    if not uom:
        return ""
    return uom.strip().lower().rstrip(".")


def normalize_to_lbs(
    quantity: float,
    uom: str,
    *,
    container_resolver=None,
    product_reference: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Optional[float]:
    """Convert a quantity to lbs.

    Direct mass units (lbs / kg / oz / tons) convert from the lookup
    table and ignore product / tenant context.

    Container and count units (case / bin / each / …) REQUIRE a
    container_resolver AND product_reference AND tenant_id. Without
    them, returns None — the caller MUST interpret that as "unknown"
    and must NOT treat it as a silent pass (#1362).

    For compatibility with the older two-arg signature, a call with no
    resolver on a container unit returns None rather than raising.
    Callers that want the strict behavior should use
    ``normalize_to_lbs_strict`` below.
    """
    key = _normalize_uom(uom)
    if not key:
        return None

    factor = _DIRECT_MASS_TO_LBS.get(key)
    if factor is not None:
        return float(quantity) * factor

    if key in CONTAINER_UOMS or key in COUNT_UOMS:
        if container_resolver is None:
            return None
        try:
            return container_resolver.to_lbs(
                quantity=float(quantity),
                uom=key,
                product_reference=product_reference,
                tenant_id=tenant_id,
            )
        except Exception:  # ContainerFactorUnknownError or similar
            return None

    return None


def normalize_to_lbs_strict(
    quantity: float,
    uom: str,
    *,
    container_resolver=None,
    product_reference: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> float:
    """Strict version of normalize_to_lbs — raises UnitConversionError.

    This is the function mass-balance and other rules should call when
    a None result would fail-open (#1362). The exception is caught by
    the evaluator and surfaced as ``compliant=None`` with reason.
    """
    key = _normalize_uom(uom)
    if not key:
        raise UnitConversionError(quantity, uom, "lbs", "empty/missing UoM string")

    factor = _DIRECT_MASS_TO_LBS.get(key)
    if factor is not None:
        return float(quantity) * factor

    if key in CONTAINER_UOMS or key in COUNT_UOMS:
        if container_resolver is None:
            raise UnitConversionError(
                quantity, uom, "lbs",
                f"container UoM {uom!r} requires a product-specific factor; "
                "no container_resolver was supplied",
            )
        try:
            return container_resolver.to_lbs(
                quantity=float(quantity),
                uom=key,
                product_reference=product_reference,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            raise UnitConversionError(
                quantity, uom, "lbs",
                f"container factor unresolved: {exc}",
            ) from exc

    raise UnitConversionError(
        quantity, uom, "lbs",
        f"UoM {uom!r} is not in the direct-mass, container, or count tables",
    )


# ---------------------------------------------------------------------------
# Temperature conversion (#1364)
# ---------------------------------------------------------------------------


_TEMP_ALIASES = {
    "c": "C", "celsius": "C", "°c": "C", "degc": "C", "deg_c": "C",
    "f": "F", "fahrenheit": "F", "°f": "F", "degf": "F", "deg_f": "F",
    "k": "K", "kelvin": "K", "°k": "K",
}


def _normalize_temp_unit(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return None
    key = unit.strip().lower()
    key = key.replace(" ", "").replace("°", "°")
    return _TEMP_ALIASES.get(key) or _TEMP_ALIASES.get(key.lstrip("°"))


def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a temperature between C, F, and K.

    Args:
        value: numeric temperature.
        from_unit / to_unit: one of C / F / K (case-insensitive; °C, degC
                             and similar aliases are accepted).

    Raises:
        UnitConversionError: when either unit is not recognized.
    """
    src = _normalize_temp_unit(from_unit)
    dst = _normalize_temp_unit(to_unit)
    if src is None:
        raise UnitConversionError(value, from_unit, str(to_unit), "unknown source temperature unit")
    if dst is None:
        raise UnitConversionError(value, str(from_unit), to_unit, "unknown target temperature unit")

    # Convert to Celsius first, then to the target.
    if src == "C":
        celsius = float(value)
    elif src == "F":
        celsius = (float(value) - 32.0) * 5.0 / 9.0
    elif src == "K":
        celsius = float(value) - 273.15
    else:  # pragma: no cover — normalized to C/F/K by now
        raise UnitConversionError(value, from_unit, to_unit, "unreachable")

    if dst == "C":
        return celsius
    if dst == "F":
        return celsius * 9.0 / 5.0 + 32.0
    if dst == "K":
        return celsius + 273.15
    raise UnitConversionError(value, from_unit, to_unit, "unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# CTE lifecycle ordering per FSMA 204 supply chain flow
# ---------------------------------------------------------------------------


CTE_LIFECYCLE_ORDER = {
    "harvesting": 0,
    "cooling": 1,
    "initial_packing": 2,
    "first_land_based_receiving": 3,
    "transformation": 4,
    "shipping": 5,
    "receiving": 6,
}


__all__ = [
    "UnitConversionError",
    "CONTAINER_UOMS",
    "COUNT_UOMS",
    "CTE_LIFECYCLE_ORDER",
    "convert_temperature",
    "normalize_to_lbs",
    "normalize_to_lbs_strict",
]
